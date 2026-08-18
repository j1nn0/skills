---
name: agent-orchestration
description: >-
  Orchestrates non-trivial software engineering work across three agents in a
  Herdr session: the current agent stays the orchestrator and reviewer, Pi
  `explorer` investigates and researches, and Pi `fixer` implements. Use when
  delegation would materially reduce uncertainty, implementation risk, or review
  risk. Requires HERDR_ENV=1 and builds on the herdr skill for pane and agent
  control. Do not use for trivial tasks the current agent can safely handle
  directly.
---

# Agent Orchestration

You remain the orchestrator and reviewer for the whole task. Never delegate the implementation
strategy, review, or completion decision.

Use the `herdr` skill as the authority for pane and agent CLI syntax.

## Roles

| Role | Agent | Kind | Model / effort |
| --- | --- | --- | --- |
| Orchestration, decisions, review | Current agent | — | Current model |
| Investigation and research | Pi `explorer` | `pi` | `opencode-go/deepseek-v4-flash`, `thinking: max` |
| Implementation | Pi `fixer` | `pi` | `openai-codex/gpt-5.6-luna`, `thinking: max` |

The explorer is read-only. Only the fixer intentionally modifies project files.

## Startup

Delegation requires a Herdr-managed pane:

```bash
test "${HERDR_ENV:-}" = 1
```

If that fails, do the task yourself. Do not run Pi in the orchestrator pane as a substitute.

All delegated agents must run in the orchestrator's current tab. Treat `$HERDR_TAB_ID` as a hard
placement and reuse boundary. Never use an agent or pane from another tab for explorer or fixer.

Before delegation:

1. Run `herdr agent list` and `herdr agent`; confirm the `pi` kind is available.
2. Resolve each required agent slot:
   1. Check whether the named agent is live.
   2. Reuse it only if its `tab_id` equals `$HERDR_TAB_ID` and its kind, model, and thinking level
      match the table above.
   3. Never reuse, stop, replace, or repurpose an agent from another tab.
   4. If an agent with the preferred name exists in another tab, choose a unique name for the
      same-tab agent and use that resolved name for all later commands.
   5. If a same-tab agent has the wrong configuration, send `/quit` and wait until it disappears
      from `herdr agent list`.
   6. Confirm with `herdr pane process-info --pane <id>` that its pane has returned to the
      interactive shell.
   7. If shutdown or shell availability cannot be confirmed, stop delegation for that role.
3. Resolve `<pane-id>` only from panes in `$HERDR_TAB_ID`. A pane from another tab is never a valid
   candidate, even if it is idle and in the same workspace.
4. Use only a same-tab pane whose process info shows an available interactive shell with no
   foreground agent, editor, or command.
5. If no suitable same-tab pane exists, create one by splitting a pane that is already in
   `$HERDR_TAB_ID`, normally the orchestrator pane:

   ```bash
   herdr pane split --current --direction right --cwd "$PWD" --no-focus
   ```

   Use the pane ID returned by Herdr. Never select a free pane from another tab as a substitute.
6. Start the role with its pinned command below.
7. After startup, verify with `herdr agent get <resolved-name>` that its `tab_id` equals
   `$HERDR_TAB_ID`. If it does not, stop delegation for that role.
8. If any required kind, model, thinking level, pane, or start operation fails, stop delegation for
   that role. Never silently fall back to a different configuration or another tab.

### Explorer

```bash
herdr agent start <explorer-name> --kind pi --pane <pane-id> -- \
  --model opencode-go/deepseek-v4-flash \
  --thinking max \
  --no-autoformat \
  --no-autofix
```

Use `explorer` as `<explorer-name>` when available. If that name is already owned by an agent in
another tab, choose a unique name for the same-tab explorer.

### Fixer

```bash
herdr agent start <fixer-name> --kind pi --pane <pane-id> -- \
  --model openai-codex/gpt-5.6-luna \
  --thinking max \
  --no-autoformat \
  --no-autofix
```

Use `fixer` as `<fixer-name>` when available. If that name is already owned by an agent in another
tab, choose a unique name for the same-tab fixer.

Both delegated agents intentionally use Pi's normal installed extensions, skills, and tools. The
skill pins only the role-specific model and thinking level.

## Workflow

