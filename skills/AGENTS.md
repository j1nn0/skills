<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-07-07 | Updated: 2026-07-07 -->

# skills

## Purpose
Container directory for reusable agent skills. Each direct child directory should represent one independently installable skill.

## Key Files

No standalone files are expected here. Put each skill's entry point in its own `skills/<skill-name>/SKILL.md`.

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `writing-ja/` | Japanese writing and editing skill. |

## For AI Agents

### Working In This Directory

- Add new skills as `skills/<skill-name>/SKILL.md`.
- Keep skill names lowercase and kebab-case.
- Do not add `AGENTS.md` inside `skills/<skill-name>/`; that directory is the copyable distribution unit for installers.
- Do not share required references across sibling skill directories unless they are intentionally duplicated or moved into a documented common location.
- Keep each skill's description precise enough for automatic routing.

### Testing Requirements

- Run `find skills -name SKILL.md -print` after adding, removing, or renaming skills.
- Read the full `SKILL.md` after editing to catch broken headings, references, or incomplete instructions.

### Common Patterns

- Each skill starts with YAML front matter containing at least `name` and `description`.
- Supporting assets belong inside the same skill directory.

## Dependencies

### Internal

- Parent repository guidance is in `../AGENTS.md`.

### External

- None.

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
