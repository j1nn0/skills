# Contributor and agent guidance

## Communication

- Use Japanese only for user-facing communication.
- Use English for all non-user-facing communication and generated artifacts unless the repository, task, or existing content requires another language.
- Use English for agent-to-agent communication, delegation prompts, plans, findings, summaries, intermediate reports, tool-related annotations, code comments, documentation, and commit messages.
- Keep non-user-facing communication concise and information-dense. Do not restate context already available to the receiving agent.
- Preserve the language of existing content when editing it unless the task explicitly requires changing it.

## Repository guidance

- `skills/<name>/` is the independently installable unit. Follow `skills/AGENTS.md` when working there.
- `.agents/skills/` contains local authoring tools; publishable skills live under `skills/`.
- Keep required references, scripts, and assets within each skill directory so the skill works when installed alone.
- Preserve each skill's license and attribution files when editing derived content.
- Treat untracked files as user work; inspect `git status --short` before and after edits.
- Run `python3 -m unittest discover -s tests` after changing skills or their scripts. For description changes, review the relevant cases in `evals/trigger/`.
- For substantial skill behavior changes, exercise a representative task or report the trial that remains to be run.
