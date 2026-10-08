---
name: agent-orchestration
description: >-
  Delegates non-trivial engineering work to an `explorer` (investigation,
  research) and a `fixer` (implementation) in a Herdr session, while the
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

| Role                             | Agent                                   |
| -------------------------------- | --------------------------------------- |
| Orchestration, decisions, review | Orchestrator (the current agent)        |
| Investigation and research       | `explorer` (session-configured harness) |
| Implementation                   | `fixer` (session-configured harness)    |

The explorer is read-only and the fixer may intentionally modify project files
within delegated implementation work. Neither agent can read this skill or your
conversation, so each role boundary only exists if the handoff prompt states it.

## Startup

Delegation requires a Herdr-managed pane:

```bash
test "${HERDR_ENV:-}" = 1
```

If that fails, do the task yourself. Do not run a delegated agent in the orchestrator pane as a substitute.

All delegated agents must run in the orchestrator's current tab. Treat `$HERDR_TAB_ID` as a hard placement and reuse boundary.

Role configuration is scoped to the current top-level orchestrator's native Herdr agent session, not to one invocation, request, task, or delegation.

Before asking the user for configuration, resolve the current orchestrator session by running `skills/agent-orchestration/scripts/sessionctl inspect` and follow [`startup.md`](references/startup.md) to interpret the result. A complete matching persisted configuration is authoritative and is reused without asking again, even when the current context no longer contains the earlier configuration exchange. Ask only when startup.md's session-state policy establishes that no complete configuration is available, then persist the settled values immediately.

Read [`startup.md`](references/startup.md) before the first delegation of every invocation, and whenever a role's agent is missing, lives in another tab, has the wrong harness, model, or effort, or needs a pane created. It holds the session-state procedure, agent resolution steps, per-role configuration and start commands, and pane layout.

## Workflow

1. Define the objective, constraints, scope, and completion criteria.
2. Route to investigation, implementation, or direct handling using the
   delegation boundaries below. Handle work yourself when it is trivial, local,
   and low-risk enough that delegation would cost more than it returns.
3. If investigation is needed, delegate one appropriately sized investigation
   unit to the explorer and evaluate its evidence and conclusions. If Parallel
   Explorers may be appropriate, read [`parallel.md`](references/parallel.md)
   before deciding admission or dispatch.
4. Decide the implementation strategy and scope yourself.
5. Before non-trivial implementation, size the work into bounded units using
   "Context routing and unit sizing". Keep the overall plan yourself and select
   only the current unit for delegation.
6. Delegate the current bounded implementation unit to the fixer.
7. Review the actual diff and verification results yourself.
8. Route follow-up work according to "Review and retry".
9. Repeat from step 2, stopping at the bound in "Two attempts without
   progress".
10. Confirm the completion criteria yourself.

## Concurrency

Only read-only Explorer work admitted under [`parallel.md`](references/parallel.md) may run in parallel to reduce investigation latency across independent units on the same repository state; serialize all writes, Fixer work, and Explorer–Fixer overlap through the orchestrator, and when in doubt serialize work there.

### Parallel Explorer batches

Read [`parallel.md`](references/parallel.md) before handling Parallel Explorer admission, dispatch, collection, resume, or convergence; it is authoritative for those operations. Use only two or three independent read-only Explorer units under one parent objective; a disabled or rejected batch falls back to sequential exploration. Give each unit a standalone prompt, validate each latest complete result independently, and do not share sibling raw outputs. Preserve failures as explicit gaps and synthesize once in the orchestrator, separating observed evidence from Explorer interpretation and preserving provenance and contradictions rather than voting.

Run the optional Explorer Gate at most once after synthesis (see [`explorer-gate.md`](references/explorer-gate.md)). Parallel investigation does not permit parallel Fixers, shared-tree writes, or skipping sequential implementation, diff review, verification, or the Completion Gate.

## Handoffs

Delegated agents do not share the orchestrator's conversation. A prompt that
begins a new agent session must be standalone and assign one role only.

A **unit** is one focused investigation problem or one bounded implementation
task. Follow-up prompts within the same unit may build on that agent's
immediately preceding result, and must state the remaining question, defect, or
objective.

