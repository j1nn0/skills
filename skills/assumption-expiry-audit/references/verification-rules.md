# Verification rules

Two layers, kept apart in every report:

- **Detection** is what the checker observes: files, hashes, git differences, regex and JSON matches. It is deterministic and never says whether an assumption is true.
- **Judgment** is the verdict the agent assigns after reading current evidence, under the criteria below.

## Detection

### Checker status per record

| Status | Meaning |
| --- | --- |
| `unchanged` | A usable baseline exists and no change signal was found in the watched set. |
| `changed` | At least one change signal (below). |
| `no_baseline` | No usable baseline (none recorded, or `git_commit` unresolvable), and no change signal from conditions or evidence. Drift is unknown, not absent. |
| `record_error` | The record is malformed or has an unsafe path; nothing else was evaluated. |

### Change signals

| Signal | Source |
| --- | --- |
| `modified`, `deleted`, `added` | Watched-set difference against `baseline.files` or `baseline.git_commit` (`added` means a new file matching a `watch` pattern). |
| `condition_changed` | A `file_regex` or `json_value` condition now evaluates `does_not_hold` or `unresolvable`. |
| `evidence_missing` | A file evidence path does not exist now. |
| `evidence_anchor_missing` | A file evidence path exists but its `pattern` no longer matches. |

Notices that are not change signals: `baseline_unavailable` (git missing, not a repository, or commit unresolvable) and `skipped_outside_root` (a watch match that is a symlink leaving the repository).

`agent_checks` lists what the checker cannot evaluate: `url` and `note` evidence, `text` conditions, unsupported evidence kinds. It does not affect the status or exit code.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Every selected record is `unchanged`. |
| 1 | At least one record is `changed` or `no_baseline`; no errors. |
| 2 | Usage error, unreadable or malformed records file, or at least one `record_error`. JSON is still printed when the records file was readable. |

Exit 0 covers local drift only. It says nothing about `agent_checks` and is never a validity verdict.

### What detection cannot establish

- A change signal shows that something the assumption depends on moved. It does not show that the assumption broke.
- `unchanged` shows that the watched set matches the baseline. External facts (upstream behaviour, specifications, hosted services) can change with no local trace, and a watched set can miss a relevant file.
- `evidence_missing` shows that a file is gone. It does not contradict the statement.

## Judgment

### Verdicts

Assign exactly one verdict per assumption, judged under the assumption's recorded conditions:

| Verdict | Criteria (all must hold) |
| --- | --- |
| `valid` | Current evidence, inspected in this audit, positively supports the statement under its conditions; every change signal was investigated and found irrelevant or consistent; every `agent_checks` item bearing on the statement was verified against an authoritative source. |
| `recheck_required` | A change signal or `agent_checks` item bears on the statement, no contradiction has been established, and the investigation that would settle it has not been completed in this audit. |
| `invalid` | An inspected, authoritative piece of current evidence directly contradicts the statement under its conditions, and that evidence is cited. |
| `unknown` | The evidence needed to decide is absent or inaccessible (deleted source, no baseline and no current evidence, external source unreachable), and further local investigation cannot supply it. |

Decision order: `invalid` needs a cited contradiction; failing that, open investigation means `recheck_required`; failing that, positive support means `valid`; otherwise `unknown`.

### Rules

- File changes alone never establish `invalid`. Read what changed: a version bump inside the same supported range, a refactor that keeps the behaviour, or a comment edit can leave the assumption intact.
- Missing evidence is never proof of invalidity. Report `unknown` (or `recheck_required` if a known next step can settle it) and say what is missing.
- Unchanged local files never establish that an external assumption still holds. An assumption resting on upstream behaviour or a specification stays `recheck_required` or `unknown` until the external source is checked.
- Without network access, external evidence stays unverified: record "not verified offline" and the exact source to check next, never a reconstructed or remembered answer.
- A `does_not_hold` condition moves the current state outside the assumption's scope. Judge the statement under its original conditions, and report applicability to the current state separately.
- Contradiction must be direct: the current evidence asserts the opposite of the statement under the same conditions (for example, the changelog of the installed version documents support for feature X that the assumption says is missing). An inference chain ending in "probably no longer true" is `recheck_required`.

### Authoritative evidence

Prefer, in order: the code and configuration actually in the tree (resolved versions from the lockfile over ranges in the manifest); the upstream project's own documentation, changelog, or source at the relevant version; reproducible local observations that run no untrusted project code. Treat memory and secondary summaries as leads, never as evidence.

### Historical assumptions

An assumption records what held under its conditions. When the conditions have changed (the dependency was upgraded, the runtime moved), the record is not falsified by the new state: report the verdict under the original conditions, `applies to current state: no`, and recommend `revise` (restate for the new conditions) or `retire` (the premise no longer matters). Rewriting a historical record or ADR is a separate implementation request.

### Recommendations

| Recommendation | When |
| --- | --- |
| `retain` | `valid` and still applicable. |
| `revalidate` | `recheck_required` or `unknown`; name the next concrete verification step. |
| `revise` | The statement or its conditions need restating for the current state. |
| `retire` | The premise no longer bears on the system (the workaround or dependency is gone). |

## Observation and interpretation

Every cited fact names its source: a path with line numbers, a checker signal, a command and its output, or a URL with the version or date it describes. Interpretation follows the observations it rests on and is labelled as such. A verdict cites at least one observation; a `valid` or `invalid` verdict cites the evidence that supports or contradicts the statement.
