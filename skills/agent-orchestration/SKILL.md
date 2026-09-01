---
name: agent-orchestration
description: >-
  Delegates non-trivial engineering work to Pi `explorer` (investigation,
  research) and Pi `fixer` (implementation) in a Herdr session, while the
  current top-level agent keeps strategy and review. Use when a root cause is
  unclear, code or architecture is unfamiliar, an external API, SDK, or
  specification needs research, or an implementation spans several files —
  even when the user never mentions agents, delegation, or orchestration.
  Do not use when the current agent was itself delegated work as an `explorer`
  or `fixer`. Requires HERDR_ENV=1. Handle trivial, local, low-risk work
  directly.
---

# Agent Orchestration

You remain the orchestrator and reviewer for the whole task.

Project-specific instructions and verification procedures take precedence over
this skill.

Work is routed, not piped:

```text
Explorer ↔ Orchestrator ↔ Fixer
```

The explorer and the fixer never hand work to each other. Every finding,
decision, follow-up request, and implementation instruction passes through you,
and you evaluate delegated output before choosing the next route.

Use the `herdr` skill as the authority for pane and agent CLI syntax.

## Roles

| Role                             | Agent                            |
| -------------------------------- | -------------------------------- |
| Orchestration, decisions, review | Orchestrator (the current agent) |
| Investigation and research       | Pi `explorer`                    |
| Implementation                   | Pi `fixer`                       |

The explorer is read-only and the fixer may intentionally modify project files
within delegated implementation work. Neither agent can read this skill or your
conversation, so each role boundary only exists if the handoff prompt states it.

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
per-role model configuration and start commands, and the pane layout.

## Workflow

1. Define the objective, constraints, scope, and completion criteria.
2. Route to investigation, implementation, or direct handling using the
   delegation boundaries below. Handle work yourself when it is trivial, local,
   and low-risk enough that delegation would cost more than it returns.
3. If investigation is needed, delegate one appropriately sized investigation
   unit to the explorer and evaluate its evidence and conclusions.
4. Decide the implementation strategy and scope yourself.
5. Before non-trivial implementation, size the work into bounded units using
   "Unit sizing". Keep the overall plan yourself and select only the current
   unit for delegation.
6. Delegate the current bounded implementation unit to the fixer.
7. Review the actual diff and verification results yourself.
8. Route follow-up work according to "Review and retry".
9. Repeat from step 2, stopping at the bound in "Two attempts without progress".
10. Confirm the completion criteria yourself.

## Concurrency

Run the explorer and the fixer one at a time on the same task. While the fixer is
working, keep every other change to the same working tree paused.

When in doubt, serialize work through the orchestrator.

## Handoffs

Delegated agents do not share the orchestrator's conversation. A prompt that
begins a new agent session must be standalone and assign one role only.

A **unit** is one focused investigation problem or one bounded implementation
task. Follow-up prompts within the same unit may build on that agent's
immediately preceding result, and must state the remaining question, defect, or
objective.

Use "Unit sizing" before sending a handoff when the work may require substantial
code exploration, research, implementation, or verification. The orchestrator
owns the overall task and plan; a delegated agent owns only its current unit.

Delegated agents do their own work and report back. They never invoke
`agent-orchestration`, delegate further, or run Herdr agent or pane control
commands.

Require every delegated response to end with one concise `<HERDR_RESULT>` block,
in the format given for that role.

## Unit sizing

Size delegated work by the **expected working context**, not by prompt length,
file count, or a fixed token threshold. Prompt size is only a weak proxy: a
short instruction can force an agent to load several subsystems and long test
outputs, while a longer instruction can still describe one tightly bounded
change.

The goal is to keep each delegated agent focused on one coherent working set and
to avoid making it retain detailed instructions for work that it is not yet
performing.

### A well-sized unit

Before delegation, confirm that the current unit normally has all of these
properties:

