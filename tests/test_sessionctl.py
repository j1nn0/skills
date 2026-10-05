import json
import os
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
SECRET = "sessionctl-test-secret-value"


def role(harness="codex", model="gpt-test", effort="high"):
    return {"harness": harness, "model": model, "effort": effort}


def state(identity=None, explorer=None, fixer=None, version=2):
    return {
        "schema_version": version,
        "orchestrator_session": dict(identity or IDENTITY),
        "explorer": dict(explorer or role()),
        "fixer": dict(fixer or role("claude", "sonnet-test", "medium")),
    }


# Older schema-v2 files may still carry the obsolete active_orchestration key,
# valid, null, or malformed. It is inert legacy input and must never invalidate
# role configuration.
LEGACY_VALUES = (
    None,
    {
        "id": "123e4567-e89b-42d3-a456-426614174000",
        "label": "legacy objective",
        "status": "active",
        "created_at": "2026-06-01T12:00:00Z",
    },
    {"status": "malformed"},
    "not-an-object",
    ["unexpected"],
    42,
)


def legacy_state(active):
    document = state()
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

    def assert_mutations_refused_without_writing(self, cases, reason):
        path = self.state_path()
        for name, args, document, raw in cases:
            with self.subTest(mutation=name):
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                contents = raw if raw is not None else json.dumps(document, indent=2) + "\n"
                path.write_text(contents, encoding="utf-8")
                os.chmod(path.parent, 0o755)
                before = path.read_bytes()
                file_stat = path.stat()
                directory_stat = path.parent.stat()

                result = self.parse_result(self.run_sessionctl(*args), ok=False)
                self.assertEqual(reason, result["reason"])
                self.assertFalse(result["changed"])
                self.assertFalse(result["identity_matched"])
                self.assertTrue(result["state_available"])
                self.assertEqual(before, path.read_bytes())
                self.assertEqual(file_stat.st_ino, path.stat().st_ino)
                self.assertEqual(file_stat.st_mtime_ns, path.stat().st_mtime_ns)
                self.assertEqual(0o755, path.parent.stat().st_mode & 0o777)
                self.assertEqual(directory_stat.st_mtime_ns, path.parent.stat().st_mtime_ns)

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

    def test_inspect_matching_v2_reports_configuration(self):
        self.write_state(state())
        result = self.inspect()
        self.assertTrue(result["state_available"])
        self.assertEqual(2, result["schema_version"])
        self.assertTrue(result["identity_matched"])
        self.assertTrue(result["configuration_complete"])
        self.assertEqual(role(), result["explorer"])
        self.assertEqual(role("claude", "sonnet-test", "medium"), result["fixer"])

    def test_inspect_matching_v1_is_valid_and_does_not_upgrade(self):
        path = self.write_state(state(version=1))
        original = path.read_bytes()
        result = self.inspect()
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["schema_version"])
        self.assertTrue(result["identity_matched"])
        self.assertTrue(result["configuration_complete"])
        self.assertEqual(original, path.read_bytes())

    def test_inspect_missing_schema_version_defaults_to_v1(self):
        document = legacy_state(None)
        document.pop("schema_version")
        path = self.write_state(document)
        original = path.read_bytes()
        result = self.inspect()
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["schema_version"])
        self.assertTrue(result["configuration_complete"])
        self.assertEqual(original, path.read_bytes())

    def test_inspect_ignores_legacy_extra_field_values(self):
        for legacy_value in LEGACY_VALUES:
            with self.subTest(legacy_value=legacy_value):
                path = self.write_state(legacy_state(legacy_value))
                original = path.read_bytes()
                result = self.inspect()
                self.assertTrue(result["ok"])
                self.assertEqual(2, result["schema_version"])
                self.assertTrue(result["identity_matched"])
                self.assertTrue(result["configuration_complete"])
                self.assertEqual(role(), result["explorer"])
                self.assertEqual(role("claude", "sonnet-test", "medium"), result["fixer"])
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

    def test_set_role_refuses_mismatched_identity_without_writing(self):
        other = dict(IDENTITY, value="/different/session.jsonl")
        cases = [
            (
                "set-role",
                ("set-role", "--role", "fixer", "--harness", "updated", "--model", "new-model", "--effort", "medium"),
                state(identity=other),
                None,
            ),
        ]
        self.assert_mutations_refused_without_writing(cases, "identity_mismatch")

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

    def test_set_role_refuses_unreadable_state_without_writing(self):
        raw = "{not-json\n"
        cases = [
            (
                "set-role",
                ("set-role", "--role", "fixer", "--harness", "claude", "--model", "sonnet", "--effort", "low"),
                {},
                raw,
            ),
        ]
        self.assert_mutations_refused_without_writing(cases, "unreadable_state")

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
        self.assertEqual(
            {"schema_version", "orchestrator_session", "explorer", "fixer"},
            set(written),
        )
        self.assertEqual(role("codex", "test-model", "high"), written["explorer"])
        self.assertEqual({field: "" for field in ROLE_FIELDS}, written["fixer"])

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
        self.assertEqual(
            {"schema_version", "orchestrator_session", "explorer", "fixer"},
            set(written),
        )
        self.assertEqual(role("new", "model", "low"), written["explorer"])
        self.assertEqual(original["fixer"], written["fixer"])

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

    def test_set_role_drops_legacy_field_and_preserves_other_role(self):
        for legacy_value in LEGACY_VALUES:
            with self.subTest(legacy_value=legacy_value):
                original = legacy_state(legacy_value)
                self.write_state(original)
                result = self.parse_result(
                    self.set_role("explorer", "updated", "new-model", "low"), ok=True
                )
                self.assertTrue(result["changed"])
                self.assertTrue(result["configuration_complete"])
                written = self.read_written_state(result)
                self.assertEqual(2, written["schema_version"])
                self.assertEqual(
                    {"schema_version", "orchestrator_session", "explorer", "fixer"},
                    set(written),
                )
                self.assertEqual(IDENTITY, written["orchestrator_session"])
                self.assertEqual(role("updated", "new-model", "low"), written["explorer"])
                self.assertEqual(original["fixer"], written["fixer"])
                self.assertTrue(self.inspect()["configuration_complete"])

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
            self.set_role("explorer", "", "model", "low"), ok=False
        )
        self.assertEqual("invalid_role_value", refused["reason"])
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
        for args in ((), ("inspect", "extra"), ("set-role", "--role", "other"), ("orchestration", "get")):
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
