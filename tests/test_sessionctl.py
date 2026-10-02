import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SESSIONCTL = ROOT / "skills" / "agent-orchestration" / "scripts" / "sessionctl"
ROLE_FIELDS = ("harness", "model", "effort")
IDENTITY = {
    "source": "herdr:pi",
    "kind": "path",
    "value": "/tmp/sessionctl-test/session.jsonl",
}
ACTIVE_ID = "123e4567-e89b-42d3-a456-426614174000"
INTERRUPTED_ID = "123e4567-e89b-42d3-a456-426614174001"
SECRET = "sessionctl-test-secret-value"


def role(harness="codex", model="gpt-test", effort="high"):
    return {"harness": harness, "model": model, "effort": effort}


def state(identity=None, explorer=None, fixer=None, active=None, version=2):
    document = {
        "schema_version": version,
        "orchestrator_session": dict(identity or IDENTITY),
        "explorer": dict(explorer or role()),
        "fixer": dict(fixer or role("claude", "sonnet-test", "medium")),
    }
    if version == 2:
        document["active_orchestration"] = active
    return document


class SessionctlTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.xdg = self.root / "xdg-state"
        self.xdg.mkdir()
        self.herdr_path = self.bin_dir / "herdr"
        self.env = {
            "PATH": str(self.bin_dir),
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.xdg),
            "HERDR_PANE_ID": "pane-test-id",
        }
        self.set_herdr_identity(IDENTITY)

    def set_herdr_identity(self, identity=None, agent=SECRET):
        if identity is None:
            payload = {"id": "opaque-pane", "result": {"pane": {"id": "pane-metadata"}}}
        else:
            session = dict(identity)
            session["agent"] = agent
            payload = {
                "id": "opaque-response-id",
                "result": {"pane": {"id": "pane-metadata", "agent_session": session}},
            }
        response = json.dumps(payload, separators=(",", ":"))
        self.herdr_path.write_text(
            "#!" + sys.executable + "\n"
            "import sys\n"
            "sys.stdout.write(" + repr(response) + ")\n",
            encoding="utf-8",
        )
        self.herdr_path.chmod(0o755)

    def run_sessionctl(self, *args, env=None):
        return subprocess.run(
            [sys.executable, str(SESSIONCTL), *args],
            capture_output=True,
            text=True,
            env=self.env if env is None else env,
            check=False,
        )

    def parse_result(self, completed, ok=None):
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(completed.stdout.endswith("\n"), completed.stdout)
        self.assertEqual(1, completed.stdout.count("\n"), completed.stdout)
        result = json.loads(completed.stdout)
        self.assertEqual(
            json.dumps(result, separators=(",", ":")), completed.stdout[:-1]
        )
        if ok is not None:
            self.assertEqual(ok, result["ok"])
        if result["ok"]:
            self.assertEqual("", completed.stderr)
            self.assertIsNone(result["reason"])
        else:
            self.assertEqual(
                "sessionctl: " + result["reason"] + "\n", completed.stderr
            )
        self.assertEqual(
            {
                "ok",
                "action",
                "reason",
                "state_file",
                "schema_version",
                "session_available",
                "state_available",
                "identity_matched",
                "configuration_complete",
                "orchestrator_session",
                "explorer",
                "fixer",
                "active_orchestration",
                "active_orchestration_status",
                "changed",
            },
            set(result),
        )
        return result

    def inspect(self, ok=True):
        return self.parse_result(self.run_sessionctl("inspect"), ok=ok)

    def state_path(self):
        result = self.inspect()
        return Path(result["state_file"])

    def write_state(self, document, raw=None):
        path = self.state_path()
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(
            raw if raw is not None else json.dumps(document, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def read_written_state(self, result):
        return json.loads(Path(result["state_file"]).read_text(encoding="utf-8"))

    def set_role(self, name, harness=" codex ", model=" test-model ", effort=" high ", env=None):
        return self.run_sessionctl(
            "set-role",
            "--role",
            name,
            "--harness",
            harness,
            "--model",
            model,
            "--effort",
            effort,
            env=env,
        )

    def test_inspect_without_state_is_side_effect_free(self):
        result = self.inspect()
        self.assertEqual("inspect", result["action"])
        self.assertTrue(result["session_available"])
        self.assertFalse(result["state_available"])
        self.assertIsNone(result["schema_version"])
        self.assertFalse(result["identity_matched"])
        self.assertFalse(result["configuration_complete"])
        self.assertEqual(IDENTITY, result["orchestrator_session"])
        self.assertIsNone(result["explorer"])
        self.assertIsNone(result["fixer"])
        self.assertFalse(result["changed"])
        self.assertFalse((self.xdg / "agent-orchestration").exists())

    def test_inspect_matching_v2_reports_configuration_and_active_null(self):
        self.write_state(state())
        result = self.inspect()
        self.assertTrue(result["state_available"])
        self.assertEqual(2, result["schema_version"])
        self.assertTrue(result["identity_matched"])
        self.assertTrue(result["configuration_complete"])
        self.assertEqual(role(), result["explorer"])
        self.assertEqual(role("claude", "sonnet-test", "medium"), result["fixer"])
        self.assertIsNone(result["active_orchestration"])
        self.assertEqual("valid", result["active_orchestration_status"])

    def test_inspect_matching_v1_is_valid_and_does_not_upgrade(self):
        path = self.write_state(state(version=1))
        original = path.read_bytes()
        result = self.inspect()
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["schema_version"])
        self.assertTrue(result["identity_matched"])
        self.assertTrue(result["configuration_complete"])
        self.assertIsNone(result["active_orchestration"])
        self.assertEqual("absent", result["active_orchestration_status"])
        self.assertEqual(original, path.read_bytes())

    def test_inspect_mismatched_identity_does_not_accept_configuration(self):
        other = dict(IDENTITY, value="/different/session.jsonl")
        self.write_state(state(identity=other))
        result = self.inspect(ok=False)
        self.assertEqual("identity_mismatch", result["reason"])
        self.assertFalse(result["identity_matched"])
        self.assertFalse(result["configuration_complete"])
        self.assertEqual(IDENTITY, result["orchestrator_session"])
        self.assertEqual(role(), result["explorer"])

    def test_mutation_overwrites_mismatched_identity_at_same_path(self):
        other = dict(IDENTITY, value="/different/session.jsonl")
        path = self.write_state(state(identity=other))
        result = self.parse_result(self.set_role("fixer", "updated", "new-model", "medium"), ok=True)
        written = self.read_written_state(result)
        self.assertTrue(result["changed"])
        self.assertEqual(IDENTITY, written["orchestrator_session"])
        self.assertEqual(role(), written["explorer"])
        self.assertEqual(role("updated", "new-model", "medium"), written["fixer"])
        self.assertEqual(path, Path(result["state_file"]))
        self.assertTrue(self.inspect()["identity_matched"])

    def test_inspect_refuses_missing_agent_session_without_fallback_or_writes(self):
        self.set_herdr_identity(None)
        result = self.inspect(ok=False)
        self.assertEqual("no_session", result["reason"])
        self.assertFalse(result["session_available"])
        self.assertIsNone(result["state_file"])
        self.assertIsNone(result["orchestrator_session"])
        self.assertFalse((self.xdg / "agent-orchestration").exists())

    def test_inspect_incomplete_explorer(self):
        incomplete = role(harness="", model="gpt-test", effort="high")
        self.write_state(state(explorer=incomplete))
        result = self.inspect()
        self.assertFalse(result["configuration_complete"])
        self.assertEqual(incomplete, result["explorer"])
        self.assertEqual(role("claude", "sonnet-test", "medium"), result["fixer"])

    def test_inspect_incomplete_fixer(self):
        incomplete = role("claude", "", "medium")
        self.write_state(state(fixer=incomplete))
        result = self.inspect()
        self.assertFalse(result["configuration_complete"])
        self.assertEqual(role(), result["explorer"])
        self.assertEqual(incomplete, result["fixer"])

    def test_inspect_malformed_json_is_unreadable_state(self):
        path = self.write_state({}, raw="{not-json\n")
        result = self.inspect(ok=False)
        self.assertEqual("unreadable_state", result["reason"])
        self.assertTrue(result["state_available"])
        self.assertIsNone(result["schema_version"])
        self.assertFalse(result["configuration_complete"])
        self.assertIsNone(result["explorer"])
        self.assertEqual("{not-json\n", path.read_text(encoding="utf-8"))

    def test_successful_mutation_overwrites_unreadable_state(self):
        path = self.write_state({}, raw="{not-json\n")
        result = self.parse_result(self.set_role("fixer", "claude", "sonnet", "low"), ok=True)
        written = self.read_written_state(result)
        self.assertTrue(result["changed"])
        self.assertEqual(2, written["schema_version"])
        self.assertEqual(IDENTITY, written["orchestrator_session"])
        self.assertEqual({field: "" for field in ROLE_FIELDS}, written["explorer"])
        self.assertEqual(role("claude", "sonnet", "low"), written["fixer"])
        self.assertIsNone(written["active_orchestration"])
        self.assertTrue(self.inspect()["identity_matched"])

    def test_inspect_malformed_active_is_reported_without_repair(self):
        document = state()
        document["active_orchestration"] = {
            "id": ACTIVE_ID,
            "label": "bad status",
            "status": "paused",
            "created_at": "2026-06-01T12:00:00Z",
        }
        path = self.write_state(document)
        original = path.read_bytes()
        result = self.inspect()
        self.assertTrue(result["ok"])
        self.assertTrue(result["configuration_complete"])
        self.assertEqual("malformed", result["active_orchestration_status"])
        self.assertIsNone(result["active_orchestration"])
        self.assertEqual(original, path.read_bytes())

    def test_inspect_valid_active_and_interrupted_records(self):
        active = {
            "id": ACTIVE_ID,
            "label": "bounded work",
            "status": "active",
            "created_at": "2026-06-01T12:00:00.123Z",
        }
        self.write_state(state(active=active))
        result = self.inspect()
        self.assertEqual("valid", result["active_orchestration_status"])
        self.assertEqual(active, result["active_orchestration"])

        interrupted = dict(active, id=INTERRUPTED_ID, status="interrupted")
        interrupted["created_at"] = "2026-06-01T14:00:00+02:00"
        self.write_state(state(active=interrupted))
        result = self.inspect()
        self.assertEqual("interrupted", result["active_orchestration"]["status"])
        self.assertEqual(interrupted, result["active_orchestration"])

    def test_session_key_is_deterministic_distinct_and_matches_posix_cksum(self):
        first = self.inspect()["state_file"]
        second = self.inspect()["state_file"]
        self.assertEqual(first, second)

        other_identity = dict(IDENTITY, value="/tmp/sessionctl-test/other.jsonl")
        self.set_herdr_identity(other_identity)
        third = self.inspect()["state_file"]
        self.assertNotEqual(first, third)

        fixture_identity = {"source": "pi", "kind": "claude", "value": "abc-123"}
        self.set_herdr_identity(fixture_identity)
        fixture_path = Path(self.inspect()["state_file"])
        self.assertEqual("session-2336936049-18.json", fixture_path.name)
        cksum = subprocess.run(
            ["cksum"],
            input=b"pi\nclaude\nabc-123\n",
            capture_output=True,
            check=True,
        )
        self.assertEqual([b"2336936049", b"18"], cksum.stdout.split()[:2])

    def test_explorer_and_fixer_role_writes_preserve_opposite_and_round_trip(self):
        explorer_result = self.parse_result(self.set_role("explorer"), ok=True)
        self.assertTrue(explorer_result["changed"])
        written = self.read_written_state(explorer_result)
        self.assertEqual(2, written["schema_version"])
        self.assertEqual(role("codex", "test-model", "high"), written["explorer"])
        self.assertEqual({field: "" for field in ROLE_FIELDS}, written["fixer"])
        self.assertIsNone(written["active_orchestration"])

        fixer_result = self.parse_result(
            self.set_role("fixer", " claude ", " sonnet ", " medium "), ok=True
        )
        written = self.read_written_state(fixer_result)
        self.assertEqual(role("codex", "test-model", "high"), written["explorer"])
        self.assertEqual(role("claude", "sonnet", "medium"), written["fixer"])
        round_trip = self.inspect()
        self.assertTrue(round_trip["configuration_complete"])
        self.assertEqual(written["explorer"], round_trip["explorer"])
        self.assertEqual(written["fixer"], round_trip["fixer"])

    def test_fixer_only_write_leaves_explorer_empty(self):
        result = self.parse_result(self.set_role("fixer"), ok=True)
        written = self.read_written_state(result)
        self.assertEqual({field: "" for field in ROLE_FIELDS}, written["explorer"])
        self.assertEqual(role("codex", "test-model", "high"), written["fixer"])

    def test_role_mutation_upgrades_v1_and_drops_unknown_top_level_keys(self):
        original = state(version=1)
        original["legacy_unknown"] = {"drop": True}
        self.write_state(original)
        result = self.parse_result(self.set_role("explorer", "new", "model", "low"), ok=True)
        written = self.read_written_state(result)
        self.assertEqual(2, written["schema_version"])
        self.assertEqual({"schema_version", "orchestrator_session", "explorer", "fixer", "active_orchestration"}, set(written))
        self.assertEqual(role("new", "model", "low"), written["explorer"])
        self.assertEqual(original["fixer"], written["fixer"])
        self.assertIsNone(written["active_orchestration"])

    def test_empty_role_value_refuses_without_creating_state_directory(self):
        result = self.parse_result(self.set_role("explorer", "codex", "   ", "high"), ok=False)
        self.assertEqual("invalid_role_value", result["reason"])
        self.assertFalse(result["changed"])
        self.assertFalse((self.xdg / "agent-orchestration").exists())

    def test_role_mutation_without_session_refuses_without_writing(self):
        self.set_herdr_identity(None)
        result = self.parse_result(self.set_role("explorer"), ok=False)
        self.assertEqual("no_session", result["reason"])
        self.assertIsNone(result["state_file"])
        self.assertFalse((self.xdg / "agent-orchestration").exists())

    def test_orchestration_set_interrupt_resume_clear_and_idempotence(self):
        set_result = self.parse_result(
            self.run_sessionctl(
                "orchestration", "set", "--id", ACTIVE_ID, "--label", "  rollout review  "
            ),
            ok=True,
        )
        record = set_result["active_orchestration"]
        self.assertEqual(ACTIVE_ID, record["id"])
        self.assertEqual("  rollout review  ", record["label"])
        self.assertEqual("active", record["status"])
        self.assertTrue(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", record["created_at"]))
        self.assertEqual({"id", "label", "status", "created_at"}, set(record))

        interrupted = self.parse_result(
            self.run_sessionctl("orchestration", "interrupt"), ok=True
        )
        interrupted_record = interrupted["active_orchestration"]
        self.assertEqual("interrupted", interrupted_record["status"])
        for field in ("id", "label", "created_at"):
            self.assertEqual(record[field], interrupted_record[field])
        state_path = Path(interrupted["state_file"])
        unchanged = state_path.read_bytes()
        again = self.parse_result(
            self.run_sessionctl("orchestration", "interrupt"), ok=True
        )
        self.assertFalse(again["changed"])
        self.assertEqual(unchanged, state_path.read_bytes())

        resumed = self.parse_result(self.run_sessionctl("orchestration", "resume"), ok=True)
        self.assertEqual("active", resumed["active_orchestration"]["status"])
        for field in ("id", "label", "created_at"):
            self.assertEqual(record[field], resumed["active_orchestration"][field])
        active_bytes = state_path.read_bytes()
        resume_again = self.parse_result(self.run_sessionctl("orchestration", "resume"), ok=True)
        self.assertFalse(resume_again["changed"])
        self.assertEqual(active_bytes, state_path.read_bytes())
        cleared = self.parse_result(self.run_sessionctl("orchestration", "clear"), ok=True)
        self.assertTrue(cleared["changed"])
        self.assertIsNone(cleared["active_orchestration"])
        cleared_bytes = state_path.read_bytes()
        clear_again = self.parse_result(self.run_sessionctl("orchestration", "clear"), ok=True)
        self.assertFalse(clear_again["changed"])
        self.assertEqual(cleared_bytes, state_path.read_bytes())

    def test_orchestration_clear_on_missing_state_is_idempotent(self):
        result = self.parse_result(self.run_sessionctl("orchestration", "clear"), ok=True)
        self.assertFalse(result["changed"])
        self.assertFalse(result["state_available"])
        self.assertFalse((self.xdg / "agent-orchestration").exists())

    def test_malformed_active_is_repaired_in_one_write_while_preserving_roles(self):
        document = state()
        document["active_orchestration"] = {"status": "not-valid"}
        self.write_state(document)
        result = self.parse_result(self.set_role("explorer", "updated", "new-model", "low"), ok=True)
        written = self.read_written_state(result)
        self.assertEqual(role("updated", "new-model", "low"), written["explorer"])
        self.assertEqual(document["fixer"], written["fixer"])
        self.assertIsNone(written["active_orchestration"])
        self.assertEqual("valid", result["active_orchestration_status"])

    def test_interrupt_resume_refuse_null_or_malformed_without_writing(self):
        path = self.write_state(state())
        before = path.read_bytes()
        for verb, reason in (
            ("interrupt", "no_active_orchestration"),
            ("resume", "no_active_orchestration"),
        ):
            with self.subTest(verb=verb):
                result = self.parse_result(
                    self.run_sessionctl("orchestration", verb), ok=False
                )
                self.assertEqual(reason, result["reason"])
                self.assertEqual(before, path.read_bytes())

        malformed = state()
        malformed["active_orchestration"] = {"label": "bad"}
        self.write_state(malformed)
        before = path.read_bytes()
        result = self.parse_result(self.run_sessionctl("orchestration", "resume"), ok=False)
        self.assertEqual("malformed_active_orchestration", result["reason"])
        self.assertEqual(before, path.read_bytes())

    def test_invalid_orchestration_id_and_label_refuse_without_writes(self):
        path = self.state_path()
        for args, reason in (
            (("--id", "ABC-e4567-e89b-42d3-a456-426614174000", "--label", "task"), "invalid_id"),
            (("--id", ACTIVE_ID, "--label", " \n "), "invalid_label"),
            (("--id", ACTIVE_ID, "--label", "x" * 257), "invalid_label"),
        ):
            with self.subTest(reason=reason, args=args):
                result = self.parse_result(
                    self.run_sessionctl("orchestration", "set", *args), ok=False
                )
                self.assertEqual(reason, result["reason"])
                self.assertFalse(path.exists())
                self.assertFalse((self.xdg / "agent-orchestration").exists())

    def test_atomic_replace_permissions_and_no_partial_write_on_refusal(self):
        directory = self.xdg / "agent-orchestration"
        directory.mkdir(mode=0o755)
        os.chmod(directory, 0o755)
        initial = self.parse_result(self.set_role("explorer", "first", "model", "low"), ok=True)
        path = Path(initial["state_file"])
        first_stat = path.stat()
        self.assertEqual(0o600, first_stat.st_mode & 0o777)
        self.assertEqual(0o700, directory.stat().st_mode & 0o777)

        updated = self.parse_result(self.set_role("fixer", "second", "model", "medium"), ok=True)
        second_stat = path.stat()
        self.assertNotEqual(first_stat.st_ino, second_stat.st_ino)
        self.assertEqual(0o600, second_stat.st_mode & 0o777)
        self.assertEqual(0o700, directory.stat().st_mode & 0o777)
        self.assertEqual([], list(directory.glob(".sessionctl-*.tmp")))
        unchanged = path.read_bytes()

        refused = self.parse_result(
            self.run_sessionctl("orchestration", "set", "--id", "bad", "--label", "task"),
            ok=False,
        )
        self.assertEqual("invalid_id", refused["reason"])
        self.assertEqual(unchanged, path.read_bytes())
        self.assertEqual(second_stat.st_ino, path.stat().st_ino)
        self.assertEqual([], list(directory.glob(".sessionctl-*.tmp")))
        self.assertEqual(updated["state_file"], str(path))

    def test_inspect_refusal_does_not_create_directory(self):
        self.set_herdr_identity(None)
        result = self.inspect(ok=False)
        self.assertEqual("no_session", result["reason"])
        self.assertFalse((self.xdg / "agent-orchestration").exists())

    def test_privacy_ignores_agent_metadata_and_secret_environment_values(self):
        env = dict(self.env)
        env["API_TOKEN"] = SECRET
        env["HERDR_RESULT"] = SECRET
        result = self.parse_result(self.set_role("explorer", env=env), ok=True)
        state_text = Path(result["state_file"]).read_text(encoding="utf-8")
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertNotIn(SECRET, state_text)
        self.assertNotIn("agent", state_text)
        self.assertNotIn("opaque-response-id", state_text)

    def test_xdg_missing_or_empty_uses_home_state_directory(self):
        for xdg_value in (None, ""):
            with self.subTest(xdg_value=xdg_value):
                env = dict(self.env)
                if xdg_value is None:
                    env.pop("XDG_STATE_HOME")
                else:
                    env["XDG_STATE_HOME"] = xdg_value
                result = self.parse_result(
                    subprocess.run(
                        [sys.executable, str(SESSIONCTL), "inspect"],
                        capture_output=True,
                        text=True,
                        env=env,
                        check=False,
                    ),
                    ok=True,
                )
                self.assertEqual(
                    self.home / ".local" / "state" / "agent-orchestration",
                    Path(result["state_file"]).parent,
                )

    def test_argv_errors_exit_two_with_usage_and_no_json(self):
        for args in ((), ("inspect", "extra"), ("set-role", "--role", "other"), ("orchestration", "set", "--id", ACTIVE_ID)):
            with self.subTest(args=args):
                completed = self.run_sessionctl(*args)
                self.assertEqual(2, completed.returncode)
                self.assertEqual("", completed.stdout)
                self.assertIn("usage:", completed.stderr)

    def test_unset_herdr_pane_id_refuses_without_fallback(self):
        env = dict(self.env)
        env.pop("HERDR_PANE_ID")
        result = self.parse_result(
            subprocess.run(
                [sys.executable, str(SESSIONCTL), "inspect"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            ),
            ok=False,
        )
        self.assertEqual("no_session", result["reason"])
        self.assertIsNone(result["state_file"])
        self.assertFalse((self.xdg / "agent-orchestration").exists())


if __name__ == "__main__":
    unittest.main()
