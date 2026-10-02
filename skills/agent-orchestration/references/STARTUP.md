# Startup

Session state, agent and pane resolution, and per-role configuration for
`agent-orchestration`. Read this before the first delegation of every invocation
of this skill, and whenever a role's agent is missing, lives in another tab, has
the wrong harness, model, or effort, or needs a pane created.

Harvest orchestration identity and capture are intentionally separated into
[`HARVEST.md`](HARVEST.md).

## Session state

The persisted session state is the authority for whether role configuration has
already been settled. Do not rely only on conversational memory.

At the start of every invocation, before asking about harnesses, models, or
effort, run the read-only inspection:

```bash
skills/agent-orchestration/scripts/sessionctl inspect
```

`sessionctl` resolves the current top-level orchestrator identity from Herdr's
native `agent_session` (`source`, `kind`, and `value`). The nested `agent` label
is not part of that identity. The tool owns the lookup and exact identity
comparison; do not reimplement these mechanics or edit the state file by hand.

Interpret the compact JSON result:

- `session_available`: a native session identity was available.
- `state_available`: the session-state file exists; it may still be unreadable
  or belong to a different identity.
- `identity_matched`: the persisted identity exactly matches this session.
  Never reuse role values unless this is true.
- `configuration_complete`: both roles have non-empty `harness`, `model`, and
  `effort`.
- `schema_version`: `1`, `2`, or `null` (no readable state); version `1` is valid.
- `active_orchestration`: the stored objective identity, or `null`.
- `active_orchestration_status`: `absent`, `valid`, or `malformed`. A malformed
  active value is reported as `null` and does not invalidate complete matching
  role settings.
- `ok` and `reason`: whether the read verdict succeeded. A refusal does not
  write or repair state.

`inspect` and `sessionctl orchestration get` are side-effect free: they do not
create the state directory, upgrade the schema, repair malformed values, or
write. Do not use a state file unless `identity_matched` is true.

If `session_available` is false (including when `agent_session` is absent), do
not substitute `$HERDR_PANE_ID`, `$HERDR_TAB_ID`, or `$HERDR_WORKSPACE_ID`.
Reuse a complete role configuration only when it is unambiguous in the current
conversation. Otherwise ask the user. Do not persist new state until Herdr
exposes a native `agent_session`.

When `identity_matched` and `configuration_complete` are both true, load those
role values and do not ask again. Otherwise, when `session_available` is true
and a complete configuration is unambiguously available in the current
conversation, persist it immediately and continue without asking. This covers
sessions configured before persisted state support.

If neither a complete matching state nor unambiguous carryover is available,
follow "Role configuration", ask once, and persist the settled values
immediately.

Persist each settled role with its own `sessionctl set-role` call, for example
`skills/agent-orchestration/scripts/sessionctl set-role --role explorer --harness H --model M --effort E`.
When the user explicitly changes one role's harness, model, or effort, update
that role immediately and leave the other role unchanged.

`sessionctl` reads and writes this shape:

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

`active_orchestration` is either `null` or the object defined in
[`HARVEST.md`](HARVEST.md). Its lifecycle is independent of role configuration.
Use `sessionctl orchestration get`, `set`, `interrupt`, `resume`, and `clear` to
read or change this stored field; lifecycle decisions belong to
[`HARVEST.md`](HARVEST.md). `sessionctl` owns atomic writes and user-only file
permissions; a refused operation leaves state unchanged.

Never store provider credentials, tokens, secrets, prompts, investigation
results, implementation details, or Harvest runtime values: plugin root, plugin
configuration directory, Harvest state directory, socket path, capability
output, agent reports, findings, or Result text. Rediscover runtime values each
time they are needed. Do not delete the session-state file when a task or unit
completes; a new native orchestrator conversation has its own session identity.

### Schema version 1 compatibility

A state file with `"schema_version": 1` and no `active_orchestration` field is a
fully valid role configuration. If its identity matches and configuration is
complete, reuse it; never ask again only because it is version 1 or lacks the
orchestration field. The read-only commands do not upgrade it. On the next
successful state mutation, `sessionctl` bundles the version-2 upgrade and
`"active_orchestration": null` with the requested change in one atomic write,
preserving the values of `orchestrator_session`, `explorer`, and `fixer`. Do not
run a separate migration or edit the file by hand.

If `active_orchestration` is malformed, inspection reports its status as
`malformed` and its value as `null`; the role configuration remains usable when
complete and identity-matched. The next successful state write repairs only
that field to `null` in the same atomic write as the requested change. The
conforming object and lifecycle are defined in [`HARVEST.md`](HARVEST.md).


## Pane layout

For ordinary two-role delegation, delegated agents share one right-hand column, Explorer above Fixer:

```text
┌──────────────────────────────┬──────────────────────┐
│                              │       Explorer       │
│                              │         ~25%         │
│      Current agent           ├──────────────────────┤
│        Orchestrator          │        Fixer         │
│           ~50%               │         ~25%         │
└──────────────────────────────┴──────────────────────┘
```

For that two-role layout, treat "one column, Explorer on top" as an invariant to satisfy, not a sequence of
splits to replay. The roles are not always created in the same order — a settled
implementation goes straight to the fixer, so the fixer often exists before any
explorer does — and placement has to reach the same layout whichever role arrived
first.

In the two-role layout, stable position is the point. Anyone glancing at the screen, you or the user,
should read the role off the position alone instead of checking which model is
printed in which pane. Three columns, or an Explorer sitting under a Fixer, costs
that on every look in this two-role layout.

Preserve existing user-owned panes when applying this layout.

### Parallel Explorer batches

For an admitted two- or three-Explorer batch in [`PARALLEL.md`](PARALLEL.md),
use distinct names such as `explorer`, `explorer-2`, and `explorer-3`. Before
each prompt, use `herdr agent get` to independently confirm that target is idle,
in the current tab, and matches the settled Explorer harness, model, and effort.
Additional Explorer panes may stack in the delegated area as space permits; the
fixed-ratio pane examples below are for ordinary two-role placement only, not
batch geometry. Never repurpose a Fixer agent or pane, use a cross-tab agent, or
disturb user-owned panes.

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

   **The column does not exist yet** — create the delegated column by splitting the
   orchestrator once, to the right. The first agent occupies it until additional
   agents are placed:

   ```bash
   herdr pane split --current --direction right --ratio 0.5 --cwd "$PWD" --no-focus
   ```

   **The delegated column already contains an agent** — split that pane downward,
   never the orchestrator a second time:

   ```bash
   herdr pane split <occupied-column-pane-id> --direction down --ratio 0.5 --cwd "$PWD" --no-focus
   ```

   For the ordinary two-role layout, the new pane is the lower one, where the fixer belongs. When the role
   you are placing is the explorer — the fixer got here first — start it in the
   new pane, then exchange the two so the explorer ends up on top:

   ```bash
   herdr pane swap --source-pane <new-pane-id> --target-pane <fixer-pane-id>
   ```

   In the two-role layout, splitting the orchestrator to the right a second time is what puts the
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
   configuration. For the ordinary two-role layout, once both roles are live, confirm the order rather than assuming the splits landed as intended:

   ```bash
   herdr pane neighbor --direction down --pane <explorer-pane-id>
   ```

   It must return the Fixer's pane. This neighbor check applies only to the ordinary
   two-role layout; a parallel batch validates each Explorer individually with
   `herdr agent get` (see "Parallel Explorer batches" above), not through one
   Explorer/Fixer neighbor pair.

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
again or to change a settled value. See [`HARVEST.md`](HARVEST.md) for that
lifecycle.

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
