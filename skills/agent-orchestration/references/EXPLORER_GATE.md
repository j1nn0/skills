# Optional Jev Explorer Gate

The Explorer Gate is an optional evidence-sufficiency decision aid for the `agent-orchestration` skill. It evaluates a compact, orchestrator-reviewed account of an Explorer's claim and evidence after investigation has returned and before the orchestrator decides whether to delegate implementation. It never performs work, authorizes a fixer by itself, or replaces the orchestrator's review of the evidence.

## Position in the lifecycle

```text
Explorer investigation
  -> Explorer result
  -> orchestrator reviews and settles the evidence
  -> optional explorer-gate
  -> orchestrator chooses: bounded fixer handoff / focused exploration / review
  -> implementation and review
  -> optional completion-gate after diff review and verification
```

The gate is post-Explorer, not a prompt to the Explorer and not a replacement for the orchestrator's own evidence review. The orchestrator sets `orchestrator_reviewed: true` only after it has read the Explorer result and checked the submitted summary against the cited observations.

## When to run

Run `scripts/jevctl explorer-gate` only when all of the following hold:

- global Jev enablement and the Explorer gate are both enabled;
- the Explorer has returned a complete result for the current investigation;
- the orchestrator has reviewed that result and can provide the settled-state input below;
- evidence sufficiency could affect whether a bounded fixer handoff is appropriate.

Do not run it before the Explorer returns, before orchestrator review, on an unsafe or incomplete evidence summary, or when the gate is disabled. With the gate disabled, `jevctl` returns `unavailable` with reason `disabled` without starting a transport. If `orchestrator_reviewed` is missing or false, it returns `review_incomplete` without starting a transport. Invalid input is also unavailable and must not be repaired by inventing evidence.

### Parallel Explorer batches

For a batch admitted under [`PARALLEL.md`](PARALLEL.md), collect and synthesize the sibling evidence first, then make zero or one Explorer Gate call for the shared parent objective—never a separate call per Explorer. Zero calls are valid when the gate is disabled or the combined request is otherwise ineligible; at most one reviewed summary may be submitted. This does not change gate eligibility, schema, thresholds, or semantics.

## Settled-state contract and privacy

Send one JSON object on stdin. Required fields are:

- `task_summary`, `investigation_goal`, and `explorer_claim`: non-empty strings;
- `evidence_supporting_claim`: a non-empty list of `{ "source": <non-empty string>, "observation": <non-empty string> }` objects;
- `contradictory_evidence`: a list of the same object shape; it may be empty;
- `remaining_unknowns`: a list of non-empty strings; it may be empty;
- `orchestrator_reviewed`: boolean `true` before the gate may make a request. Missing or false is a review-incomplete short circuit.

Optional fields are `files_examined`, `tests_examined`, and `external_sources` (lists of non-empty strings), plus `explorer_confidence` (`{"level":"high|medium|low","reason":"..."}`). The confidence reason must be non-empty. Only these allowed fields are serialized as the compact state; unrelated caller fields are dropped.

The following top-level keys are forbidden and make the request `invalid_request`: `transcript`, `raw_transcript`, `agent_transcript`, `source_files`, `full_source`, `repository_dump`, `orchestrator_decision`, `intended_action`, `tentative_action`, `retry_count`, `retry_counter`, `loop_count`, `loop_counter`, `round_count`, `attempt_count`, `harness`, `model`, `effort`, `prompt`, `prompts`, `harvest_id`, and `orchestration_id`.

Send settled facts, not the conversation that produced them. Do not include secrets, credentials, raw agent transcripts, full source files, repository dumps, orchestration metadata, or instructions that steer the model toward a preferred answer. Jev does not inspect the workspace; the orchestrator remains responsible for source attribution and factual accuracy.

## Questions and thresholds

The request uses System One's `{ "state": ..., "questions": {...} }` shape. Its three Noul questions estimate:

- `evidence_grounded`: whether the listed, traceable observations ground the claim;
- `claim_supported`: whether those observations substantiate the specific claim rather than merely fit it;
- `material_gap`: whether contradictions or unknowns materially limit the claim or a safe next step.

The `next_step` choice is one of `proceed_to_fix`, `explore_more`, or `orchestrator_review`. Questions direct Jev to judge the evidence itself and to distrust assertive phrases such as “root cause confirmed,” “definitely caused by,” or “fully verified” unless the cited observations support them.

Defaults are centralized in `scripts/jevctl`:

| Threshold | Default | Meaning |
| --- | ---: | --- |
| `grounded_min` | `0.75` | `evidence_grounded` must meet or exceed this value. |
| `supported_min` | `0.75` | `claim_supported` must meet or exceed this value. |
| `material_gap_max` | `0.20` | `material_gap` must be at or below this value. |
| `action_conf_min` | `0.75` | `next_step_confidence` at or above this value is `decided`; otherwise status is `uncertain`. |

`action` and `next_step` are the validated Jev recommendation unchanged; thresholds never rewrite the choice. `status` is `decided` iff `next_step_confidence >= action_conf_min`; otherwise it is `uncertain`. `evidence_sufficient` is true exactly when all five conditions hold: action is `proceed_to_fix`, the choice is confident, `evidence_grounded >= grounded_min`, `claim_supported >= supported_min`, and `material_gap <= material_gap_max`. The normalized response includes this additive boolean on decided/uncertain results and sets it false on unavailable results; `schema_version` remains `1`. `would_block` remains true only for a decided, confident `explore_more` choice. `auto_apply` is always false; there is no completion-confidence scalar.

