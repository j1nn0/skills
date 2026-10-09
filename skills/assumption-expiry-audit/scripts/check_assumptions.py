#!/usr/bin/env python3
"""Deterministically inspect assumption evidence and local drift."""

import argparse
import hashlib
import json
import os
import posixpath
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


NOTE = "Statuses report local observations only; they are not validity verdicts."
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
HASH_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


class RecordsError(ValueError):
    pass


class RecordError(ValueError):
    pass


class UsageError(ValueError):
    pass


def reject_json_constant(_value):
    raise ValueError("non-standard JSON constant")


def emit_json(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def empty_check_result(errors=None):
    return {
        "schema_version": 1,
        "summary": {
            "total": 0,
            "unchanged": 0,
            "changed": 0,
            "no_baseline": 0,
            "record_error": 0,
        },
        "errors": [] if errors is None else errors,
        "assumptions": [],
        "note": NOTE,
    }


def load_document(text):
    try:
        document = json.loads(text, parse_constant=reject_json_constant)
    except (ValueError, TypeError, RecursionError):
        raise RecordsError("records are not valid JSON")

    if not isinstance(document, dict):
        raise RecordsError("records must be an object")
    if "schema_version" in document:
        version = document["schema_version"]
        if type(version) is not int or version != 1:
            raise RecordsError("schema_version must be 1")

    if "assumptions" in document:
        records = document["assumptions"]
        if not isinstance(records, list):
            raise RecordsError("assumptions must be a list")
        ids = set()
        for record in records:
            if isinstance(record, dict) and isinstance(record.get("id"), str):
                record_id = record["id"]
                if record_id in ids:
                    raise RecordsError("duplicate assumption ids")
                ids.add(record_id)
        return document, records, False

    return document, [document], True


def read_records(source):
    try:
        if source == "-":
            text = sys.stdin.read()
        else:
            with open(source, "r", encoding="utf-8") as records_file:
                text = records_file.read()
    except (OSError, UnicodeError, ValueError):
        raise RecordsError("records file could not be read")
    return load_document(text)


def normalized_path(value, field):
    if not isinstance(value, str):
        raise RecordError(field + " must be a string")
    if not value:
        raise RecordError(field + " must not be empty")
    if "\x00" in value:
        raise RecordError(field + " contains a NUL byte")
    if "\\" in value:
        raise RecordError(field + " must use POSIX separators")
    if value.startswith("/"):
        raise RecordError(field + " must be repository-relative")
    if ".." in value.split("/"):
        raise RecordError(field + " must not contain '..' segments")
    normalized = posixpath.normpath(value)
    if normalized in ("", "."):
        raise RecordError(field + " must name a file")
    if normalized == ".." or normalized.startswith("../"):
        raise RecordError(field + " must stay inside the repository")
    return normalized


def is_within_root(root, candidate):
    try:
        return os.path.commonpath((str(root), str(candidate))) == str(root)
    except ValueError:
        return False


def validate_explicit_path(value, field, root):
    path = normalized_path(value, field)
    real_path = Path(os.path.realpath(str(root / Path(*path.split("/")))))
    if not is_within_root(root, real_path):
        raise RecordError(field + " resolves outside the repository")
    return path


def has_glob_magic(path):
    return "*" in path or "?" in path


def glob_regex(pattern):
    pieces = ["^"]
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*" and index + 1 < len(pattern) and pattern[index + 1] == "*":
            index += 2
            if index < len(pattern) and pattern[index] == "/":
                pieces.append("(?:.*/)?")
                index += 1
            else:
                pieces.append(".*")
        elif char == "*":
            pieces.append("[^/]*")
            index += 1
        elif char == "?":
            pieces.append("[^/]")
            index += 1
        else:
            pieces.append(re.escape(char))
            index += 1
    pieces.append("$")
    return re.compile("".join(pieces))



def glob_can_match_below(pattern, directory):
    pattern_parts = pattern.split("/")
    directory_parts = directory.split("/")
    segment_patterns = [None if part == "**" else glob_regex(part) for part in pattern_parts]
    memo = {}

    def matches(pattern_index, directory_index):
        state = (pattern_index, directory_index)
        if state in memo:
            return memo[state]
        if directory_index == len(directory_parts):
            result = pattern_index < len(pattern_parts)
        elif pattern_index == len(pattern_parts):
            result = False
        elif pattern_parts[pattern_index] == "**":
            result = matches(pattern_index + 1, directory_index) or matches(pattern_index, directory_index + 1)
        else:
            result = (
                segment_patterns[pattern_index].fullmatch(directory_parts[directory_index]) is not None
                and matches(pattern_index + 1, directory_index + 1)
            )
        memo[state] = result
        return result

    return matches(0, 0)


def validate_pointer(pointer, field):
    if pointer != "" and not pointer.startswith("/"):
        raise RecordError(field + " must be an RFC 6901 JSON Pointer")
    if re.search(r"~(?![01])", pointer):
        raise RecordError(field + " has an invalid JSON Pointer escape")


def optional_string(obj, field, label):
    if field in obj and not isinstance(obj[field], str):
        raise RecordError(label + " must be a string")


def validate_record(record, root):
    if not isinstance(record, dict):
        raise RecordError("record must be an object")

    record_id = record.get("id")
    if not isinstance(record_id, str) or ID_RE.fullmatch(record_id) is None:
        raise RecordError("id must use lowercase letters, digits, '.', '_' or '-' and start with a letter or digit")
    for field in ("statement", "scope"):
        if not isinstance(record.get(field), str):
            raise RecordError(field + " is required and must be a string")
    evidence = record.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise RecordError("evidence is required and must be a non-empty list")

    conditions = record.get("conditions", [])
    if not isinstance(conditions, list):
        raise RecordError("conditions must be a list")
    watch = record.get("watch", [])
    if not isinstance(watch, list):
        raise RecordError("watch must be a list")
    optional_string(record, "verified_at", "verified_at")
    optional_string(record, "notes", "notes")

    explicit_paths = set()
    checked_evidence = []
    for index, item in enumerate(evidence):
        label = "evidence[{}]".format(index)
        if not isinstance(item, dict):
            raise RecordError(label + " must be an object")
        kind = item.get("kind")
        if not isinstance(kind, str) or not kind:
            raise RecordError(label + ".kind is required and must be a string")
        checked = {"kind": kind, "index": index, "item": item}
        if kind == "file":
            if "path" not in item:
                raise RecordError(label + ".path is required")
            path = validate_explicit_path(item["path"], label + ".path", root)
            explicit_paths.add(path)
            checked["path"] = path
            if "pattern" in item:
                if not isinstance(item["pattern"], str):
                    raise RecordError(label + ".pattern must be a string")
                try:
                    checked["pattern_re"] = re.compile(item["pattern"], re.MULTILINE)
                except re.error:
                    raise RecordError(label + ".pattern is not a valid regular expression")
            optional_string(item, "description", label + ".description")
        elif kind == "url":
            if not isinstance(item.get("url"), str):
                raise RecordError(label + ".url is required and must be a string")
            optional_string(item, "description", label + ".description")
        elif kind == "note":
            if not isinstance(item.get("description"), str):
                raise RecordError(label + ".description is required and must be a string")
        elif "path" in item:
            path = validate_explicit_path(item["path"], label + ".path", root)
            explicit_paths.add(path)
            checked["path"] = path
        checked_evidence.append(checked)

    checked_conditions = []
    for index, item in enumerate(conditions):
        label = "conditions[{}]".format(index)
        if not isinstance(item, dict):
            raise RecordError(label + " must be an object")
        kind = item.get("kind")
        if not isinstance(kind, str) or not kind:
            raise RecordError(label + ".kind is required and must be a string")
        checked = {"kind": kind, "index": index, "item": item}
        if kind in ("file_regex", "json_value"):
            if "path" not in item:
                raise RecordError(label + ".path is required")
            path = validate_explicit_path(item["path"], label + ".path", root)
            explicit_paths.add(path)
            checked["path"] = path
            if kind == "file_regex":
                if not isinstance(item.get("pattern"), str):
                    raise RecordError(label + ".pattern is required and must be a string")
                try:
                    checked["pattern_re"] = re.compile(item["pattern"], re.MULTILINE)
                except re.error:
                    raise RecordError(label + ".pattern is not a valid regular expression")
            else:
                if not isinstance(item.get("pointer"), str):
                    raise RecordError(label + ".pointer is required and must be a string")
                validate_pointer(item["pointer"], label + ".pointer")
                if "equals" not in item:
                    raise RecordError(label + ".equals is required")
            optional_string(item, "description", label + ".description")
        elif kind == "text":
            if not isinstance(item.get("description"), str):
                raise RecordError(label + ".description is required and must be a string")
        else:
            raise RecordError(label + ".kind is unsupported")
        checked_conditions.append(checked)

    checked_watch = []
    for index, value in enumerate(watch):
        label = "watch[{}]".format(index)
        path = normalized_path(value, label)
        if has_glob_magic(path):
            checked_watch.append({"path": path, "regex": glob_regex(path), "glob": True})
        else:
            path = validate_explicit_path(path, label, root)
            explicit_paths.add(path)
            checked_watch.append({"path": path, "regex": None, "glob": False})

    if "baseline" in record and not isinstance(record["baseline"], dict):
        raise RecordError("baseline must be an object")
    baseline = record.get("baseline")
    baseline_files = None
    if baseline is not None:
        if "git_commit" in baseline and not isinstance(baseline["git_commit"], str):
            raise RecordError("baseline.git_commit must be a string")
        if "files" in baseline:
            files = baseline["files"]
            if not isinstance(files, dict):
                raise RecordError("baseline.files must be an object")
            baseline_files = {}
            for key, value in files.items():
                path = validate_explicit_path(key, "baseline.files path", root)
                if path in baseline_files:
                    raise RecordError("baseline.files contains duplicate normalized paths")
                if value is not None and (not isinstance(value, str) or HASH_RE.fullmatch(value) is None):
                    raise RecordError("baseline.files values must be sha256 hashes or null")
                baseline_files[path] = value

    return {
        "id": record_id,
        "evidence": checked_evidence,
        "conditions": checked_conditions,
        "watch": checked_watch,
        "explicit_paths": explicit_paths,
        "baseline": baseline,
        "baseline_files": baseline_files,
    }


def watched_state(root, validated, include_baseline_paths=False):
    paths = set(validated["explicit_paths"])
    baseline = validated["baseline"]
    if include_baseline_paths and isinstance(baseline, dict):
        paths.update(validated["baseline_files"] or {})
    notices = set()
    patterns = [entry for entry in validated["watch"] if entry["glob"]]
    if patterns:
        walk_errors = []

        def on_walk_error(error):
            walk_errors.append(error)

        for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False, onerror=on_walk_error):
            dirnames.sort()
            filenames.sort()
            current = Path(directory)
            relative_dir = current.relative_to(root).as_posix()
            if relative_dir == ".":
                relative_dir = ""

            # Never descend into a .git directory, regardless of the pattern.
            retained_dirs = []
            for name in dirnames:
                rel = posixpath.join(relative_dir, name) if relative_dir else name
                if name == ".git":
                    continue
                retained_dirs.append(name)
                if not any(
                    pattern["regex"].fullmatch(rel) or glob_can_match_below(pattern["path"], rel)
                    for pattern in patterns
                ):
                    continue
                candidate = root / Path(*rel.split("/"))
                real_candidate = Path(os.path.realpath(str(candidate)))
                if not is_within_root(root, real_candidate):
                    notices.add(("skipped_outside_root", rel, "watch", "glob match resolves outside the repository"))
            dirnames[:] = retained_dirs

            for name in filenames:
                rel = posixpath.join(relative_dir, name) if relative_dir else name
                if ".git" in rel.split("/"):
                    continue
                if not any(pattern["regex"].fullmatch(rel) for pattern in patterns):
                    continue
                candidate = root / Path(*rel.split("/"))
                real_candidate = Path(os.path.realpath(str(candidate)))
                if not is_within_root(root, real_candidate):
                    notices.add(("skipped_outside_root", rel, "watch", "glob match resolves outside the repository"))
                elif candidate.is_file():
                    paths.add(rel)
        if walk_errors:
            raise RecordError("a watched directory could not be inspected")

    hashes = {}
    for path in sorted(paths):
        candidate = root / Path(*path.split("/"))
        real_candidate = Path(os.path.realpath(str(candidate)))
        if not is_within_root(root, real_candidate):
            # Explicit paths were rejected during validation; this is defensive.
            raise RecordError("watched path resolves outside the repository")
        if candidate.is_dir():
            raise RecordError("watched path is not a file")
        if not candidate.is_file():
            hashes[path] = None
            continue
        digest = hashlib.sha256()
        try:
            with candidate.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            raise RecordError("a watched file could not be read")
        hashes[path] = "sha256:" + digest.hexdigest()
    return hashes, sorted(notices)


