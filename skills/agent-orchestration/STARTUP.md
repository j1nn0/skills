# Startup

Agent and pane resolution for `agent-orchestration`. Read this before the first
delegation of a session, and whenever a role's agent is missing, lives in another
tab, has the wrong model or thinking level, or needs a pane created.

## Recommended layout

Prefer this layout when creating panes for delegated agents:

```text
┌──────────────────────────────┬──────────────────────┐
│                              │       Explorer       │
│                              │                      │
│       Orchestrator           ├──────────────────────┤
│                              │        Fixer         │
│                              │                      │
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
   - its model matches;
   - its thinking level matches.
3. Never reuse, stop, replace, or repurpose an agent from another tab.
4. If the preferred name belongs to an agent in another tab, choose a unique name
   for the same-tab agent and use that resolved name thereafter.
5. If a same-tab agent has the wrong configuration:
   - send `/quit`;
   - wait until it disappears from `herdr agent list`;
   - confirm its pane has returned to an available interactive shell with
     `herdr pane process-info --pane <id>`.
6. Use only an idle same-tab pane with no foreground agent, editor, or command.
7. If no suitable pane exists, split a pane in `$HERDR_TAB_ID`, normally the
   orchestrator pane, and use the resulting pane id in the start command:

   ```bash
   herdr pane split --current --direction right --cwd "$PWD" --no-focus
   ```

8. Start the role with its pinned configuration.
9. Verify after startup with `herdr agent get <resolved-name>` that its `tab_id`
   equals `$HERDR_TAB_ID`.

If the required kind, model, thinking level, pane, shutdown, or startup cannot be
confirmed, stop delegation for that role. Never silently fall back to another
model, configuration, or tab. Handle the work directly when it is trivial enough
to be safe; otherwise escalate under "Escalation" in `SKILL.md`.

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
and tools. The skill pins only the role-specific model and thinking level.
