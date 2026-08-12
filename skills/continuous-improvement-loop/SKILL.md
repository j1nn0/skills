---
name: continuous-improvement-loop
description: >-
  Runs autonomous software-engineering improvement as repeated, reviewable
  rounds until the repository converges: each round reassesses the current
  state, selects one worthwhile improvement, uses agent-orchestration for
  investigation and implementation, verifies and commits the result, then
  decides from the new repository state whether another round is justified.
  Use when the user wants a codebase to keep improving autonomously rather than
  complete a fixed task list. Requires the agent-orchestration skill when a
  round meets the delegation criteria defined below.
---

# Continuous Improvement Loop

Continuously improve the current repository through independent engineering rounds until no further
safe, evidence-backed, worthwhile improvement remains.

This skill owns the **outer loop**. It decides whether another round should happen after each completed
change. For the engineering work inside a round, use `agent-orchestration` whenever the round meets
the delegation criteria in **Round Workflow §4**.

Do not turn the whole run into one fixed backlog. The repository changes after every round, so the next
round must be chosen from the new state rather than from an old plan.

## Preconditions

Before starting the loop:

1. Read the repository-level instructions and project documentation that govern the work.
2. Identify the current branch and working-tree state.
3. Preserve unrelated user changes. Never absorb them into improvement commits silently.
   If uncommitted user changes overlap with the selected improvement area, do not modify, stash,
   reset, or absorb those changes. Prefer selecting a different, non-overlapping improvement
   candidate when one exists. If no worthwhile non-overlapping candidate exists, stop the round and
   escalate to the caller to resolve the working-tree state before continuing.
4. Capture the caller's constraints as hard loop constraints. Examples include:
   - breaking changes allowed or forbidden;
   - security invariants that must not be weakened;
   - directories or subsystems that are out of scope;
   - required verification commands;
   - release, compatibility, performance, or API constraints.
5. Confirm that `agent-orchestration` is available before relying on it. If it is unavailable, perform
   the round as a single agent while keeping the same review and convergence rules.

Caller constraints and project-specific instructions override this skill. Treat them as hard boundaries, not
preferences. Autonomous decision-making applies only inside those boundaries.

If an otherwise delegated decision would require violating a caller constraint or project-specific
instruction, do not make that decision autonomously. Choose a compliant alternative when one exists. If
no safe compliant option exists, escalate to the caller rather than overriding the constraint.

## Responsibilities

The current agent remains responsible for the loop itself. Never delegate:

- deciding whether another round is justified;
- selecting the next improvement;
- interpreting caller constraints;
- accepting or rejecting investigation findings;
- approving the implementation strategy;
- reviewing the actual diff;
- deciding commit boundaries;
- deciding whether the repository has converged.

When a round meets the delegation criteria in **Round Workflow §4**, `agent-orchestration` is
responsible for its engineering workflow: Pi `explorer` investigates read-only, the current agent
evaluates the findings and decides the strategy, Pi `fixer` implements, and the current agent reviews
and verifies the result.

## Loop Model

One round is:

```text
reassess repository
       ↓
find candidate improvements
       ↓
select one worthwhile improvement
       ↓
investigate when needed
       ↓
decide strategy and round completion criteria
       ↓
implement
       ↓
review + verify
       ↓
commit in logical units
       ↓
reassess the new repository state
       ↓
continue or stop
```

The output of a round is not merely code. A round is complete only when the change is reviewed,
verified, and recorded in coherent commits.

## Round Workflow

### 1. Reassess the current state

Start every round from the repository as it exists **after all previous rounds**.

Inspect enough of the codebase, tests, documentation, configuration, dependency state, architecture,
and recent changes to understand where the highest-value improvement may now be.

Do not assume that candidates discovered in an earlier round are still the right priorities.

### 2. Generate candidates

Identify plausible improvements across any area allowed by the caller and repository instructions,
including when relevant:

- correctness and bug prevention;
- security;
- useful product or library capability;
- API and configuration design;
- architecture and responsibility boundaries;
- framework, SDK, and dependency integration;
- error handling and failure behavior;
- test quality and missing coverage;
- static analysis and type safety;
- performance and resource usage;
- developer experience and maintainability;
- documentation accuracy;
- removal of unnecessary complexity or compatibility layers.

