# Optional Jev Completion Gate

The Completion Gate is an optional decision aid for `agent-orchestration`, disabled by default until the live path is smoke-tested. It can assess a settled implementation report and recommend a next action; it does not replace diff review, deterministic project verification, or orchestrator judgment. Enabling or removing it adds no startup question and leaves Explorer/Fixer persistence unchanged.

## Authority and scope

Decision precedence is:

```text
user > safety > skill invariants > persisted config > deterministic verification > Jev > conservative fallback
```

Jev may assess outcome support, unresolved issues, scope, and one next action (`complete`, `retry_fix`, `reinvestigate`, or `orchestrator_review`). It cannot waive user or safety requirements, change skill invariants, override deterministic failures, make project changes, or select harnesses, models, or effort. The orchestrator remains responsible for reviewing the actual diff and deciding what to do.

## Completion lifecycle

The orchestrator should invoke the gate only after diff review and deterministic project verification have passed. As a defensive short-circuit, valid input with `deterministic_pass: false` returns unavailable with reason `deterministic_failure` before request construction or any `cmd` subprocess. A deterministic failure stays in the existing review/retry workflow; Jev is never asked to override it.

```text
fixer report -> diff review -> verification -> orchestrator review -> gate -> complete / retry / reinvestigate / orchestrator_review
```

## Settled input and privacy

`scripts/jevctl completion-gate` reads one JSON object from stdin containing `task_summary`, `root_cause_summary`, `implementation_summary`, `changed_files`, `diff_stats`, `verification`, `tests_summary`, `remaining_issues`, `review_findings`, and `deterministic_pass`. It sends only these settled report fields as compact `state`, not extra caller data. The orchestrator sets `deterministic_pass`; Jev is never asked to overrule a failed deterministic check.

The state is capped by `JEVCTL_MAX_STATE_CHARS` (default `12000` characters) and truncated with a marker. This deliberately conservative cap leaves room for the questions and reduces the chance of approaching the model budget; character count is not an exact token count. TypeSafe's input-token budgets are 64k for state plus all questions combined, and 32k for state plus the single longest question. Both budgets count encoded input tokens, so keep the full request below both limits.

Callers must not send secrets, credentials, API keys, tokens, authorization headers, raw transcripts, full-repository contents, or unrelated history. Authentication comes from the logged-in Command Code `cmd` session (`cmd login`); the gate does not access the credential file or forward credential variables. `CMD_ZDR`, when set, is forwarded unchanged to `cmd`. The child environment otherwise remains limited to runtime essentials. Command stderr is captured and never copied into stdout or response reasons.

## Questions

The request has the System One shape `{ "state": ..., "questions": {...} }`. `questions` is an object keyed by the four caller-chosen ids; it is not an array. Each Noul item has `type`, `instructions`, and `criteria` with explicit `true` and `false` meanings. The choice item has `type`, `instructions`, and a `criteria` object mapping each allowed action to its instruction:

- `outcome_supported` (`noul`): probability that the settled evidence supports the requested outcome.
- `unresolved_issue` (`noul`): probability that a material issue remains unresolved.
- `scope_exceeded` (`noul`): probability that implementation exceeded authorized scope.
- `next_action` (`choice`): one of `complete`, `retry_fix`, `reinvestigate`, or `orchestrator_review`.

Noul values are probabilities from `0` to `1` that the corresponding `true` criterion holds; Noul answers have no confidence. A choice answer carries separate confidence and probabilities.

## Decision and completion policy

Defaults are centralized in `scripts/jevctl` and may be overridden by environment variables or the configuration file:

| Setting | Default | Passing condition |
| --- | ---: | --- |
| `JEVCTL_OUTCOME_MIN` / `outcome_min` | `0.90` | `outcome_supported >= threshold` |
| `JEVCTL_UNRESOLVED_MAX` / `unresolved_max` | `0.10` | `unresolved_issue <= threshold` |
| `JEVCTL_SCOPE_MAX` / `scope_max` | `0.15` | `scope_exceeded <= threshold` |
| `JEVCTL_ACTION_CONF_MIN` / `action_conf_min` | `0.80` | `next_action_confidence >= threshold` |

For a valid Jev response, `status` is `decided` iff `next_action_confidence >= ACTION_CONF_MIN`; otherwise it is `uncertain`. Disabled and deterministic-failure short-circuits, as well as integration failures, return `unavailable`. Completion eligibility is a separate conjunction:

```text
outcome_supported >= OUTCOME_MIN
and unresolved_issue <= UNRESOLVED_MAX
and scope_exceeded <= SCOPE_MAX
```

`completion_confidence` is the minimum of `outcome_supported`, `1 - unresolved_issue`, `1 - scope_exceeded`, and `next_action_confidence`. It describes overall completion suitability; it does not determine `status` by itself. In `active` mode, `would_auto_apply` is the existing deterministic/status/action/completion-eligibility calculation and `auto_apply` equals it. In `shadow` mode, `would_auto_apply` reports that same active-mode calculation, while `auto_apply` is always false. A confident `retry_fix` or `reinvestigate` can be `decided` but never auto-applies. Weak completion evidence also never auto-applies.

