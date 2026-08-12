# agent-orchestration

A reusable skill for coordinating non-trivial software engineering work through Herdr.

| Role | Agent | Model / effort |
| --- | --- | --- |
| Orchestration, decisions, review | Current agent | Current model |
| Investigation and research | Pi `explorer` | `opencode-go/deepseek-v4-flash`, `thinking: max` |
| Implementation | Pi `fixer` | `openai-codex/gpt-5.6-luna`, `thinking: max` |

The current agent owns strategy, review, and completion. `explorer` is read-only; `fixer` owns project
file changes. Both delegated agents use pinned Pi models and explicit extension profiles rather than
global Pi defaults.

The workflow is:

```text
explorer investigation
        ↓
orchestrator evaluation / strategy
        ↓
fixer implementation
        ↓
orchestrator review / verification
```

The skill requires `HERDR_ENV=1`. Herdr pane and agent mechanics remain the responsibility of the
existing `herdr` skill.

## Recommended layout

```text
┌──────────────────────────────┬──────────────────────┐
│                              │       Explorer       │
│      Current agent           ├──────────────────────┤
│        ~50%                  │        Fixer         │
└──────────────────────────────┴──────────────────────┘
```

See `SKILL.md` for the pinned startup commands, handoff rules, recovery behavior, and delegation
boundary.