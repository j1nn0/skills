# agent-orchestration

A reusable skill for coordinating non-trivial software engineering work through Herdr.

| Role                             | Agent                            |
| -------------------------------- | -------------------------------- |
| Orchestration, decisions, review | Orchestrator (the current agent) |
| Investigation and research       | Session-configured `explorer`    |
| Implementation                   | Session-configured `fixer`       |

The orchestrator owns strategy, review, and completion. `explorer` is read-only by role; `fixer` owns
project file changes.

Before the first delegation of the current top-level orchestrator conversation, the user selects the
harness, model, and effort independently for `explorer` and `fixer`. Those choices remain in effect
for the rest of that conversation unless the user explicitly changes them. Invoking
`agent-orchestration` again, sending another request, completing a task, or starting a new task does
not reset the configuration. Delegated agents otherwise use their selected harness's normal installed
extensions, skills, and tools. See `STARTUP.md` for configuration and startup.

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

| File          | Contents                                                                                                       |
| ------------- | -------------------------------------------------------------------------------------------------------------- |
| `SKILL.md`    | Roles, workflow, routing, per-role boundaries and handoff formats, review and retry.                           |
| `STARTUP.md`  | Pane layout, agent resolution and reuse rules, per-role harness/model/effort configuration and start commands. |
| `RECOVERY.md` | Submission failures, timeout, `blocked`, and stuck-agent handling.                                             |
