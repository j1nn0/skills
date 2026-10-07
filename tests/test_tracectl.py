import ast
import importlib.machinery
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
TRACECTL = ROOT / "skills" / "agent-orchestration" / "scripts" / "tracectl"
SESSIONCTL = ROOT / "skills" / "agent-orchestration" / "scripts" / "sessionctl"
PARALLEL_VALIDATE = (
    ROOT / "skills" / "agent-orchestration" / "scripts" / "parallel_validate"
)
TRACE_MODULE_LOADER = importlib.machinery.SourceFileLoader(
    "tracectl_test_module", str(TRACECTL)
)
TRACE_MODULE_SPEC = importlib.util.spec_from_loader(
    TRACE_MODULE_LOADER.name, TRACE_MODULE_LOADER
)
TRACECTL_MODULE = importlib.util.module_from_spec(TRACE_MODULE_SPEC)
TRACE_MODULE_LOADER.exec_module(TRACECTL_MODULE)


class TracectlTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.no_bin_dir = self.root / "empty-bin"
        self.no_bin_dir.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.xdg = self.root / "xdg-state"
        self.xdg.mkdir()
        self.repo = self.root / "private-repo"
        self.repo.mkdir()
        self.herdr_path = self.bin_dir / "herdr"
        self.identity = {
            "source": "identity-source-secret",
            "kind": "identity-kind-token",
            "value": str(self.repo / "identity-value-secret.jsonl"),
        }
        self.env = {
            "PATH": str(self.bin_dir),
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.xdg),
            "HERDR_PANE_ID": "fake-pane-identifier-secret",
        }
        self.set_herdr_identity(self.identity)

    def set_herdr_identity(self, identity=None):
        if identity is None:
            payload = {"result": {"pane": {"id": "pane-without-session"}}}
        else:
            session = dict(identity)
            session["agent"] = "agent-session-private-value"
            payload = {
                "id": "opaque-herdr-response-id",
                "result": {"pane": {"id": "opaque-pane-id", "agent_session": session}},
            }
        response = json.dumps(payload, separators=(",", ":"))
        self.herdr_path.write_text(
            "#!" + sys.executable + "\n"
            "import sys\n"
            "sys.stdout.write(" + repr(response) + ")\n",
            encoding="utf-8",
        )
        self.herdr_path.chmod(0o755)

    def run_tracectl(self, *args, env=None):
        return subprocess.run(
            [sys.executable, str(TRACECTL), *args],
            capture_output=True,
            text=True,
            env=self.env if env is None else env,
            check=False,
        )

    def run_sessionctl(self, *args):
        return subprocess.run(
            [sys.executable, str(SESSIONCTL), *args],
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )

    def result(self, completed, ok=None):
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stderr)
        self.assertTrue(completed.stdout.endswith("\n"), completed.stdout)
        self.assertEqual(1, completed.stdout.count("\n"), completed.stdout)
        value = json.loads(completed.stdout)
        self.assertEqual(
            json.dumps(value, separators=(",", ":")), completed.stdout[:-1]
        )
        if ok is not None:
            self.assertEqual(ok, value["ok"])
        return value

    def state_file(self):
        completed = self.run_sessionctl("inspect")
        self.assertEqual(0, completed.returncode, completed.stderr)
        return Path(json.loads(completed.stdout)["state_file"])

    def trace_file(self, identity=None):
        state_file = self.state_file()
        if identity is not None and identity != self.identity:
            self.set_herdr_identity(identity)
            state_file = self.state_file()
        return state_file.parent / "traces" / state_file.with_suffix(".jsonl").name

    def record(self, *args, env=None):
        return self.result(self.run_tracectl("record", *args, env=env))

    def summarize(self, *args, env=None):
        return self.result(self.run_tracectl("summary", *args, env=env))

    def assert_usage_error(self, *args):
        completed = self.run_tracectl(*args)
        self.assertEqual(2, completed.returncode)
        self.assertEqual("", completed.stdout)
        self.assertIn("usage:", completed.stderr)

    def test_cli_usage_rejects_unknown_missing_duplicate_and_extra_arguments(self):
        cases = (
            ("unknown-action",),
            ("record", "unknown", "--reason", "blocked"),
            ("record", "recovery"),
            ("record", "recovery", "--reason"),
            ("record", "recovery", "--reason", "blocked", "--reason", "timeout"),
            ("record", "recovery", "--reason", "blocked", "--note", "secret"),
            ("record", "delegation", "--role", "explorer", "--role", "fixer", "--outcome", "accepted"),
            ("summary", "--all", "--all"),
            ("summary", "extra"),
        )
        for args in cases:
            with self.subTest(args=args):
                self.assert_usage_error(*args)

    def test_invalid_enum_values_are_rejected_before_session_resolution(self):
        env = dict(self.env, PATH=str(self.no_bin_dir))
        cases = (
            ("delegation", "--role", "unknown-role", "--outcome", "accepted"),
            ("delegation", "--role", "explorer", "--outcome", "unknown-outcome"),
            ("recovery", "--reason", "unknown-reason"),
            ("parallel", "--phase", "unknown-phase", "--outcome", "admitted"),
            ("parallel", "--phase", "admission", "--outcome", "unknown-outcome"),
            ("parallel", "--phase", "convergence", "--outcome", "admitted"),
        )
        for args in cases:
            with self.subTest(args=args):
                result = self.result(
                    self.run_tracectl("record", *args, env=env), ok=False
                )
                self.assertEqual("invalid_event", result["reason"])
                self.assertFalse((self.xdg / "agent-orchestration").exists())

    def test_each_event_shape_appends_with_private_permissions_and_xdg_path(self):
        events = (
            (
                ("delegation", "--role", "explorer", "--outcome", "accepted"),
                {"schema_version", "ts", "event", "role", "outcome"},
                "delegation",
            ),
            (
                ("recovery", "--reason", "timeout"),
                {"schema_version", "ts", "event", "reason"},
                "recovery",
            ),
            (
                ("parallel", "--phase", "admission", "--outcome", "admitted"),
                {"schema_version", "ts", "event", "phase", "outcome"},
                "parallel",
            ),
        )
        trace = self.trace_file()
        for args, expected_keys, expected_event in events:
            result = self.record(*args)
            self.assertEqual({"ok": True, "reason": "recorded"}, result)
            lines = trace.read_text(encoding="utf-8").splitlines()
            line = json.loads(lines[-1])
            self.assertEqual(expected_keys, set(line))
            self.assertEqual(1, line["schema_version"])
            self.assertEqual(expected_event, line["event"])
            self.assertRegex(line["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

        self.assertEqual(3, len(trace.read_text(encoding="utf-8").splitlines()))
        self.assertEqual(0o700, stat.S_IMODE(trace.parent.stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE(trace.stat().st_mode))
        self.assertEqual(self.xdg / "agent-orchestration", trace.parent.parent)
        self.assertEqual(self.state_file().with_suffix(".jsonl").name, trace.name)
        self.assertTrue(os.access(TRACECTL, os.X_OK))

        trace_name = trace.name
        trace_text = trace.read_text(encoding="utf-8")
        for private_value in (*self.identity.values(), str(self.repo), self.env["HERDR_PANE_ID"]):
            self.assertNotIn(private_value, trace_name)
            self.assertNotIn(private_value, trace_text)

    def test_privacy_and_free_form_arguments_never_reach_trace_storage(self):
        self.record("delegation", "--role", "fixer", "--outcome", "recovery")
        trace = self.trace_file()
        trace_text = trace.read_text(encoding="utf-8")
        forbidden = (
            "prompt",
            "result",
            "objective",
            "evidence",
            "path",
            "command",
            "token",
            "secret",
            str(self.repo),
            *self.identity.values(),
            "fake-pane-identifier-secret",
        )
        for value in forbidden:
            self.assertNotIn(value, trace_text)
            self.assertNotIn(value, trace.name)

        rejected = (
            ("record", "recovery", "--reason", "prompt"),
            ("record", "recovery", "--reason", "result"),
            ("record", "delegation", "--role", "secret", "--outcome", "accepted"),
            ("record", "parallel", "--phase", "admission", "--outcome", "objective"),
            ("record", "recovery", "--reason", "path"),
            ("record", "recovery", "--reason", "command"),
            ("record", "recovery", "--reason", "token"),
            ("record", "recovery", "--reason", "evidence"),
        )
        for args in rejected:
            with self.subTest(args=args):
                value = self.result(self.run_tracectl(*args), ok=False)
                self.assertEqual("invalid_event", value["reason"])
        self.assertEqual(1, len(trace.read_text(encoding="utf-8").splitlines()))

    def test_no_session_for_missing_herdr_or_missing_agent_session(self):
        for env, remove_herdr in (
            (dict(self.env, PATH=str(self.no_bin_dir)), True),
            (self.env, False),
        ):
            if not remove_herdr:
                self.set_herdr_identity(None)
            with self.subTest(remove_herdr=remove_herdr):
                result = self.result(
                    self.run_tracectl(
                        "record", "recovery", "--reason", "blocked", env=env
                    ),
                    ok=False,
                )
                self.assertEqual("no_session", result["reason"])
                self.assertFalse((self.xdg / "agent-orchestration").exists())
        self.set_herdr_identity(self.identity)

    def test_trace_unavailable_leaves_session_configuration_unchanged(self):
        state_file = self.state_file()
        state_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        original = b"pre-existing session configuration must remain byte-identical\n"
        state_file.write_bytes(original)
        traces_path = state_file.parent / "traces"
        traces_path.write_text("not a directory", encoding="utf-8")

        result = self.result(
            self.run_tracectl(
                "record", "recovery", "--reason", "blocked"
            ),
            ok=False,
        )
        self.assertEqual("trace_unavailable", result["reason"])
        self.assertEqual(original, state_file.read_bytes())
        self.assertTrue(traces_path.is_file())

    def test_summary_without_session_and_all_scope_without_session(self):
        env = dict(self.env, PATH=str(self.no_bin_dir))
        result = self.result(self.run_tracectl("summary", env=env), ok=False)
        self.assertEqual({"ok": False, "reason": "no_session"}, result)
        all_result = self.result(self.run_tracectl("summary", "--all", env=env))
        self.assertTrue(all_result["ok"])
        self.assertEqual("all", all_result["scope"])
        self.assertEqual(0, all_result["events"])
        self.assertFalse((self.xdg / "agent-orchestration").exists())

    def test_empty_summary_has_all_zero_counts(self):
        result = self.summarize()
        expected = TRACECTL_MODULE.empty_counts("session")
        self.assertEqual(expected, result)

    def test_summary_counts_delegations_recoveries_and_parallel_phases(self):
        self.record("delegation", "--role", "explorer", "--outcome", "accepted")
        self.record("delegation", "--role", "explorer", "--outcome", "recovery")
        self.record("delegation", "--role", "fixer", "--outcome", "accepted")
        self.record("recovery", "--reason", "timeout")
        self.record("parallel", "--phase", "admission", "--outcome", "admitted")
        self.record("parallel", "--phase", "admission", "--outcome", "disabled")
        self.record("parallel", "--phase", "convergence", "--outcome", "all_accepted")

        result = self.summarize()
        self.assertEqual(7, result["events"])
        self.assertEqual(0, result["invalid_lines"])
        self.assertEqual(
            {"accepted": 1, "recovery": 1}, result["delegations"]["explorer"]
        )
        self.assertEqual(
            {"accepted": 1, "recovery": 0}, result["delegations"]["fixer"]
        )
        self.assertEqual(set(TRACECTL_MODULE.RECOVERY_REASONS), set(result["recoveries"]))
        self.assertEqual(1, result["recoveries"]["timeout"])
        for reason, count in result["recoveries"].items():
            if reason != "timeout":
                self.assertEqual(0, count)
        self.assertEqual({"admitted": 1, "disabled": 1}, result["parallel"]["admission"])
        self.assertEqual({"all_accepted": 1}, result["parallel"]["convergence"])

    def test_summary_skips_and_counts_malformed_nonempty_lines(self):
        trace = self.trace_file()
        self.record("delegation", "--role", "fixer", "--outcome", "accepted")
        valid_extra = {
            "schema_version": 1,
            "ts": "anything-is-allowed-as-a-string",
            "event": "recovery",
            "reason": "blocked",
            "unexpected": "private-content-not-returned",
        }
        wrong_enum = {
            "schema_version": 1,
            "ts": "still-a-string",
            "event": "parallel",
            "phase": "admission",
            "outcome": "not-a-known-reason",
        }
        wrong_type = {
            "schema_version": 1,
            "ts": "also-a-string",
            "event": "parallel",
            "phase": "admission",
            "outcome": [],
        }
        with trace.open("a", encoding="utf-8") as stream:
            stream.write("{bad-json\n")
            stream.write(json.dumps(valid_extra, separators=(",", ":")) + "\n")
            stream.write(json.dumps(wrong_enum, separators=(",", ":")) + "\n")
            stream.write(json.dumps(wrong_type, separators=(",", ":")) + "\n")
            stream.write("\n")

        result = self.summarize()
        self.assertEqual(1, result["events"])
        self.assertEqual(4, result["invalid_lines"])
        self.assertEqual(1, result["delegations"]["fixer"]["accepted"])
        self.assertNotIn(str(trace), json.dumps(result))
        self.assertNotIn("private-content-not-returned", json.dumps(result))

    def test_all_scope_aggregates_two_session_trace_files(self):
        self.record("recovery", "--reason", "blocked")
        first_trace = self.trace_file()
        second_identity = {
            "source": "second-source-secret",
            "kind": "second-kind-secret",
            "value": str(self.repo / "second-session-secret.jsonl"),
        }
        self.set_herdr_identity(second_identity)
        self.record("delegation", "--role", "fixer", "--outcome", "accepted")
        second_trace = self.trace_file()
        self.assertNotEqual(first_trace.name, second_trace.name)

        current = self.summarize()
        self.assertEqual("session", current["scope"])
        self.assertEqual(1, current["events"])
        all_result = self.summarize("--all")
        self.assertEqual("all", all_result["scope"])
        self.assertEqual(2, all_result["events"])
        self.assertEqual(1, all_result["recoveries"]["blocked"])
        self.assertEqual(1, all_result["delegations"]["fixer"]["accepted"])
        self.assertNotIn(str(first_trace), json.dumps(all_result))
        self.assertNotIn(str(second_trace), json.dumps(all_result))

    def test_unreadable_trace_file_returns_trace_unavailable(self):
        trace = self.trace_file()
        trace.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        trace.mkdir()
        result = self.summarize()
        self.assertEqual({"ok": False, "reason": "trace_unavailable"}, result)


    def test_trace_symlink_is_rejected_without_modifying_its_target(self):
        trace = self.trace_file()
        trace.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = self.root / "symlink-target.jsonl"
        original = b"target must remain unchanged\n"
        target.write_bytes(original)
        trace.symlink_to(target)

        result = self.record("recovery", "--reason", "timeout")
        self.assertEqual({"ok": False, "reason": "trace_unavailable"}, result)
        self.assertTrue(trace.is_symlink())
        self.assertEqual(original, target.read_bytes())


    def test_nonregular_trace_file_is_rejected_without_writing(self):
        if not hasattr(os, "mkfifo") or not hasattr(os, "O_NONBLOCK"):
            self.skipTest("named pipes are unavailable")
        trace = self.trace_file()
        trace.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.mkfifo(trace)
        reader_fd = os.open(trace, os.O_RDONLY | os.O_NONBLOCK)
        try:
            result = self.record("recovery", "--reason", "timeout")
            self.assertEqual({"ok": False, "reason": "trace_unavailable"}, result)
            self.assertTrue(stat.S_ISFIFO(trace.stat().st_mode))
            self.assertEqual(b"", os.read(reader_fd, 1))
        finally:
            os.close(reader_fd)

    def test_record_restricts_preexisting_trace_directory_permissions(self):
        trace = self.trace_file()
        trace.parent.mkdir(mode=0o777, parents=True, exist_ok=True)
        trace.parent.chmod(0o777)
        self.assertEqual(0o777, stat.S_IMODE(trace.parent.stat().st_mode))

        result = self.record("recovery", "--reason", "timeout")
        self.assertEqual({"ok": True, "reason": "recorded"}, result)
        self.assertEqual(0o700, stat.S_IMODE(trace.parent.stat().st_mode))
        self.assertEqual(1, len(trace.read_text(encoding="utf-8").splitlines()))

    def test_record_stdout_failure_is_silent_and_event_is_appended(self):
        trace = self.trace_file()
        process = subprocess.Popen(
            [
                sys.executable,
                str(TRACECTL),
                "record",
                "recovery",
                "--reason",
                "timeout",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )
        self.assertIsNotNone(process.stdout)
        self.assertIsNotNone(process.stderr)
        process.stdout.close()
        stderr = process.stderr.read()
        returncode = process.wait(timeout=10)
        process.stderr.close()

        self.assertEqual(0, returncode, stderr)
        self.assertEqual("", stderr)
        self.assertEqual(1, len(trace.read_text(encoding="utf-8").splitlines()))


    def test_missing_sessionctl_is_best_effort_for_well_formed_commands(self):
        isolated_dir = self.root / "tracectl-without-sessionctl"
        isolated_dir.mkdir()
        isolated_script = isolated_dir / "tracectl"
        isolated_script.write_bytes(TRACECTL.read_bytes())
        self.assertEqual(["tracectl"], [path.name for path in isolated_dir.iterdir()])

        commands = (
            (("record", "recovery", "--reason", "timeout"), "trace_unavailable"),
            (("summary", "--all"), "trace_unavailable"),
            (("record", "recovery", "--reason", "unknown-reason"), "invalid_event"),
        )
        for args, reason in commands:
            with self.subTest(args=args):
                completed = subprocess.run(
                    [sys.executable, str(isolated_script), *args],
                    capture_output=True,
                    text=True,
                    env=self.env,
                    check=False,
                )
                result = self.result(completed, ok=False)
                self.assertEqual(reason, result["reason"])
                self.assertEqual(["tracectl"], [path.name for path in isolated_dir.iterdir()])
                self.assertEqual([], list(self.xdg.iterdir()))

    def test_parallel_reason_taxonomies_match_validator_calls(self):
        tree = ast.parse(PARALLEL_VALIDATE.read_text(encoding="utf-8"))

        def reason_literals(function_name):
            reasons = set()
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == function_name
                    and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)
                ):
                    reasons.add(node.args[1].value)
            return reasons

        self.assertEqual(
            reason_literals("admission_result"), TRACECTL_MODULE.ADMISSION_OUTCOMES
        )
        self.assertEqual(
            reason_literals("convergence_result"), TRACECTL_MODULE.CONVERGENCE_OUTCOMES
        )


if __name__ == "__main__":
    unittest.main()
