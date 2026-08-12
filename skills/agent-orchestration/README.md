# agent-orchestration

A reusable agent skill for coordinating software engineering work through Herdr with three fixed roles:

| Role | Agent | Herdr kind | Model / effort |
| --- | --- | --- | --- |
| Orchestration, decisions, review | Current agent | — | Current model |
| Investigation and research | OMP | `omp` | `opencode-go/deepseek-v4-flash`, `thinking: xhigh` |
| Implementation | Codex | `codex` | `gpt-5.6-luna`, `effort: max` |

The skill pins the delegated agents' model and reasoning level explicitly through `herdr agent start`
instead of relying on the user's global OMP or Codex defaults.

```bash
herdr agent start omp --kind omp --pane <pane-id> -- \
  --model opencode-go/deepseek-v4-flash \
  --thinking xhigh

herdr agent start codex --kind codex --pane <pane-id> -- \
  --model gpt-5.6-luna \
  -c model_reasoning_effort=max
```

The skill requires `HERDR_ENV=1`; outside a Herdr session it falls back to single-agent work. It
intentionally contains orchestration policy only — Herdr command syntax and terminal control remain
the responsibility of the existing `herdr` skill.

## Recommended layout

When both delegated agents are active, the skill prefers the current orchestrator in the left 50% of the current
tab, with OMP in the upper-right 25% and Codex in the lower-right 25%. The ratio is a preference;
existing user panes and readability take precedence.