def file_text(root, path):
    candidate = root / Path(*path.split("/"))
    if not candidate.is_file():
        return None
    try:
        return candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def resolve_pointer(value, pointer):
    if pointer == "":
        return True, value
    current = value
    for encoded_token in pointer[1:].split("/"):
        token = encoded_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                return False, None
            current = current[token]
        elif isinstance(current, list):
            if token == "-" or re.fullmatch(r"0|[1-9][0-9]*", token) is None:
                return False, None
            index = int(token)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def json_values_equal(left, right):
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if isinstance(left, (int, float)) and not isinstance(left, bool):
        if not (isinstance(right, (int, float)) and not isinstance(right, bool)):
            return False
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(json_values_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(json_values_equal(left[key], right[key]) for key in left)
    return left == right


def signal(signal_type, path, source, detail=None):
    result = {"type": signal_type}
    if path is not None:
        result["path"] = path
    result["source"] = source
    if detail is not None:
        result["detail"] = detail
    return result


def watch_glob_matches_path(watch, path):
    return any(entry["glob"] and entry["regex"].fullmatch(path) for entry in watch)


def git_pathspecs(validated):
    specs = set()
    for path in validated["explicit_paths"]:
        specs.add("(literal)" + path)
    for entry in validated["watch"]:
        magic = "(glob)" if entry["glob"] else "(literal)"
        specs.add(magic + entry["path"])
    for path in validated["baseline_files"] or {}:
        specs.add("(literal)" + path)
    return [":" + spec for spec in sorted(specs)]


def run_git(root, args):
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        env.pop(name, None)
    return subprocess.run(
        ["git", "-C", str(root), "-c", "core.fsmonitor=false", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
        check=False,
    )


def git_revision_available(root, revision):
    if revision.startswith("-") or "\x00" in revision:
        return False
    try:
        completed = run_git(root, ["rev-parse", "--verify", "--quiet", revision + "^{commit}"])
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def parse_git_diff(output):
    fields = output.split(b"\x00")
    if fields and fields[-1] == b"":
        fields.pop()
    changes = []
    index = 0
    while index < len(fields):
        status = os.fsdecode(fields[index])
        index += 1
        if index >= len(fields):
            break
        path = os.fsdecode(fields[index])
        index += 1
        changes.append((status, path))
    return changes


def git_signals(root, revision, validated, covered_paths):
    notices = []
    if not git_revision_available(root, revision):
        return [], [("baseline_unavailable", None, "baseline.git_commit", "git revision is unavailable")]
    pathspecs = git_pathspecs(validated)
    if not pathspecs:
        return [], notices
    try:
        diff = run_git(
            root,
            [
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                "--relative",
                "--name-status",
                "-z",
                revision,
                "--",
                *pathspecs,
            ],
        )
        untracked = run_git(
            root,
            ["ls-files", "--others", "--exclude-standard", "-z", "--", *pathspecs],
        )
        ignored = run_git(
            root,
            ["ls-files", "--others", "--ignored", "--exclude-standard", "-z", "--", *pathspecs],
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return [], [("baseline_unavailable", None, "baseline.git_commit", "git could not inspect the watched set")]
    if diff.returncode != 0 or untracked.returncode != 0 or ignored.returncode != 0:
        return [], [("baseline_unavailable", None, "baseline.git_commit", "git could not inspect the watched set")]

    results = []

    def skipped_outside_root(path):
        if not watch_glob_matches_path(validated["watch"], path):
            return False
        candidate = root / Path(*path.split("/"))
        real_candidate = Path(os.path.realpath(str(candidate)))
        if is_within_root(root, real_candidate):
            return False
        notices.append(("skipped_outside_root", path, "watch", "glob match resolves outside the repository"))
        return True

    for status, path in parse_git_diff(diff.stdout):
        if skipped_outside_root(path):
            continue
        if status.startswith("D"):
            kind = "deleted"
        elif status.startswith("A"):
            kind = "added"
        else:
            kind = "modified"
        results.append(signal(kind, path, "baseline.git_commit", "git status " + status))
    for raw_path in untracked.stdout.split(b"\x00"):
        if not raw_path:
            continue
        path = os.fsdecode(raw_path)
        if skipped_outside_root(path):
            continue
        kind = "added"
        results.append(signal(kind, path, "baseline.git_commit", "untracked file"))
    for raw_path in ignored.stdout.split(b"\x00"):
        if not raw_path:
            continue
        path = os.fsdecode(raw_path)
        if path not in covered_paths:
            notices.append(
                (
                    "ignored_by_git",
                    path,
                    "baseline.git_commit",
                    "git cannot establish its baseline state for this ignored path",
                )
            )
    return results, notices


def evaluate_evidence(root, validated):
    results = []
    signals = []
    agent_checks = []
    for evidence in validated["evidence"]:
        index = evidence["index"]
        kind = evidence["kind"]
        result = {"index": index, "kind": kind}
        item = evidence["item"]
        if kind == "file":
            path = evidence["path"]
            result["path"] = path
            candidate = root / Path(*path.split("/"))
            if not candidate.is_file():
                result["status"] = "missing"
                signals.append(signal("evidence_missing", path, "evidence", "file evidence is missing"))
            elif "pattern" not in item:
                result["status"] = "present"
            else:
                text = file_text(root, path)
                if text is None:
                    result["status"] = "not_checked"
                    result["detail"] = "file content could not be read as UTF-8"
                    agent_checks.append({"source": "evidence", "index": index, "kind": kind, "reason": "file content could not be read"})
                elif evidence["pattern_re"].search(text) is None:
                    result["status"] = "anchor_missing"
                    result["detail"] = "pattern does not match current file content"
                    signals.append(signal("evidence_anchor_missing", path, "evidence", "pattern does not match current file content"))
                else:
                    result["status"] = "anchor_found"
        elif kind == "url":
            result["url"] = item["url"]
            result["status"] = "not_checked"
            agent_checks.append({"source": "evidence", "index": index, "kind": kind, "reason": "URL evidence is never fetched by the checker"})
        elif kind == "note":
            result["status"] = "not_checked"
            agent_checks.append({"source": "evidence", "index": index, "kind": kind, "reason": "manual evidence requires agent verification"})
        else:
            result["status"] = "unsupported"
            agent_checks.append({"source": "evidence", "index": index, "kind": kind, "reason": "unsupported evidence kind requires agent verification"})
            if "path" in evidence:
                result["path"] = evidence["path"]
        results.append(result)
    return results, signals, agent_checks


def evaluate_conditions(root, validated):
    results = []
    signals = []
    agent_checks = []
    for condition in validated["conditions"]:
        index = condition["index"]
        kind = condition["kind"]
        item = condition["item"]
        result = {"index": index, "kind": kind}
        if kind == "text":
            result["status"] = "manual"
            result["detail"] = item["description"]
            agent_checks.append({"source": "condition", "index": index, "kind": kind, "reason": "text condition requires agent verification"})
        elif kind == "file_regex":
            path = condition["path"]
            result["path"] = path
            text = file_text(root, path)
            if text is None:
                status = "unresolvable"
                detail = "file is missing or could not be read as UTF-8"
            elif condition["pattern_re"].search(text) is None:
                status = "does_not_hold"
                detail = "pattern does not match current file content"
            else:
                status = "holds"
                detail = None
            result["status"] = status
            if detail is not None:
                result["detail"] = detail
            if status in ("does_not_hold", "unresolvable"):
                signals.append(signal("condition_changed", path, "condition", status))
        else:
            path = condition["path"]
            result["path"] = path
            text = file_text(root, path)
            if text is None:
                status = "unresolvable"
                detail = "file is missing or could not be read as UTF-8"
            else:
                try:
                    document = json.loads(text, parse_constant=reject_json_constant)
                except (ValueError, TypeError, RecursionError):
                    status = "unresolvable"
                    detail = "file is not valid JSON"
                else:
                    found, value = resolve_pointer(document, item["pointer"])
                    if found and json_values_equal(value, item["equals"]):
                        status = "holds"
                        detail = None
                    else:
                        status = "does_not_hold"
                        detail = "JSON pointer is missing or its value differs"
            result["status"] = status
            if detail is not None:
                result["detail"] = detail
            if status in ("does_not_hold", "unresolvable"):
                signals.append(signal("condition_changed", path, "condition", status))
        results.append(result)
    return results, signals, agent_checks


def compare_file_baseline(current, baseline_files):
    results = []
    paths = sorted(set(current) | set(baseline_files))
    for path in paths:
        before = baseline_files.get(path, "__absent_from_baseline__")
        after = current.get(path, "__not_watched_now__")
        if before == after:
            continue
        if before == "__absent_from_baseline__":
            if after not in (None, "__not_watched_now__"):
                kind = "added"
                results.append(signal(kind, path, "baseline.files", "path was not in the file baseline"))
        elif after == "__not_watched_now__":
            # Old snapshot paths remain relevant until explicitly re-snapshotted.
            continue
        elif before is not None and after is None:
            results.append(signal("deleted", path, "baseline.files", "file no longer exists"))
        elif before is None and after is not None:
            kind = "added"
            results.append(signal(kind, path, "baseline.files", "file now exists"))
        elif before != after:
            results.append(signal("modified", path, "baseline.files", "SHA-256 differs from baseline"))
    return results


def make_record_error(record, error):
    raw_id = record.get("id") if isinstance(record, dict) else None
    record_id = raw_id if isinstance(raw_id, str) and ID_RE.fullmatch(raw_id) else None
    return {
        "id": record_id,
        "status": "record_error",
        "signals": [],
        "notices": [],
        "evidence": [],
        "conditions": [],
        "agent_checks": [],
        "errors": [str(error)],
    }


def evaluate_record(record, root, since=None):
    try:
        validated = validate_record(record, root)
        current, outside_notices = watched_state(root, validated, include_baseline_paths=True)
        if not current:
            outside_notices.append(
                (
                    "empty_watched_set",
                    None,
                    "watch",
                    "no paths are covered by file evidence, conditions, watch matches, or baseline.files",
                )
            )
    except RecordError as error:
        return make_record_error(record, error)
    except OSError:
        return make_record_error(record, "repository files could not be inspected")

    evidence, evidence_signals, evidence_checks = evaluate_evidence(root, validated)
    conditions, condition_signals, condition_checks = evaluate_conditions(root, validated)
    signals = evidence_signals + condition_signals
    notices = list(outside_notices)

    baseline = validated["baseline"] if since is None else None
    usable_baseline = False
    if since is not None:
        git_changes, git_notices = git_signals(root, since, validated, set())
        signals.extend(git_changes)
        notices.extend(git_notices)
        usable_baseline = not git_notices
    elif isinstance(baseline, dict):
        if "files" in baseline:
            usable_baseline = True
            signals.extend(compare_file_baseline(current, validated["baseline_files"]))
        if "git_commit" in baseline:
            git_changes, git_notices = git_signals(root, baseline["git_commit"], validated, set(validated["baseline_files"] or {}))
            signals.extend(git_changes)
            notices.extend(git_notices)
            if not git_notices:
                usable_baseline = True
    if not current or any(notice[0] == "ignored_by_git" for notice in notices):
        usable_baseline = False

    if signals:
        status = "changed"
    elif usable_baseline:
        status = "unchanged"
    else:
        status = "no_baseline"

    signals = sorted(
        signals,
        key=lambda item: (item["type"], item.get("path", ""), item["source"], item.get("detail", "")),
    )
    notices = sorted(
        set(notices),
        key=lambda item: (item[0], item[1] or "", item[2], item[3]),
    )
    notices = [
        {"type": kind, "source": source, "detail": detail, **({"path": path} if path is not None else {})}
        for kind, path, source, detail in notices
    ]
    agent_checks = sorted(evidence_checks + condition_checks, key=lambda item: (item["source"], item["index"], item["kind"], item["reason"]))
    return {
        "id": validated["id"],
        "status": status,
        "signals": signals,
        "notices": notices,
        "evidence": evidence,
        "conditions": conditions,
        "agent_checks": agent_checks,
        "errors": [],
    }


def select_records(records, ids):
    known_ids = {record["id"] for record in records if isinstance(record, dict) and isinstance(record.get("id"), str)}
    unknown = set(ids or ()) - known_ids
    if unknown:
        raise UsageError("one or more requested ids do not exist")
    if not ids:
        return records
    requested = set(ids)
    return [record for record in records if isinstance(record, dict) and record.get("id") in requested]


def check_document(records, root, since=None):
    assumptions = [evaluate_record(record, root, since=since) for record in records]
    assumptions.sort(key=lambda item: (item["id"] is None, item["id"] or ""))
    summary = {
        "total": len(assumptions),
        "unchanged": sum(item["status"] == "unchanged" for item in assumptions),
        "changed": sum(item["status"] == "changed" for item in assumptions),
        "no_baseline": sum(item["status"] == "no_baseline" for item in assumptions),
        "record_error": sum(item["status"] == "record_error" for item in assumptions),
    }
    return {
        "schema_version": 1,
        "summary": summary,
        "errors": [],
        "assumptions": assumptions,
        "note": NOTE,
    }


def error_check_result(kind, detail):
    result = empty_check_result([{"type": kind, "detail": detail}])
    return result


def snapshot_document(document, selected, root):
    for record in selected:
        try:
            validated = validate_record(record, root)
            hashes, _notices = watched_state(root, validated)
        except (RecordError, OSError) as error:
            raise RecordError(str(error))
        if "baseline" not in record:
            record["baseline"] = {}
        record["baseline"]["files"] = {path: hashes[path] for path in sorted(hashes)}
    return document


def atomic_write(path, text):
    destination = Path(path)
    parent = destination.parent if str(destination.parent) else Path(".")
    try:
        original_mode = stat.S_IMODE(destination.stat().st_mode)
    except OSError:
        original_mode = None
    descriptor, temporary = tempfile.mkstemp(prefix="." + destination.name + ".", dir=str(parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        if original_mode is not None:
            os.chmod(temporary, original_mode)
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def make_parser():
    parser = argparse.ArgumentParser(description="Check local drift in assumption records.")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="inspect evidence and compare baselines")
    check.add_argument("--repo", required=True)
    check.add_argument("--records", required=True, help="records JSON file, or - for stdin")
    check.add_argument("--id", action="append", default=[])
    check.add_argument("--since")
    snapshot = commands.add_parser("snapshot", help="refresh baseline.files")
    snapshot.add_argument("--repo", required=True)
    snapshot.add_argument("--records", required=True, help="records JSON file, or - for stdin")
    snapshot.add_argument("--id", action="append", default=[])
    snapshot.add_argument("--write", action="store_true")
    return parser


def resolve_repo(value):
    try:
        root = Path(value).resolve(strict=True)
    except (OSError, RuntimeError):
        raise UsageError("repository directory could not be resolved")
    if not root.is_dir():
        raise UsageError("repository must be a directory")
    return root


def main(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        try:
            document, records, bare = read_records(args.records)
        except RecordsError as error:
            emit_json(error_check_result("records_error", str(error)))
            return 2
        try:
            selected = select_records(records, args.id)
            root = resolve_repo(args.repo)
        except UsageError as error:
            emit_json(error_check_result("usage_error", str(error)))
            return 2
        result = check_document(selected, root, since=args.since)
        emit_json(result)
        if result["summary"]["record_error"]:
            return 2
        if result["summary"]["changed"] or result["summary"]["no_baseline"]:
            return 1
        return 0

    if args.write and args.records == "-":
        print("snapshot --write cannot be used with --records -", file=sys.stderr)
        return 2
    try:
        document, records, bare = read_records(args.records)
        selected = select_records(records, args.id)
        root = resolve_repo(args.repo)
    except (RecordsError, UsageError) as error:
        print("snapshot: " + str(error), file=sys.stderr)
        return 2
    try:
        updated = snapshot_document(document, selected, root)
    except RecordError as error:
        print("snapshot: " + str(error), file=sys.stderr)
        return 2
    output = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        try:
            atomic_write(args.records, output)
        except OSError:
            print("snapshot: records file could not be replaced", file=sys.stderr)
            return 2
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
