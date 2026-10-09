# Assumption model

The record format read by `scripts/check_assumptions.py`. JSON, UTF-8.

## File shape

A records file is either an object holding a list:

```json
{"schema_version": 1, "assumptions": [{"id": "...", "...": "..."}]}
```

or one bare record object (handy for a one-off record piped on stdin). `schema_version` is optional and must be `1` when present.

## Record

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `id` | yes | string | Unique within the file. Lowercase letters, digits, `.`, `_`, `-`; starts with a letter or digit. |
| `statement` | yes | string | The assumption, as one falsifiable sentence. |
| `scope` | yes | string | Where and under which conditions it applies, in prose (component, environment, versions, time). |
| `evidence` | yes | non-empty list | What the assumption was accepted on. See "Evidence". |
| `conditions` | no | list | Machine-checkable applicability conditions. See "Conditions". |
| `watch` | no | list of strings | Extra repo-relative paths or glob patterns whose change should trigger revalidation. |
| `baseline` | no | object | The state the assumption was accepted against. See "Baseline". Without it, drift cannot be detected. |
| `verified_at` | no | string | ISO 8601 date of the last evidence-based verification. Informational; never set it without performing one. |
| `notes` | no | string | Free text. |

Unknown fields are ignored. Record only evidence that was actually observed; when the source of an assumption is unknown, say so in a `note` evidence item instead of guessing a file or URL.

## Paths

Every path (`evidence[].path`, `conditions[].path`, `watch[]`, `baseline.files` keys) is repo-relative, POSIX-separated, and stays inside the repository: no absolute paths, no `..` segments, and no symlink resolving outside the repository root. A record with an unsafe path is reported as `record_error` and not evaluated.

`watch` entries may use `*` (within one path segment), `?`, and `**` (zero or more directories). The `.git` directory is never matched.

The **watched set** of a record is: every file evidence path, every condition path, and every file matching a `watch` entry.

## Evidence

Each item has a `kind`; `description` is optional on `file` and `url` and required on `note`.

| Kind | Fields | Checker behaviour |
| --- | --- | --- |
| `file` | `path` (required), `pattern` (optional regex) | Reports whether the file exists now and, with `pattern`, whether the regex still matches its content (`re.search`, multiline). |
| `url` | `url` (required) | Never fetched. Listed under `agent_checks` for the agent to verify. |
| `note` | `description` (required) | Evidence with no locatable source, such as a manual observation. Listed under `agent_checks`. |

An unrecognised `kind` is reported as `unsupported` and listed under `agent_checks`; the rest of the record is still checked.

## Conditions

Conditions state the applicability scope in a form the checker can test against the current tree.

| Kind | Fields | Holds when |
| --- | --- | --- |
| `file_regex` | `path`, `pattern` | The file exists and the regex matches its content. |
| `json_value` | `path`, `pointer` (RFC 6901), `equals` (any JSON value) | The file parses as JSON and the value at `pointer` equals `equals`. |
| `text` | `description` | Not machine-checkable; listed under `agent_checks`. |

`description` is optional on `file_regex` and `json_value`. Condition results are `holds`, `does_not_hold` (including a missing JSON pointer), `unresolvable` (file missing or unparseable), or `manual` (`text`). A condition that no longer holds means the current state has left the assumption's recorded scope; it does not mean the assumption was false.

## Baseline

| Field | Meaning |
| --- | --- |
| `files` | Object mapping each watched path to `"sha256:<hex>"`, or `null` when the path did not exist. Written by `snapshot`. |
| `git_commit` | A commit the assumption was accepted against. Drift is the difference between that commit and the working tree (including uncommitted and untracked files) over the watched set. |

Either or both may be present; when both are, both are compared. `check --since <rev>` replaces the record baselines with `<rev>` for one run.

Create or refresh `files` only on explicit request, and only after the assumption has been verified against the current state: a refreshed baseline asserts "accepted against this state". `snapshot` prints the updated records to stdout; `snapshot --write` replaces the records file.

## Examples

Minimal record (no baseline; the checker reports evidence status only):

```json
{
  "id": "no-redis-queue",
  "statement": "Background jobs run in-process; the app does not need a Redis-backed queue.",
  "scope": "api service, production config",
  "evidence": [{"kind": "file", "path": "config/queue.yml", "pattern": "driver:\\s*sync"}]
}
```

Full record:

```json
{
  "schema_version": 1,
  "assumptions": [
    {
      "id": "pg-driver-no-pipeline",
      "statement": "The pg driver in use does not support query pipelining, so batch inserts use a manual transaction loop.",
      "scope": "api service with pg 8.11.x on Node 20",
      "conditions": [
        {"kind": "json_value", "path": "package.json", "pointer": "/dependencies/pg", "equals": "^8.11.0"},
        {"kind": "file_regex", "path": ".nvmrc", "pattern": "^20\\."}
      ],
      "evidence": [
        {"kind": "file", "path": "src/db/batch.ts", "pattern": "manual transaction loop", "description": "Workaround and its comment"},
        {"kind": "url", "url": "https://node-postgres.com/apis/client", "description": "Client API docs consulted for 8.11"}
      ],
      "watch": ["package-lock.json", "src/db/**"],
      "baseline": {"git_commit": "3f2a9c1"},
      "verified_at": "2026-03-14"
    }
  ]
}
```

A one-off record needs no file in the target repository:

```bash
echo '{"id": "...", "statement": "...", "scope": "...", "evidence": [...], "baseline": {"git_commit": "<rev>"}}' \
  | python3 scripts/check_assumptions.py check --repo <repo> --records -
```
