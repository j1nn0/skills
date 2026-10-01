# Parallel Explorers v1

## Purpose

Parallel Explorers reduce investigation latency only. They are not parallel implementation, a replacement for orchestrator synthesis, or a new decision gate. V1 permits two or three mutually independent, read-only Explorer units to inspect the same repository state under one shared parent objective, followed by one orchestrator-owned convergence.

## Supported and unsupported scope

A batch is supported only when each Explorer can complete its bounded investigation without needing a sibling's findings, output, or decisions. Units may inspect overlapping read scopes: overlap is guidance, not a write reservation, and does not make otherwise independent investigations dependent.

V1 does not support:

- parallel Fixers or any Explorer/Fixer overlap;
- dependencies between units, including a unit whose scope or strategy depends on another unit's result;
- nested batches, competing implementations, DAGs, worktrees, branch/merge coordination, or merge logic;
- cross-cutting work whose shared architectural or schema decision must be settled before investigation can be meaningfully independent;
- destructive operations, writes, environment/state changes, or treating an Explorer as anything but read-only.

If a batch fails admission, run the ordinary sequential Explorer workflow. Do not split merely to reach the normal batch size of two.

## Admission and unit model

`parallel.enabled` defaults to `false`; `parallel.max_explorers` defaults to `3` and accepts only `2` or `3`. Two Explorers is the normal batch size; three is the hard limit. The documented policy shape is:

```json
{"parallel":{"enabled":false,"max_explorers":3}}
```

This is policy documentation, not a v1 config-file loader. `jev.json` remains Jev-scoped; v1 adds no XDG file or persisted session-state fields for Parallel. The caller passes a normalized admission object directly to `scripts/parallel_validate`:

```json
{
  "mode":"admission",
  "enabled":true,
  "max_explorers":3,
  "objective":"Investigate the intermittent import failure",
  "active_batches":0,
  "units":[
    {
      "unit_id":"import-path",
      "role":"explorer",
      "read_only":true,
      "objective":"Trace the package import path",
      "completion_criteria":"Identify the import path and cite the relevant code",
      "depends_on":[],
      "read_scope":["src/imports/"]
    },
    {
      "unit_id":"runtime-env",
      "role":"explorer",
      "read_only":true,
      "objective":"Check whether runtime environment resolution changes the import path",
      "completion_criteria":"Establish the environment-dependent path from code or primary documentation",
      "depends_on":[],
      "read_scope":["src/runtime/","docs/runtime.md"]
    }
  ]
}
```

The top-level `objective` is the shared parent; each unit has its own bounded objective and independently checkable completion criteria. Admission requires 2–3 unique, stable `unit_id` values, `role: "explorer"` for every unit, `read_only: true`, non-empty objectives and completion criteria, and empty `depends_on` arrays. A single valid Explorer unit returns `admitted: false` with reason `single_unit_sequential`, directing the caller to the sequential path rather than reporting malformed input.

`active_batches` is the caller/Orchestrator's attestation of the number of
parallel batches already active for this objective: `0` means none are active, so
this candidate may be admitted as the one; `1` means one is already active, so
this candidate is rejected. The helper validates only the supplied count and
cannot discover live batches system-wide.

`read_scope` is optional guidance only; overlaps are explicitly allowed. Do not provide `write_scope` or `write_intent` keys, even as empty values, and do not mark a batch or unit nested. The helper validates explicit structural claims, not semantic independence: before admission, the Orchestrator must confirm that no sibling result can change another unit's question, strategy, or safe completion condition. Reject any fixer role, sibling dependency, or shared-write requirement.

The helper emits one JSON verdict on stdout and makes no Herdr, Harvest, Jev, filesystem-state, or network calls. `mode: "admission"` returns `admitted`, a stable `reason`, and deterministic `checks`. `enabled` omitted is treated as disabled; `max_explorers` omitted defaults to three. Malformed JSON or an unrecognized/missing mode returns the mode-independent failure envelope `{"admitted":false,"ready":false,"reason":"invalid_input"}`, so neither an admission nor a convergence caller can mistake it for success; convergence responses always carry `ready`. Admission failure means sequential fallback, not task failure.

## Dispatch

1. Decompose the investigation before prompting. Give every unit a stable ID,
   distinct bounded objective, independent completion criteria, and read-only
   scope guidance; validate the batch with `parallel_validate`.
