# Startup

Session state, agent and pane resolution, and per-role configuration for
`agent-orchestration`. Read this before the first delegation of every invocation
of this skill, and whenever a role's agent is missing, lives in another tab, has
the wrong harness, model, or effort, or needs a pane created.

## Session state

The persisted session state is the authority for whether role configuration has already been settled; do not rely only on conversational memory. At the start of every invocation, before asking about harnesses, models, or effort, run:

```bash
skills/agent-orchestration/scripts/sessionctl inspect
```

`sessionctl` resolves the identity from Herdr's native `agent_session` (`source`, `kind`, `value`). The nested `agent` label is not part of that identity. The tool owns the lookup and exact identity comparison; do not reimplement these mechanics or edit the state file by hand.

Role configuration is scoped to the current top-level orchestrator's native Herdr `agent_session`, not to one invocation, one user request, one task, one delegation, or one unit. Re-invoking `agent-orchestration`, receiving a new request, completing or starting a task, starting a new unit, restarting an agent, recreating a pane, or compacting context reloads the persisted configuration instead of starting a new configuration session.

Apply this decision contract:

- If `session_available` is false (including when `agent_session` is absent), never substitute `$HERDR_PANE_ID`, `$HERDR_TAB_ID`, or `$HERDR_WORKSPACE_ID`, and do not persist new state until Herdr exposes a native `agent_session`. Reuse a complete role configuration only when it is unambiguous in the current conversation; otherwise ask the user.
- If `identity_matched` and `configuration_complete` are both true, load those role values and do not ask again.
- Otherwise, when `session_available` is true and a complete configuration is unambiguously available in the current conversation, persist it immediately and continue without asking. This covers sessions configured before persisted state support.
- Otherwise, follow "Role configuration", ask once, and persist the settled values immediately.

Never reuse role values from persisted state unless `identity_matched` is true.

`inspect` is side-effect free: it does not create the state directory, upgrade the schema, or write. Mutations create state only when no file exists and update only when identity matches; mismatches and unreadable whole-state files refuse with `ok: false`, `changed: false`, leaving the file and directory untouched.

Persist each settled role with its own `sessionctl set-role` call, for example `skills/agent-orchestration/scripts/sessionctl set-role --role explorer --harness H --model M --effort E`. When the user explicitly changes one role's harness, model, or effort, update that role immediately and leave the other role unchanged.

Never store provider credentials, tokens, secrets, prompts, investigation results, or implementation details. Do not delete the session-state file when a task or unit completes; a new native orchestrator conversation has its own session identity.

### State file versions

State files with `schema_version` 1 or 2 are valid. Reuse a complete identity-matched configuration from either without asking. Read-only commands never rewrite the file; mutations write schema version 2. Unrecognized top-level fields from older versions are ignored and are not carried forward by the next mutation. Do not migrate or edit the file by hand.

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

Treat that two-role layout as an invariant to satisfy from the current layout, not a fixed sequence of splits to replay: roles may arrive in either order, and settled implementation goes straight to the fixer. Stable positions let anyone read the role from its position instead of checking which model is printed in each pane; three columns or Explorer under Fixer breaks that. Preserve existing user-owned panes.

### Parallel Explorer batches

For an admitted two- or three-Explorer batch in [`PARALLEL.md`](PARALLEL.md), use distinct names such as `explorer`, `explorer-2`, and `explorer-3`. Before each prompt, use `herdr agent get` to independently confirm that target is idle, in the current tab, and matches the settled Explorer harness, model, and effort. Additional Explorer panes may stack in the delegated area as space permits; the fixed-ratio pane examples below are for ordinary two-role placement only, not batch geometry. Never repurpose a Fixer agent or pane, use a cross-tab agent, or disturb user-owned panes.

## Resolution

Before using any delegated role, run "Session state" first. If it loads a valid matching persisted configuration, use that configuration exactly and do not ask the user again.

Before using a delegated role:

