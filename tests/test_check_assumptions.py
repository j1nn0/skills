import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
CHECKER = ROOT / "skills" / "assumption-expiry-audit" / "scripts" / "check_assumptions.py"


class CheckAssumptionsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.temp_root = Path(self.temp.name)
        self.repo = self.temp_root / "repo"
        self.repo.mkdir()
        self.manifest = self.repo / "manifest.json"
        self.manifest.write_text('{"name":"fixture"}\n', encoding="utf-8")
        self.env = os.environ.copy()
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"
        self.env["GIT_OPTIONAL_LOCKS"] = "0"

    def digest(self, path):
        return "sha256:" + hashlib.sha256((self.repo / path).read_bytes()).hexdigest()

    def record(self, **overrides):
        record = {
            "id": "fixture",
            "statement": "The fixture assumption holds.",
            "scope": "the temporary repository",
            "evidence": [{"kind": "file", "path": "manifest.json"}],
        }
        record.update(overrides)
        return record

    def write_records(self, value, name="records.json"):
        path = self.temp_root / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def run_cli(self, command="check", records=None, records_path=None, args=(), input_text=None, repo=None):
        if records_path is None:
            if records is None:
                raise AssertionError("records or records_path is required")
            records_path = self.write_records(records)
        completed = subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                command,
                "--repo",
                str(repo or self.repo),
                "--records",
                str(records_path),
                *args,
            ],
            cwd=ROOT,
            env=self.env,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )
        return completed

    def run_check(self, record_or_document, **kwargs):
        return self.run_cli("check", records=record_or_document, **kwargs)

    def result(self, completed):
        self.assertTrue(completed.stdout, completed.stderr)
        return json.loads(completed.stdout)

    def git(self, *args, cwd=None):
        completed = subprocess.run(
            ["git", "-C", str(cwd or self.repo), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        return completed.stdout.strip()

    def commit_fixture(self):
        self.git("init", "-q")
        self.git("config", "user.name", "Assumption Test")
        self.git("config", "user.email", "assumption-test@example.invalid")
        self.git("add", "--", ".")
        self.git("commit", "-q", "-m", "fixture")
        return self.git("rev-parse", "HEAD")

    def tree_digest(self):
        digest = hashlib.sha256()
        for path in sorted(self.repo.rglob("*"), key=lambda item: item.relative_to(self.repo).as_posix()):
            relative = path.relative_to(self.repo).as_posix()
            metadata = path.lstat()
            digest.update(relative.encode("utf-8", errors="surrogateescape"))
            digest.update(str(metadata.st_mode).encode("ascii"))
            if path.is_symlink():
                digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
            elif path.is_file():
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def index_state(self):
        index = self.repo / ".git" / "index"
        metadata = index.stat()
        return metadata.st_mtime_ns, hashlib.sha256(index.read_bytes()).hexdigest()

    def test_unchanged_files_baseline_exits_zero(self):
        record = self.record(baseline={"files": {"manifest.json": self.digest("manifest.json")}})
        completed = self.run_check(record)
        self.assertEqual(0, completed.returncode, completed.stderr)
        result = self.result(completed)
        self.assertEqual("unchanged", result["assumptions"][0]["status"])
        self.assertEqual(1, result["summary"]["unchanged"])
        self.assertEqual("present", result["assumptions"][0]["evidence"][0]["status"])

    def test_modified_dependency_manifest_reports_modified(self):
        dependency = self.repo / "pyproject.toml"
        dependency.write_text("[project]\nversion='1'\n", encoding="utf-8")
        record = self.record(
            watch=["pyproject.toml"],
            baseline={
                "files": {
                    "manifest.json": self.digest("manifest.json"),
                    "pyproject.toml": self.digest("pyproject.toml"),
                }
            },
        )
        dependency.write_text("[project]\nversion='2'\n", encoding="utf-8")
        completed = self.run_check(record)
        result = self.result(completed)
        self.assertEqual(1, completed.returncode)
        self.assertEqual("changed", result["assumptions"][0]["status"])
        self.assertIn(
            {"type": "modified", "path": "pyproject.toml", "source": "baseline.files", "detail": "SHA-256 differs from baseline"},
            result["assumptions"][0]["signals"],
        )

    def test_deleted_evidence_reports_missing_and_deleted_not_a_validity_verdict(self):
        record = self.record(baseline={"files": {"manifest.json": self.digest("manifest.json")}})
        self.manifest.unlink()
        completed = self.run_check(record)
        result = self.result(completed)
        assumption = result["assumptions"][0]
        self.assertEqual(1, completed.returncode)
        self.assertEqual("changed", assumption["status"])
        self.assertIn("evidence_missing", [signal["type"] for signal in assumption["signals"]])
        self.assertIn("deleted", [signal["type"] for signal in assumption["signals"]])
        self.assertEqual("missing", assumption["evidence"][0]["status"])
        self.assertNotIn(assumption["status"], {"valid", "invalid", "unknown"})

    def test_new_file_under_watch_glob_reports_added(self):
        source = self.repo / "src"
        source.mkdir()
        (source / "base.py").write_text("base = True\n", encoding="utf-8")
        record = self.record(
            watch=["src/**/*.py"],
            baseline={
                "files": {
                    "manifest.json": self.digest("manifest.json"),
                    "src/base.py": self.digest("src/base.py"),
                }
            },
        )
        (source / "new.py").write_text("new = True\n", encoding="utf-8")
        completed = self.run_check(record)
        result = self.result(completed)
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            ("added", "src/new.py"),
            {(signal["type"], signal.get("path")) for signal in result["assumptions"][0]["signals"]},
        )

    def test_unrelated_file_change_outside_watched_set_is_unchanged(self):
        record = self.record(baseline={"files": {"manifest.json": self.digest("manifest.json")}})
        (self.repo / "unrelated.txt").write_text("not watched\n", encoding="utf-8")
        completed = self.run_check(record)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("unchanged", self.result(completed)["assumptions"][0]["status"])

    def test_git_baseline_detects_uncommitted_and_untracked_changes(self):
        dependency = self.repo / "pyproject.toml"
        dependency.write_text("[project]\nversion='1'\n", encoding="utf-8")
        source = self.repo / "src"
        source.mkdir()
        (source / "base.py").write_text("base = True\n", encoding="utf-8")
        commit = self.commit_fixture()
        record = self.record(watch=["pyproject.toml", "src/**/*.py"], baseline={"git_commit": commit})
        dependency.write_text("[project]\nversion='2'\n", encoding="utf-8")
        (source / "new.py").write_text("new = True\n", encoding="utf-8")
        completed = self.run_check(record)
        result = self.result(completed)
        self.assertEqual(1, completed.returncode)
        self.assertEqual("changed", result["assumptions"][0]["status"])
        signals = result["assumptions"][0]["signals"]
        self.assertIn(("modified", "pyproject.toml"), {(item["type"], item.get("path")) for item in signals})
        self.assertIn(("added", "src/new.py"), {(item["type"], item.get("path")) for item in signals})
        self.assertTrue(all(item["source"] == "baseline.git_commit" for item in signals))

    def test_git_baseline_reports_ignored_watched_file_as_uncovered(self):
        (self.repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        commit = self.commit_fixture()
        (self.repo / "ignored.txt").write_text("created after baseline\n", encoding="utf-8")
        record = self.record(watch=["ignored.txt"], baseline={"git_commit": commit})

        for args in ((), ("--since", commit)):
            with self.subTest(args=args):
                completed = self.run_check(record, args=args)
                assumption = self.result(completed)["assumptions"][0]
                self.assertEqual(1, completed.returncode)
                self.assertEqual("no_baseline", assumption["status"])
                self.assertEqual([], assumption["signals"])
                self.assertIn(
                    {
                        "type": "ignored_by_git",
                        "source": "baseline.git_commit",
                        "detail": "git cannot establish its baseline state for this ignored path",
                        "path": "ignored.txt",
                    },
                    assumption["notices"],
                )

    def test_git_baseline_does_not_notice_ignored_file_covered_by_files_baseline(self):
        (self.repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        commit = self.commit_fixture()
        (self.repo / "ignored.txt").write_text("captured by files baseline\n", encoding="utf-8")
        record = self.record(
            watch=["ignored.txt"],
            baseline={
                "git_commit": commit,
                "files": {
                    "manifest.json": self.digest("manifest.json"),
                    "ignored.txt": self.digest("ignored.txt"),
                },
            },
        )

        completed = self.run_check(record)
        assumption = self.result(completed)["assumptions"][0]
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("unchanged", assumption["status"])
        self.assertNotIn("ignored_by_git", [notice["type"] for notice in assumption["notices"]])

        # --since replaces the record baselines, so baseline.files no longer covers the ignored path.
        completed = self.run_check(record, args=("--since", commit))
        assumption = self.result(completed)["assumptions"][0]
        self.assertEqual("no_baseline", assumption["status"])
        self.assertIn("ignored_by_git", [notice["type"] for notice in assumption["notices"]])

    def test_empty_watched_set_has_no_baseline(self):
        record = self.record(
            evidence=[{"kind": "note", "description": "Manual evidence only"}],
            conditions=[{"kind": "text", "description": "A manual condition"}],
            watch=[],
            baseline={"files": {}},
        )

        completed = self.run_check(record)
        assumption = self.result(completed)["assumptions"][0]
        self.assertEqual(1, completed.returncode)
        self.assertEqual("no_baseline", assumption["status"])
        self.assertIn(
            {"type": "empty_watched_set", "source": "watch", "detail": "no paths are covered by file evidence, conditions, watch matches, or baseline.files"},
            assumption["notices"],
        )

    def test_since_includes_baseline_files_paths_in_git_pathspecs(self):
        path = self.repo / "baseline-only.txt"
        path.write_text("before\n", encoding="utf-8")
        commit = self.commit_fixture()
        record = self.record(
            evidence=[{"kind": "note", "description": "Manual evidence only"}],
            watch=[],
            baseline={"files": {"baseline-only.txt": self.digest("baseline-only.txt")}},
        )
        path.write_text("after\n", encoding="utf-8")

        completed = self.run_check(record, args=("--since", commit))
        assumption = self.result(completed)["assumptions"][0]
        self.assertEqual(1, completed.returncode)
        self.assertEqual("changed", assumption["status"])
        self.assertIn(
            ("modified", "baseline-only.txt"),
            {(item["type"], item.get("path")) for item in assumption["signals"]},
        )

    def test_git_diff_paths_are_relative_to_repo_subdirectory(self):
        subdir = self.repo / "sub"
        subdir.mkdir()
        (self.repo / ".gitignore").write_text("sub/ignored.txt\n", encoding="utf-8")
        watched = subdir / "f.txt"
        watched.write_text("before\n", encoding="utf-8")
        commit = self.commit_fixture()
        record = self.record(
            evidence=[{"kind": "file", "path": "f.txt"}],
            watch=["new.txt", "ignored.txt"],
            baseline={"git_commit": commit},
        )
        watched.write_text("after\n", encoding="utf-8")
        (subdir / "new.txt").write_text("untracked after baseline\n", encoding="utf-8")
        (subdir / "ignored.txt").write_text("ignored after baseline\n", encoding="utf-8")

        completed = self.run_check(record, repo=subdir)
        assumption = self.result(completed)["assumptions"][0]
        self.assertEqual(1, completed.returncode)
        self.assertEqual(
            [("added", "new.txt"), ("modified", "f.txt")],
            [(item["type"], item.get("path")) for item in assumption["signals"]],
        )
        self.assertIn(
            {"type": "ignored_by_git", "source": "baseline.git_commit", "detail": "git cannot establish its baseline state for this ignored path", "path": "ignored.txt"},
            assumption["notices"],
        )

    def test_file_present_but_absent_from_baseline_is_added_without_watch_glob(self):
        new_file = self.repo / "new-evidence.txt"
        new_file.write_text("new evidence\n", encoding="utf-8")
        record = self.record(
            evidence=[{"kind": "file", "path": "new-evidence.txt"}],
            baseline={"files": {"manifest.json": self.digest("manifest.json")}},
        )

        completed = self.run_check(record)
        assumption = self.result(completed)["assumptions"][0]
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            ("added", "new-evidence.txt"),
            {(item["type"], item.get("path")) for item in assumption["signals"]},
        )

    def test_missing_evidence_anchor_detail_describes_current_content(self):
        record = self.record(
            evidence=[{"kind": "file", "path": "manifest.json", "pattern": "not-present"}],
        )

        completed = self.run_check(record)
        assumption = self.result(completed)["assumptions"][0]
        signal = next(item for item in assumption["signals"] if item["type"] == "evidence_anchor_missing")
        self.assertEqual("pattern does not match current file content", signal["detail"])

    def test_since_replaces_record_baseline_for_one_run(self):
        dependency = self.repo / "dependency.txt"
        dependency.write_text("before\n", encoding="utf-8")
        commit = self.commit_fixture()
        record = self.record(
            watch=["dependency.txt"],
            baseline={"files": {"manifest.json": "sha256:" + "0" * 64}},
        )
        dependency.write_text("after\n", encoding="utf-8")
        completed = self.run_check(record, args=("--since", commit))
        result = self.result(completed)
        self.assertEqual(1, completed.returncode)
        signals = result["assumptions"][0]["signals"]
        self.assertEqual({"baseline.git_commit"}, {item["source"] for item in signals})
        self.assertIn("modified", [item["type"] for item in signals])

    def test_unresolvable_git_revision_is_a_notice_and_no_baseline(self):
        self.commit_fixture()
        record = self.record(baseline={"git_commit": "not-a-real-commit"})
        completed = self.run_check(record)
        result = self.result(completed)
        assumption = result["assumptions"][0]
        self.assertEqual(1, completed.returncode)
        self.assertEqual("no_baseline", assumption["status"])
        self.assertIn("baseline_unavailable", [notice["type"] for notice in assumption["notices"]])

    def test_conditions_report_holds_does_not_hold_and_unresolvable(self):
        config = self.repo / "config.json"
        runtime = self.repo / ".runtime"
        config.write_text('{"dependencies":{"engine":"2.4"}}\n', encoding="utf-8")
        runtime.write_text("20.12\n", encoding="utf-8")
        record = self.record(
            evidence=[{"kind": "note", "description": "Conditions fixture"}],
            conditions=[
                {"kind": "json_value", "path": "config.json", "pointer": "/dependencies/engine", "equals": "2.4"},
                {"kind": "file_regex", "path": ".runtime", "pattern": "^20\\."},
            ],
        )

        holds = self.result(self.run_check(record))["assumptions"][0]
        self.assertEqual(["holds", "holds"], [condition["status"] for condition in holds["conditions"]])
        self.assertEqual("no_baseline", holds["status"])

        config.write_text('{"dependencies":{"engine":"3.0"}}\n', encoding="utf-8")
        runtime.write_text("22.1\n", encoding="utf-8")
        does_not_hold = self.result(self.run_check(record))["assumptions"][0]
        self.assertEqual(["does_not_hold", "does_not_hold"], [condition["status"] for condition in does_not_hold["conditions"]])
        self.assertEqual("changed", does_not_hold["status"])

        config.unlink()
        runtime.unlink()
        unresolvable = self.result(self.run_check(record))["assumptions"][0]
        self.assertEqual(["unresolvable", "unresolvable"], [condition["status"] for condition in unresolvable["conditions"]])
        self.assertEqual("changed", unresolvable["status"])

    def test_manual_and_unsupported_evidence_checks_do_not_change_status_or_exit(self):
        record = self.record(
            evidence=[
                {"kind": "file", "path": "manifest.json"},
                {"kind": "url", "url": "https://example.invalid/reference"},
                {"kind": "note", "description": "Observed manually"},
                {"kind": "opaque", "description": "Unknown evidence"},
            ],
            conditions=[{"kind": "text", "description": "The deployment uses the expected environment."}],
            baseline={"files": {"manifest.json": self.digest("manifest.json")}},
        )
        completed = self.run_check(record)
        result = self.result(completed)
        assumption = result["assumptions"][0]
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("unchanged", assumption["status"])
        self.assertEqual(["present", "not_checked", "not_checked", "unsupported"], [item["status"] for item in assumption["evidence"]])
        self.assertEqual("manual", assumption["conditions"][0]["status"])
        self.assertEqual(4, len(assumption["agent_checks"]))

    def test_malformed_json_is_a_file_level_error(self):
        records_path = self.temp_root / "bad.json"
        records_path.write_text("{", encoding="utf-8")
        completed = self.run_cli(records_path=records_path)
        result = self.result(completed)
        self.assertEqual(2, completed.returncode)
        self.assertEqual([], result["assumptions"])
        self.assertEqual("records_error", result["errors"][0]["type"])

    def test_missing_required_fields_and_bad_regex_are_record_errors(self):
        missing = self.record()
        del missing["scope"]
        bad_regex = self.record(evidence=[{"kind": "file", "path": "manifest.json", "pattern": "["}])
        for record in (missing, bad_regex):
            with self.subTest(record=record):
                completed = self.run_check(record)
                result = self.result(completed)
                self.assertEqual(2, completed.returncode)
                self.assertEqual("record_error", result["assumptions"][0]["status"])

    def test_duplicate_ids_are_a_file_level_error(self):
        records = {"schema_version": 1, "assumptions": [self.record(), self.record()]}
        completed = self.run_check(records)
        result = self.result(completed)
        self.assertEqual(2, completed.returncode)
        self.assertEqual("records_error", result["errors"][0]["type"])
        self.assertEqual(0, result["summary"]["total"])

    def test_absolute_parent_and_escaping_symlink_paths_are_rejected(self):
        outside = self.temp_root / "outside.txt"
        outside.write_text("secret\n", encoding="utf-8")
        (self.repo / "escape.txt").symlink_to(outside)
        paths = [str(outside), "../outside.txt", "escape.txt"]
        for path in paths:
            with self.subTest(path=path):
                record = self.record(evidence=[{"kind": "file", "path": path}])
                completed = self.run_check(record)
                result = self.result(completed)
                self.assertEqual(2, completed.returncode)
                self.assertEqual("record_error", result["assumptions"][0]["status"])
        self.assertNotIn(str(outside), completed.stdout)

    def test_outside_symlink_glob_match_is_not_a_change_signal(self):
        commit = self.commit_fixture()
        outside = self.temp_root / "external.txt"
        outside.write_text("external\n", encoding="utf-8")
        (self.repo / "external.txt").symlink_to(outside)
        record = self.record(
            watch=["**/*"],
            baseline={"git_commit": commit, "files": {"manifest.json": self.digest("manifest.json")}},
        )
        completed = self.run_check(record)
        result = self.result(completed)
        assumption = result["assumptions"][0]
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("unchanged", assumption["status"])
        self.assertIn("skipped_outside_root", [notice["type"] for notice in assumption["notices"]])
        self.assertNotIn(("added", "external.txt"), {(item["type"], item.get("path")) for item in assumption["signals"]})


    def test_outside_symlink_directory_is_reported_without_following_it(self):
        commit = self.commit_fixture()
        outside = self.temp_root / "outside-dir"
        outside.mkdir()
        (outside / "child.txt").write_text("outside\n", encoding="utf-8")
        (self.repo / "linked").symlink_to(outside, target_is_directory=True)
        record = self.record(
            watch=["linked/**/*.txt"],
            baseline={"git_commit": commit},
        )
        completed = self.run_check(record)
        result = self.result(completed)
        assumption = result["assumptions"][0]
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("unchanged", assumption["status"])
        self.assertIn("skipped_outside_root", [notice["type"] for notice in assumption["notices"]])
        self.assertEqual([], assumption["signals"])

    def test_snapshot_stdout_preserves_repo_and_records_and_write_refreshes_only_baseline(self):
        source = self.repo / "src"
        source.mkdir()
        (source / "lib.py").write_text("answer = 42\n", encoding="utf-8")
        commit = self.commit_fixture()
        record = self.record(
            watch=["src/**/*.py"],
            baseline={"git_commit": commit},
            notes="keep this field naïve",
        )
        records_path = self.write_records(record)
        before_tree = self.tree_digest()
        before_records = records_path.read_bytes()
        preview = self.run_cli("snapshot", records_path=records_path)
        self.assertEqual(0, preview.returncode, preview.stderr)
        preview_record = json.loads(preview.stdout)
        self.assertNotIn("assumptions", preview_record)
        self.assertEqual(commit, preview_record["baseline"]["git_commit"])
        self.assertEqual("keep this field naïve", preview_record["notes"])
        self.assertEqual(list(record), list(preview_record))
        self.assertEqual(["git_commit", "files"], list(preview_record["baseline"]))
        self.assertIn("naïve", preview.stdout)
        self.assertEqual({"manifest.json", "src/lib.py"}, set(preview_record["baseline"]["files"]))
        self.assertEqual(before_records, records_path.read_bytes())
        self.assertEqual(before_tree, self.tree_digest())

        before_names = sorted(path.name for path in self.temp_root.iterdir())
        written = self.run_cli("snapshot", records_path=records_path, args=("--write",))
        self.assertEqual(0, written.returncode, written.stderr)
        self.assertEqual(json.loads(written.stdout), json.loads(records_path.read_text(encoding="utf-8")))
        self.assertEqual(before_names, sorted(path.name for path in self.temp_root.iterdir()))
        self.assertEqual(before_tree, self.tree_digest())
        checked = self.run_cli("check", records_path=records_path)
        self.assertEqual(0, checked.returncode, checked.stderr)
        self.assertEqual("unchanged", self.result(checked)["assumptions"][0]["status"])

    def test_snapshot_records_null_for_missing_explicit_path(self):
        record = self.record(evidence=[{"kind": "file", "path": "missing.txt"}])
        completed = self.run_cli("snapshot", records=record)
        self.assertEqual(0, completed.returncode, completed.stderr)
        updated = json.loads(completed.stdout)
        self.assertIsNone(updated["baseline"]["files"]["missing.txt"])

    def test_check_does_not_modify_repo_tree_or_git_index(self):
        commit = self.commit_fixture()
        record = self.record(baseline={"git_commit": commit})
        records_path = self.write_records(record)
        before_tree = self.tree_digest()
        before_index = self.index_state()
        completed = self.run_cli("check", records_path=records_path)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(before_tree, self.tree_digest())
        self.assertEqual(before_index, self.index_state())

    def test_output_is_identical_across_runs(self):
        record = self.record(baseline={"files": {"manifest.json": self.digest("manifest.json")}})
        records_path = self.write_records(record)
        first = self.run_cli("check", records_path=records_path)
        second = self.run_cli("check", records_path=records_path)
        self.assertEqual(0, first.returncode)
        self.assertEqual(0, second.returncode)
        self.assertEqual(first.stdout, second.stdout)

    def test_stdin_records_and_unknown_id_usage_error(self):
        record = self.record(baseline={"files": {"manifest.json": self.digest("manifest.json")}})
        completed = self.run_cli(
            "check",
            records_path="-",
            input_text=json.dumps(record, ensure_ascii=False),
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("unchanged", self.result(completed)["assumptions"][0]["status"])

        records_path = self.write_records({"schema_version": 1, "assumptions": [record]})
        unknown = self.run_cli("check", records_path=records_path, args=("--id", "absent"))
        result = self.result(unknown)
        self.assertEqual(2, unknown.returncode)
        self.assertEqual("usage_error", result["errors"][0]["type"])

    def test_snapshot_write_is_rejected_for_stdin(self):
        completed = self.run_cli("snapshot", records_path="-", args=("--write",), input_text="{}")
        self.assertEqual(2, completed.returncode)
        self.assertEqual("", completed.stdout)


if __name__ == "__main__":
    unittest.main()