Use "Context routing and unit sizing" before sending a handoff when the work
may require substantial code exploration, research, implementation, or
verification. The orchestrator owns the overall task and plan; a delegated agent
owns only its current unit.

Delegated agents do their own work and report back. They never invoke
`agent-orchestration`, delegate further, or run Herdr agent or pane control
commands.

Require every delegated response to end with one `<HERDR_RESULT>` block in the
format given for that role, and say in the handoff that it is a concise
transport summary, not the full report: the core findings or changes and only
the key evidence or verification review needs. Only when supporting detail
would not fit safely does the agent write it to a temporary Markdown file such
as `/tmp/<descriptive-name>.md` and cite the path inside an existing field. For
an explorer, say that this file under `/tmp`, outside the working tree, is its
only permitted write.

## Context routing and unit sizing

The orchestrator owns context routing. A new-unit handoff is a projection of
settled task state for one working set, not a copy of the conversation or prior
agent output.

Size delegated work by the **expected working context**, not by prompt length,
file count, or a fixed token threshold. Prompt size is only a weak proxy: a
short instruction can force an agent to load several subsystems and long test
outputs, while a longer instruction can still describe one tightly bounded
change.

### Context contract

Pass **settled state, not reasoning history**. A new-unit handoff includes only
what can affect the current unit:

- the role boundary;
- the current unit's objective or question, plus the overall objective only
  when it explains why the unit exists;
- the current unit's scope, referring to relevant paths, systems, APIs, or
  interfaces rather than preloading code;
- current constraints and the cross-unit invariants that constrain this unit;
- the settled strategy, when delegating implementation;
- relevant validated evidence, converted from investigation history;
- the current unit's completion criteria or required conclusion.

Leave out conversation transcripts, raw tool or agent output, repeated findings,
already-resolved discussion, sibling raw results, and detailed instructions for
later units. Omit rejected alternatives unless the current unit must avoid a
specific tempting but unsafe path.

A long handoff does not automatically mean the unit is too large; apply this
contract first. If the handoff is still broad because the agent would need
several independent working sets, split it.

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

### Progressive handoff

For a larger task, the orchestrator may maintain an ordered internal plan such
as:

```text
Overall objective
  Unit 1 -> independently reviewable result
  Unit 2 -> independently reviewable result
  Unit 3 -> independently reviewable result
```

Build each unit's handoff under "Context contract" rather than preloading every
unit's detailed instructions.

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
use "Context routing and unit sizing" and investigate them in ordered focused
units.

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

State the read-only rule in the prompt; without it, an explorer may apply the fix
it finds and break role separation.

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

This is a read-only investigation of a defect in the repository at /srv/api: do
not edit files, run migrations, or change any state. Another agent implements
the fix.

Objective: find why POST /v1/orders intermittently returns 500 under concurrent
requests.

Relevant paths: src/orders/handler.py, src/orders/repository.py,
src/db/session.py.

Constraints: PostgreSQL 16, SQLAlchemy 2.0. Reproduce using the existing test
suite only. Do not touch the staging database.

Questions:
1. Which code path and exception produce the 500?
2. Is the cause session lifecycle, transaction boundaries, or application logic,
   and which of those is supported by evidence rather than inference?

Keep the result block to the core findings and key evidence. If supporting
detail is long, write it to /tmp/<descriptive-name>.md, outside the repository
and the only file you may write, and cite the path in Evidence.

End your response with exactly one block in this format and nothing after it:

<the Explorer result format above, verbatim>
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

Before delegating a large settled implementation, apply "Context routing and
unit sizing". A settled strategy does not mean the entire implementation must be
one fixer unit.

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

For a multi-unit implementation, apply "Context contract".

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

Say in the prompt that the fixer must report unresolved uncertainty to the
orchestrator rather than resolve it by guesswork; otherwise a plausible guess
can pass as a finished change.

A complete handoff looks like this — the strategy is already decided, and what
is left open is only the local implementation detail:

