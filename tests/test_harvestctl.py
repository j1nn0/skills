import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
HARVESTCTL = ROOT / "skills" / "agent-orchestration" / "scripts" / "harvestctl"
PLUGIN_ID = "j1nn0.herdr-harvest"
CAPTURE_PROTOCOL = "harvest-capture"
LOCATOR_PROTOCOL = "harvest-runtime-locator"
ORCHESTRATION_ID = "123e4567-e89b-42d3-a456-426614174000"
EXISTING_ID = "123e4567-e89b-42d3-a456-426614174001"
SECRET = "harvestctl-test-secret-value"

HERDR_STUB = '''
import json
import os
import sys

with open(os.environ["HARVEST_TEST_CONFIG"], encoding="utf-8") as stream:
    config = json.load(stream)
args = sys.argv[1:]
with open(config["herdr_log"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(args) + "\\n")
if args == ["plugin", "list", "--plugin", "j1nn0.herdr-harvest", "--json"]:
    plan = config["herdr_list"]
elif args == ["plugin", "config-dir", "j1nn0.herdr-harvest"]:
    plan = config["herdr_config_dir"]
else:
    plan = {"returncode": 9, "stdout": "", "stderr": "unexpected herdr call"}
sys.stdout.write(plan.get("stdout", ""))
sys.stderr.write(plan.get("stderr", ""))
sys.exit(plan.get("returncode", 0))
'''

NODE_STUB = '''
import json
import os
import sys

with open(os.environ["HARVEST_TEST_CONFIG"], encoding="utf-8") as stream:
    config = json.load(stream)
args = sys.argv[1:]
if args[-1:] == ["--capabilities"]:
    plan = config["node_capabilities"]
else:
    captured_env = {
        "harvest_state_dir_present": "HARVEST_STATE_DIR" in os.environ,
        "plugin_state_dir": os.environ.get("HERDR_PLUGIN_STATE_DIR"),
        "socket_path": os.environ.get("HERDR_SOCKET_PATH"),
        "api_token": os.environ.get("API_TOKEN"),
        "argv": args[1:],
    }
    with open(config["capture_log"], "w", encoding="utf-8") as stream:
        json.dump(captured_env, stream)
    plan = config["node_capture"]
sys.stdout.write(plan.get("stdout", ""))
sys.stderr.write(plan.get("stderr", ""))
sys.exit(plan.get("returncode", 0))
'''


def json_plan(value, returncode=0):
    return {"returncode": returncode, "stdout": json.dumps(value) + "\n", "stderr": ""}


def plugin_record(root, enabled=True, plugin_root=None):
    return {
        "plugin_id": PLUGIN_ID,
        "enabled": enabled,
        "plugin_root": str(root) if plugin_root is None else plugin_root,
        "version": "diagnostic-only-version",
    }


def capabilities(features=None, roles=None, protocol=CAPTURE_PROTOCOL, version=1):
    return {
        "protocol": protocol,
        "protocolVersion": version,
        "features": ["orchestration-claim", "runtime-locator"] if features is None else features,
        "roles": ["explorer", "fixer"] if roles is None else roles,
    }


def locator(state_dir, socket_path, protocol=LOCATOR_PROTOCOL, version=1, plugin_id=PLUGIN_ID):
    return {
        "protocol": protocol,
        "protocolVersion": version,
        "pluginId": plugin_id,
        "stateDir": str(state_dir),
        "socketPath": socket_path,
        "updatedAtMs": 1,
    }


def capture_summary(status="captured", claim_status="claimed", orchestration_id=ORCHESTRATION_ID):
    summary = {"status": status, "paneId": "opaque-pane"}
    if claim_status is not None:
        summary["orchestration"] = {"status": claim_status, "id": orchestration_id}
    return summary


class HarvestctlTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.plugin_root = self.root / "fixture-plugin-root"
        self.config_dir = self.root / "fixture-config-dir"
        self.config_dir.mkdir()
        self.state_dir = self.root / "fixture-runtime-state"
        self.socket_path = str(self.root / "fixture-herdr-socket")
        self.locator_path = self.config_dir / "orchestration-capture-runtime.json"
        self.config_path = self.root / "fake-tool-config.json"
        self.herdr_log = self.root / "herdr-invocations.jsonl"
        self.capture_log = self.root / "capture-environment.json"
        self.herdr_path = self.bin_dir / "herdr"
        self.node_path = self.bin_dir / "node"
        self.herdr_path.write_text(
            "#!" + sys.executable + "\n" + HERDR_STUB, encoding="utf-8"
        )
        self.node_path.write_text(
            "#!" + sys.executable + "\n" + NODE_STUB, encoding="utf-8"
        )
        self.herdr_path.chmod(0o755)
        self.node_path.chmod(0o755)
        self.env = {
            "PATH": str(self.bin_dir),
            "HOME": str(self.home),
            "HERDR_SOCKET_PATH": self.socket_path,
            "HARVEST_STATE_DIR": str(self.root / "wrong-harvest-state"),
            "HARVEST_TEST_CONFIG": str(self.config_path),
            "API_TOKEN": SECRET,
            "HERDR_RESULT": "another-secret-fixture",
        }
        self.reset_fake_tools()

    def reset_fake_tools(self):
        plugin_list = {"result": {"plugins": [plugin_record(self.plugin_root)]}}
        successful_capture = capture_summary()
        self.fake = {
            "herdr_log": str(self.herdr_log),
            "capture_log": str(self.capture_log),
            "herdr_list": json_plan(plugin_list),
            "herdr_config_dir": {
                "returncode": 0,
                "stdout": str(self.config_dir) + "\n",
                "stderr": "",
            },
            "node_capabilities": json_plan(capabilities()),
            "node_capture": json_plan(successful_capture),
        }
        self.write_fake_config()
        self.write_locator(locator(self.state_dir, self.socket_path))

    def write_fake_config(self):
        self.config_path.write_text(json.dumps(self.fake), encoding="utf-8")

    def write_locator(self, document=None, raw=None):
        if raw is None:
            raw = json.dumps(document, indent=2) + "\n"
        self.locator_path.write_text(raw, encoding="utf-8")
        self.locator_path.chmod(0o600)

    def set_plugin_list(self, response=None, raw=None, returncode=0):
        if raw is None:
            raw = json.dumps(response) + "\n"
        self.fake["herdr_list"] = {
            "returncode": returncode,
            "stdout": raw,
            "stderr": SECRET,
        }
        self.write_fake_config()

    def set_capabilities(self, response=None, raw=None, returncode=0):
        if raw is None:
            raw = json.dumps(response if response is not None else capabilities()) + "\n"
        self.fake["node_capabilities"] = {
            "returncode": returncode,
            "stdout": raw,
            "stderr": SECRET,
        }
        self.write_fake_config()

    def set_capture(self, response=None, raw=None, returncode=0):
        if raw is None:
            raw = json.dumps(response if response is not None else capture_summary()) + "\n"
        self.fake["node_capture"] = {
            "returncode": returncode,
            "stdout": raw,
            "stderr": SECRET,
        }
        self.write_fake_config()

    def run_harvestctl(self, *args, env=None):
        return subprocess.run(
            [sys.executable, str(HARVESTCTL), *args],
            capture_output=True,
            text=True,
            env=self.env if env is None else env,
            check=False,
        )

    def doctor(self, role="explorer", env=None):
        return self.run_harvestctl("doctor", "--role", role, env=env)

    def claim_args(self, pane="delegated-pane", orchestration_id=ORCHESTRATION_ID, label="bounded task", role="explorer"):
        return (
            "claim",
            "--pane",
            pane,
            "--id",
            orchestration_id,
            "--label",
            label,
            "--role",
            role,
        )

    def parse_result(self, completed, action):
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(completed.stdout.endswith("\n"), completed.stdout)
        self.assertEqual(1, completed.stdout.count("\n"), completed.stdout)
        result = json.loads(completed.stdout)
        self.assertEqual(json.dumps(result, separators=(",", ":")), completed.stdout[:-1])
        expected_keys = (
            {"ok", "available", "claim_supported", "reason", "role"}
            if action == "doctor"
            else {"ok", "claimed", "status", "claim_status", "reason"}
        )
        self.assertEqual(expected_keys, set(result))
        expected_stderr = "" if result["reason"] is None else "harvestctl: " + result["reason"] + "\n"
        self.assertEqual(expected_stderr, completed.stderr)
        protected_values = (
            str(self.plugin_root),
            str(self.config_dir),
            str(self.state_dir),
            self.socket_path,
            self.env["HARVEST_STATE_DIR"],
            SECRET,
            self.env["HERDR_RESULT"],
            "HARVEST_STATE_DIR",
            "HERDR_PLUGIN_STATE_DIR",
        )
        for value in protected_values:
            self.assertNotIn(value, completed.stdout)
            self.assertNotIn(value, completed.stderr)
        return result

    def assert_doctor(self, completed, available, reason=None, role="explorer"):
        result = self.parse_result(completed, "doctor")
        self.assertEqual(
            {
                "ok": True,
                "available": available,
                "claim_supported": available,
                "reason": reason,
                "role": role,
            },
            result,
        )
        return result

    def assert_unavailable_claim(self, completed, reason):
        result = self.parse_result(completed, "claim")
        self.assertEqual(
            {
                "ok": False,
                "claimed": False,
                "status": "unavailable",
                "claim_status": None,
                "reason": reason,
            },
            result,
        )
        self.assertFalse(self.capture_log.exists())
        return result

    def test_doctor_success_is_side_effect_free_and_does_not_require_locator(self):
        self.locator_path.unlink()
        self.fake["herdr_config_dir"]["returncode"] = 1
        self.write_fake_config()
        self.assert_doctor(self.doctor(), True)
        calls = [json.loads(line) for line in self.herdr_log.read_text().splitlines()]
        self.assertEqual(
            [["plugin", "list", "--plugin", PLUGIN_ID, "--json"]], calls
        )
        self.assertFalse(self.capture_log.exists())

    def test_plugin_discovery_failures(self):
        cases = (
            ("missing", {"result": {"plugins": []}}, None, 0),
            ("disabled", {"result": {"plugins": [plugin_record(self.plugin_root, enabled=False)]}}, None, 0),
            ("empty root", {"result": {"plugins": [plugin_record(self.plugin_root, plugin_root="  ")]}}, None, 0),
            ("malformed JSON", None, "{not-json\n", 0),
            ("herdr failure", None, json.dumps({"result": {"plugins": [plugin_record(self.plugin_root)]}}) + "\n", 1),
        )
        for name, response, raw, returncode in cases:
            with self.subTest(case=name):
                self.reset_fake_tools()
                self.set_plugin_list(response=response, raw=raw, returncode=returncode)
                self.assert_doctor(self.doctor(), False, "plugin_unavailable")

    def test_capability_negotiation_failures(self):
        invalid_features = ["runtime-locator"]
        cases = (
            ("node failure", None, None, 1, "capability_probe_failed"),
            ("malformed JSON", None, "{not-json\n", 0, "capability_invalid"),
            ("wrong protocol", capabilities(protocol="other"), None, 0, "protocol_mismatch"),
            ("wrong version", capabilities(version=2), None, 0, "protocol_version_mismatch"),
            ("missing feature", capabilities(features=invalid_features), None, 0, "feature_missing"),
            ("role unsupported", capabilities(roles=["fixer"]), None, 0, "role_unsupported"),
        )
        for name, response, raw, returncode, reason in cases:
            with self.subTest(case=name):
                self.reset_fake_tools()
                self.set_capabilities(response=response, raw=raw, returncode=returncode)
                self.assert_doctor(self.doctor(), False, reason)

    def test_claim_captured_duplicate_and_already_claimed(self):
        cases = (
            ("captured", "claimed", "captured", "claimed"),
            ("duplicate", "claimed", "duplicate", "claimed"),
            ("duplicate", "already_claimed", "duplicate", "already_claimed"),
        )
        for native_status, native_claim_status, status, claim_status in cases:
            with self.subTest(status=status, claim_status=claim_status):
                self.reset_fake_tools()
                self.set_capture(
                    capture_summary(native_status, native_claim_status)
                )
                result = self.parse_result(self.run_harvestctl(*self.claim_args()), "claim")
                self.assertEqual(
                    {
                        "ok": True,
                        "claimed": True,
                        "status": status,
                        "claim_status": claim_status,
                        "reason": None,
                    },
                    result,
                )


    def test_claim_revalidates_capabilities_after_a_prior_doctor_verdict(self):
        self.assert_doctor(self.doctor(), True)
        self.set_capabilities(capabilities(protocol="changed-after-doctor"))
        result = self.assert_unavailable_claim(
            self.run_harvestctl(*self.claim_args()), "protocol_mismatch"
        )
        self.assertEqual("unavailable", result["status"])
    def test_claim_uses_explicit_cli_identity_and_sanitized_runtime_environment(self):
        summary = capture_summary()
        summary["debug"] = SECRET
        summary["reportedPluginRoot"] = str(self.plugin_root)
        self.set_capture(summary)
        label = "  preserve this label verbatim  "
        result = self.parse_result(
            self.run_harvestctl(*self.claim_args(pane="pane-from-cli", label=label)),
            "claim",
        )
        self.assertTrue(result["claimed"])
        received = json.loads(self.capture_log.read_text(encoding="utf-8"))
        self.assertFalse(received["harvest_state_dir_present"])
        self.assertEqual(str(self.state_dir), received["plugin_state_dir"])
        self.assertEqual(self.socket_path, received["socket_path"])
        self.assertEqual(SECRET, received["api_token"])
        self.assertEqual(
            [
                "--pane",
                "pane-from-cli",
                "--orchestration-id",
                ORCHESTRATION_ID,
                "--orchestration-label",
                label,
                "--orchestration-role",
                "explorer",
            ],
            received["argv"],
        )

    def test_runtime_locator_failures_are_unavailable(self):
        cases = (
            ("missing", None, None, None),
            ("malformed", None, "{not-json\n", None),
            ("wrong protocol", locator(self.state_dir, self.socket_path, protocol="other"), None, None),
            ("wrong version", locator(self.state_dir, self.socket_path, version=2), None, None),
            ("wrong plugin id", locator(self.state_dir, self.socket_path, plugin_id="other.plugin"), None, None),
            ("relative state dir", locator("relative-state", self.socket_path), None, None),
            ("empty state dir", locator("", self.socket_path), None, None),
            ("empty socket", locator(self.state_dir, ""), None, None),
            ("socket mismatch", locator(self.state_dir, str(self.root / "another-socket")), None, None),
            ("config-dir failure", None, None, 1),
        )
        for name, document, raw, config_returncode in cases:
            with self.subTest(case=name):
                self.reset_fake_tools()
                if name == "missing":
                    self.locator_path.unlink()
                elif name != "config-dir failure":
                    self.write_locator(document, raw=raw)
                if config_returncode is not None:
                    self.fake["herdr_config_dir"]["returncode"] = config_returncode
                    self.write_fake_config()
                self.assert_unavailable_claim(
                    self.run_harvestctl(*self.claim_args()), "runtime_locator_unavailable"
                )

    def test_claim_requires_current_socket_environment(self):
        env = dict(self.env)
        env.pop("HERDR_SOCKET_PATH")
        self.assert_unavailable_claim(
            self.run_harvestctl(*self.claim_args(), env=env),
            "runtime_locator_unavailable",
        )

    def test_native_skipped_failed_and_conflict_outcomes(self):
        cases = (
            (
                "skipped",
                capture_summary("skipped", claim_status=None),
                0,
                {"ok": False, "claimed": False, "status": "skipped", "claim_status": None, "reason": "capture_skipped"},
            ),
            (
                "failed",
                capture_summary("failed", claim_status=None),
                1,
                {"ok": False, "claimed": False, "status": "failed", "claim_status": None, "reason": "capture_failed"},
            ),
            (
                "conflict",
                {"status": "conflict", "requestedOrchestrationId": ORCHESTRATION_ID, "existingOrchestrationId": EXISTING_ID},
                3,
                {"ok": False, "claimed": False, "status": "conflict", "claim_status": None, "reason": "claim_conflict"},
            ),
        )
        for name, response, code, expected in cases:
            with self.subTest(status=name):
                self.reset_fake_tools()
                self.set_capture(response, returncode=code)
                self.assertEqual(expected, self.parse_result(self.run_harvestctl(*self.claim_args()), "claim"))

    def test_malformed_or_inconsistent_native_responses_fail_closed(self):
        conflict_with_claim = {
            "status": "conflict",
            "requestedOrchestrationId": ORCHESTRATION_ID,
            "existingOrchestrationId": EXISTING_ID,
            "orchestration": {"status": "claimed", "id": ORCHESTRATION_ID},
        }
        cases = (
            ("captured missing orchestration", capture_summary("captured", claim_status=None), 0, None),
            ("duplicate bad nested status", capture_summary("duplicate", "claimed-but-not-valid"), 0, None),
            ("conflict with orchestration", conflict_with_claim, 3, None),
            ("unknown status", {"status": "surprise"}, 0, None),
            ("wrong nested id", capture_summary("captured", "claimed", EXISTING_ID), 0, None),
            ("malformed JSON", None, 0, "{not-json\n"),
            ("multiple stdout lines", None, 0, json.dumps(capture_summary()) + "\n{}\n"),
        )
        for name, response, code, raw in cases:
            with self.subTest(case=name):
                self.reset_fake_tools()
                self.set_capture(response=response, raw=raw, returncode=code)
                result = self.parse_result(self.run_harvestctl(*self.claim_args()), "claim")
                self.assertEqual(
                    {"ok": False, "claimed": False, "status": "failed", "claim_status": None, "reason": "invalid_capture_response"},
                    result,
                )

    def test_capture_process_failure_is_normalized(self):
        self.fake["node_capture"] = {"returncode": 1, "stdout": "", "stderr": SECRET}
        self.write_fake_config()
        # Exit 1 without the required summary is a malformed protocol response.
        result = self.parse_result(self.run_harvestctl(*self.claim_args()), "claim")
        self.assertEqual("invalid_capture_response", result["reason"])

    def test_capture_exit_one_failed_summary_maps_to_capture_failed(self):
        self.set_capture(capture_summary("failed", claim_status=None), returncode=1)
        result = self.parse_result(self.run_harvestctl(*self.claim_args()), "claim")
        self.assertEqual(
            {"ok": False, "claimed": False, "status": "failed", "claim_status": None, "reason": "capture_failed"},
            result,
        )

    def test_cli_argument_validation_exits_two_without_json_or_tool_calls(self):
        valid = self.claim_args()
        cases = (
            ("invalid role", ("doctor", "--role", "Explorer")),
            ("claim invalid role", self.claim_args(role="EXPLORER")),
            ("blank pane", self.claim_args(pane=" \t ")),
            ("malformed UUID", self.claim_args(orchestration_id="not-a-uuid")),
            ("noncanonical UUID", self.claim_args(orchestration_id=ORCHESTRATION_ID.upper())),
            ("blank label", self.claim_args(label=" \t ")),
            ("too-long label", self.claim_args(label="é" * 257)),
            ("multiline label", self.claim_args(label="first\nsecond")),
            ("NUL-like line separator label", self.claim_args(label="first\u2028second")),
            ("duplicate option", valid + ("--role", "fixer")),
            ("missing pane", ("claim", "--id", ORCHESTRATION_ID, "--label", "task", "--role", "explorer")),
            ("missing value", ("claim", "--pane")),
            ("unknown option", valid + ("--unexpected", "value")),
            ("doctor missing role", ("doctor",)),
            ("doctor duplicate role", ("doctor", "--role", "explorer", "--role", "fixer")),
        )
        for name, args in cases:
            with self.subTest(case=name):
                self.reset_fake_tools()
                completed = self.run_harvestctl(*args)
                self.assertEqual(2, completed.returncode)
                self.assertEqual("", completed.stdout)
                self.assertIn("usage:", completed.stderr)
                self.assertEqual("", self.herdr_log.read_text(encoding="utf-8") if self.herdr_log.exists() else "")
                self.assertFalse(self.capture_log.exists())

    def test_script_is_executable(self):
        self.assertTrue(os.access(HARVESTCTL, os.X_OK))


if __name__ == "__main__":
    unittest.main()