1. Define the objective, constraints, scope, and completion criteria.
2. Delegate investigation when the **Delegation boundary** applies and evidence is needed.
3. Evaluate the explorer's findings yourself. Do not pass them directly to the fixer as instructions.
4. Decide the implementation strategy and scope.
5. Delegate implementation to the fixer when warranted.
6. Review the actual diff and verification results yourself.
7. Re-investigate or re-implement when needed, then confirm the completion criteria.

## Handoffs

Delegated agents do not share your conversation. Every prompt must be standalone and assign one role
only. Unless explicitly instructed by you, delegated agents must not invoke `agent-orchestration` or
delegate their own work.

Require every delegated response to end with one concise final result block:

```text
<HERDR_RESULT>
...
</HERDR_RESULT>
```

When reading agent output, use the last complete `HERDR_RESULT` block as the handoff result and ignore
preceding thinking or progress output. If no complete block is visible, ask the agent to re-emit only
its final result without repeating the work.

### Explorer handoff

Give the explorer the objective, relevant paths or systems, constraints, and questions to answer.
Require a concise report containing:

- conclusion;
- evidence and sources;
- relevant code, files, APIs, or specifications;
- constraints and impact;
- alternatives when relevant;
- hypothesis and confidence when applicable.

Prefer primary official sources for external technical research.

If any required field is missing or confidence is explicitly too low to proceed safely, send a focused
follow-up that states exactly what evidence or information is missing before deciding the strategy.

Keep the result concise enough to recover reliably from the pane; if necessary, ask the explorer to
re-emit a shorter final result rather than repeat the investigation.

### Fixer handoff

Before every fixer task, send `/new` and wait for the new session to settle. This applies to the first
implementation task, each subsequent implementation unit, and retries. Never rely on fixer context
from a previous task; every fixer prompt after `/new` must be standalone.

Give the fixer the objective, scope, constraints, chosen strategy, completion criteria, and relevant
validated findings. Let the fixer make local implementation decisions inside those boundaries.

## Waiting and recovery

`herdr agent prompt <name> --wait` settling on `idle`, `done`, or `blocked` is authoritative when the
integration is healthy.

A timeout alone means the agent may still be working. Inspect `herdr agent get` and
`herdr agent read` before intervening.

If two consecutive polls show no new output and the agent is not `blocked`, interrupt it with
`herdr agent send-keys <name> ctrl+c`, inspect its last output, then either re-prompt with a smaller
scoped task or escalate.

If an agent is `blocked`, inspect why and address the cause before retrying. Handle expected permission
prompts safely; never weaken or bypass the permission policy just to make progress.

## Review and retry

Verify independently. Read the diff and run the project's own verification rather than trusting the
fixer's report.

Review for:

- completion criteria;
- consistency with the chosen strategy;
- out-of-scope or unnecessary changes;
- unintended behavior changes;
- verification results;
- whether the change addresses the root cause.

If the same problem recurs, stop stacking local fixes. Re-evaluate the assumptions and strategy,
return to the explorer when the cause is uncertain, then give the fixer an updated bounded task.

If retries produce no meaningful progress, change the approach or consult the user.

## Recommended layout

```text
┌──────────────────────────────┬──────────────────────┐
│                              │       Explorer       │
│                              │         ~25%         │
│      Current agent           ├──────────────────────┤
│        Orchestrator          │        Fixer         │
│           ~50%               │         ~25%         │
└──────────────────────────────┴──────────────────────┘
```

Keep explorer and fixer in the orchestrator's current tab. Treat `$HERDR_TAB_ID` as an isolation
boundary for delegated-agent placement and reuse. Preserve existing user-owned panes and readability;
use the `herdr` skill for layout changes.

## Escalation

Consult the user when requirements are materially ambiguous, a decision would substantially change
behavior or architecture, destructive or irreversible work is required, scope would expand
substantially, security or important data may be affected, or investigation cannot establish a safe
approach.

Never perform destructive or irreversible operations, out-of-scope changes, or unnecessary access to
secrets without explicit permission.

## Delegation boundary

Delegate when at least one applies:

- the root cause or implementation strategy is not obvious from local inspection;
- multiple plausible explanations or approaches require investigation;
- external documentation, APIs, SDK behavior, or specifications need research;
- the change crosses logical or architectural boundaries;
- security, compatibility, data-integrity, or operational risk is meaningful;
- implementation is complex enough that independent investigation, implementation, and review
  materially reduce risk.

Handle trivial, local, low-risk work directly when delegation would add more overhead than value.

Project-specific instructions and verification procedures take precedence over this skill.
