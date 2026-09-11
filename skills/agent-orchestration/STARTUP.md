# Startup

Agent and pane resolution for `agent-orchestration`. Read this before the first
delegation of a session, and whenever a role's agent is missing, lives in another
tab, has the wrong harness, model, or effort, or needs a pane created.

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

Before using any delegated role, first settle the configuration under
"Role configuration" if it has not already been settled for the current
orchestrator session.

Before using a delegated role:

1. Run `herdr agent list` to see the live agents and the tab each one is in.
2. Reuse a live agent only when:
   - its `tab_id` equals `$HERDR_TAB_ID`;
   - its kind matches the harness settled for that role;
   - its model and effort match the configuration settled for that role in this
     session.
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

Before the first delegation of an orchestrator session, ask the user to select
the harness, model, and effort independently for both roles:

| Role     | Harness | Model | Effort |
| -------- | ------- | ----- | ------ |
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

Once the user has selected them, treat those values as that role's configuration
for the rest of the current orchestrator session. New units, agent restarts,
retries, and pane recreation reuse the same configuration without asking again.

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
