# skills

Portable agent skills for writing, editing, and maintaining agent behavior.

This repository keeps each skill as a portable directory. A skill should be understandable on its own, with its main instructions in `SKILL.md` and any required references, templates, examples, or scripts stored beside it.

## Available Skills

| Skill | Description |
| --- | --- |
| `writing-ja` | Self-contained Japanese writing and editing rules for blog posts, technical articles, and business documents. It combines argument structure, Japanese technical prose conventions, and human-sounding rewrite guidance, with conflict rules resolved against the j1nn0.com article style. |

## Repository Layout

```text
.
├── README.md
├── AGENTS.md
└── skills/
    ├── AGENTS.md
    └── writing-ja/
        └── SKILL.md
```

`skills/` is the canonical source directory. Each direct child of `skills/` is intended to be independently installable or copyable.

If a local `.agents/` directory exists, treat it as development-only material. It is not the canonical source for published skills unless a task explicitly says so.

## Skill Format

Each skill lives under `skills/<skill-name>/` and uses a lowercase kebab-case directory name.

The entry point is always `SKILL.md`. It should include YAML front matter with at least `name` and `description`, followed by concise instructions that explain when to use the skill, what to read, and what output to produce.

Supporting files belong inside the same skill directory so the skill remains portable. Do not place `AGENTS.md` inside a distributable skill directory because installers may copy that directory into another project.

No package manager, build system, automated test runner, or skill lock file is currently maintained in this repository.

## Maintenance

Before and after edits, check the working tree.

```sh
git status --short
```

After adding, moving, or removing skills, verify the available entry points.

```sh
find skills -name SKILL.md -print
```

For wording changes, read the rendered Markdown structure and confirm the skill still works without relying on files outside its own directory.
