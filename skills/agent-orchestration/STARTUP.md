# Startup

Agent and pane resolution for `agent-orchestration`. Read this before the first
delegation of a session, and whenever a role's agent is missing, lives in another
tab, has the wrong model or thinking level, or needs a pane created.

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

Before using a delegated role:

1. Run `herdr agent list` to see the live agents and the tab each one is in.
2. Reuse a live agent only when:
   - its `tab_id` equals `$HERDR_TAB_ID`;
   - its kind matches;
   - its model and thinking level match the configuration settled for that role
     in this session — the default below, or the substitute the user approved.
3. Never reuse, stop, replace, or repurpose an agent from another tab.
4. If the preferred name belongs to an agent in another tab, choose a unique name
   for the same-tab agent and use that resolved name thereafter.
5. If a same-tab agent has the wrong configuration:
   - send `herdr agent prompt <name> '/quit'` without `--wait`, since the agent
     ends rather than settling into a state to wait for;
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

   **The column already holds the other role** — split *that* pane downward,
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
   equals `$HERDR_TAB_ID`. Once both roles are live, confirm the order rather
   than assuming the splits landed as intended:

   ```bash
   herdr pane neighbor --direction down --pane <explorer-pane-id>
   ```

   It must return the fixer's pane. If it returns nothing or another pane, the
   layout is wrong — correct it with `herdr pane swap` now, while you still know
   which pane holds which role.

If the kind, thinking level, pane, shutdown, or startup cannot be confirmed after
the recovery in step 8, stop delegation for that role. Never silently fall back
to another configuration or tab. Handle the work directly when it is trivial
enough to be safe; otherwise escalate under "Escalation" in `SKILL.md`.

## Role configuration

| Role | Model | Thinking |
| --- | --- | --- |
| Explorer | `opencode-go/deepseek-v4-flash` | `max` |
| Fixer | `openai-codex/gpt-5.6-luna` | `max` |

These are defaults chosen for the shape of each role — a fast high-reasoning
model for investigation, a strong coding model for implementation — not
requirements. A model only exists where its provider is configured, so this skill
travels to installs that have neither.

When a role's default model is unavailable, do not stop and do not pick a
replacement on your own. Tell the user which model is missing and what the role
needs, ask which model to use instead, and treat their answer as that role's
configuration for the rest of the session. The property worth protecting is that
the choice is deliberate and visible: a role quietly downgraded to whatever
happened to be available produces delegated work whose quality you have no basis
to trust, and the failure surfaces much later as a bad diff you accepted.

The start commands below use the defaults. Substitute the approved model in
`--model` when one was chosen.

## Explorer

```bash
herdr agent start <explorer-name> --kind pi --pane <pane-id> -- \
  --model opencode-go/deepseek-v4-flash \
  --thinking max \
  --no-autoformat \
  --no-autofix
```

Use `explorer` as `<explorer-name>` when available.

## Fixer

```bash
herdr agent start <fixer-name> --kind pi --pane <pane-id> -- \
  --model openai-codex/gpt-5.6-luna \
  --thinking max \
  --no-autoformat \
  --no-autofix
```

Use `fixer` as `<fixer-name>` when available.

Both delegated agents intentionally use Pi's normal installed extensions, skills,
and tools. Only the role-specific model and thinking level are set here.
