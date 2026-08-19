---
name: agent-orchestration
description: >-
  Orchestrates non-trivial software engineering work across three agents in a
  Herdr session: the orchestrator (the current agent) owns strategy and review,
  Pi `explorer` investigates and researches, and Pi `fixer` implements. Use this
  whenever a task involves an unclear root cause, several plausible
  explanations, unfamiliar code or architecture, research into external APIs,
  SDKs, or specifications, or an implementation spanning multiple files or
  components — even when the user does not mention agents, delegation, or
  orchestration at all. Requires HERDR_ENV=1 and builds on the herdr skill for
  pane and agent control. Do not use for trivial, local, low-risk tasks the
  orchestrator can safely handle directly.
---

# Agent Orchestration

You remain the orchestrator and reviewer for the whole task.

Core principles:

1. The orchestrator owns strategy, review, and completion, and defines the
   boundaries for delegated decisions.
2. The explorer reduces uncertainty without intentionally modifying the project.
3. The fixer implements a bounded strategy once it is sufficiently established.
4. Explorer and fixer never hand work directly to each other. Every finding,
   decision, follow-up request, and implementation instruction passes through
   the orchestrator.
5. Return to the explorer whenever meaningful uncertainty appears.
6. Verify delegated results independently.

Use the `herdr` skill as the authority for pane and agent CLI syntax.

## Roles

| Role | Agent | Model / effort |
| --- | --- | --- |
| Orchestration, decisions, review | Orchestrator | Current model |
| Investigation and research | Pi `explorer` | `opencode-go/deepseek-v4-flash`, `thinking: max` |
| Implementation | Pi `fixer` | `openai-codex/gpt-5.6-luna`, `thinking: max` |

The explorer is read-only. The fixer may intentionally modify project files
within delegated implementation work.

## Recommended layout

Prefer this layout when creating panes for delegated agents:

```text
┌──────────────────────────────┬──────────────────────┐
│                              │       Explorer       │
│                              │                      │
│       Orchestrator           ├──────────────────────┤
│                              │        Fixer         │
│                              │                      │
└──────────────────────────────┴──────────────────────┘
```

Keep the orchestrator on the left, with the explorer above the fixer on the
right. Preserve existing user-owned panes when applying this layout.

## Startup

Delegation requires a Herdr-managed pane:

```bash
test "${HERDR_ENV:-}" = 1
```

If that fails, do the task yourself. Do not run Pi in the orchestrator pane as a
substitute.

All delegated agents must run in the orchestrator's current tab. Treat
`$HERDR_TAB_ID` as a hard placement and reuse boundary.

Before using a delegated role:

1. Run `herdr agent list` and `herdr agent`; confirm the `pi` kind is available.
2. Reuse a live agent only when:
   - its `tab_id` equals `$HERDR_TAB_ID`;
   - its kind matches;
   - its model matches;
   - its thinking level matches.
3. Never reuse, stop, replace, or repurpose an agent from another tab.
4. If the preferred name belongs to an agent in another tab, choose a unique name
   for the same-tab agent and use that resolved name thereafter.
5. If a same-tab agent has the wrong configuration:
   - send `/quit`;
   - wait until it disappears from `herdr agent list`;
   - confirm its pane has returned to an available interactive shell with
     `herdr pane process-info --pane <id>`.
6. Use only an idle same-tab pane with no foreground agent, editor, or command.
7. If no suitable pane exists, split a pane in `$HERDR_TAB_ID`, normally the
   orchestrator pane, and use the resulting pane id in the start command:

   ```bash
   herdr pane split --current --direction right --cwd "$PWD" --no-focus
   ```

8. Start the role with its pinned configuration.
9. Verify after startup with `herdr agent get <resolved-name>` that its `tab_id`
   equals `$HERDR_TAB_ID`.

