# Harvest orchestration capture

Optional Harvest integration for `agent-orchestration`. This file owns the
orchestration objective identity, its persisted lifecycle, claim ordering,
and graceful degradation. Deterministic Harvest protocol mechanics live in
`scripts/harvestctl`; persisted session state lives in
`scripts/sessionctl`.

The ordinary interaction is:

```text
decide objective identity using this policy
→ persist identity using sessionctl
→ harvestctl doctor
→ delegate work
→ accept delegated result
→ harvestctl claim
```

Do not reproduce plugin discovery, capability validation, runtime locator
parsing, environment sanitization, or exit-code interpretation by hand.
`harvestctl` is the tested adapter for those mechanics.

Read this before the first delegated prompt of every invocation that will delegate. Harvest grouping is enrichment, not a prerequisite. When Harvest is unavailable, disabled, incompatible, or failing, delegation proceeds unchanged and the persisted explorer/fixer role configuration is untouched; never ask the user to install Harvest because of this integration.

## Orchestration identity

Role configuration is scoped to the native Herdr session of the current top-level orchestrator and managed by [`STARTUP.md`](STARTUP.md); the orchestration identity has a different lifetime and must remain independent.

The identity is scoped to one coherent top-level engineering objective, not the session, invocation, request, unit, or delegated agent. It survives the move from explorer to fixer, every bounded unit within the objective, review and fix retries, delegated-agent restarts, pane recreation, context compaction, and interruption followed by resume. Creating, reusing, interrupting, resuming, or clearing it never re-asks for or changes the explorer/fixer harness, model, or effort.

Before the first delegated prompt of an objective, reuse the existing identity when the current work clearly continues that objective: another bounded unit, a review or fix retry, the move from explorer to fixer, a resume after interruption, or work continuing after context compaction. Create a new identity only when the request is clearly an independent objective. When identity is genuinely ambiguous, prefer a new identity or none at all; under-grouping is safer than false grouping. Do not create one merely because the skill was invoked, a message arrived, context was compacted, a pane was created, or an agent restarted.

The identity is stable for the whole objective: the same id and label cover every explorer and fixer unit within it, and the label never changes because the plan or wording evolved.

### Claim ordering

Claim ordering is mandatory when Harvest capture is available.

Once a delegated explorer or fixer result has settled and been accepted as the
answer to the prompt just sent, claim it for the current identity and inspect
the claim's JSON outcome before sending that role another prompt, before
reusing its pane or agent for another unit, and before moving on to another
delegated unit.

The orchestrator may review the diff and evidence before or after the claim,
but must not mutate or reuse the delegated agent's turn until the claim has
been attempted. Claim every completed unit, not just the last one.

The ordering matters because panes and agents are reused across objectives: a
synchronous claim right after each completed turn is the only thing that keeps
a reused pane's next Result from being attributed to the previous objective.
Existing stale-result protections still apply: an old result block is never a
new completion, and a stale block must never be claimed.

Only `explorer` and `fixer` are Harvest orchestration roles. Never claim the
long-lived top-level orchestrator pane.

A failed or conflicting claim never fails the engineering work or discards a
valid delegated result. Record the integration problem and mention it once in
the final report, not after every unit.

Do not put the orchestration id, Harvest paths, locator, or anything about the
claim protocol into explorer or fixer handoff prompts. Delegated agents do not
need to know Harvest exists; the orchestrator owns the association externally.

## Persisted active orchestration

The `active_orchestration` field in the session-state file defined by [`STARTUP.md`](STARTUP.md) holds the identity of the current orchestration objective:

```json
"active_orchestration": {
  "id": "<canonical lowercase UUIDv4>",
  "label": "<stable one-line objective label>",
  "status": "active",
  "created_at": "<ISO-8601 timestamp>"
}
```

Allowed status values are exactly `active` and `interrupted`. No other value is valid.

Use `skills/agent-orchestration/scripts/sessionctl` for persisted lifecycle state. It handles storage only; the orchestrator applies the policy in this section and must not edit the state file directly. `harvestctl` never reads or writes session state, never decides objective reuse, and never calls `sessionctl`.

### Scope and lifetime