1. Run `herdr agent list` to see the live agents and the tab each one is in.
2. Reuse a live agent only when its `tab_id` equals `$HERDR_TAB_ID`, its kind matches the harness settled for that role, and its model and effort match the configuration settled for that role.
3. Never reuse, stop, replace, or repurpose an agent from another tab.
4. If the preferred name belongs to a cross-tab agent, choose a unique same-tab name and use it thereafter.
5. If a same-tab agent has the wrong configuration:
   - stop it using the selected harness's normal exit mechanism; do not assume one harness's exit command is valid for another;
   - wait until it disappears from `herdr agent list`;
   - confirm its pane has returned to an available interactive shell with `herdr pane process-info --pane <id>`.
6. Use only an idle same-tab pane with no foreground agent, editor, or command; prefer one already in the delegated column. An idle pane elsewhere in the tab is usually the user's.
7. If no suitable pane exists, create one from the current delegated-column layout. Take the new pane id from `.result.pane.pane_id`.

   **The delegated column does not exist** — split the orchestrator once to the right:

   ```bash
   herdr pane split --current --direction right --ratio 0.5 --cwd "$PWD" --no-focus
   ```

   **The delegated column already contains an agent** — split that pane downward, never the orchestrator a second time:

   ```bash
   herdr pane split <occupied-column-pane-id> --direction down --ratio 0.5 --cwd "$PWD" --no-focus
   ```

   In the ordinary two-role layout the new pane is the lower one (the fixer position). If the role being placed is the explorer because the fixer got there first, start the explorer in the new pane and exchange the two so the explorer ends up on top:

   ```bash
   herdr pane swap --source-pane <new-pane-id> --target-pane <fixer-pane-id>
   ```

   When the tab already holds user panes, check the geometry first with `herdr pane layout --pane "$HERDR_PANE_ID"` and place the split so no pane becomes unusable.
8. Start the role with the configuration settled for it. `agent start` returning `agent_not_ready` is not a failed start: the agent was detected but is blocked at a startup prompt, and its name stays usable for `herdr agent read` and `herdr agent send-keys`. Inspect and unblock it through the permission path ("Permission and approval UIs" in `RECOVERY.md`), and wait for idle before prompting. Do not re-run `agent start` and do not give up on the role.
9. Verify after startup with `herdr agent get <resolved-name>` that its `tab_id` equals `$HERDR_TAB_ID` and that kind, model, and effort match the settled configuration. For the ordinary two-role layout, once both roles are live, confirm the order with:

   ```bash
   herdr pane neighbor --direction down --pane <explorer-pane-id>
   ```

   It must return the Fixer's pane. A parallel batch validates each Explorer individually with `herdr agent get`, not through one Explorer/Fixer neighbor pair.

If kind, model, effort, pane, shutdown, or startup cannot be confirmed after the recovery in step 8, stop delegation for that role. Never silently fall back to another configuration or tab. Handle the work directly when it is trivial enough to be safe; otherwise escalate under "Escalation" in `SKILL.md`.

## Role configuration

When configuration is required, first run:

```bash
herdr integration status
```

Offer the installed Herdr integrations that can be started as Herdr agent kinds as harness choices. Ask the user to select the harness, model, and effort independently for both roles; ask for both roles together when practical:

| Role     | Harness       | Model         | Effort        |
| -------- | ------------- | ------------- | ------------- |
| Explorer | user-selected | user-selected | user-selected |
| Fixer    | user-selected | user-selected | user-selected |

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

Do not choose a harness, model, or effort on the user's behalf. Persist the settled values immediately using "Session state".

Only change a settled role configuration when the user explicitly instructs you to. A missing model, provider error, quota error, startup failure, or other availability problem does not authorize an automatic fallback. If a selected configuration becomes unavailable, tell the user which value cannot be used and ask them to choose a replacement, leaving the other role's configuration unchanged.

The harness determines how model and effort are expressed on its command line. Use that harness's installed CLI help or existing authoritative instructions to resolve the appropriate arguments. Arguments after `--` in `herdr agent start` are passed to the selected harness. Do not silently omit either the selected model or effort and fall back to a harness default.

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
