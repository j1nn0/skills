# Startup

Session state, the active orchestration identity, agent, and pane resolution
for `agent-orchestration`, plus the optional Harvest orchestration capture
integration. Read this before the first delegation of every invocation of this
skill, and whenever a role's agent is missing, lives in another tab, has the
wrong harness, model, or effort, or needs a pane created.

## Session state

The persisted session state is the authority for whether role configuration has
already been settled. Do not rely only on conversational memory.

At the start of every invocation of this skill, before asking the user about
harnesses, models, or effort:

1. Run:

   ```bash
   herdr pane get "$HERDR_PANE_ID"
   ```

2. Read the returned pane's `agent_session` object. Use these fields as the
   current top-level orchestrator session identity:

   - `source`
   - `kind`
   - `value`

   The `agent` label is diagnostic metadata, not part of the identity.

3. If `agent_session` is absent, do not treat `$HERDR_PANE_ID`,
   `$HERDR_TAB_ID`, or `$HERDR_WORKSPACE_ID` as a substitute session identity.
   Reuse a complete role configuration only when it is still unambiguous in the
   current conversation. Otherwise ask the user. Do not persist new state until
   Herdr exposes a native `agent_session`.

4. When `agent_session` is present, use:

   ```text
   ${XDG_STATE_HOME:-$HOME/.local/state}/agent-orchestration/
   ```

   as the state directory.

   Build a deterministic file key from the exact `source`, `kind`, and `value`.
   A portable option on macOS and Linux is the first two fields emitted by
   POSIX `cksum` for these three values joined with newlines:

   ```bash
   printf '%s\n%s\n%s\n' '<source>' '<kind>' '<value>' |
     cksum |
     awk '{print $1 "-" $2}'
   ```

   Use the resulting key as:

   ```text
   <state-dir>/session-<key>.json
   ```

   `cksum` is only a filename key. Never trust the key alone.

5. If the state file exists, read it and verify that
   `orchestrator_session.source`, `orchestrator_session.kind`, and
   `orchestrator_session.value` exactly equal the current `agent_session`.
   This exact comparison is mandatory because the filename key is not the
   identity itself.

6. A state file is usable only when both roles contain non-empty `harness`,
   `model`, and `effort` values. When it is valid, load those values and do not
   ask the user again.

7. If no valid matching state exists but a complete configuration is already
   unambiguously available in the current conversation, persist that
   configuration immediately and continue without asking again. This handles
   sessions that were configured before persisted state support was added.

8. Otherwise follow "Role configuration", ask once, and persist the answer
   immediately.

Persist this shape:

```json
{
  "schema_version": 2,
  "orchestrator_session": {
    "source": "<agent_session.source>",
    "kind": "<agent_session.kind>",
    "value": "<agent_session.value>"
  },
  "explorer": {
    "harness": "<selected harness>",
    "model": "<selected model>",
    "effort": "<selected effort>"
  },
  "fixer": {
    "harness": "<selected harness>",
    "model": "<selected model>",
    "effort": "<selected effort>"
  },
  "active_orchestration": null
}
```

`active_orchestration` is either `null` or an object, and that object is
described under "Active orchestration".

Create the state directory with user-only permissions where practical and write
the JSON atomically, for example through a temporary file followed by `mv`.
Never store provider credentials, tokens, secrets, prompts, investigation
results, or implementation details in this state. Never store any Harvest
runtime value either: plugin root, plugin config directory, Harvest state
directory, socket path, capability output, agent reports, findings, or Result
text. Rediscover each of those every time it is needed.

When the user explicitly changes a role's harness, model, or effort, update the
same state file immediately. Leave the other role unchanged.

Do not delete the state file when a task or unit completes. A new native
orchestrator conversation receives a different `agent_session` identity and
therefore a different state key.

### Schema version 1 compatibility

A state file written with `"schema_version": 1` has no `active_orchestration`
field and is still a fully valid role configuration. Never ask the user for
harness, model, or effort again merely because the file is version 1 or has no
orchestration field.

Upgrade it the next time the file has to be written for any reason: set
`"schema_version"` to `2`, add `"active_orchestration": null`, and leave the
`orchestrator_session`, `explorer`, and `fixer` objects byte-for-byte
equivalent. The upgrade is one atomic write, not a separate migration pass,
and it happens before an objective is recorded.

If `active_orchestration` alone is present but malformed — not an object and
not `null`, or missing a conforming `id`, `label`, `status`, or `created_at` —
discard and replace only that field with `null`. Never invalidate an
otherwise-valid role configuration because of it.

## Active orchestration

The `active_orchestration` field holds the identity of the current
orchestration objective:

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
top-level objective, and only after Harvest capability negotiation under
"Harvest orchestration capture" succeeds. Persist it atomically before that
prompt is sent.

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
credentials and secrets, and identical for the whole lifetime of the id. The
plan or wording evolving later is not a reason to rename it: Harvest treats a
different label or role snapshot for the same id as a conflict.

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

