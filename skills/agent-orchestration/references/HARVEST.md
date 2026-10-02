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

Read this before the first delegated prompt of every invocation that will
delegate. Reuse or replace the current objective identity according to the
lifecycle below. Harvest grouping is enrichment, not a prerequisite for
delegation. When Harvest is unavailable, disabled, incompatible, or failing,
delegation proceeds unchanged and the persisted explorer/fixer role
configuration is untouched.

Never ask the user to install Harvest because of this integration.

## Orchestration identity

The role configuration and orchestration identity have different lifetimes and
must remain independent.

Role configuration is scoped to the current top-level orchestrator's native
Herdr agent session and is managed by [`STARTUP.md`](STARTUP.md).

The orchestration identity is scoped to one coherent top-level engineering
objective rather than to the session, invocation, request, unit, or delegated
agent. Creating, reusing, interrupting, resuming, or clearing that identity
never re-asks for or changes the explorer/fixer harness, model, or effort.

Before the first delegated prompt of an objective, either reuse the existing
identity or create a new one when Harvest is available. Reuse it when the
current work continues the same objective: another bounded unit, a review or
fix retry, the move from explorer to fixer, a resume after interruption, or
work continuing after context compaction.

Create a new one only when the request is clearly an independent objective.
When identity is genuinely ambiguous, prefer a new identity or none at all,
because under-grouping is safer than false grouping. Do not create one merely
because the skill was invoked, a message arrived, context was compacted, a pane
was created, or an agent restarted.

The identity is stable for the whole objective: the same id and label cover
every explorer and fixer unit within it, and the label never changes because
the plan or wording evolved.

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

The `active_orchestration` field in the session-state file defined by
[`STARTUP.md`](STARTUP.md) holds the identity of the current orchestration
objective:

```json
"active_orchestration": {
  "id": "<canonical lowercase UUIDv4>",
  "label": "<stable one-line objective label>",
  "status": "active",
  "created_at": "<ISO-8601 timestamp>"
}
```

Allowed `status` values are exactly `active` and `interrupted`. No other value
is valid.

Use `skills/agent-orchestration/scripts/sessionctl` for persisted lifecycle
state. It handles storage only; the orchestrator applies the policy in this section
and must not edit the state file directly. `harvestctl` never reads or writes
session state, never decides objective reuse, and never calls `sessionctl`.

### Scope and lifetime

One `active_orchestration` represents one coherent top-level engineering
objective. It survives the move from explorer to fixer, every bounded unit
within the objective, review and fix retries, delegated-agent restarts, pane
recreation, context compaction, and interruption followed by resume. It is not
per skill invocation, not per user message, not per unit, and not per delegated
agent.

Do not create one merely because the skill was invoked, a user sent a message,
context was compacted, a role pane was created, or a role agent restarted.
Create it immediately before the first actual delegated prompt of one coherent
top-level objective, and only after
`skills/agent-orchestration/scripts/harvestctl doctor --role <explorer|fixer>`
reports the integration available for that role. Record it before sending that
prompt with
`skills/agent-orchestration/scripts/sessionctl orchestration set --id UUID --label LABEL`;
the command stores it as `active` with its creation timestamp.

### Reuse

Before creating one, run `skills/agent-orchestration/scripts/sessionctl orchestration get`
and check whether a valid existing `active_orchestration` represents the current
objective. Reuse it when the current work is
clearly a continuation — for example continuing the same unfinished task,
resuming after an interruption, continuing after context compaction, moving
from explorer to fixer for the same objective, starting another bounded unit of
the same objective, or a review/fix retry for the same objective.

If the current user request is clearly an independent objective, do not reuse
the old id. If identity is genuinely ambiguous, prefer a new identity, or no
Harvest integration at all. Under-grouping is safer than false grouping, and
two unrelated objectives must never be merged merely to maximize grouping.

### Generating the identity

Generate the UUID with Node's built-in `randomUUID()`; no dependency is
required:

```bash
node -e 'console.log(require("node:crypto").randomUUID())'
```

The canonical lowercase form it returns is what Harvest requires. Never
hand-edit or re-case the id.

The label must be a concise single line describing the top-level engineering
objective. It must be non-blank, at most 256 Unicode code points, free of
credentials and secrets, and identical for the whole lifetime of the id.
The plan or wording evolving later is not a reason to rename it: Harvest treats
a different label or role snapshot for the same id as a conflict.

### Interruption and resume