- **one coherent outcome** — the purpose can be stated as one focused outcome,
  not as several independently useful changes joined together;
- **one cohesive boundary** — the relevant files, components, APIs, or research
  areas serve the same immediate problem, even if several files are involved;
- **independent verification** — the unit has a meaningful conclusion or
  completion check that can be evaluated when the unit finishes;
- **no detailed future dependency** — the agent does not need the detailed
  implementation instructions for later units to perform the current one
  correctly;
- **focused working set** — the agent does not need to keep several unrelated
  subsystems, concerns, phases, or large bodies of evidence in active context at
  once.

If one of these properties fails because the work contains a natural independent
boundary, split before delegation. Do not force a task into one unit merely
because it was originally requested as one task.

### Strong split signals

Prefer multiple ordered units when any of the following is true:

- the handoff contains multiple outcomes that can be completed and reviewed
  independently;
- the work crosses natural subsystem, package, layer, or phase boundaries and
  each side has its own meaningful completion condition;
- different kinds of work are mixed even though they can be completed
  separately, such as an enabling refactor plus a behavior change, a migration
  plus application adoption, or implementation plus unrelated cleanup;
- completing and verifying an earlier part can materially change what the next
  part should do;
- part of the completion criteria can be satisfied and reviewed before the rest;
- the agent would need detailed later-step requirements that are irrelevant to
  the code or evidence it is handling now;
- the agent would have to explore several largely independent areas before it
  could make progress on any one of them.

Do not split mechanically by number of files, lines, questions, or prompt
characters. Several files that jointly implement one behavior may be one unit,
while one file containing multiple independent behavioral changes may require
several units.

Do not over-fragment tightly coupled work. If splitting would leave an
intermediate state that cannot be meaningfully verified, would require the same
context to be rediscovered immediately, or would separate changes that must be
reasoned about atomically for correctness, keep them in one unit.

### Reduce context before splitting

A long handoff does not automatically mean the unit is too large. First remove
context that the delegated agent does not need:

- convert investigation history into validated evidence;
- convert deliberation into the chosen decision or strategy;
- omit rejected alternatives unless the current unit must avoid a specific
  tempting but unsafe path;
- omit transcripts, repeated findings, and already-resolved discussion;
- include only constraints and cross-unit invariants that can affect the current
  unit;
- refer to relevant paths and interfaces instead of preloading unrelated code or
  later-unit detail.

Pass **settled state, not reasoning history**. If the handoff is still broad
because the current agent would need several independent working sets, split it.

### Progressive handoff

For a larger task, the orchestrator may maintain an ordered internal plan such
as:

```text
Overall objective
  Unit 1 -> independently reviewable result
  Unit 2 -> independently reviewable result
  Unit 3 -> independently reviewable result
```

Do not preload the delegated agent with the detailed instructions for every
unit. Send only what is needed for the current unit:

- the overall objective only when it helps explain why the current unit exists;
- cross-unit invariants that constrain the current unit;
- the current unit's objective or question;
- the current unit's scope;
- the settled strategy, when delegating implementation;
- relevant validated evidence;
- current constraints;
- the current unit's completion criteria or required conclusion.

After the unit completes, review its result yourself. Use only the validated
result as input when constructing the next unit. A completed unit may confirm,
change, merge, split, or eliminate later planned units.

This makes unit boundaries a context reset mechanism: the orchestrator retains
task continuity while each delegated agent receives only the working context it
needs now.

## Explorer

### When to use

Use the explorer when:

- the root cause is unclear;
- multiple plausible explanations exist;
- external documentation, APIs, SDK behavior, or specifications need research;
- unfamiliar code or architecture requires investigation;
- security, compatibility, data-integrity, or operational assumptions need
  evidence.

A large investigation is not automatically one explorer unit. If it contains
independent questions across unrelated code paths, systems, or specifications,
use "Unit sizing" and investigate them in ordered focused units.

