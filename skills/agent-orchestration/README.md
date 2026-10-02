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
use their selected harness's normal installed extensions, skills, and tools. See `references/STARTUP.md` for
session state, configuration, pane layout, and agent startup.

The skill also records an optional orchestration grouping identity, scoped to one coherent top-level
engineering objective rather than to the native session. It spans the `explorer` and `fixer` work,
every bounded unit, review and fix retries, interruption and resume, and context compaction, and it
is cleared when the objective completes. It is independent of the role configuration and never
causes the harness, model, or effort question to be asked again.

The grouping is delivered by an optional Harvest Herdr plugin and is detected by capability
negotiation rather than by a version number. When Harvest is absent, disabled, incompatible, or
failing, the skill delegates exactly as it otherwise would. Harvest identity, runtime discovery,
claim ordering, and graceful degradation live in `references/HARVEST.md`.

The optional Completion Gate in `references/JEV.md` uses Jev only after diff review and
deterministic project verification, to recommend completion or a bounded follow-up
action. It cannot override deterministic failures, policy, or orchestrator review;
when disabled or unavailable, the existing workflow remains unchanged.

Work is routed, not piped:

```text
Explorer ↔ Orchestrator ↔ Fixer
```

The orchestrator chooses the next route at every decision point according to the current need, rather
than running a fixed explorer → fixer pipeline. Every finding, decision, and instruction passes
through it; `explorer` and `fixer` never hand work directly to each other.

The skill requires `HERDR_ENV=1`. Herdr pane and agent mechanics remain the responsibility of the
existing `herdr` skill.

For session-state policy and reuse rules, see [`references/STARTUP.md`](references/STARTUP.md).
From the repository root, inspect the session or persist a confirmed role selection (`H`, `M`,
and `E` stand for the selected values):

```sh
skills/agent-orchestration/scripts/sessionctl inspect
skills/agent-orchestration/scripts/sessionctl set-role --role explorer --harness H --model M --effort E
```

## Files

| File | Contents |
| --- | --- |
| `SKILL.md` | Roles, workflow, routing, unit sizing, per-role boundaries and handoff formats, delegation mechanics, review and retry. |
| `README.md` | Skill overview and file layout. |
| `references/STARTUP.md` | Persisted session state, pane layout, agent resolution and reuse rules, and per-role harness/model/effort configuration and start commands. |
| `references/HARVEST.md` | Optional Harvest orchestration identity, objective lifecycle, capability negotiation, runtime locator validation, claim protocol, and graceful degradation. |
| `references/RECOVERY.md` | Submission failures, timeout, `blocked`, and stuck-agent handling. |
| `references/PARALLEL.md` | Policy for bounded, read-only parallel Explorer batches, admission, result collection, and orchestrator convergence. |
| `scripts/parallel_validate` | Pipe one JSON object on stdin, for example `printf '%s\n' "$json" | scripts/parallel_validate`; `mode` is `admission` or `convergence` (payloads in `references/PARALLEL.md`). |
| `scripts/sessionctl` | Stdlib-only session-state inspector and role/orchestration persistence CLI; see `references/STARTUP.md` for policy. |
| `references/JEV.md` | Completion Gate policy, with the multi-gate overview and Explorer Gate pointer. |
| `references/EXPLORER_GATE.md` | Optional post-Explorer evidence-sufficiency policy, thresholds, conservative action rules, and integration. |
| `scripts/jevctl` | Stdlib-only CLI for `doctor`, `completion-gate`, and `explorer-gate`; `doctor` makes no model request. |