```text
You are a delegated fixer, not the orchestrator. Do not invoke
agent-orchestration, delegate work to other agents, or run Herdr agent or pane
control commands.

You are implementing a bounded change in the repository at /srv/api.

Objective: make POST /v1/orders safe under concurrent requests.

Validated evidence (settled): src/db/session.py:41 builds one Session at import
time and shares it across request handlers, so concurrent requests interleave
on a single transaction.

Chosen strategy: scope the Session to each request with a per-request
sessionmaker dependency. Do not add a connection-pool library or change the ORM
layer.

Scope: src/db/session.py and src/orders/handler.py only; leave
src/orders/repository.py unchanged.

Constraints: no schema migration or new dependency; keep the public handler
signature unchanged.

Completion criteria: pytest tests/orders passes, and
tests/orders/test_concurrent_post.py fails before your change and passes after it.

Make local implementation decisions inside those boundaries. If any part of
this instruction turns out to be wrong or underdetermined, stop and report it
instead of guessing.

Keep the result block to what review needs. Put long logs or details in
/tmp/<descriptive-name>.md and cite the path in Verification.

End your response with exactly one block in this format and nothing after it:

<the Fixer result format above, verbatim>
```

## Delegation mechanics

### Minimal example

One pass through a delegated cycle looks like this:

```bash
# investigate
herdr agent get <explorer-name>   # confirm idle; keep as baseline
herdr agent prompt <explorer-name> '<standalone investigation prompt>' --wait
herdr agent get <explorer-name>   # freshness check (see "Waiting")
herdr agent read <explorer-name> --source recent-unwrapped --lines 200
# evaluate the evidence and decide the strategy yourself
# implement
herdr agent get <fixer-name>
herdr agent prompt <fixer-name> '<standalone implementation prompt>' --wait
herdr agent get <fixer-name>
herdr agent read <fixer-name> --source recent-unwrapped --lines 200
```

Then review the result yourself before deciding the next route.

### Session reuse

Keep an agent's session for the whole unit: remaining questions, missing evidence, a review correction, a test failure caused by the current implementation, and completion of an unfinished part belong to it; repeated corrections stay in the same unit.

A new unit is the normal context-reset boundary for substantial work; restart so it begins with a standalone handoff from settled state, unless the next work is genuinely still the same unit. Also restart for a materially different problem, another independently reviewable slice of a larger plan, an abandoned strategy, or work that prior context would bias. Do not use a harness-native new-session command if it could fall back to the harness's default model or effort instead of preserving the role's settled configuration.

Restart the same role with its settled harness, model, and effort. Before the first prompt of the new unit, verify with `herdr agent get <name>` that the agent is in the current tab and its harness, model, and effort match the settled role configuration. Use [`startup.md`](references/startup.md) §Resolution for the stop, wait-for-shell, restart, and verification procedure.

### Reading results

Use only the last complete `<HERDR_RESULT>` block emitted in response to the
current prompt.

Ignore:

- preceding thinking or progress output;
- blocks merely echoed from the prompt or quoted as examples;
- result blocks from earlier prompts or sessions.

Read a result only after the "Waiting" freshness check passes. Before accepting
the isolated block, pipe `{"role": "explorer" | "fixer",
"result": "<block>"}` to `scripts/result_validate` and require `valid: true`. It
checks role-specific structure only; freshness, evidence quality, and
completion remain yours to validate.

Read with `--source recent-unwrapped`. The default `recent` source is
line-wrapped, so a long result can arrive with its tags and fields broken
mid-line and look malformed when it is intact.

When the block is missing or truncated:

1. Raise `--lines` once. This recovers a block that merely scrolled past the
   default window.
2. If that reveals nothing more, the block scrolled away: the agent draws on
   the terminal's alternate screen, whose scrolled rows never reach Herdr's
   scrollback. Do not ask for the same long block again. In one same-unit
   prompt, ask the agent, without redoing the work, to save its detailed
   response to a new temporary Markdown file and end with one concise
   `<HERDR_RESULT>` citing the path, then read that file yourself.

When the block is short but missing or malformed for another reason, such as
progress output in its place, asking the agent to re-emit only its final result
is enough. Either request is a same-unit recovery prompt that re-delivers
finished work, not new investigation or another Explorer round; existing retry
bounds and the "Waiting" freshness check apply.

### Trace

