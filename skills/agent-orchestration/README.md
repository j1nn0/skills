# agent-orchestration

A Claude Code skill for coordinating software engineering work through Herdr with three fixed roles:

| Role | Agent | Herdr kind | Model / effort |
| --- | --- | --- | --- |
| Orchestration, decisions, review | Claude Code | — | Opus 5, `thinking: high` |
| Investigation and research | OMP | `omp` | `opencode-go/deepseek-v4-flash`, `thinking: xhigh` |
| Implementation | Codex | `codex` | `gpt-5.6-luna`, `effort: max` |

The models and levels come from each CLI's own configuration (`~/.omp/agent/config.yml`,
`~/.codex/config.toml`), so agents are started by kind alone with no model override flags.

The skill requires `HERDR_ENV=1`; outside a Herdr session it falls back to single-agent work. It
intentionally contains orchestration policy only — Herdr command syntax and terminal control remain
the responsibility of the existing `herdr` skill.

## Recommended layout

When both delegated agents are active, the skill prefers Claude Code in the left 50% of the current
tab, with OMP in the upper-right 25% and Codex in the lower-right 25%. The ratio is a preference;
existing user panes and readability take precedence.
