# Recovery

Timeout, `blocked`, and stuck-agent handling for `agent-orchestration`. Read this
when a prompt times out, an agent settles on `blocked`, or an agent appears
stuck.

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

only when the inspection above shows no progress or the agent is clearly stuck.

After interruption, inspect the last output and choose one of:

- continue with a more focused prompt;
- reduce the task scope;
- return to the explorer if the cause is uncertain;
- change the strategy;
- escalate.

If an agent is `blocked`, inspect the cause before retrying. Handle expected
permission prompts safely; never weaken or bypass the permission policy merely
to make progress.
