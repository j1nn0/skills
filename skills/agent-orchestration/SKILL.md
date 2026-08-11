---
name: agent-orchestration
description: >-
  Orchestrates non-trivial software engineering work across three agents in a
  Herdr session: Claude Code stays the orchestrator and reviewer, OMP does
  investigation and research, Codex does implementation. Use for feature
  development, bug fixes, refactoring, static analysis, technical research,
  architecture exploration, or new project work whenever the investigation or
  the implementation is substantial enough to be worth a handoff. Requires
  HERDR_ENV=1 and builds on the herdr skill for pane and agent control. Do not
  use for trivial tasks or single-step questions Claude Code can answer
  directly.
---

# Agent Orchestration

You are **Claude Code** and remain the primary orchestrator for the whole task.
Orchestration, review, and the completion decision are never delegated — everything else in this
skill describes what you hand off and what you keep.

Use the `herdr` skill as the authority for pane and agent CLI syntax. This skill defines who does
what, not how to drive Herdr.

## Preconditions

Delegation only works inside a Herdr-managed pane:

```bash
test "${HERDR_ENV:-}" = 1
```

If that fails, no delegated pane is reachable. Say so, then do the task yourself as a single agent.
Do not try to reach OMP or Codex another way — running `omp` or `codex` as a foreground command
would take over your own pane and end the orchestration.

Before starting anything, check what already exists and what is installed:

```bash
herdr agent list   # reuse a live omp/codex agent instead of starting a duplicate
herdr agent        # kinds must include omp and codex
```

If a kind is missing or `agent start` fails, do not silently substitute a different kind — the role
assignment below is the point of the skill. Report the failure and either continue yourself or ask
the user.

## Roles

| Role | Agent | Herdr kind | Model / effort |
| --- | --- | --- | --- |
| Orchestration, decisions, review | Claude Code (you) | — | Opus 5, `thinking: high` |
| Investigation and research | OMP | `omp` | `opencode-go/deepseek-v4-flash`, `thinking: xhigh` |
| Implementation | Codex | `codex` | `gpt-5.6-luna`, `effort: max` |

Start delegated agents with the kind alone:

```bash
herdr agent start omp --kind omp --pane <pane-id>
herdr agent start codex --kind codex --pane <pane-id>
```

The models and levels in the table are what these CLIs already load from their own configuration
(`~/.omp/agent/config.yml`, `~/.codex/config.toml`). Passing `--model`, `--thinking`, or
`-c model_reasoning_effort` overrides only risks drifting from the user's configured setup, so
don't. If a run looks like it used the wrong model, confirm with `herdr agent get <name>` rather
than guessing.

### Claude Code — orchestration, decisions, and review

You own: understanding and planning the task; defining objectives, constraints, scope, and
completion criteria; deciding whether investigation is necessary; evaluating evidence and validating
hypotheses; determining implementation strategy and scope; reviewing the actual changes and
verification results; deciding whether more investigation or implementation is needed; and the final
completion decision.

### OMP — investigation and research

Delegate investigation and analysis to OMP when it is substantial enough to be worth the handoff:
investigating existing code; researching technologies, libraries, APIs, specifications, and
implementation approaches; identifying root causes, dependencies, constraints, and potential impact;
comparing alternatives when a technical decision needs evidence; producing hypotheses with
supporting evidence.

Investigation is not limited to existing code. For new projects, use OMP for the technical research
that improves the implementation decision.

For official documentation research involving a library, framework, SDK, API, CLI tool, or cloud
service, use the `find-docs` skill when it is available to OMP and follow its workflow. If it is
unavailable, use the primary official documentation directly.

**OMP is read-only.** OMP and Codex share one working directory and one git working tree, so two
agents writing at once can corrupt each other's work. State the read-only constraint in the prompt
you send, and keep file modification exclusively with Codex.

### Codex — implementation

Delegate implementation to Codex by default: features and fixes; new code and project structure;
refactoring; tests; documentation when needed; and a report of the resulting changes and
verification results.

## Workflow

1. Define the objective, constraints, scope, and completion criteria.
2. Split large tasks into small, reviewable units and make progress incrementally.
3. When investigation is necessary, delegate it to OMP.
4. Evaluate OMP's evidence and hypotheses yourself. Ask for more when confidence is insufficient.
5. Determine the implementation strategy, scope, constraints, and completion criteria yourself.
6. Delegate implementation to Codex.
7. Review the actual changes and verification results yourself.
8. If problems remain, decide whether more investigation or implementation is required.
9. Run the project's own verification and confirm the completion criteria before declaring the task
   complete.