If the required kind, model, thinking level, pane, shutdown, or startup cannot be
confirmed, stop delegation for that role. Never silently fall back to another
model, configuration, or tab. Handle the work directly if it is trivial enough to
be safe; otherwise escalate to the user when delegation is materially needed.

### Explorer

```bash
herdr agent start <explorer-name> --kind pi --pane <pane-id> -- \
  --model opencode-go/deepseek-v4-flash \
  --thinking max \
  --no-autoformat \
  --no-autofix
```

Use `explorer` as `<explorer-name>` when available.

### Fixer

```bash
herdr agent start <fixer-name> --kind pi --pane <pane-id> -- \
  --model openai-codex/gpt-5.6-luna \
  --thinking max \
  --no-autoformat \
  --no-autofix
```

Use `fixer` as `<fixer-name>` when available.

Both delegated agents intentionally use Pi's normal installed extensions, skills,
and tools. The skill pins only the role-specific model and thinking level.

## Concurrency

Do not run the explorer and the fixer concurrently on the same task.

Do not run delegated implementation concurrently with any other work that may
modify the same working tree.

State consistency matters more here than parallelism. When in doubt, serialize
work through the orchestrator.

## Routing

Do not treat orchestration as a fixed Explorer → Fixer pipeline. At every
meaningful decision point, route work according to the current need, using the
criteria in "Delegation boundary".

The orchestrator must evaluate delegated output before deciding the next route.

```text
Explorer ↔ Orchestrator ↔ Fixer

Typical flows:
  Orchestrator
  Explorer → Orchestrator
  Fixer → Orchestrator
  Explorer → Orchestrator → Fixer → Orchestrator
  Orchestrator → Explorer → Orchestrator → Fixer → Orchestrator
```

## Workflow

1. Define the objective, constraints, scope, and completion criteria.
2. Determine whether investigation, implementation, or direct handling is
   appropriate.
3. If investigation is needed, delegate to the explorer and evaluate its evidence
   and conclusions.
4. Decide the implementation strategy and scope yourself.
5. If implementation is non-trivial, delegate a bounded implementation unit to
   the fixer.
6. Review the actual diff and verification results yourself.
7. Route follow-up work according to "Review and retry".
8. Repeat only while meaningful progress is being made.
9. Confirm the completion criteria yourself.

## Handoffs

Delegated agents do not share the orchestrator's conversation. The orchestrator
is the only handoff boundary between delegated roles: explorer and fixer must
never instruct, prompt, or delegate work directly to each other.

A prompt that begins a new agent session must be standalone and assign one role
only.

Follow-up prompts within the same investigation or implementation unit may build
on that agent's immediately preceding result, but must clearly state the remaining
question, defect, or objective.

Unless explicitly instructed by the orchestrator, delegated agents must not invoke
`agent-orchestration` or delegate their own work.

Require every delegated response to end with one concise final result block.

### Minimal example

One pass through a delegated cycle looks like this:

```bash
# investigate
herdr agent prompt <explorer-name> --wait -- '<standalone investigation prompt>'
herdr agent read <explorer-name>
```

Evaluate the evidence, decide the strategy yourself, then:

```bash
# implement
herdr agent prompt <fixer-name> --wait -- '<standalone implementation prompt>'
herdr agent read <fixer-name>
```

Then review the result yourself before deciding the next route. See the `herdr`
skill for full CLI syntax.

### Session reuse

Reuse the current session for follow-up that belongs to the same investigation or
implementation unit, such as a remaining question, missing evidence, a review
correction, a test failure caused by the current implementation, or completion of
an incomplete part of the same bounded task.

When reusing an existing delegated agent for a new independent unit, send `/new`
and wait for it to settle before sending the next standalone prompt.

Also start a fresh session when:

- the task moves to a materially different problem;
- the previous investigation or strategy is no longer relevant;
- prior context is likely to bias or mislead the new session.

Do not reset an agent merely because its work needs one or more corrections.

### Reading results