A candidate is not valuable merely because code can be changed.

Reject candidates that are primarily cosmetic, speculative, redundant, or change-for-change's-sake.

### 3. Select exactly one improvement theme

Choose the single candidate with the strongest current justification.

Evaluate candidates by evidence, expected benefit, safety, alignment with the repository's purpose,
complexity, implementation risk, maintenance cost, and caller constraints.

Prefer an improvement that can be reviewed as one coherent theme. A theme may still require multiple
commits when those commits represent distinct logical steps.

Do not select a candidate whose value depends on inventing user requirements that are not supported by
the repository or caller instructions.

### 4. Investigate before implementation when needed

Invoke `agent-orchestration` when **any** of the following applies:

- the root cause or best implementation approach cannot be established from one local code path and the
  repository's existing instructions;
- external documentation, APIs, SDK behavior, framework behavior, or specifications need research;
- the change crosses architectural components, subsystems, or responsibility boundaries;
- the change affects a public API, configuration contract, persisted data format, security-sensitive
  behavior, compatibility boundary, or operational behavior;
- security, compatibility, data-integrity, or operational risk warrants independent investigation and
  review;
- implementation requires multiple coordinated behavior changes rather than a mechanical local edit.

Handle a round directly only when the change is local, mechanically obvious, low-risk, does not require
external research, and does not require a cross-component design decision. When uncertain which case
applies, use `agent-orchestration`.

Use Pi `explorer` for evidence gathering when the right change is not already clear. Require Pi
`explorer` to remain read-only. The current agent must evaluate the findings before turning them into
an implementation strategy.

If the explorer's findings are inconclusive, contradictory, or too weak to support the proposed
change, do not proceed to implementation. Request a targeted follow-up investigation when a focused
question could reasonably resolve the uncertainty. If sufficient evidence still cannot be established
without disproportionate effort or speculation, treat that candidate as blocked for the current loop
and evaluate the next-best candidate.

Do not use investigation merely to justify a change already chosen by preference.

### 5. Define the round

Before implementation, decide:

- objective;
- scope;
- hard constraints;
- implementation strategy;
- expected behavior after the change;
- tests or checks that must demonstrate success;
- likely commit boundaries.

These are **round-level** completion criteria, not final loop completion criteria.

### 6. Implement

If the round meets the delegation criteria in **Round Workflow §4**, delegate implementation to Pi
`fixer` through `agent-orchestration`. Otherwise, the current agent may implement the local low-risk
change directly.

Keep the implementation inside the approved theme and strategy. Allow local implementation decisions
when they do not change the approved scope or constraints.

If new evidence invalidates the strategy, stop extending the patch and return to investigation or
strategy selection.

### 7. Review independently

Do not accept an implementer's success report as proof of correctness.

Review the actual diff and check for:

- whether the selected improvement was actually achieved;
- unnecessary or unrelated changes;
- accidental behavior changes;
- weakened invariants or caller constraints;
- avoidable complexity;
- missing tests or documentation;
- whether the implementation addresses the root cause rather than hiding it.

If the same failure recurs, stop stacking patches. Re-evaluate the assumptions and investigate again.

### 8. Verify

Run the repository's own relevant verification commands.

Prefer project-defined tests, static analysis, linting, formatting checks, builds, integration tests,
and security checks over invented substitutes.

Add or strengthen tests when the new behavior or guarantee is not already covered.

A round cannot be considered complete while required verification is failing because of the round's
changes.

### 9. Commit in logical units

Create reviewable commits instead of accumulating the entire loop in one large commit.

Use these principles:

- one commit has one clear purpose;
- unrelated changes do not share a commit;
- a large improvement theme may span multiple commits when the steps are independently understandable;
- avoid intentionally broken intermediate commits;
- keep tests with the behavior they validate when that produces the clearest commit;
- separate mechanical refactoring from behavior changes when doing so materially improves reviewability;
- update documentation with the change it describes unless a separate documentation commit is clearer;
- do not split commits mechanically just to increase commit count.

Before committing, inspect the working tree and ensure unrelated pre-existing user changes are not
included.

