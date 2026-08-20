# agent-orchestration

A reusable skill for coordinating non-trivial software engineering work through Herdr.

| Role | Agent |
| --- | --- |
| Orchestration, decisions, review | Orchestrator (the current agent) |
| Investigation and research | Pi `explorer` |
| Implementation | Pi `fixer` |

The orchestrator owns strategy, review, and completion. `explorer` is read-only by role; `fixer` owns
project file changes. Both delegated agents use their normal installed Pi extensions, skills, and tools,
with only the role-specific model and thinking level set — see `STARTUP.md` for the defaults and how
to substitute a model that an install does not have.

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
| `STARTUP.md` | Pane layout, agent resolution and reuse rules, per-role model configuration and start commands. |
| `RECOVERY.md` | Timeout, `blocked`, and stuck-agent handling. |