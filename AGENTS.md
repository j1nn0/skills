<!-- Generated: 2026-07-07 | Updated: 2026-07-07 -->

# skills

## Purpose
This repository stores portable agent skill definitions. Each skill is meant to be self-contained so it can be copied, installed, reviewed, and maintained independently.

## Key Files

| File | Description |
|------|-------------|
| `README.md` | Minimal repository overview. |
| `skills-lock.json` | Records locally installed skill sources and hashes when present. |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `skills/` | Canonical skill definitions for this repository. See `skills/AGENTS.md`. |
| `.agents/` | Local or vendored agent assets used during development; do not treat as canonical skill source unless the user asks. |

## For AI Agents

### Working In This Directory

- Keep reusable skills under `skills/<skill-name>/` with lowercase kebab-case directory names.
- Keep the primary instructions for every skill in `SKILL.md`.
- Make each skill directory portable: references, templates, examples, and scripts needed by a skill should live inside that skill directory.
- Do not put `AGENTS.md` inside a distributable skill directory. Installers may copy the full skill directory into another project, where extra agent instructions can affect that project unexpectedly.
- Prefer concise Markdown with concrete trigger rules, scope boundaries, workflow steps, and output expectations.
- Do not introduce package manifests, build tooling, or generated metadata unless the change requires it.
- Treat untracked files as user work. Do not remove or rewrite them unless the user explicitly asks.

### Testing Requirements

- Run `git status --short` before and after edits.
- Run `find skills -name SKILL.md -print` when adding or moving skills.
- For skill wording changes, manually review the rendered Markdown structure and verify the skill remains self-contained.
- For larger behavioral changes, run or describe a trial task that exercises the updated skill.

### Common Patterns

- Skill directories use kebab-case, for example `skills/article-editor/`.
- Skill entry files are always named `SKILL.md`.
- Markdown headings should be stable and descriptive because agents use them for navigation.
- Repository-level prose should stay in English unless the file is intentionally language-specific.

## Dependencies

### Internal

- `skills/writing-ja/` is the current canonical skill in this repository.

### External

- No runtime dependencies, package manager, build system, or automated test runner are configured.

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