Use only the last complete `<HERDR_RESULT>` block emitted in response to the
current prompt.

Ignore:

- preceding thinking or progress output;
- blocks merely echoed from the prompt or quoted as examples;
- result blocks from earlier prompts or sessions.

If the current prompt produced no complete result block, ask the agent to
re-emit only its final result without repeating the work.

## Explorer handoff

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

Evidence should identify relevant code, files, APIs, specifications, or external
sources as appropriate. Prefer primary official sources for external technical
research.

Treat the explorer's recommendation as input, not as the implementation decision.
The orchestrator may pass validated evidence to the fixer, but must separately
state the chosen strategy and implementation boundaries.

Investigation may be iterative. Ask only for the missing evidence or unresolved
question rather than a repeat of already-established findings.

If confidence remains too low to proceed safely, continue focused investigation or
escalate rather than turning an uncertain conclusion into an implementation
instruction.

## Fixer handoff

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

## Waiting and recovery

`herdr agent prompt <name> --wait` settling on `idle`, `done`, or `blocked` is
authoritative when the integration is healthy.

A timeout alone does not mean the agent is stuck.

After a timeout, inspect:

- `herdr agent get`;
- recent output with `herdr agent read`;
- the foreground process state when relevant.

No new agent output by itself is not evidence of failure. Long-running tests,
builds, analysis, searches, or other commands may legitimately remain quiet.

Interrupt with:

```bash
herdr agent send-keys <name> ctrl+c
```

only when there is no evidence of meaningful progress or the agent is clearly
stuck.

After interruption, inspect the last output and choose one of:

- continue with a more focused prompt;
- reduce the task scope;
- return to the explorer if the cause is uncertain;
- change the strategy;
- escalate.

If an agent is `blocked`, inspect the cause before retrying. Handle expected
permission prompts safely; never weaken or bypass the permission policy merely
to make progress.

## Review and retry

Verify independently. Do not trust the fixer's report as proof of completion.
Read the actual diff and run the project's own appropriate verification.

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

### No meaningful progress

If two consecutive attempts on the same issue produce no meaningful progress,
stop retrying the same approach. Re-evaluate the evidence and strategy, use the
explorer if uncertainty remains, and escalate to the user if no materially
different safe approach is available.

Do not stack local fixes on a recurring problem.

## Escalation

Consult the user when:

- requirements are materially ambiguous;
- a decision would substantially change behavior or architecture;
- destructive or irreversible work is required;
- scope would expand substantially;
- security or important data may be affected;
- investigation cannot establish a sufficiently safe approach;
- delegation is materially needed but a required role cannot be configured.

Never perform destructive or irreversible operations, out-of-scope changes, or
unnecessary access to secrets without explicit permission.

## Completion lifecycle

On normal completion:

- leave correctly configured delegated agents running for reuse;
- leave panes intact;
- do not close or rearrange user-owned panes;
- do not `/quit` agents merely because the current task completed.

Stop an agent only when:

- its configuration must be replaced;
- it is unhealthy or unusable;
- the user explicitly asks for cleanup.

## Delegation boundary

### Explorer

Use the explorer when investigation would materially reduce uncertainty, including
when:

- the root cause is unclear;
- multiple plausible explanations exist;
- external documentation, APIs, SDK behavior, or specifications need research;
- unfamiliar code or architecture requires investigation;
- security, compatibility, data-integrity, or operational assumptions need
  evidence.

Do not use the explorer merely because implementation is large.

### Fixer

Use the fixer when the implementation strategy is sufficiently established and
implementation is non-trivial, including when:

- multiple files or components must change;
- implementation complexity is meaningful;
- independent implementation materially reduces implementation or review risk.

Do not send unresolved investigation questions to the fixer as implementation
tasks.

### Direct handling

Handle work directly when it is trivial, local, low-risk, and delegation would
add more overhead than value.

Project-specific instructions and verification procedures take precedence over
this skill.
