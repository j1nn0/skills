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
| `no_baseline` | No baseline covers the whole watched set (none recorded, `git_commit` unresolvable, a watched path git ignores, or an empty watched set), and no change signal was found. Drift is unknown, not absent. |
| `record_error` | The record is malformed or has an unsafe path; nothing else was evaluated. |

### Change signals

| Signal | Source |
| --- | --- |
| `modified`, `deleted`, `added` | Watched-set difference against `baseline.files` or `baseline.git_commit` (`added`: the path is present now and absent from the baseline). |
| `condition_changed` | A `file_regex` or `json_value` condition now evaluates `does_not_hold` or `unresolvable`. |
| `evidence_missing` | A file evidence path does not exist now. |
| `evidence_anchor_missing` | A file evidence path exists but its `pattern` does not match the current content. Anchors are evaluated on the working tree only, never at the baseline. |

Notices that are not change signals:

- `baseline_unavailable`: git missing, not a repository, or commit unresolvable.
- `ignored_by_git`: a watched path git ignores, so a `git_commit` baseline cannot know its earlier state. Cover such paths with `baseline.files`.
- `empty_watched_set`: the record watches nothing, so no drift can be observed.
- `skipped_outside_root`: a watch match that is a symlink leaving the repository.

A `git_commit` comparison sees content as git does: after line-ending conversion and the clean filters configured for the repository (such as git-lfs), which git runs as programs while comparing. Use `baseline.files` for byte-level comparison or for a repository whose git configuration you do not trust.

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

Assign exactly one verdict per assumption, judged **within its recorded conditions**: evidence about a state those conditions exclude (a newer version, a moved runtime) bears on applicability, not on the verdict.

| Verdict | Criteria (all must hold) |
| --- | --- |
| `valid` | Evidence inspected in this audit positively supports the statement within its conditions, and nothing bearing on it is left open: every change signal was investigated and found irrelevant or consistent, and every `agent_checks` item bearing on the statement was verified against an authoritative source. |
| `recheck_required` | Something bearing on the statement is unresolved (a change signal, an `agent_checks` item, or a gap found while inspecting), no contradiction is established, and a named verification step could settle it: reading a source, recovering a file from history, rerunning an experiment with the user's go-ahead. |
| `invalid` | Authoritative current evidence within the statement's conditions directly contradicts it, and that evidence is cited. |
| `unknown` | The available evidence neither supports nor contradicts the statement, and no available step can supply what is missing: the source is gone everywhere, was never recorded in a checkable form, or cannot be reached. |

Decide in this order:

1. `invalid` when a cited, direct contradiction within the conditions exists.
2. Otherwise `recheck_required` when anything bearing on the statement is unresolved and a named step could settle it.
3. Otherwise `valid` when the evidence positively supports the statement with nothing left open.
4. Otherwise `unknown`.

### Rules

- File changes alone never establish `invalid`. Read what changed: a version bump inside the same supported range, a refactor that keeps the behaviour, or a comment edit can leave the assumption intact.
- Missing evidence is never proof of invalidity. Say what is missing, and name the step that could recover or replace it (such as `git show <rev>:<path>` for a deleted file); with no such step, the verdict is `unknown`.
- Unchanged local files never establish that an external assumption still holds. An assumption resting on upstream behaviour or a specification stays `recheck_required` or `unknown` until the external source is checked.
- Without network access, external evidence stays unverified: record "not verified offline" and the exact source to check next, never a reconstructed or remembered answer.
- A `does_not_hold` condition moves the current state outside the assumption's scope. Judge the statement within its original conditions, and report applicability to the current state separately. An `unresolvable` condition leaves applicability unknown until the agent reads the file.
- Contradiction must be direct: evidence within the statement's conditions asserts the opposite (for example, the changelog of the installed version documents support for feature X that the assumption says is missing). An inference chain ending in "probably no longer true" is `recheck_required`.

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