If commit creation becomes unavailable or fails after implementation is complete, including after some
but not all intended commits have been created, do not start another round.

Leave completed working-tree changes and any already-created commits untouched. Do not rewrite,
squash, amend, reset, stash, or otherwise alter them merely to recover commit creation.

Report:

- commits that were created successfully, if any;
- implemented but uncommitted changes;
- the intended remaining commit boundaries and commit messages;
- verification already completed;
- the reason commit creation could not be completed.

Then stop the loop until the caller resolves the repository or environment state. Never carry an
incomplete commit plan into a new improvement round.

## Convergence Decision

After the round is fully reviewed, verified, and committed, forget the previous candidate ranking and
reassess the repository again.

Continue only when there is another **safe, evidence-backed, worthwhile** improvement.

The loop has converged when the remaining ideas fall only into categories such as:

- no clear benefit;
- benefit is smaller than the added complexity or risk;
- evidence is insufficient;
- the change would violate caller or repository constraints;
- the change could weaken security or another protected invariant;
- user requirements would have to be invented;
- an external decision, specification, dependency, or future event is required;
- the change is primarily cosmetic or stylistic;
- the existing implementation is already reasonable;
- the proposal is change-for-change's-sake.

The stopping question is:

> Is there another change that this repository should reasonably receive now, given the available
> evidence and constraints?

It is **not**:

> Can anything else be changed?

Software can almost always be changed. The loop must stop when further autonomous work is no longer
well justified.

## Anti-Loop Guards

Do not manufacture work to keep the loop alive.

Stop or change approach when any of these occur:

- the same problem recurs without meaningful new evidence;
- multiple attempts produce no meaningful progress;
- proposed changes become increasingly speculative;
- improvements become successively smaller while complexity keeps increasing;
- the next step requires violating a protected constraint;
- progress depends on destructive or irreversible action that was not authorized;
- the repository needs a product, security, legal, or operational decision that cannot be derived
  safely from the available context.

When the blocker is a decision the caller explicitly delegated to the agent and sufficient evidence
exists, make the decision **only if it stays within every hard caller and repository constraint**. If the
delegated decision would require violating one of those constraints, choose a compliant alternative or
escalate to the caller. Escalate whenever safe autonomous judgment is not possible within those
boundaries.

## Security and Protected Invariants

Treat any caller- or repository-defined security invariant as a hard lower bound across all rounds.

Never trade a protected security guarantee for convenience, compatibility, performance, or a larger
feature set unless the caller explicitly changes that constraint.

When uncertain whether a proposed change weakens a protected invariant, do not implement it until the
risk is resolved through investigation.

Security improvements are valid candidates when they preserve or strengthen all existing protected
guarantees.

## State and Memory

The repository is the durable state of the loop.

Prefer durable evidence over conversational memory:

- committed code;
- tests;
- project documentation;
- architecture decisions;
- configuration;
- commit history.

Do not create a permanent loop-state file by default. Add one only when the caller or repository
workflow requires persistent cross-session loop metadata.

Each new round must be understandable from the repository's current state plus the caller's original
constraints; it must not depend on undocumented private reasoning from earlier rounds.

## Relationship to `agent-orchestration`

`continuous-improvement-loop` and `agent-orchestration` operate at different levels:

```text
continuous-improvement-loop
  ├─ choose round
  ├─ agent-orchestration
  │    ├─ Pi explorer investigation
  │    ├─ current-agent decision
  │    ├─ Pi fixer implementation
  │    └─ current-agent review / verification
  ├─ commit logical units
  ├─ reassess repository
  └─ continue / stop
```

Do not duplicate `agent-orchestration`'s Herdr commands, model assignments, waiting behavior, or agent
handoff mechanics here. That skill is the authority for those details.

## Completion Report

Report only after the loop has converged or cannot safely continue.

Summarize:

- the main improvements completed across the rounds;
- the commits created and the purpose of each logical commit;
- important behavior or API changes;
- protected invariants maintained or strengthened;
- final verification results;
- important candidates considered but intentionally not implemented, with reasons;
- why another autonomous improvement round is no longer justified.

Keep the report concise relative to the work performed.