Record a best-effort counter with `scripts/tracectl record` only at these
settled boundaries: a delegated prompt's final disposition (`delegation`,
`accepted` or `recovery`), each recovery route entered (`recovery`, named by
the Herdr, freshness, or result failure, or `transport_fallback` for the
"Reading results" file route), and each `parallel_validate` verdict you act on
(`parallel`, with its reason). It accepts enums only, so never pass task content.
A failed or unavailable trace never changes the task flow.

## Waiting

`herdr agent prompt --wait` settling on `idle`, `done`, or `blocked` tells you
when to look, not which prompt produced what you read. It does not track turns:
prompting an agent that is already working lets the wait match that earlier turn
finishing, and the read then returns the previous turn's result — a stale
`<HERDR_RESULT>` that reads as an answer to the prompt you just sent. Once you
hold a plausible-looking block, nothing in it tells you which prompt produced
it, so establish freshness from Herdr's lifecycle sequence, not the text:

1. Before prompting, run `herdr agent get <name>`, prompt only an `idle` or
   `done` agent, and keep that agent object as the baseline. `state_change_seq`
   is a server-wide counter stamped on every state transition; `completion_seq`
   is present only while the current state is a completed turn.
2. After the wait returns, whatever it returned, run `herdr agent get <name>`
   again and pipe `{"baseline": <agent>, "current": <agent>}` to
   `scripts/freshness_validate`.
3. Read the result only on `fresh: true` (`completion_advanced`): a completion
   newer than the baseline, even if `working` was never observed.
   `progress_observed` means still working, so wait again; `baseline_not_ready`
   means the prompt should not have been sent. `blocked`, `no_progress`,
   `unknown_status`, and `sequence_regressed` (the Herdr server restarted, so
   freshness cannot be proven) go to `recovery.md`.

Baselines belong to the current prompt only; never persist them in session
state. Herdr has no prompt or turn id, so do not invent one. Freshness and
`result_validate` structure are separate checks: a fresh turn can return a
malformed block, and a well-formed block can be stale.

Read [`recovery.md`](references/recovery.md) when a prompt is rejected before it reaches the
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

### Optional Jev completion gate

[`jev.md`](references/jev.md) is authoritative for the optional gate. Run the Completion Gate only after the orchestrator reviews the actual diff and deterministic project verification passes; Jev cannot override deterministic failures, policy, or this skill's invariants. If Jev is disabled, unavailable, invalid, or uncertain, continue the existing workflow conservatively; disabled or unavailable Jev leaves behavior unchanged. Report unavailability concisely without failing the task.

#### Shadow mode

In enabled `shadow` mode, work, review, and verify normally, then decide the next action without consulting Jev. Invoke Jev at most once per eligible decision, and only when the gate would genuinely run; never on deterministic failure, incomplete review, or an unsafe payload. Record `action_match` and `completion_match`, then continue with the original decision. **The Jev result MUST NOT cause the Orchestrator to revise the decision in shadow mode.**

Use this report template:

```text
## Jev Shadow
Orchestrator decision: <action>
Jev status: <status>
Jev action: <action>
next_action_confidence: <value>
outcome_supported: <value>
unresolved_issue: <value>
scope_exceeded: <value>
completion_confidence: <value>
would_auto_apply: <bool>
auto_apply: false
Agreement:
action_match: (orchestrator_action==jev_action)
completion_match: ((both complete) or (both not complete))
```

### Optional Jev Explorer gate

[`explorer-gate.md`](references/explorer-gate.md) is authoritative for the optional post-Explorer evidence gate. Run it only after the Explorer returns and you have reviewed and settled its evidence. Set `orchestrator_reviewed: true` only after that review. Disabled or incomplete-review gates do not start `cmd`.

In `shadow`, record the result without changing the route. In `active`, only a decided, confident `explore_more` may hold the fixer handoff. `proceed_to_fix` is not authorization; neither mode auto-applies. For invalid, uncertain, or unavailable results, continue from your evidence review or escalate.

The Explorer Gate precedes implementation.

On normal completion:

- leave the persisted role configuration intact for the lifetime of the current orchestrator native session;
- leave correctly configured delegated agents running for reuse;
- leave panes intact, including user-owned panes.

Stop an agent only when:

- its configuration must be replaced;
- it is unhealthy or unusable;
- the user explicitly asks for cleanup.
