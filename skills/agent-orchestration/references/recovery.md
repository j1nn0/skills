# Recovery

Submission, timeout, `blocked`, and stuck-agent handling for
`agent-orchestration`. Read this when a prompt is rejected, times out, settles on
`blocked`, or an agent appears stuck.

Separate the two kinds of failure before reacting. A prompt can fail at
submission, before any input reaches the agent, or it can fail after the agent
started working. Only the second kind is ever about the agent being stuck, and
interrupting the first kind makes the situation worse.

## Submission failures

`herdr agent prompt` reports these instead of delivering the prompt.

`agent_blocked` — the agent is already sitting at an approval or question UI, so
Herdr refused the submission. This is not the same as a prompt that settles on
`blocked`; here nothing was sent. Inspect the UI with `herdr agent read`, then
follow the permission handling at the end of this file.

`agent_prompt_stalled` — the text was submitted, but no state change was
observed within 5000ms, so the agent likely never started a turn. Common causes
are a slash command that returns immediately, an empty or malformed prompt, or a
pane no longer running the agent. Read the recent output and confirm the agent
with `herdr agent get` before resending; do not interrupt, and do not assume the
prompt was lost until you have looked. A turn that finished before `working` was
observed can also report this: if the "Waiting" freshness check in `SKILL.md`
returns `completion_advanced`, read the result instead of resending. A
`no_progress` verdict after any wait is handled like this failure.

## After the agent starts working

A timeout alone does not mean the agent is stuck.

After a timeout, inspect:

- `herdr agent get`, with the "Waiting" freshness check; `progress_observed`
  means the turn is still running;
- recent output with `herdr agent read`;
- the foreground process state when relevant.

No new agent output by itself is not evidence of failure. Long-running tests,
builds, analysis, searches, or other commands may legitimately remain quiet.

Interrupt with:

```bash
herdr agent send-keys <name> ctrl+c
```

only when the inspection above shows no progress or the agent is clearly stuck.

After interruption, inspect the last output and choose one of:

- continue with a more focused prompt;
- reduce the task scope;
- return to the explorer if the cause is uncertain;
- change the strategy;
- escalate.

## Permission and approval UIs

An agent is `blocked` whenever Herdr recognizes an approval or question UI —
because a prompt settled there, because a submission was refused with
`agent_blocked`, or because `agent start` returned `agent_not_ready`. Inspect
the cause before retrying. Handle expected permission prompts safely, and ask the
user before answering one on their behalf. Never weaken or bypass the permission
policy merely to make progress.


## Convergence status mapping

These outcomes map to Parallel Explorers convergence status ([`parallel.md`](parallel.md)):

- `agent_blocked` (submission refused before input was sent) and a prompt that settles on `blocked`: the unit has not settled; while recovery is possible it is `incomplete` (recoverable), not `failed`.
- `agent_prompt_stalled`, or no observable progress after a batch submission within the bounded liveness window: submission/start failure → `incomplete`; inspect and re-prompt the same unit before judging it.
- Interruption before an accepted result: `incomplete`; resume the same unit. Accepted sibling results are kept and never rerun.
- Timeout during collection: inspect before deciding; the unit remains `incomplete`/`running` until it settles. A timeout alone is not a terminal failure, and successful siblings are preserved.
- No valid `HERDR_RESULT` after the unit settles: `incomplete`, with the evidence gap recorded; an invalid or missing result is never promoted to success.

Only after the Orchestrator has exhausted or deliberately abandoned recovery for a unit may it record terminal `failed` with one or more explicit non-empty `gaps` for `ready_with_gaps`. Recoverable operational failures must never be normalized to terminal `failed` merely so a batch can converge.