### Qualification cases and calibration

**Case 1:** `proceed_to_fix` with confidence `0.91` and `material_gap: 0.24` is still `decided` and keeps the raw `proceed_to_fix` action, but `evidence_sufficient` is false because `0.24 > material_gap_max (0.20)`. This is not a positive gate endorsement; the Orchestrator must not treat it as clearance.

**Case 5:** a raw `proceed_to_fix` with confidence `0.29` is `uncertain` and has `evidence_sufficient: false`. It returns control to the Orchestrator for its ordinary evidence judgment; the raw action is not operational risk or permission.

Define `false_decided_proceed` as true **only** when the Orchestrator judged the evidence insufficient, normalized `status == "decided"`, normalized `action == "proceed_to_fix"`, and `evidence_sufficient == true`. An uncertain raw `proceed_to_fix` never counts.

Keep `material_gap_max: 0.20` provisional and defer calibration: one `0.24` sample is insufficient to justify changing the threshold. Preserve the observed separation between `0.24` and the `0.51` / `0.86+` examples; Case 1 is now visible through `evidence_sufficient`, not a threshold tweak.

## Shadow and active modes

Explorer mode defaults to `shadow`, even if the global completion mode is `active`. `gates.explorer.mode` or `JEVCTL_EXPLORER_MODE` may select `active`; the environment variable overrides config. The Explorer gate is enabled separately with `gates.explorer.enabled` or `JEVCTL_EXPLORER_ENABLED`, and global `JEVCTL_ENABLED=0` disables both gates.

- In `shadow`, report the result for observation only. The orchestrator follows its independently reached decision and does not block, reroute, or accelerate work because of Jev.
- In `active`, a decided `explore_more` recommendation with `would_block: true` may hold the transition to a fixer while the orchestrator obtains the missing evidence or escalates. No result dispatches an agent or changes files. `proceed_to_fix` remains advice, not authorization, and `auto_apply` remains false.

## One-way conservative rule

The gate may add a cautious hold; it cannot grant permission, broaden scope, or overrule user direction, safety rules, skill invariants, deterministic requirements, or orchestrator judgment. In particular, a `proceed_to_fix` response is never a substitute for the orchestrator validating the evidence and selecting the implementation strategy.

| Result | Shadow handling | Active handling |
| --- | --- | --- |
| Decided `proceed_to_fix` with `evidence_sufficient: true` | Record as an observation; make the normal orchestrator decision. | The evidence may support considering a bounded fixer handoff; the orchestrator still decides and supplies scope. |
| `proceed_to_fix` with `evidence_sufficient: false` | Ignore Jev as a control signal; inspect the evidence and choose the normal route. | Do not treat the recommendation as clearance. Resolve the factual gap or use the normal review/escalation path; the gate itself does not auto-apply or invent a block. |
| Decided, confident `explore_more` (`would_block: true`) | Report only; continue with the pre-existing orchestrator decision. | Hold the fixer handoff for focused evidence gathering or orchestrator review. |
| `orchestrator_review` | Report only; the orchestrator judges the evidence and route. | The orchestrator reviews, re-scopes, asks the user, or routes further investigation; Jev does not choose among them. |
| Uncertain, unavailable, disabled, invalid, or review-incomplete | Do not treat the result as permission or as a task failure; use the normal workflow. | Same conservative fallback; uncertain raw `proceed_to_fix` has `evidence_sufficient: false` and returns control to the Orchestrator. No automatic action or model transport for an ineligible request. |

## Fallback and completion interaction

Unavailable results normalize to `action: "orchestrator_review"`, `next_step: "orchestrator_review"`, `auto_apply: false`, `would_block: false`, `evidence_sufficient: false`, null evidence answers, and a sanitized reason. Transport failures, invalid responses, missing commands, invalid config, interruption, and disabled/incomplete-review short circuits do not authorize a fixer. The orchestrator continues from its own evidence review, gathers missing facts when useful, or escalates; Jev failure alone does not fail the task.

The Explorer Gate precedes implementation. The separate Completion Gate remains post-implementation and retains its existing input, deterministic-verification requirement, thresholds, action set, and completion decision behavior; see [`JEV.md`](JEV.md). Do not call the Completion Gate to settle an Explorer claim, and do not let either gate replace the other gate's lifecycle.

Limit Explorer investigation to at most **three rounds per objective**. For this evidence loop, progress means a new or materially changed evidence fact: a source observation newly corroborated or contradicted, or a specific unknown resolved or narrowed. Rephrasing a claim, repeating a source, or increasing confidence language without changing evidence facts is not progress. After two consecutive Explorer attempts on the same evidence question make no such progress, change the question or strategy, re-scope, or escalate instead of repeating the same probe; never exceed the three-round objective cap. This evidence-progress bound complements rather than resets the existing two-attempt implementation/review rule.

## Safety constraints

- Keep the Explorer read-only; the gate does not make investigation or implementation changes.
- The orchestrator reviews evidence, decides whether a fixer is appropriate, and writes the bounded implementation handoff.
- Never send transcripts, credentials, secrets, full-source material, or harness/model/effort settings.
- Treat Jev's confidence as a probability estimate, not proof. Cite and verify facts independently.
- Keep deterministic checks, policy, scope, and human review authoritative; neither mode auto-applies an action.
