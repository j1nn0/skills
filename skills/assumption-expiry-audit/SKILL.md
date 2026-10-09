---
name: assumption-expiry-audit
description: >-
  Audits whether previously accepted engineering assumptions still hold: the
  premises behind architecture decisions, workarounds, dependency or runtime
  limitations, and configuration choices. Detects local drift since a recorded
  baseline with a read-only checker, then gives each assumption an
  evidence-backed verdict (valid, recheck required, invalid, unknown). Use when
  asked whether an earlier decision, ADR premise, or workaround is still
  justified after an upgrade, dependency, configuration, or specification
  change, or which recorded assumptions recent changes affect. Article
  fact-checking, library selection, and ordinary debugging are out of scope.
---

# Assumption Expiry Audit

An **assumption** is a statement accepted as true under stated conditions on identifiable evidence. It **expires** when those conditions or that evidence change. Expiry is a reason to investigate, never a verdict: the audit ends on evidence, not on drift.

The audit is read-only. Collect evidence by reading files, running read-only `git` commands, and running the checker; running project scripts, builds, or tests needs the user's go-ahead. A `git_commit` baseline makes git run the clean filters configured for the repository; for a repository whose git configuration you do not trust, use a `files` baseline. Changing code, dependencies, assumption records, baselines, or architecture decisions, removing a workaround, and committing are separate requests the user makes explicitly.

## Entry points

- **One supplied assumption.** Build a record in memory and pipe it to the checker with `--records -`; create no file.
- **A records file.** Audit the records the user names, or the subset given with `--id`.
- **Recent changes.** Run `check --since <rev>` over a records file to find the assumptions a change range touches.

## Workflow

1. **Pin the assumption.** Express each one as a record: statement, scope, conditions, and the evidence actually observed. Read [`references/assumption-model.md`](references/assumption-model.md) before writing or interpreting a record. When the original evidence is unknown, record that as a `note`; never invent a source.
2. **Fix the baseline.** Use the record's baseline. For a one-off, take the commit or version the assumption was accepted against from the user, an ADR, or `git log`. Without one, drift stays unknown and the audit rests on current evidence alone.
3. **Detect.** Run the checker. This step is done when every record has a status.

   ```bash
   python3 <skill-dir>/scripts/check_assumptions.py check --repo <repo> --records <file|-> [--id <id>...] [--since <rev>]
   ```

4. **Triage.** `changed`, `no_baseline`, and every `agent_checks` item need investigation; `record_error` needs the record fixed first. Read [`references/verification-rules.md`](references/verification-rules.md) now: it defines the statuses, signals, and verdicts.
5. **Investigate.** For each signal, read what actually changed (`git diff <rev> -- <path>`, the lockfile's resolved version, the edited config). For external facts, consult the upstream documentation, changelog, or source for the relevant version when the network is available. When it is not, record the limitation and the exact source to check next.
6. **Judge.** Assign one verdict per assumption under the criteria in `verification-rules.md`, judged under the assumption's original conditions. Done when every verdict cites the observations it rests on.
7. **Report and recommend** in the format below.

## Report

One section per assumption, then a summary table (`id | verdict | applies now | recommendation`).

```markdown
### <id>: <verdict>

- Statement: <statement> (scope: <scope>)
- Applies to current state: yes | no | unknown, with the condition results
- Observations:
  - <fact>, from <checker signal | path:line | command | URL @ version>
- Interpretation: <reasoning from the observations above>
- Verdict: valid | recheck_required | invalid | unknown, with the criterion met
- Limitations: <what was not or could not be verified>
- Recommendation: retain | revalidate | revise | retire, with the next concrete step
```

Keep observations and interpretation in their own fields. When the user asks for follow-up changes, list them as proposals for a separate request.
