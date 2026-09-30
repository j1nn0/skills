# Harvest orchestration capture

Optional Harvest integration for `agent-orchestration`. This file owns the
orchestration objective identity, its persisted lifecycle, capability
negotiation, runtime discovery, and result claim protocol.

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
top-level objective, and only after capability negotiation under "Capability
negotiation" succeeds. Persist it atomically before that prompt is sent.

### Reuse

Before creating one, decide whether a valid existing `active_orchestration`
already represents the current objective. Reuse it when the current work is
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

When the orchestrator gets an explicit opportunity to record a pause, set
`status` to `interrupted` and keep the id and label. If the process or the user
interrupts abruptly before that update lands, leaving `status` as `active` is
acceptable. The invariant to protect is: never clear `active_orchestration`
merely because work stopped temporarily.

When the same objective resumes, reuse the same id and label and set `status`
back to `active`.

### Completion

Set `active_orchestration` to `null` only after the orchestrator itself has
confirmed the top-level objective's completion criteria, or the user has
explicitly abandoned or cancelled the objective. Persist that update
atomically, before the user-facing final report where practical.

Do not clear it because one explorer or fixer unit finished, and do not clear
it between explorer and fixer. Do not accumulate completed-orchestration
history in this file; Harvest Results already snapshot completed identity.

## Discovery

Use only supported public surfaces. First:

```bash
herdr plugin list --plugin j1nn0.herdr-harvest --json
```

The plugin objects are under `.result.plugins`. Require an exact installed
plugin:

```text
plugin_id == j1nn0.herdr-harvest
enabled == true
plugin_root is non-empty
```

Take `plugin_root` from that output and use it for every later command. Do not
hard-code a managed checkout path and do not infer a plugin directory from XDG
paths. The reported `version` field is diagnostic only.

Never gate the integration on a Harvest version number. Do not write or rely on
a rule of the form "Harvest >= 0.x.y is sufficient". Capability negotiation is
the only authority.

If no exact enabled plugin with a non-empty `plugin_root` is available, Harvest
integration is unavailable and ordinary orchestration continues.

## Capability negotiation

Run:

```bash
node "<plugin_root>/src/bin/capture.ts" --capabilities
```

It prints one JSON line and touches neither the environment, the database, nor
Herdr:

```json
{"protocol":"harvest-capture","protocolVersion":1,"features":["orchestration-claim","runtime-locator"],"roles":["explorer","fixer"]}
```

Require all of:

```text
protocol == harvest-capture
protocolVersion == 1
features contains orchestration-claim
features contains runtime-locator
roles contains the role being claimed
```

`protocolVersion` must equal `1`. A higher, unknown protocol version is not
compatible merely because it is numerically greater.

If Node cannot execute the entrypoint, or the probe fails or prints anything
else, Harvest integration is unavailable and ordinary orchestration continues.
Do not create a new `active_orchestration` unless capability negotiation has
succeeded.

## Runtime locator

For an actual claim, resolve the plugin config directory through Herdr rather
than computing it:

```bash
herdr plugin config-dir j1nn0.herdr-harvest
```

It prints one raw path on stdout followed by a newline; it is not JSON. Read:

```text
<config-dir>/orchestration-capture-runtime.json
```

Require:

```text
protocol == harvest-runtime-locator
protocolVersion == 1
pluginId == j1nn0.herdr-harvest
stateDir is a non-empty absolute path
socketPath is a non-empty string
socketPath == the current HERDR_SOCKET_PATH
```

`updatedAtMs` may be read as diagnostic metadata but must never override the
socket identity check. The socket comparison is what proves the locator
describes the Herdr server this orchestrator is actually talking to.

If the locator is missing, malformed, or points at another socket, Harvest
integration is unavailable for this claim. Do not guess another state directory
and do not reproduce Herdr's internal state-directory calculation. A missing
locator can simply mean Harvest has not run yet in this Herdr session, so a
later claim in the same objective may still succeed.

## Claiming a completed delegated result

The only authoritative orchestration association is this explicit claim:

```bash
env -u HARVEST_STATE_DIR \
  HERDR_PLUGIN_STATE_DIR="<locator.stateDir>" \
  node "<plugin_root>/src/bin/capture.ts" \
    --pane "<delegated-pane-id>" \
    --orchestration-id "<uuid-v4>" \
    --orchestration-label "<stable-label>" \
    --orchestration-role "<explorer|fixer>"
```

Rules:

- `HARVEST_STATE_DIR` must actually be absent from the child environment.
  Harvest resolves its state directory as
  `HARVEST_STATE_DIR ?? HERDR_PLUGIN_STATE_DIR`, so a leftover
  `HARVEST_STATE_DIR` silently wins and the claim lands in the wrong database.
  Equivalent environment handling is fine as long as the variable is genuinely
  unset for the child.
- The current `HERDR_SOCKET_PATH` must be preserved in the child process;
  Harvest needs it to reach Herdr and read the pane.
- `--pane` is the delegated agent's pane id, never the orchestrator's pane.
- The three orchestration options are all-or-nothing: supplying only some of
  them is a usage error that captures nothing.
- `--orchestration-id` must be a canonical lowercase UUIDv4; uppercase or
  prefixed tokens are rejected.
- `--orchestration-label` must be 1-256 non-blank Unicode code points and is
  stored verbatim.
- `--orchestration-role` is exactly `explorer` or `fixer`, case-sensitive.

### Transport boundaries

The UUID, label, and role travel only through these CLI arguments. Never
transport orchestration identity through pane metadata tokens, `state_labels`,
workspace/tab/pane inference, native session inference, environment variables
such as `HARVEST_ORCHESTRATION_ID`, prompt embedding, terminal-output parsing,
or timestamps.

There is no metadata token, TTL, or sequence number in this design; do not
reintroduce one. Never claim the long-lived top-level orchestrator pane — only
`explorer` and `fixer` are Harvest orchestration roles.

## Claim results

The command prints one JSON summary line on stdout. Outcomes:

```text
exit 0  captured | duplicate | skipped
exit 1  failed (capture or runtime failure)
exit 2  invalid arguments
exit 3  conflict
```

Top-level `status` is one of `captured`, `duplicate`, `conflict`, `skipped`, or
`failed`. An `orchestration` object of the form
`{"status":"...","id":"..."}` appears only with `captured` or `duplicate`,
and its `status` is either `claimed` or `already_claimed`.

Treat only these as success:

```text
status == captured  or  status == duplicate
and orchestration.status == claimed  or  already_claimed
```

`already_claimed` is successful idempotency, not an error: it means the stored
row already holds the identical id, label, and role.

A conflict is `exit 3` with `status == conflict`, plus
`requestedOrchestrationId` and `existingOrchestrationId`; it carries no
`orchestration` object. Harvest refuses only the attribution — the delegated
Result itself is still stored.

A conflict must never be repaired by changing the UUID, changing the label,
overwriting the existing claim, or retrying with guessed metadata. Record the
integration problem and continue the engineering workflow.

## Graceful degradation

None of these may fail the delegated engineering task:

- `skipped`;
- `failed`;
- malformed JSON;
- a missing or stale locator;
- a capability mismatch;
- a conflict;
- a process failure.

Never discard an otherwise valid explorer or fixer result because Harvest
failed. Never change role configuration because of a Harvest failure.

If one or more claims failed or conflicted during an objective, mention it once
in the user-facing final report so the user knows the grouping may be
incomplete; do not report a Harvest problem after every unit.
