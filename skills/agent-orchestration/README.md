# agent-orchestration

A reusable skill for coordinating non-trivial software engineering work through Herdr.

| Role | Agent |
| --- | --- |
| Orchestration, decisions, review | Orchestrator (the current agent) |
| Investigation and research | Session-configured `explorer` |
| Implementation | Session-configured `fixer` |

The orchestrator owns strategy, review, and completion. `explorer` is read-only by role; `fixer` owns
project file changes.

Before the first delegation of a native orchestrator session, the user selects the harness, model, and
effort independently for `explorer` and `fixer`. The selection is persisted under the user's XDG
state directory and keyed by Herdr's native `agent_session` identity. Reinvoking
`agent-orchestration`, sending another request, completing or starting a task, changing units, or
compacting context reloads the same configuration instead of asking again. Only an explicit user
change or a different native orchestrator session changes that behavior. Delegated agents otherwise
use their selected harness's normal installed extensions, skills, and tools. See `STARTUP.md` for
session state, configuration, and startup.

Work is routed, not piped:

```text
Explorer ↔ Orchestrator ↔ Fixer
```

The orchestrator chooses the next route at every decision point according to the current need, rather
than running a fixed explorer → fixer pipeline. Every finding, decision, and instruction passes
through it; `explorer` and `fixer` never hand work directly to each other.

The skill requires `HERDR_ENV=1`. Herdr pane and agent mechanics remain the responsibility of the
existing `herdr` skill.

## Files

| File | Contents |
| --- | --- |
| `SKILL.md` | Roles, workflow, routing, per-role boundaries and handoff formats, review and retry. |
| `STARTUP.md` | Persisted session state, pane layout, agent resolution and reuse rules, per-role harness/model/effort configuration and start commands. |
| `RECOVERY.md` | Submission failures, timeout, `blocked`, and stuck-agent handling. |