2. Confirm the runtime preconditions before launching: `active_batches` is attested as `0`, and no Fixer is executing against this shared repository working tree. Use `herdr agent get <fixer-name>` to check the resolved Fixer's lifecycle; it must be idle (or done). This is absolute, not objective-scoped: v1 has no worktree isolation, so a Fixer writing during the batch races on files, tests, and process state regardless of which objective it serves. While the batch is active, do not start or prompt a Fixer. The sequential Fixer may begin only after all Explorer units settle, convergence completes, and the Orchestrator has settled strategy. Enforcement boundary: `parallel_validate` structurally rejects non-Explorer and write-intent units; runtime Fixer idleness is verified by the Orchestrator through Herdr lifecycle state. The validator cannot prove Fixer idleness or inspect live batches.
3. Use distinct Explorer identities such as `explorer`, `explorer-2`, and `explorer-3`, reusing the settled Explorer harness, model, and effort. Keep every target in the current tab; cross-tab use is forbidden. Before each prompt, run `herdr agent get` and confirm the target is idle and matches the settled configuration. Never repurpose a Fixer agent or pane. Every sibling handoff must state that the Explorer is read-only and must not edit repository files, change application/project state, invoke `agent-orchestration`, delegate to another agent, create/start/control any pane or agent, spawn another parallel batch, or perform Git mutations. The Orchestrator owns orchestration; the Explorer owns only its bounded investigation and returns one `<HERDR_RESULT>`. Nothing in the handoff authorizes modifying the working tree or orchestrating siblings. Place Explorer panes in the delegated area, preserve user-owned panes, and follow [`STARTUP.md`](STARTUP.md) without assuming fixed geometry.
4. Submit prompts in quick succession without waiting for siblings. Validate A with `herdr agent get`, record its `completion_seq` and `state_change_seq` baseline, and submit A with `herdr agent prompt <name>` (without `--wait`). Validate B with `herdr agent get`, record its baselines, and submit B the same way; then validate C, record its baselines, and submit C. Do not pass `--wait` on submission commands: a blocking wait between sibling submissions serializes the batch. Sequential `--wait` on a single prompt outside a parallel batch is unchanged.
5. Only after all submissions are complete, verify each target independently made observable progress within a bounded window: `herdr agent wait <name> --until working --until blocked --until done --timeout 30000`, then confirm with `herdr agent get <name>` that it is `working`, `blocked`, or `done`, or that its `completion_seq`/`state_change_seq` advanced past the recorded baseline. Status can flap and a fast unit can complete before the first observation, so comparison with the baseline counts. `blocked` means the submission landed but the target needs the [`RECOVERY.md`](RECOVERY.md) permission path. A target with no observable progress is a submission/start failure for that unit: classify it recoverable (`incomplete`), never a terminal `failed` gap, and do not let it block collection of successful siblings.
6. Collect each verified target with a bounded wait: `herdr agent wait <name> --timeout <ms>` (a finite bound sized to the unit's expected work, for example `600000`), then `herdr agent read <name> --source recent-unwrapped`. A wait can return immediately for an already-settled agent, so always validate that the block is the latest complete `<HERDR_RESULT>` for the current prompt. If the wait fails or times out, inspect and route that unit to [`RECOVERY.md`](RECOVERY.md); do not restart successful siblings.

The shared per-session schema-v2 state remains unchanged: no batch, unit, prompt, result, or Harvest runtime values are added to `session-<cksum>.json`. The one objective-scoped `active_orchestration` remains the shared parent identity.

## Collection and partial failure

After the bounded progress and collection waits in Dispatch, read each pane's latest complete result using `herdr agent read --source recent-unwrapped`. Apply the existing stale-result rule: only the complete `<HERDR_RESULT>` for the current prompt counts; old, partial, echoed, or missing output is not success. Validate every accepted result independently against that unit's completion criteria and cited evidence.

When Harvest is available, use the shared parent objective ID/label and claim each accepted result for its producing pane before prompting or reusing that pane again. Harvest remains optional; it does not create the batch or change per-session role state.

A missing, malformed, rejected, or failed result affects only that unit. Preserve successful sibling results and mark the affected unit `incomplete` (recoverable, with the precise evidence gap recorded) unless recovery has been exhausted or deliberately abandoned; only then record terminal `failed` with an explicit non-empty gap. Use the existing per-unit procedures in [`RECOVERY.md`](RECOVERY.md): inspect agent state/output/process, interrupt only when justified, apply existing retry bounds, and keep the Explorer three-round cap. Retry incomplete units with focused questions; do not restart successful siblings. Recoverable operational failures are never normalized to terminal `failed` merely to let the batch use `ready_with_gaps`.

## Convergence and resume

After collection, the Orchestrator alone synthesizes one result for the parent objective. Separate observed evidence from each Explorer's interpretation, preserve contradictions and provenance, and state unresolved gaps. Never majority-vote, concatenate sibling reports into a model prompt, or ask Jev to choose which Explorer is right. If evidence conflicts or a conclusion depends on a sibling result, ask one focused sequential follow-up Explorer after the batch converges.

The helper's `mode: "convergence"` accepts unit statuses `accepted`, `failed`, `incomplete`, `pending`, or `running`, and separates active work, recovery, and terminal outcomes:

- `accepted` — carries a valid latest complete tag-delimited `accepted_result` (`<HERDR_RESULT>…</HERDR_RESULT>`); counts as complete. The helper checks only the result envelope, so the Orchestrator must still validate freshness, content, evidence, and completion criteria.
- `pending` — the prompt was accepted but the unit has not yet been observed to begin; active, not terminal, not a success.
- `running` — the unit has demonstrated progress and is still executing; active, not terminal, not a success.
- `incomplete` — the unit needs recovery (recollection, re-prompt/retry, or interruption resume) before it can settle: malformed or missing `accepted_result`, unsupported status, submission/start failure, `agent_prompt_stalled`, `agent_blocked` while recovery is possible, or interruption with no accepted result. Recoverable.
- `failed` — a settled terminal failure whose normal recovery the Orchestrator has exhausted or deliberately abandoned; only terminal failures participate in `ready_with_gaps`, and only with one or more explicit non-empty `gaps`.

The verdict reports `accepted_units`, `failed_units`, `incomplete_units`, `pending_units`, `running_units`, `gaps`, `recoverable_units`, and `recoverable`. `recoverable_units` lists only units that still require recovery action (the `incomplete` set); pending and running units are active, and terminal failed units are settled. When pending or running units remain after invalid-result, invalid-status, failed-without-gaps, and incomplete checks, the verdict is `ready: false` with reason `active_units`. `ready: true` requires every unit accepted, or `ready_with_gaps` with every failed unit carrying explicit gaps and no incomplete, pending, or running units. Pending, running, incomplete, invalid results, unsupported statuses, and invalid input are never ready; an explicit gap cannot skip recovery for an unresolved unit. The verdict does not change unit status or accept a result on the Orchestrator's behalf.

On resume, accepted results remain accepted and are not gratuitously rerun. Incomplete units are recoverable; revalidate each target with `herdr agent get` (idle, same tab, settled configuration) before resuming its same unit. Pending and running units are active, not recoverable: wait for them or re-check their lifecycle rather than re-prompting. If a target is unhealthy or a prompt failed after start, follow [`RECOVERY.md`](RECOVERY.md) for that unit. Keep accepted sibling evidence and Harvest claims intact; retry only what remains unresolved.

## Explorer Gate interaction

After synthesis and review of the combined evidence, the Orchestrator may make zero or one Explorer Gate call for the batch—never one per sibling. Zero is valid whenever the gate is disabled or the request is otherwise ineligible; at most one compact summary marked `orchestrator_reviewed: true` may be submitted. [`EXPLORER_GATE.md`](EXPLORER_GATE.md) is authoritative for eligibility and gate behavior, which do not change for parallel use. Batch size does not multiply calls or extend the Explorer round cap.

## Sequential implementation and completion

All Fixer work and all writes remain sequential in the shared working tree. V1 has no worktree isolation: simultaneous Fixers or a Fixer overlapping investigation can race on files, tests, and process state. After convergence, choose one strategy and one bounded implementation handoff, then run the ordinary sequence:

```text
Explorer batch -> orchestrator convergence -> strategy -> sequential fixer
  -> diff review -> deterministic verification -> Completion Gate (if enabled)
```

Parallel Explorer success skips no review, verification, retry, or completion criteria. The Completion Gate remains post-implementation and is not a batch-convergence mechanism. The existing cap of three Explorer rounds per objective and two consecutive attempts on the same issue without progress still apply; progress means changing the observed failure or resolving a review finding, supported by evidence facts rather than repeated claims or unchanged evidence.

## Why there is no Parallel Gate

Admission is deterministic and checked by the Orchestrator; convergence is an evidence-synthesis responsibility requiring source comparison and judgment. A new model gate would add no safe control that the admission helper and one orchestrator-owned synthesis do not already provide. The Explorer Gate covers the adjacent post-investigation evidence-sufficiency decision, and the Completion Gate covers post-implementation completion; neither needs parallel-specific semantics.

## Safety

Use parallelism only to shorten independent, read-only investigation. Keep prompts and results out of persisted session state; do not include credentials, secrets, or raw sibling output in another handoff. Preserve the user’s working tree and panes. If independence, safety, same-state visibility, or a unit's completion condition is unclear, serialize the investigation or ask the Orchestrator to resolve the uncertainty before dispatch.