When the orchestrator gets an explicit opportunity to record a pause, run
`skills/agent-orchestration/scripts/sessionctl orchestration interrupt`. It sets
`status` to `interrupted` and keeps the id, label, and creation timestamp. If the
process or the user interrupts abruptly before that update lands, leaving
`status` as `active` is acceptable. Never clear `active_orchestration` merely
because work stopped temporarily.

When the same objective resumes, reuse the same id and label and run
`skills/agent-orchestration/scripts/sessionctl orchestration resume` to set
`status` back to `active`.

### Completion

Run `skills/agent-orchestration/scripts/sessionctl orchestration clear` to set
`active_orchestration` to `null` only after the orchestrator itself has
confirmed the top-level objective's completion criteria, or the user has
explicitly abandoned or cancelled the objective. Persist that update before the
user-facing final report where practical.

Do not clear it because one explorer or fixer unit finished, and do not clear
it between explorer and fixer. Do not accumulate completed-orchestration
history in this file; Harvest Results already snapshot completed identity.

## Harvest availability and claims via harvestctl

`harvestctl` speaks the Harvest protocol; this file decides identity. The
wrapper rediscovers runtime state on every run and keeps no persistent state.
Consume its normalized JSON, never native capture exit codes or internals.

### doctor

```bash
skills/agent-orchestration/scripts/harvestctl doctor --role <explorer|fixer>
```

`doctor` is a side-effect free preflight: it checks plugin and capability
compatibility for the requested role. It never captures a result, never writes
session or Harvest state, and never requires a runtime locator — a missing
locator before Harvest has run does not mean protocol incompatibility.

It prints exactly one JSON object:

```json
{"ok":true,"available":true,"claim_supported":true,"reason":null,"role":"explorer"}
```

An unavailable integration keeps process exit 0 with `available` and
`claim_supported` false and a stable `reason` such as `plugin_unavailable`,
`capability_probe_failed`, `capability_invalid`, `protocol_mismatch`,
`protocol_version_mismatch`, `feature_missing`, or `role_unsupported`.
Exit 2 means invalid wrapper usage. When unavailable, ordinary orchestration
continues and no new `active_orchestration` is created.

### claim

After a delegated result settles and the Orchestrator accepts it, claim before
prompting or reusing that role again:

```bash
skills/agent-orchestration/scripts/harvestctl claim \
  --pane "<delegated-pane-id>" \
  --id "<uuid-v4>" \
  --label "<stable-label>" \
  --role <explorer|fixer>
```

Pass the delegated pane (never the orchestrator pane) with the current stable
id, label, and role. `claim` independently revalidates plugin, capabilities,
role support, runtime locator, and socket identity, builds a sanitized child
environment, invokes capture, and normalizes the verdict — do not run `doctor`
immediately before every claim.

It prints exactly one JSON object with `claimed` true only on a successful
association:

```json
{"ok":true,"claimed":true,"status":"duplicate","claim_status":"already_claimed","reason":null}
```

`claimed` is true for a fresh or idempotent duplicate association
(`already_claimed` is success, not an error). A conflict reports
`claimed` false with `status` `conflict` and `reason` `claim_conflict`. An
integration that cannot attempt the claim reports `status` `unavailable`;
a skipped or failed capture reports its own `status` with a stable `reason`.
Malformed or inconsistent native responses fail closed. Valid wrapper
verdicts exit 0 so optional Harvest failures never fail shell control flow;
exit 2 means invalid wrapper input.

A conflict must never be repaired by changing the UUID, changing the label,
overwriting the existing claim, or retrying with guessed metadata. Record the
integration problem and continue the engineering workflow.

### Transport boundaries

The UUID, label, and role travel only through the explicit claim arguments. Never
transport orchestration identity through pane metadata tokens, `state_labels`,
workspace/tab/pane inference, native session inference, environment variables
such as `HARVEST_ORCHESTRATION_ID`, prompt embedding, terminal-output parsing,
or timestamps.

There is no metadata token, TTL, or sequence number in this design; do not
reintroduce one. Never claim the long-lived top-level orchestrator pane — only
`explorer` and `fixer` are Harvest orchestration roles.

## Graceful degradation

None of these may fail the delegated engineering task:

- `skipped`;
- `failed`;
- malformed responses;
- a missing or stale locator;
- a capability mismatch;
- a conflict;
- a process failure.

Never discard an otherwise valid explorer or fixer result because Harvest
failed. Never change role configuration because of a Harvest failure.

If one or more claims failed or conflicted during an objective, mention it once
in the user-facing final report so the user knows the grouping may be
incomplete; do not report a Harvest problem after every unit.