## Pane layout

Delegated agents share one right-hand column, explorer above fixer:

```text
┌──────────────────────────────┬──────────────────────┐
│                              │       Explorer       │
│                              │         ~25%         │
│      Current agent           ├──────────────────────┤
│        Orchestrator          │        Fixer         │
│           ~50%               │         ~25%         │
└──────────────────────────────┴──────────────────────┘
```

Treat "one column, explorer on top" as an invariant to satisfy, not a sequence of
splits to replay. The roles are not always created in the same order — a settled
implementation goes straight to the fixer, so the fixer often exists before any
explorer does — and placement has to reach the same layout whichever role arrived
first.

Stable position is the point. Anyone glancing at the screen, you or the user,
should read the role off the position alone instead of checking which model is
printed in which pane. Three columns, or an explorer sitting under a fixer, costs
that on every look.

Preserve existing user-owned panes when applying this layout.

## Resolution

Before using any delegated role, first run "Session state". If it loads a valid
matching persisted configuration, use that configuration exactly and do not ask
the user again.

Before using a delegated role:

1. Run `herdr agent list` to see the live agents and the tab each one is in.
2. Reuse a live agent only when:
   - its `tab_id` equals `$HERDR_TAB_ID`;
   - its kind matches the harness settled for that role;
   - its model and effort match the configuration settled for that role in this
     conversation.
3. Never reuse, stop, replace, or repurpose an agent from another tab.
4. If the preferred name belongs to an agent in another tab, choose a unique name
   for the same-tab agent and use that resolved name thereafter.
5. If a same-tab agent has the wrong configuration:
   - stop it using the selected harness's normal exit mechanism; do not assume
     one harness's exit command is valid for another;
   - wait until it disappears from `herdr agent list`;
   - confirm its pane has returned to an available interactive shell with
     `herdr pane process-info --pane <id>`.
6. Use only an idle same-tab pane with no foreground agent, editor, or command,
   and prefer one already sitting in the delegated column. An idle pane
   elsewhere in the tab is usually the user's; taking it both breaks the layout
   and takes something that is not yours.
7. If no suitable pane exists, create one from the current state of the delegated
   column rather than from the role you happen to be placing. Take the new pane
   id from `.result.pane.pane_id`.

   **The column does not exist yet** — split the orchestrator once, to the
   right. Whichever role you are placing holds the whole column until the other
   one arrives:

   ```bash
   herdr pane split --current --direction right --ratio 0.5 --cwd "$PWD" --no-focus
   ```

   **The column already holds the other role** — split _that_ pane downward,
   never the orchestrator a second time:

   ```bash
   herdr pane split <occupied-column-pane-id> --direction down --ratio 0.5 --cwd "$PWD" --no-focus
   ```

   The new pane is the lower one, which is where the fixer belongs. When the role
   you are placing is the explorer — the fixer got here first — start it in the
   new pane, then exchange the two so the explorer ends up on top:

   ```bash
   herdr pane swap --source-pane <new-pane-id> --target-pane <fixer-pane-id>
   ```

   Splitting the orchestrator to the right a second time is what puts the
   explorer and fixer side by side in three columns. It also narrows every column
   past the width an agent's UI needs, and a column that cannot render is a
   column whose output you cannot read.

   When the tab already holds user panes, check the geometry first with
   `herdr pane layout --pane "$HERDR_PANE_ID"` and place the split so no pane
   becomes unusable.

8. Start the role with the configuration settled for it. `agent start` returning
   `agent_not_ready` is not a failed start: the agent was detected but is
   blocked at a startup prompt, and its name stays usable for `herdr agent read`
   and `herdr agent send-keys`. Inspect it, resolve the block under
   "Permission and approval UIs" in `RECOVERY.md`, and wait for idle before
   prompting. Do not re-run `agent start` and do not give up on the role.
9. Verify after startup with `herdr agent get <resolved-name>` that its `tab_id`
   equals `$HERDR_TAB_ID` and that its kind, model, and effort match the settled
   configuration. Once both roles are live, confirm the order rather than
   assuming the splits landed as intended:

   ```bash
   herdr pane neighbor --direction down --pane <explorer-pane-id>
   ```

   It must return the fixer's pane. If it returns nothing or another pane, the
   layout is wrong — correct it with `herdr pane swap` now, while you still know
   which pane holds which role.

If the kind, model, effort, pane, shutdown, or startup cannot be confirmed after
the recovery in step 8, stop delegation for that role. Never silently fall back
to another configuration or tab. Handle the work directly when it is trivial
enough to be safe; otherwise escalate under "Escalation" in `SKILL.md`.

## Role configuration

The role configuration is scoped to the current top-level orchestrator's native
Herdr `agent_session`.

Orchestration identity is independent of role configuration. Creating, reusing,
interrupting, resuming, or clearing an `active_orchestration`, and any Harvest
availability or failure, are never reasons to ask for harness, model, or effort
again or to change a settled value.