A large implementation whose strategy is already settled goes straight to the
fixer.

### Handoff

Give the explorer:

- that this is investigation only, with no file, state, or environment changes;
- that it is a delegated explorer, not the orchestrator, and must not invoke
  `agent-orchestration`, delegate further, or control Herdr agents or panes;
- the objective;
- relevant paths, systems, or APIs;
- constraints;
- the specific questions to answer.

The read-only instruction has to be in the prompt. An investigation agent that
was not told to keep its hands off will often "helpfully" apply the fix it found,
which destroys the separation this skill depends on.

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

A complete handoff looks like this — one role, explicit boundaries, and enough
context to stand alone:

```text
You are a delegated explorer, not the orchestrator. Do not invoke
agent-orchestration, delegate work to other agents, or run Herdr agent or pane
control commands.

You are investigating a defect in the repository at /srv/api. This is a
read-only investigation: do not edit files, run migrations, or change any
state. Another agent will implement the fix.

Objective: determine why POST /v1/orders intermittently returns 500 under
concurrent requests.

Relevant paths: src/orders/handler.py, src/orders/repository.py,
src/db/session.py.

Constraints: PostgreSQL 16, SQLAlchemy 2.0. Reproduce using the existing test
suite only. Do not touch the staging database.

Questions to answer:
1. Which code path produces the 500, and what exception reaches it?
2. Is the cause session lifecycle, transaction boundaries, or application
   logic?
3. Which of those is supported by evidence rather than inference?

End your response with exactly one block in this format and nothing after it:

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

Use the fixer once the strategy is **settled** — its evidence is validated and no
open question would change it — and implementation is non-trivial, including
when:

- multiple files or components must change;
- independent implementation reduces implementation or review risk.

Before delegating a large settled implementation, apply "Unit sizing". A settled
strategy does not mean the entire implementation must be one fixer unit.

Send unresolved questions to the explorer first.

### Handoff

Give the fixer:

- that it is a delegated fixer, not the orchestrator, and must not invoke
  `agent-orchestration`, delegate further, or control Herdr agents or panes;
- the objective;
- bounded implementation scope;
- constraints;
- the chosen strategy;
- completion criteria;
- relevant validated evidence.

For a multi-unit implementation, include only cross-unit invariants and overall
context that can affect the current unit. Do not preload detailed instructions
for later units.

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
to the orchestrator rather than resolving it by guesswork. Say so in the prompt:
an implementation agent left to its own devices will usually pick something
plausible and keep going, and that guess arrives disguised as a finished change.

A complete handoff looks like this — the strategy is already decided, and what
is left open is only the local implementation detail:

```text
You are a delegated fixer, not the orchestrator. Do not invoke
agent-orchestration, delegate work to other agents, or run Herdr agent or pane
control commands.

You are implementing a bounded change in the repository at /srv/api.

Objective: make POST /v1/orders safe under concurrent requests.

Validated evidence: src/db/session.py:41 builds one Session at import time and
shares it across request handlers, so concurrent requests interleave on a
single transaction. This has been confirmed; treat it as settled.

Chosen strategy: scope the Session to the request with a per-request
sessionmaker dependency. Do not add a connection-pool library and do not
change the ORM layer.

Scope: src/db/session.py and src/orders/handler.py only. Leave
src/orders/repository.py unchanged.

Constraints: no schema migration, no new dependency, and the public handler
signature stays as it is.

Completion criteria: pytest tests/orders passes, and
tests/orders/test_concurrent_post.py fails before your change and passes
after it.

Make the local implementation decisions inside those boundaries yourself. If
any part of this instruction turns out to be wrong or underdetermined, stop
and report it instead of guessing.

End your response with exactly one block in this format and nothing after it:

