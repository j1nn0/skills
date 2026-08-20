---
name: agent-orchestration
description: >-
  Delegates non-trivial engineering work to Pi `explorer` (investigation,
  research) and Pi `fixer` (implementation) in a Herdr session, while the
  current agent keeps strategy and review. Use when a root cause is unclear,
  code or architecture is unfamiliar, an external API, SDK, or specification
  needs research, or an implementation spans several files — even when the user
  never mentions agents, delegation, or orchestration. Requires HERDR_ENV=1.
  Handle trivial, local, low-risk work directly.
---

# Agent Orchestration

You remain the orchestrator and reviewer for the whole task.

Project-specific instructions and verification procedures take precedence over
this skill.

Core principles:

1. The orchestrator owns strategy, review, and completion, and defines the
   boundaries for delegated decisions.
2. The explorer reduces uncertainty.
3. The fixer implements a bounded strategy once it is **settled** — its evidence
   is validated and no open question would change it.
4. Explorer and fixer never hand work directly to each other. Every finding,
   decision, follow-up request, and implementation instruction passes through
   the orchestrator.
5. Return to the explorer whenever uncertainty could change the strategy.
6. Verify delegated results independently.

Use the `herdr` skill as the authority for pane and agent CLI syntax.

## Roles

| Role | Agent |
| --- | --- |
| Orchestration, decisions, review | Orchestrator (the current agent) |
| Investigation and research | Pi `explorer` |
| Implementation | Pi `fixer` |

The explorer is read-only. The fixer may intentionally modify project files
within delegated implementation work.

## Startup

Delegation requires a Herdr-managed pane:

```bash
test "${HERDR_ENV:-}" = 1
```

If that fails, do the task yourself. Do not run Pi in the orchestrator pane as a
substitute.

All delegated agents must run in the orchestrator's current tab. Treat
`$HERDR_TAB_ID` as a hard placement and reuse boundary.

Read [`STARTUP.md`](STARTUP.md) before the first delegation of a session, and
whenever a role's agent is missing, lives in another tab, has the wrong model or
thinking level, or needs a pane created. It holds the agent resolution steps, the
pinned start commands, and the pane layout.

## Workflow

1. Define the objective, constraints, scope, and completion criteria.
2. Route to investigation, implementation, or direct handling using the
   delegation boundaries below.
3. If investigation is needed, delegate to the explorer and evaluate its evidence
   and conclusions.
4. Decide the implementation strategy and scope yourself.
5. If implementation is non-trivial, delegate a bounded implementation unit to
   the fixer.
6. Review the actual diff and verification results yourself.
7. Route follow-up work according to "Review and retry".
8. Repeat from step 2, stopping at the bound in "Two attempts without progress".
9. Confirm the completion criteria yourself.

## Routing

Route each step from the current need, using the delegation boundaries below.
The orchestrator must evaluate delegated output before deciding the next route.

```text
Explorer ↔ Orchestrator ↔ Fixer
```

## Concurrency

Run the explorer and the fixer one at a time on the same task. While the fixer is
working, keep every other change to the same working tree paused.

When in doubt, serialize work through the orchestrator.

## Handoffs

Delegated agents do not share the orchestrator's conversation. A prompt that
begins a new agent session must be standalone and assign one role only.

A **unit** is one investigation question or one bounded implementation task.
Follow-up prompts within the same unit may build on that agent's immediately
preceding result, and must state the remaining question, defect, or objective.

Delegated agents do their own work and report back; they invoke
`agent-orchestration` or delegate further only when the orchestrator explicitly
instructs it.

Require every delegated response to end with one concise `<HERDR_RESULT>` block,
in the format given for that role.

## Explorer

### When to use

Use the explorer when:

- the root cause is unclear;
- multiple plausible explanations exist;
- external documentation, APIs, SDK behavior, or specifications need research;
- unfamiliar code or architecture requires investigation;
- security, compatibility, data-integrity, or operational assumptions need
  evidence.

A large implementation whose strategy is already settled goes straight to the
fixer.

### Handoff

Give the explorer:

- the objective;
- relevant paths, systems, or APIs;
- constraints;
- the specific questions to answer.

Require this result format:

```text
<HERDR_RESULT>
Conclusion:
Evidence:
Impact:
Recommendation:
Confidence: high | medium | low — <reason>
</HERDR_RESULT>
```