The normalized response contains `schema_version`, `gate`, `mode`, `status`, `action`, `auto_apply`, `would_auto_apply`, `completion_confidence`, `answers` (`outcome_supported`, `unresolved_issue`, `scope_exceeded`), `next_action`, and `next_action_confidence`. Unavailable results have the resolved `mode` (or `active` when configuration cannot be resolved), both apply fields false, `completion_confidence: 0.0`, null Noul answers, and `action: "orchestrator_review"`.

## Shadow mode

Set `mode` to `shadow` to request an observation-only Jev evaluation. The orchestrator first completes its normal work, review, verification, and next-action decision without consulting Jev; it then invokes the gate at most once for an eligible decision and continues with the original decision. The Jev result MUST NOT cause the Orchestrator to revise the decision in shadow mode. Eligibility is unchanged: do not invoke Jev for disabled gates, deterministic failures, incomplete review, or unsafe payloads. The orchestrator—not `jevctl`—compares Jev's action with its own decision; the definitions of `action_match` and `completion_match` are in `SKILL.md`.

Shadow mode creates no telemetry, logs, or extra files. `would_auto_apply` reports what active mode would have done; `auto_apply` remains false. Unavailable Jev results are observational only and do not fail the task.

## Response validation and compatibility

Validation is strict for fields that affect the decision, but tolerant of additive fields. The response must include `model`, `answers`, and `usage`; all four expected answer ids must be present. Unknown top-level fields and unknown extra answer ids are ignored. Extra fields on known answer objects are also ignored, including a future field on a Noul answer. Consumed types, finite probability ranges, choice names, and probability keys are still validated; violations make the gate unavailable.

The returned `model` must be a non-empty string and either match the configured request model verbatim or look like a Jev family id (`jev-latest`, a `jev-` version such as `jev-1.13.0`, or a `typesafe/jev` id). Command Code may report the resolved version that answered instead of the alias requested.

## Enablement and configuration

The optional configuration file is `${XDG_CONFIG_HOME:-$HOME/.config}/agent-orchestration/jev.json`. It may contain `model`, `transport`, `timeout`, `thresholds`, boolean `enabled`, and `mode`. Enablement precedence is `JEVCTL_ENABLED` environment variable, then the config-file value, then the default `false`; Jev therefore remains globally disabled unless opted in. The enabled parser is case-insensitive, strips whitespace, and accepts `1`, `true`, `yes`, `on`, `0`, `false`, `no`, or `off`; other values fail conservatively. `JEVCTL_ENABLED=1` opts in. Mode precedence is `JEVCTL_MODE` environment variable, then the config-file value, then default `active` for backward compatibility. Mode accepts only case-insensitive, whitespace-trimmed `active` or `shadow`; any other value, including `on` or `true`, is `invalid_config`. `active` preserves the existing behavior; `shadow` never changes the orchestrator action. When disabled, `completion-gate` returns unavailable with reason `disabled` without spawning `cmd`; `doctor` reports `enabled: false`, `mode`, `ok: false`, and reason `disabled` without a probe.

Other overrides are `JEVCTL_MODEL` (default `typesafe/jev`), `JEVCTL_TRANSPORT` (default `cmd`), `JEVCTL_TIMEOUT` (default `60` seconds), `JEVCTL_MAX_STATE_CHARS`, and the threshold variables above. Environment settings take precedence over config. Authentication is solely the `cmd` login session; v1 has no API-key handling or provider API transport.

## Transport failures and diagnostics

Any missing command, timeout, nonzero exit, malformed JSON, invalid probability, or consumed-schema violation returns `status: "unavailable"`, `action: "orchestrator_review"`, `auto_apply: false`, `would_auto_apply: false`, the resolved `mode` (or `active` if configuration is unresolvable), and a machine-readable reason. No failure retries or falls back to another transport.

Command Code headless exit codes map to reasons as follows:

| Exit code | Reason |
| ---: | --- |
| `0` | success; validate the response |
| `1` | `transport_error` |
| `3` | `auth_error` |
| `4` | `permission_denied` |
| `5` | `rate_limited` |
| `6` | `connection_error` |
| `7` | `server_error` |
| `8` | `max_turns_exceeded` |
| `9` | `no_response` |
| `10` | `insufficient_credits` (credits for the billing period are exhausted) |
| `130` | `interrupted` |
| any other nonzero | `transport_error` |

With `CMD_ZDR=1`, `cmd` preserves the session-wide ZDR opt-in. Jev has no ZDR-capable upstream, so Command Code may refuse the request with HTTP 422 (`cmd_zdr_no_providers`) rather than route it to a retaining provider. Such a refusal remains unavailable; the gate does not disable ZDR or fail over.

`scripts/jevctl doctor` is diagnostic only and always prints one JSON object including `enabled` and `mode`. When enabled on the `cmd` transport it checks for `cmd` and runs the local `cmd --version` smoke probe; probe failures use the same exit-code mapping. It makes no model request and mutates no local state. Gate results also include `mode` and `would_auto_apply`. Both subcommands keep JSON alone on stdout and send only sanitized diagnostics to stderr.

The `provider` transport remains an unimplemented extension point. Explorer, Parallel, and Plan gates are not part of this change and are unspecified.