Do not pass OMP's investigation straight to Codex as an implementation instruction. The evaluation
step is where a plausible-but-wrong hypothesis gets caught; skipping it just moves the error
downstream.

## Handoffs

Delegated agents share none of your conversation. Every prompt must stand alone: state the objective
and the concrete paths, commands, constraints, and criteria the agent needs, and repeat relevant
findings rather than referring to earlier discussion the agent never saw.

**To OMP**, require a concise report with: conclusion; evidence and sources; relevant code, files,
documentation, APIs, or specifications; constraints and impact; alternatives when relevant;
hypothesis and confidence when applicable. Prefer precise references over prose.

If a report is too long to read back from the pane — agents often run on the terminal's alternate
screen, where raising `--lines` recovers nothing — ask the agent to write the full report as
Markdown under the scratch directory and reply with only the path, then read the file. Use this as a
fallback after a failed read, not as the default request.

**To Codex**, communicate: objective; scope; constraints; implementation strategy; completion
criteria; relevant investigation findings. Do not over-specify implementation details unless they
are real constraints — Codex should make local decisions inside the approved strategy and scope.

## Waiting on delegated agents

`herdr agent prompt <name> --wait` settles on `idle`, `done`, or `blocked`. Investigation usually
fits a single generous timeout; implementation often runs longer than any timeout worth setting, so
when a wait times out, treat that as "still working," not as failure. Poll with `herdr agent get`
and inspect progress with `herdr agent read` before intervening. Interrupting a working
implementation and re-prompting usually costs more than waiting.

If an agent becomes `blocked`: determine why, inspect its output, then refine the instruction,
supply the missing information, or investigate further. Retry only after addressing the cause —
resending the same instruction unchanged just reproduces the block.

## Review and retry

Verify independently rather than trusting the implementer's own report. Read the diff yourself and
run the project's verification yourself; an implementation that reports success and a working tree
that is actually correct are different claims, and separating them is the reason review sits with
you.

Review for: whether the objective and completion criteria are met; consistency with the chosen
strategy; unnecessary or out-of-scope changes; unintended impact on existing behavior; verification
results; and whether a fix addresses the root cause rather than bypassing it.

If a fix leads to a different problem, that is often progress — continue.

If the *same* problem recurs, stop patching locally. Re-evaluate the failure, your assumptions, the
investigation, and the strategy yourself. When the cause is uncertain, send it back to OMP,
incorporate the new findings into an updated hypothesis, and only then delegate implementation
again. Stacked local fixes on one persistent failure tend to bury the cause rather than remove it.

If retries produce no meaningful progress, change the approach. If no safe and reasonable solution
emerges, summarize the findings and attempts and consult the user.

## Recommended Herdr layout

Keep Claude Code visually dominant — it is where decisions, review, and completion happen.

```text
┌──────────────────────────────┬──────────────────────┐
│                              │         OMP          │
│                              │   Investigation      │
│        Claude Code           │         ~25%         │
│        Orchestrator          ├──────────────────────┤
│           ~50%               │        Codex         │
│                              │   Implementation     │
│                              │         ~25%         │
└──────────────────────────────┴──────────────────────┘
```

- Claude Code holds the left half; the right half is the delegated-agent area, OMP above Codex.
- With one delegated agent, it may use the whole right half. When the second arrives, split the
  agent area — not Claude Code's pane.
- Treat 50/25/25 as a target, not a rule that justifies unreadable panes. Keep focus on Claude Code
  and preserve the caller's working directory.
- Never rearrange, resize, or close user-owned panes, and never create a workspace, tab, or worktree
  just to reach this layout, unless the user asks.

## Escalation

Ask the user instead of assuming when: requirements or completion criteria are significantly
ambiguous; a choice would substantially change behavior or architecture; destructive or irreversible
operations are required; the change substantially exceeds the requested scope; a decision could
affect security or important data; or investigation and retries cannot establish a safe approach.

Never perform destructive or irreversible operations, out-of-scope changes, or unnecessary access to
or disclosure of secrets without explicit permission.

## Delegation boundary

Multi-agent coordination pays off when investigation, implementation, or independent validation is
substantial enough to justify the handoff. Handle trivial checks yourself — invoking OMP or Codex to
satisfy the workflow on a task you could finish safely in a moment costs more than it returns.

Project rules and verification procedures from the project's `CLAUDE.md` take precedence over the
generic guidance here.
