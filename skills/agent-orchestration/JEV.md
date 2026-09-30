# Optional Jev Completion Gate

The Completion Gate is an optional decision aid for the `agent-orchestration` skill. It lets TypeSafe AI Jev assess a settled implementation report and recommend whether the orchestrator should complete, retry a fix, reinvestigate, or review the result. Jev does not replace the orchestrator's review or project verification, and removing or disabling Jev leaves the existing workflow unchanged. It adds no startup question.

## Authority and scope

Decision precedence is:

```text
user > safety > skill invariants > persisted config > deterministic verification > Jev > conservative fallback
```

Jev may assess whether the reported outcome is supported, whether issues appear unresolved, whether scope appears exceeded, and which bounded next action is appropriate. Jev cannot waive user or safety requirements, change skill invariants, override deterministic failures, make project changes, or select harnesses, models, or effort. The orchestrator remains responsible for reviewing the actual diff and deciding what to do.

## Completion lifecycle

The gate is considered only after the orchestrator's diff review and project verification have passed. Deterministic failures stay in the existing review/retry workflow and are not sent as a request to Jev.

```text
fixer report -> diff review -> verification -> orchestrator review -> gate -> complete / retry / reinvestigate / orchestrator_review
```

The gate's `auto_apply` field is only a completion signal for the caller; it never applies changes. It can be true only when deterministic checks passed, Jev's result is sufficiently certain, and Jev recommends `complete`.

## Settled input state

`bin/jevctl completion-gate` reads one JSON object from stdin with these fields:

- `task_summary`, `root_cause_summary`, `implementation_summary`
- `changed_files` (array), `diff_stats`
- `verification` (`commands` plus `exit_status` or per-command `per_command_results` / `results`)
- `tests_summary`, `remaining_issues` (array), `review_findings`
- `deterministic_pass` (boolean, set by the orchestrator)

The request contains only these settled report fields, serialized compactly as `state`. The state is capped at `JEVCTL_MAX_STATE_CHARS` characters (default `12000`) and truncated with a marker when necessary. Keep it well below Jev's 64k budget, including the questions and protocol overhead. Callers must not send secrets, credentials, tokens, authorization headers, raw transcripts, or unrelated history. Do not put secrets in the configuration file or environment for this gate; authentication is supplied by the logged-in `cmd` session (`cmd login`). The gate does not read, copy, or display the Command Code credential file or credential values.

## Questions

The request uses the System One shape `{ "state": ..., "questions": {...} }`. `questions` is an object keyed by the caller-chosen ids, not an array; each value has its `type` and `instructions`. Each `noul` question also has `criteria` with explicit `true` and `false` meanings. The `choice` question uses `criteria` as a mapping from each action name to its instruction; there are no per-question `id`, `question`, or `options` fields.

The four question ids and meanings are:

1. `outcome_supported` (`noul`): probability the settled evidence supports the requested outcome.
2. `unresolved_issue` (`noul`): probability that a material issue remains unresolved.
3. `scope_exceeded` (`noul`): probability that implementation exceeded authorized scope.
4. `next_action` (`choice`): select one action from the criteria mapping:
   - `complete`: the outcome is supported, deterministic checks passed, and no material issue or scope violation remains;
   - `retry_fix`: a clear implementation defect needs a bounded correction;
   - `reinvestigate`: a cause or assumption remains uncertain;
   - `orchestrator_review`: the result needs the orchestrator's judgment.

Noul values are probabilities from `0` to `1` that their `true` criterion holds; they do not carry confidence. The choice answer includes a separate confidence and probabilities for its options.

## Thresholds and normalized result

Defaults are centralized in `bin/jevctl` and can be overridden by the corresponding `JEVCTL_*` environment variable or JSON configuration threshold:

| Setting | Default | Passing condition |
| --- | ---: | --- |
| `JEVCTL_OUTCOME_MIN` / `outcome_min` | `0.90` | `outcome_supported >= threshold` |
| `JEVCTL_UNRESOLVED_MAX` / `unresolved_max` | `0.10` | `unresolved_issue <= threshold` |
| `JEVCTL_SCOPE_MAX` / `scope_max` | `0.15` | `scope_exceeded <= threshold` |
| `JEVCTL_ACTION_CONF_MIN` / `action_conf_min` | `0.80` | `next_action_confidence >= threshold` |

Certainty is:

```text
min(outcome_supported, 1 - unresolved_issue, 1 - scope_exceeded, next_action_confidence)
```

A valid response is `decided` only when all four threshold conditions hold; otherwise it is `uncertain`. The normalized object has `schema_version`, `gate`, `status`, `action`, `auto_apply`, `certainty`, `answers` (`outcome_supported`, `unresolved_issue`, `scope_exceeded`), `next_action`, and `next_action_confidence`. `action` and `next_action` carry Jev's validated choice. `auto_apply` is true only when `deterministic_pass` is true, status is `decided`, action is `complete`, and all thresholds pass.

## Failure behavior

Missing `cmd`, timeout, nonzero exit, malformed JSON, invalid probabilities, or any response-schema violation produces `status: "unavailable"`, `action: "orchestrator_review"`, and `auto_apply: false`, with a machine-readable `reason`. No failure or uncertain result auto-completes work. Auth and rate-limit exit codes are reported as unavailable; the gate does not retry or fail over to another transport. A missing or disabled `cmd` therefore leaves the skill's existing workflow intact.

`bin/jevctl doctor` is diagnostic only. It prints one JSON object, checks that `cmd` is available, and runs the local `cmd --version` smoke probe. It does not perform a model request or change local state; it reports `ok: false` with a reason when the command is unavailable or the probe fails. Neither subcommand prints command diagnostics or credentials to stdout.

## Configuration and transport

The optional JSON file is `${XDG_CONFIG_HOME:-$HOME/.config}/agent-orchestration/jev.json`. It may contain only `model`, `transport`, `timeout`, and `thresholds` settings. Environment variables take precedence: `JEVCTL_MODEL` (default `typesafe/jev`), `JEVCTL_TRANSPORT` (default `cmd`), `JEVCTL_TIMEOUT` (default `60` seconds), and the threshold variables above. `JEVCTL_MAX_STATE_CHARS` controls the state cap. Authentication comes from the logged-in Command Code `cmd` session; v1 has no API-key configuration or provider API transport.

The current transport invokes `cmd -p '<request-json>' -m typesafe/jev`. The provider transport is only a marked extension point. Future Explorer, Parallel, and Plan gates are also possible extension points, but are not specified or implemented here.
