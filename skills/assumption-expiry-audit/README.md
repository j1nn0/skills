# assumption-expiry-audit

Audits whether engineering assumptions a project already accepted still hold: "pg 8.11 has no pipelining, so batch inserts use a manual loop", "jobs run in-process, so no Redis queue", "this polyfill exists because Node 18's fetch lacks X". Each assumption carries its conditions, evidence, and a baseline; a read-only checker reports what moved since the baseline, and the agent then decides, from current evidence, whether the assumption is `valid`, `recheck_required`, `invalid`, or `unknown`.

Use it after an upgrade, a dependency or configuration change, or before relying on an old decision (an ADR premise, a workaround's justification). It works for one assumption stated in conversation (no files created) and for a recorded set kept in the repository.

## How it differs

- **From fact-checking** (such as `fact-check-ja`): fact-checking verifies claims in prose against primary sources once. This skill audits premises the codebase already depends on, against a recorded baseline and applicability conditions, and separates "something changed" from "the assumption is false".
- **From decision logs and ADR tooling** (adr-tools, Log4Brains, decision-log skills): those record and link decisions but never notice that a decision's supporting evidence moved.
- **From diff-scoped assumption extractors** (for example [Teycir/Assumptions](https://github.com/Teycir/Assumptions)): those surface assumptions in a change once; this skill re-audits stored assumptions against their own baselines over time.
- **From ADR drift and doc-freshness checkers** ([adr-kit](https://github.com/rvdbreemen/adr-kit) Guardian, [docfresh](https://github.com/os-tack/docfresh)): the closest neighbours. adr-kit judges ADR sets against a recent commit window; docfresh tracks page-to-source freshness. This skill keeps a per-assumption baseline and applicability conditions, has the checker report drift only, and never turns a change or a missing source into `invalid`.
- **From dependency updaters** (Renovate, Dependabot, upgrade skills): those manage the upgrade itself; this skill tells you which earlier premises the upgrade puts in question.

These comparisons reflect the projects as checked on 2026-10-09.

## Install

```sh
npx skills@latest add j1nn0/skills -s assumption-expiry-audit
```

It needs Python 3 (standard library only) and, for `git_commit` baselines, `git`. It does not depend on Herdr or any other skill.

## Example

Ask the agent:

> We upgraded pixelpipe last week. Is the recorded assumption `pixelpipe-has-no-avif-output` in `docs/assumptions.json` still valid? Audit only.

A minimal record:

```json
{
  "id": "no-redis-queue",
  "statement": "Background jobs run in-process; the app does not need a Redis-backed queue.",
  "scope": "api service, production config",
  "evidence": [{"kind": "file", "path": "config/queue.yml", "pattern": "driver:\\s*sync"}]
}
```

Add `conditions`, `watch`, and `baseline` to detect drift; see [`references/assumption-model.md`](references/assumption-model.md). Record a baseline from the current state only after verifying the assumption against it:

```sh
python3 scripts/check_assumptions.py snapshot --repo . --records docs/assumptions.json          # prints, writes nothing
python3 scripts/check_assumptions.py snapshot --repo . --records docs/assumptions.json --write  # updates the records file
```

Checker output after the pixelpipe upgrade (abridged; exit code 1):

```json
{
  "id": "pixelpipe-has-no-avif-output",
  "status": "changed",
  "signals": [
    {"type": "modified", "path": "package-lock.json", "source": "baseline.files", "detail": "SHA-256 differs from baseline"},
    {"type": "modified", "path": "package.json", "source": "baseline.files", "detail": "SHA-256 differs from baseline"}
  ],
  "agent_checks": [{"source": "evidence", "index": 0, "kind": "url", "reason": "URL evidence is never fetched by the checker"}]
}
```

The agent's report for it, offline:

```markdown
### pixelpipe-has-no-avif-output: recheck_required

- Statement: The external pixelpipe library does not support AVIF output. (scope: pixelpipe versions used by the image service)
- Applies to current state: unknown; no machine-checkable conditions are recorded
- Observations:
  - package.json and package-lock.json changed since the baseline, from checker signals `modified`
  - the lockfile now resolves pixelpipe 4.3.1, from package-lock.json
  - the 4.2 output-format docs were not fetched, from checker `agent_checks` (network unavailable)
- Interpretation: the upgrade could have added AVIF output; nothing inspected confirms or contradicts that.
- Verdict: recheck_required; a relevant change exists and no contradiction is established
- Limitations: upstream documentation not verified offline
- Recommendation: revalidate; read the pixelpipe 4.3.1 changelog and output-format docs
```

## Limitations

- The checker sees only the local tree. Upstream behaviour, specifications, and hosted services can change with no local trace; such assumptions stay `recheck_required` or `unknown` until the agent checks the source.
- Drift detection is only as good as the watched set: a relevant file left out of `evidence`, `conditions`, and `watch` is not monitored.
- Conditions cover regex matches and exact JSON values. Version ranges, lockfile semantics, and other formats are not interpreted; the agent reads them.
- `git_commit` baselines compare content as git sees it: external diff and textconv drivers are disabled, but line-ending conversion and the clean filters configured for the repository (git-lfs and the like) apply, and git runs those filter programs. Use a `files` baseline for repositories whose git configuration you do not trust.
- Git cannot know the earlier state of files it ignores (local config, `.env`). A `git_commit` baseline reports them as `ignored_by_git` and the record as `no_baseline` unless a `files` baseline covers them.
- Evidence `pattern` anchors are checked against the working tree only, never at the baseline revision.
- Verdicts are agent judgments under written criteria, not proofs. The behavior evaluation suite measures how consistently a model follows them.