**Invoking `agent-orchestration` again does not start a new orchestration
session and does not reset role configuration.**

Always run "Session state" before deciding whether configuration is required.

Ask the user for configuration only when:

- there is no valid persisted configuration matching the current
  `agent_session`;
- no complete configuration is already unambiguously available in the current
  conversation; or
- the user explicitly asks to change the configuration.

A new user message, another explicit request to use `agent-orchestration`, task
completion, a new task, a new unit, an agent restart, pane recreation, or
context compaction is not a reason to ask again.

When configuration is required, ask the user to select the harness, model, and
effort independently for both roles:

| Role     | Harness       | Model         | Effort        |
| -------- | ------------- | ------------- | ------------- |
| Explorer | user-selected | user-selected | user-selected |
| Fixer    | user-selected | user-selected | user-selected |

First run:

```bash
herdr integration status
```

Use the installed Herdr integrations that can be started as Herdr agent kinds as
the harness choices presented to the user.

Ask for both roles together when practical:

```text
Explorer
  Harness:
  Model:
  Effort:

Fixer
  Harness:
  Model:
  Effort:
```

Do not choose a harness, model, or effort on the user's behalf.

Once the user has selected them, persist the values immediately using "Session
state". New user requests, repeated invocations of this skill, new tasks, new
units, agent restarts, retries, pane recreation, and context compaction reload
the same configuration without asking again while the native `agent_session`
identity remains the same.

Only change a settled role configuration when the user explicitly instructs you
to do so. A missing model, provider error, quota error, startup failure, or other
availability problem does not authorize an automatic fallback.

If a selected configuration becomes unavailable, tell the user which value
cannot be used and ask them to choose a replacement. Leave the other role's
configuration unchanged.

The harness determines how model and effort are expressed on its command line.
Use that harness's installed CLI help or existing authoritative instructions to
resolve the appropriate arguments. Arguments after `--` in `herdr agent start`
are passed to the selected harness.

Do not silently omit either the selected model or effort and fall back to a
harness default.

## Explorer

```bash
herdr agent start <explorer-name> --kind <explorer-harness> --pane <pane-id> -- \
  <explorer-model-and-effort-arguments>
```

Use `explorer` as `<explorer-name>` when available.

## Fixer

```bash
herdr agent start <fixer-name> --kind <fixer-harness> --pane <pane-id> -- \
  <fixer-model-and-effort-arguments>
```

Use `fixer` as `<fixer-name>` when available.

Both delegated agents intentionally use the selected harness's normal installed
extensions, skills, and tools. Only the role-specific model and effort are set
explicitly here.

## Harvest orchestration capture

Harvest orchestration capture is optional. Harvest grouping is enrichment,
never a prerequisite for engineering orchestration, and the skill must behave
normally when Harvest is not installed, is disabled, is too old, fails
capability negotiation, has a missing or stale runtime locator, or when a
claim fails. Never ask the user to install Harvest merely because this
integration is unavailable, and never change role configuration because of it.

### Discovery

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

### Capability negotiation

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
compatible merely because it is numerically greater. If Node cannot execute the
entrypoint, or the probe fails or prints anything else, Harvest integration is
unavailable and ordinary orchestration continues.

### Runtime locator

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

### Claiming a completed delegated result

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

**Transport boundaries.** The UUID, label, and role travel only through these
CLI arguments. Never transport orchestration identity through pane metadata
tokens, `state_labels`, workspace/tab/pane inference, native session inference,
environment variables such as `HARVEST_ORCHESTRATION_ID`, prompt embedding,
terminal-output parsing, or timestamps. There is no metadata token, TTL, or
sequence number in this design; do not reintroduce one. Never claim the
long-lived top-level orchestrator pane — only `explorer` and `fixer` are
Harvest orchestration roles.

### Claim results

The command prints one JSON summary line on stdout. Outcomes:

```text
exit 0  captured | duplicate | skipped
exit 1  failed (capture or runtime failure)
exit 2  invalid arguments
exit 3  conflict
```

Top-level `status` is one of `captured`, `duplicate`, `conflict`, `skipped`, or
`failed`. An `orchestration` object of the form `{"status":"...","id":"..."}`
appears only with `captured` or `duplicate`, and its `status` is either
`claimed` or `already_claimed`.

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
Result itself is still stored. A conflict must never be repaired by changing
the UUID, changing the label, overwriting the existing claim, or retrying with
guessed metadata. Record the integration problem and continue the engineering
workflow.

### Graceful degradation

None of these may fail the delegated engineering task: `skipped`, `failed`,
malformed JSON, a missing or stale locator, a capability mismatch, a conflict,
or a process failure. Never discard an otherwise valid explorer or fixer result
because Harvest failed. If one or more claims failed or conflicted during an
objective, mention it once in the user-facing final report so the user knows
the grouping may be incomplete; do not report a Harvest problem after every
unit.
