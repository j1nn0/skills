# Startup

Agent and pane resolution for `agent-orchestration`. Read this before the first
delegation of a session, and whenever a role's agent is missing, lives in another
tab, has the wrong model or thinking level, or needs a pane created.

## Recommended layout

Prefer this layout when creating panes for delegated agents:

```text
┌──────────────────────────────┬──────────────────────┐
│                              │       Explorer       │
│                              │         ~25%         │
│      Current agent           ├──────────────────────┤
│        Orchestrator          │        Fixer         │
│           ~50%               │         ~25%         │
└──────────────────────────────┴──────────────────────┘
```

Keep the orchestrator on the left, with the explorer above the fixer on the
right. Preserve existing user-owned panes when applying this layout.

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
6. Use only an idle same-tab pane with no foreground agent, editor, or command.
7. If no suitable pane exists, split a pane in `$HERDR_TAB_ID` and take the new
   pane id from `.result.pane.pane_id`. Which pane you split, and in which
   direction, depends on the role being placed:

   ```bash
   # explorer: take the right half of the orchestrator pane
   herdr pane split --current --direction right --ratio 0.5 --cwd "$PWD" --no-focus

   # fixer: split the explorer's pane downward, not the orchestrator again
   herdr pane split <explorer-pane-id> --direction down --ratio 0.5 --cwd "$PWD" --no-focus
   ```

   Splitting the orchestrator pane to the right twice produces three narrow
   columns instead of the layout above, and a column too narrow to render an
   agent's UI is also a column whose output you cannot read. When the tab already
   holds user panes, check the geometry first with
   `herdr pane layout --pane "$HERDR_PANE_ID"` and place the split so no pane
   becomes unusable.

8. Start the role with the configuration settled for it. `agent start` returning
   `agent_not_ready` is not a failed start: the agent was detected but is
   blocked at a startup prompt, and its name stays usable for `herdr agent read`
   and `herdr agent send-keys`. Inspect it, resolve the block under
   "Permission and approval UIs" in `RECOVERY.md`, and wait for idle before
   prompting. Do not re-run `agent start` and do not give up on the role.
9. Verify after startup with `herdr agent get <resolved-name>` that its `tab_id`
   equals `$HERDR_TAB_ID`.

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