See [Orchestration identity](#orchestration-identity) for the objective scope and the decision to create, reuse, or decline a stored identity; role configuration has the separate session lifetime defined in [`STARTUP.md`](STARTUP.md).

Create the identity immediately before the first actual delegated prompt of one coherent top-level objective, and only after `skills/agent-orchestration/scripts/harvestctl doctor --role <explorer|fixer>` reports the integration available for that role. Record it before sending that prompt with `skills/agent-orchestration/scripts/sessionctl orchestration set --id UUID --label LABEL`; the command stores it as `active` with its creation timestamp.

### Reuse

Before creating, run `skills/agent-orchestration/scripts/sessionctl orchestration get`. Reuse the existing id and label when the identity decision in "Orchestration identity" says the objective continues; for a clearly independent objective, do not reuse the old id, and never merge unrelated objectives.

### Generating the identity

Generate the UUID with Node's built-in `randomUUID()`; no dependency is required:

```bash
node -e 'console.log(require("node:crypto").randomUUID())'
```

The canonical lowercase form it returns is what Harvest requires. Never hand-edit or re-case the id.

The label must be a concise single line describing the top-level engineering objective. It must be non-blank, at most 256 Unicode code points, free of credentials and secrets, and identical for the whole lifetime of the id. The plan or wording evolving later is not a reason to rename it: Harvest treats a different label or role snapshot for the same id as a conflict.

### Interruption and resume

When the orchestrator gets an explicit opportunity to record a pause, run `skills/agent-orchestration/scripts/sessionctl orchestration interrupt`. It sets `status` to `interrupted` and keeps the id, label, and creation timestamp. If the process or the user interrupts abruptly before that update lands, leaving `status` as `active` is acceptable. Never clear `active_orchestration` merely because work stopped temporarily.

When the same objective resumes, reuse the same id and label and run `skills/agent-orchestration/scripts/sessionctl orchestration resume` to set status back to `active`.

### Completion

Run `skills/agent-orchestration/scripts/sessionctl orchestration clear` to set `active_orchestration` to `null` only after the orchestrator itself has confirmed the top-level objective's completion criteria, or the user has explicitly abandoned or cancelled the objective. Persist that update before the user-facing final report where practical.

Do not clear it because one explorer or fixer unit finished, and do not clear it between explorer and fixer. Do not accumulate completed-orchestration history in this file; Harvest Results already snapshot completed identity.

## Harvest availability and claims via harvestctl

`harvestctl` speaks the Harvest protocol; this file decides identity. The
wrapper rediscovers runtime state on every run and keeps no persistent state.
Consume its normalized JSON, never native capture exit codes or internals.

### doctor

```bash
skills/agent-orchestration/scripts/harvestctl doctor --role <explorer|fixer>
```

`doctor` is a side-effect-free preflight: it checks plugin and capability compatibility for the requested role, never captures a result, never writes session or Harvest state, and never requires a runtime locator. A missing locator before Harvest has run does not mean protocol incompatibility.

It prints exactly one JSON object:

```json
{"ok":true,"available":true,"claim_supported":true,"reason":null,"role":"explorer"}
```

An unavailable integration keeps process exit 0 with `available` and `claim_supported` false; `reason` is diagnostic only. When unavailable, ordinary orchestration continues and no new `active_orchestration` is created. Exit 2 means invalid wrapper usage.

### claim

When "Claim ordering" requires a capture, invoke:

```bash
skills/agent-orchestration/scripts/harvestctl claim \
  --pane "<delegated-pane-id>" \
  --id "<uuid-v4>" \
  --label "<stable-label>" \
  --role <explorer|fixer>
```

Pass the delegated pane (never the orchestrator pane) with the current stable id, label, and role. `claim` independently revalidates plugin, capabilities, role support, runtime locator, and socket identity, builds a sanitized child environment, invokes capture, and normalizes the verdict; do not run `doctor` immediately before every claim.

It prints exactly one JSON object with `claimed` true only on a successful association:

```json
{"ok":true,"claimed":true,"status":"duplicate","claim_status":"already_claimed","reason":null}
```

`claimed` is true for a fresh or idempotent duplicate association (`already_claimed` is success, not an error). A conflict reports `claimed` false with `status` `conflict` and `reason` `claim_conflict`. An integration that cannot attempt the claim reports `status` `unavailable`; a skipped or failed capture reports its own `status` with a stable `reason`. Malformed or inconsistent native responses fail closed. Valid wrapper verdicts exit 0; exit 2 means invalid wrapper input.

A conflict must never be repaired by changing the UUID, changing the label, overwriting the existing claim, or retrying with guessed metadata. Record the integration problem and continue the engineering workflow.

### Transport boundaries

The UUID, label, and role travel only through the explicit claim arguments. Never transport orchestration identity through pane metadata tokens, `state_labels`, workspace/tab/pane inference, native session inference, environment variables such as `HARVEST_ORCHESTRATION_ID`, prompt embedding, terminal-output parsing, or timestamps.

There is no metadata token, TTL, or sequence number in this design; do not reintroduce one.

## Graceful degradation

Harvest failures—including skipped or failed capture, malformed responses, a missing or stale locator, a capability mismatch, a conflict, or a process failure—never fail the delegated engineering task. Never discard an otherwise valid explorer or fixer result because Harvest failed, and never change role configuration because of a Harvest failure.

If one or more claims failed or conflicted during an objective, mention it once in the user-facing final report so the user knows the grouping may be incomplete; do not report a Harvest problem after every unit.