Evidence must cite specific code, files, APIs, or specifications. Prefer primary
official sources for external technical research.

Treat the explorer's recommendation as input, not as the implementation decision.
The orchestrator may pass validated evidence to the fixer, but must separately
state the chosen strategy and implementation boundaries.

Ask only for the missing evidence or unresolved question rather than a repeat of
already-established findings.

If confidence remains too low to proceed safely, continue focused investigation or
escalate rather than turning an uncertain conclusion into an implementation
instruction.

## Fixer

### When to use

Use the fixer when the strategy is settled and implementation is non-trivial,
including when:

- multiple files or components must change;
- independent implementation reduces implementation or review risk.

Send unresolved questions to the explorer first.

### Handoff

Give the fixer:

- the objective;
- bounded implementation scope;
- constraints;
- the chosen strategy;
- completion criteria;
- relevant validated evidence.

Let the fixer make local implementation decisions inside those boundaries.

Require this result format:

```text
<HERDR_RESULT>
Changes:
Verification:
- <command>: <result>
Remaining issues:
</HERDR_RESULT>
```

If the fixer encounters unresolved uncertainty, it must report that uncertainty
to the orchestrator rather than resolving it by guesswork.

## Direct handling

Handle work directly when it is trivial, local, low-risk, and delegation would
add more overhead than value.

## Delegation mechanics

### Minimal example

One pass through a delegated cycle looks like this:

```bash
# investigate
herdr agent prompt <explorer-name> '<standalone investigation prompt>' --wait
herdr agent read <explorer-name>
```

Evaluate the evidence, decide the strategy yourself, then:

```bash
# implement
herdr agent prompt <fixer-name> '<standalone implementation prompt>' --wait
herdr agent read <fixer-name>
```

Then review the result yourself before deciding the next route.

### Session reuse

Keep an agent's session for the whole unit: remaining questions, missing
evidence, a review correction, a test failure caused by the current
implementation, and completion of an unfinished part all belong to it. Repeated
corrections stay in the same unit.

Send `/new` and wait for it to settle when the next prompt opens a different
unit — a materially different problem, a strategy that has been abandoned, or
work that prior context would bias.

### Reading results

Use only the last complete `<HERDR_RESULT>` block emitted in response to the
current prompt.

Ignore:

- preceding thinking or progress output;
- blocks merely echoed from the prompt or quoted as examples;
- result blocks from earlier prompts or sessions.

If the current prompt produced no complete result block, ask the agent to
re-emit only its final result without repeating the work.

## Waiting

`herdr agent prompt --wait` settling on `idle`, `done`, or `blocked` is
authoritative when the integration is healthy.

Read [`RECOVERY.md`](RECOVERY.md) when a prompt times out, an agent settles on
`blocked`, or an agent appears stuck. It holds the inspection order, when
interrupting is justified, and the routes out.

## Review and retry

Treat the fixer's report as a claim. Read the actual diff and run the project's
own appropriate verification.

Review for:

- completion criteria;
- consistency with the chosen strategy;
- out-of-scope or unnecessary changes;
- unintended behavior changes;
- verification results;
- whether the change addresses the root cause.

Route follow-up work according to the failure:

### Clear implementation defect

Return the bounded correction to the current fixer session when it belongs to the
same implementation unit.

### Uncertain cause or assumption

Return to the explorer for focused investigation before deciding another
implementation step.

### Flawed strategy

Re-evaluate the evidence and strategy yourself before asking the fixer to make
further changes.

### Two attempts without progress

An attempt makes progress when it changes the observed failure or resolves one of
the review findings above. After two consecutive attempts on the same issue make
none, change approach: re-evaluate the evidence and strategy, use the explorer
if uncertainty remains, and escalate to the user when no materially different
safe approach is available.

## Escalation

Consult the user when:

- requirements are materially ambiguous;
- a decision would substantially change behavior or architecture;
- destructive or irreversible work is required;
- scope would expand substantially;
- security or important data may be affected;
- investigation cannot establish a safe approach;
- delegation is needed but a required role cannot be configured.

Never perform destructive or irreversible operations, out-of-scope changes, or
unnecessary access to secrets without explicit permission.

## Completion lifecycle

On normal completion:

- leave correctly configured delegated agents running for reuse;
- leave panes intact, including user-owned panes.

Stop an agent only when:

- its configuration must be replaced;
- it is unhealthy or unusable;
- the user explicitly asks for cleanup.