<HERDR_RESULT>
Changes:
Verification:
- <command>: <result>
Remaining issues:
</HERDR_RESULT>
```

## Delegation mechanics

### Minimal example

One pass through a delegated cycle looks like this:

```bash
# investigate
herdr agent get <explorer-name>   # confirm idle before prompting
herdr agent prompt <explorer-name> '<standalone investigation prompt>' --wait
herdr agent read <explorer-name> --source recent-unwrapped --lines 200
```

Evaluate the evidence, decide the strategy yourself, then:

```bash
# implement
herdr agent get <fixer-name>
herdr agent prompt <fixer-name> '<standalone implementation prompt>' --wait
herdr agent read <fixer-name> --source recent-unwrapped --lines 200
```

Then review the result yourself before deciding the next route.

### Session reuse

Keep an agent's session for the whole unit: remaining questions, missing
evidence, a review correction, a test failure caused by the current
implementation, and completion of an unfinished part all belong to it. Repeated
corrections stay in the same unit.

A new unit is also the normal context-reset boundary for substantial work. When
the next unit begins, do not retain a long prior session merely because the same
role will handle it. Restart so the new unit begins with the standalone handoff
constructed from settled state, unless the next work is genuinely still the
same unit.

Restart the agent when the next prompt opens a different unit — a materially
different problem, another independently reviewable slice of a larger plan, a
strategy that has been abandoned, or work that prior context would bias. Do not
use `/new`: a new Pi session may fall back to its default model instead of
preserving the role's configured model.

Before stopping the agent, record its pane and the role's settled model and
thinking level. Then:

```bash
herdr agent get <name>
herdr agent prompt <name> '/quit'
```

Omit `--wait` for `/quit`, since the agent exits rather than settling into a
state to wait for. Wait until it disappears from `herdr agent list`, confirm its
pane has returned to an available interactive shell, then restart the same role
in that pane using the start command in [`STARTUP.md`](STARTUP.md). Explicitly
pass the role's settled `--model` and `--thinking`; never rely on Pi's defaults.

After restart, verify with `herdr agent get <name>` that the agent is in the
current tab and that its model and thinking level match the settled role
configuration before sending the first prompt of the new unit.

### Reading results

Use only the last complete `<HERDR_RESULT>` block emitted in response to the
current prompt.

Ignore:

- preceding thinking or progress output;
- blocks merely echoed from the prompt or quoted as examples;
- result blocks from earlier prompts or sessions.

Read with `--source recent-unwrapped`. The default `recent` source is
line-wrapped, so a long result can arrive with its tags and fields broken
mid-line and look malformed when it is intact.

When the block is missing or truncated, escalate in this order:

1. Raise `--lines`. This recovers a block that merely scrolled past the default
   window.
2. If a higher `--lines` reveals nothing more, stop raising it. The agent is
   drawing on the terminal's alternate screen, where rows that scroll away never
   reach Herdr's scrollback, so no line count can bring them back.
3. Ask the agent to re-emit only its final result without repeating the work.
4. If the result is long enough to scroll away again, ask the agent to write its
   complete response as Markdown to a temporary file and reply with the path
   only, then read that file yourself.

Keep step 4 as a fallback rather than folding it into the handoff. Routing every
delegation through a file costs an extra round trip and a temporary file to
solve a problem most units never hit.

## Waiting

`herdr agent prompt --wait` settling on `idle`, `done`, or `blocked` is
authoritative when the integration is healthy.

It does not track turns, though. Prompting an agent that is already working lets
the wait match that earlier turn finishing, and the read then returns the
previous turn's result — a stale `<HERDR_RESULT>` that reads as an answer to the
prompt you just sent. Confirm the agent is idle with `herdr agent get` before
prompting, rather than trying to detect staleness afterwards: once you hold a
plausible-looking block, nothing in it tells you which prompt produced it.

Read [`RECOVERY.md`](RECOVERY.md) when a prompt is rejected before it reaches the
agent, times out, settles on `blocked`, or an agent appears stuck. It holds the
submission failures, the inspection order, when interrupting is justified, and
the routes out.

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
