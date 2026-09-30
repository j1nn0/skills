import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
JEVCTL = ROOT / "skills" / "agent-orchestration" / "scripts" / "jevctl"


class JevctlTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.xdg = self.root / "xdg"
        self.config_path = self.xdg / "agent-orchestration" / "jev.json"
        self.config_path.parent.mkdir(parents=True)
        self.env = os.environ.copy()
        self.env.pop("JEVCTL_MODEL", None)
        self.env.pop("JEVCTL_TRANSPORT", None)
        self.env.pop("JEVCTL_ENABLED", None)
        self.env.pop("CMD_ZDR", None)
        self.env.pop("JEVCTL_TIMEOUT", None)
        self.env.pop("JEVCTL_MAX_STATE_CHARS", None)
        for key in (
            "JEVCTL_OUTCOME_MIN",
            "JEVCTL_UNRESOLVED_MAX",
            "JEVCTL_SCOPE_MAX",
            "JEVCTL_ACTION_CONF_MIN",
        ):
            self.env.pop(key, None)
        self.env.update(
            {
                "PATH": str(self.bin_dir),
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.xdg),
            }
        )

    def install_cmd(self, response=None, raw_stdout=None, exit_code=0, version_code=0, capture_path=None, invocation_marker=None, env_capture_path=None):
        if raw_stdout is None:
            raw_stdout = json.dumps(response, separators=(",", ":")) if response is not None else ""
        capture = ""
        if capture_path is not None:
            capture = (
                "if len(sys.argv) > 2 and sys.argv[1] == '-p':\n"
                f"    open({str(capture_path)!r}, 'w', encoding='utf-8').write(sys.argv[2])\n"
            )
        invocation = ""
        if invocation_marker is not None:
            invocation += f"open({str(invocation_marker)!r}, 'a').write('called\\n')\n"
        if env_capture_path is not None:
            invocation += (
                f"open({str(env_capture_path)!r}, 'w', encoding='utf-8').write("
                "os.environ.get('CMD_ZDR', '<absent>'))\n"
            )
        script = (
            f"#!{sys.executable}\n"
            "import os, sys\n"
            + invocation
            + "if len(sys.argv) > 1 and sys.argv[1] == '--version':\n"
            "    print('cmd test stub')\n"
            f"    raise SystemExit({version_code})\n"
            + capture
            + f"sys.stdout.write({raw_stdout!r})\n"
            + f"raise SystemExit({exit_code})\n"
        )
        command = self.bin_dir / "cmd"
        command.write_text(script, encoding="utf-8")
        command.chmod(0o755)
        return command

    @staticmethod
    def valid_response(
        outcome=0.97,
        unresolved=0.02,
        scope=0.03,
        action="complete",
        confidence=0.95,
        model="typesafe/jev",
    ):
        return {
            "model": model,
            "answers": {
                "outcome_supported": {"type": "noul", "noul": outcome},
                "unresolved_issue": {"type": "noul", "noul": unresolved},
                "scope_exceeded": {"type": "noul", "noul": scope},
                "next_action": {
                    "type": "choice",
                    "choice": action,
                    "confidence": confidence,
                    "probabilities": {action: confidence},
                },
            },
            "usage": {},
        }

    @staticmethod
    def gate_input(deterministic_pass=True):
        return {
            "task_summary": "Add an optional completion gate.",
            "root_cause_summary": "Not applicable to this feature.",
            "implementation_summary": "Added a bounded decision aid.",
            "changed_files": ["skills/agent-orchestration/scripts/jevctl"],
            "diff_stats": {"files": 1, "insertions": 10, "deletions": 0},
            "verification": {"commands": ["python3 -m unittest"], "exit_status": 0},
            "tests_summary": "All relevant tests passed.",
            "remaining_issues": [],
            "review_findings": [],
            "deterministic_pass": deterministic_pass,
        }

    def run_jevctl(self, subcommand, payload=None, env=None):
        return subprocess.run(
            [sys.executable, str(JEVCTL), subcommand],
            input=json.dumps(payload) if payload is not None else "",
            capture_output=True,
            text=True,
            env=env or self.env,
            check=False,
        )

    def run_gate(self, response=None, **kwargs):
        self.install_cmd(response=response)
        payload = self.gate_input(**kwargs)
        env = dict(self.env, JEVCTL_ENABLED="1")
        return self.run_jevctl("completion-gate", payload, env=env)

    def parse_single_json(self, completed):
        self.assertEqual(0, completed.returncode, completed.stderr)
        value = json.loads(completed.stdout)
        self.assertIsInstance(value, dict)
        return value

    def test_valid_complete_response_auto_applies(self):
        result = self.parse_single_json(self.run_gate(self.valid_response()))

        self.assertEqual("decided", result["status"])
        self.assertEqual("complete", result["action"])
        self.assertTrue(result["auto_apply"])
        self.assertAlmostEqual(0.95, result["completion_confidence"])
        self.assertNotIn("certainty", result)

    def test_outcome_below_threshold_does_not_auto_apply(self):
        result = self.parse_single_json(self.run_gate(self.valid_response(outcome=0.89)))

        self.assertEqual("decided", result["status"])
        self.assertAlmostEqual(0.89, result["completion_confidence"])
        self.assertFalse(result["auto_apply"])

    def test_unresolved_issue_above_threshold_does_not_auto_apply(self):
        result = self.parse_single_json(self.run_gate(self.valid_response(unresolved=0.11)))

        self.assertEqual("decided", result["status"])
        self.assertFalse(result["auto_apply"])

    def test_scope_exceeded_above_threshold_does_not_auto_apply(self):
        result = self.parse_single_json(self.run_gate(self.valid_response(scope=0.16)))

        self.assertEqual("decided", result["status"])
        self.assertFalse(result["auto_apply"])

    def test_non_complete_next_action_does_not_auto_apply(self):
        result = self.parse_single_json(self.run_gate(self.valid_response(action="retry_fix")))

        self.assertEqual("decided", result["status"])
        self.assertEqual("retry_fix", result["action"])
        self.assertFalse(result["auto_apply"])

    def test_high_confidence_reinvestigate_is_decided_without_auto_apply(self):
        result = self.parse_single_json(
            self.run_gate(self.valid_response(action="reinvestigate", confidence=0.95))
        )

        self.assertEqual("decided", result["status"])
        self.assertEqual("reinvestigate", result["action"])
        self.assertFalse(result["auto_apply"])

    def test_low_choice_confidence_is_uncertain(self):
        result = self.parse_single_json(self.run_gate(self.valid_response(confidence=0.79)))

        self.assertEqual("uncertain", result["status"])
        self.assertAlmostEqual(0.79, result["completion_confidence"])
        self.assertFalse(result["auto_apply"])

    def test_malformed_response_falls_back_to_unavailable(self):
        self.install_cmd(raw_stdout="not-json")
        env = dict(self.env, JEVCTL_ENABLED="1")

        completed = self.run_jevctl("completion-gate", self.gate_input(), env=env)
        result = self.parse_single_json(completed)

        self.assertEqual("unavailable", result["status"])
        self.assertEqual("invalid_response", result["reason"])
        self.assertEqual("orchestrator_review", result["action"])
        self.assertFalse(result["auto_apply"])
        self.assertEqual(0.0, result["completion_confidence"])
        self.assertIn("invalid_response", completed.stderr)

    def test_nonzero_cmd_exit_falls_back_to_unavailable(self):
        self.install_cmd(response=self.valid_response(), exit_code=5)
        env = dict(self.env, JEVCTL_ENABLED="1")

        result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input(), env=env)
        )

        self.assertEqual("unavailable", result["status"])
        self.assertEqual("rate_limited", result["reason"])
        self.assertEqual("orchestrator_review", result["action"])
        self.assertFalse(result["auto_apply"])

    def test_exit_code_reasons_cover_documented_failures(self):
        cases = {
            3: "auth_error",
            4: "permission_denied",
            5: "rate_limited",
            6: "connection_error",
            7: "server_error",
            8: "max_turns_exceeded",
            9: "no_response",
            10: "insufficient_credits",
            130: "interrupted",
            1: "transport_error",
        }
        env = dict(self.env, JEVCTL_ENABLED="1")
        for exit_code, reason in cases.items():
            with self.subTest(exit_code=exit_code):
                self.install_cmd(response=self.valid_response(), exit_code=exit_code)
                result = self.parse_single_json(
                    self.run_jevctl("completion-gate", self.gate_input(), env=env)
                )
                self.assertEqual("unavailable", result["status"])
                self.assertEqual(reason, result["reason"])
                self.assertFalse(result["auto_apply"])

    def test_missing_cmd_is_unavailable_and_doctor_reports_failure(self):
        empty_path = self.root / "empty-path"
        empty_path.mkdir()
        env = dict(self.env, PATH=str(empty_path), JEVCTL_ENABLED="1")

        gate = self.run_jevctl("completion-gate", self.gate_input(), env=env)
        gate_result = self.parse_single_json(gate)
        doctor = self.run_jevctl("doctor", env=env)
        doctor_result = self.parse_single_json(doctor)

        self.assertEqual("unavailable", gate_result["status"])
        self.assertEqual("missing_command", gate_result["reason"])
        self.assertFalse(gate_result["auto_apply"])
        self.assertFalse(doctor_result["ok"])
        self.assertTrue(doctor_result["enabled"])
        self.assertEqual("missing_command", doctor_result["reason"])

    def test_doctor_success_and_smoke_probe_failure_are_json(self):
        self.install_cmd()
        env = dict(self.env, JEVCTL_ENABLED="1")
        success = self.parse_single_json(self.run_jevctl("doctor", env=env))
        self.assertTrue(success["ok"])
        self.assertEqual("typesafe/jev", success["model"])
        self.assertEqual("cmd", success["transport"])
        self.assertTrue(success["enabled"])
        self.assertIn("cmd_path", success)

        self.install_cmd(version_code=1)
        failure = self.parse_single_json(self.run_jevctl("doctor", env=env))
        self.assertFalse(failure["ok"])
        self.assertTrue(failure["enabled"])
        self.assertEqual("transport_error", failure["reason"])

    def test_stdout_is_one_json_object_and_stderr_holds_diagnostic(self):
        self.install_cmd(raw_stdout="broken")
        env = dict(self.env, JEVCTL_ENABLED="1")

        completed = self.run_jevctl("completion-gate", self.gate_input(), env=env)
        result = self.parse_single_json(completed)

        self.assertEqual("unavailable", result["status"])
        self.assertTrue(completed.stdout.endswith("\n"))
        self.assertEqual(1, completed.stdout.count("\n"))
        self.assertEqual("jevctl: invalid_response\n", completed.stderr)

    def test_default_disabled_doctor_reports_disabled(self):
        marker = self.root / "invoked"
        self.install_cmd(invocation_marker=marker)

        doctor = self.parse_single_json(self.run_jevctl("doctor"))

        self.assertFalse(doctor["ok"])
        self.assertFalse(doctor["enabled"])
        self.assertEqual("disabled", doctor["reason"])
        self.assertFalse(marker.exists())

    def test_disabled_gate_never_invokes_cmd(self):
        marker = self.root / "invoked"
        self.install_cmd(response=self.valid_response(), invocation_marker=marker)

        result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input())
        )

        self.assertEqual("unavailable", result["status"])
        self.assertEqual("disabled", result["reason"])
        self.assertEqual("orchestrator_review", result["action"])
        self.assertFalse(result["auto_apply"])
        self.assertEqual(0.0, result["completion_confidence"])
        self.assertFalse(marker.exists())

    def test_environment_enabled_opt_in_runs_gate(self):
        marker = self.root / "invoked"
        self.install_cmd(response=self.valid_response(), invocation_marker=marker)
        env = dict(self.env, JEVCTL_ENABLED="1")

        result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input(), env=env)
        )

        self.assertTrue(result["auto_apply"])
        self.assertTrue(marker.exists())

    def test_config_file_enabled_opt_in_runs_gate(self):
        self.config_path.write_text(json.dumps({"enabled": True}), encoding="utf-8")
        self.install_cmd(response=self.valid_response())

        result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input())
        )

        self.assertTrue(result["auto_apply"])

    def test_environment_enabled_overrides_config(self):
        self.config_path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
        marker = self.root / "invoked"
        self.install_cmd(response=self.valid_response(), invocation_marker=marker)
        enabled_env = dict(self.env, JEVCTL_ENABLED=" YES ")

        enabled_result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input(), env=enabled_env)
        )

        self.assertTrue(enabled_result["auto_apply"])
        self.assertTrue(marker.exists())

        marker.unlink()
        self.config_path.write_text(json.dumps({"enabled": True}), encoding="utf-8")
        disabled_env = dict(self.env, JEVCTL_ENABLED=" OFF ")
        disabled_result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input(), env=disabled_env)
        )
        self.assertEqual("disabled", disabled_result["reason"])
        self.assertFalse(marker.exists())

    def test_invalid_enabled_values_fail_conservatively(self):
        marker = self.root / "invoked"
        self.install_cmd(response=self.valid_response(), invocation_marker=marker)
        for value in ("maybe", "2", ""):
            with self.subTest(value=value):
                env = dict(self.env, JEVCTL_ENABLED=value)
                result = self.parse_single_json(
                    self.run_jevctl("completion-gate", self.gate_input(), env=env)
                )
                self.assertEqual("unavailable", result["status"])
                self.assertEqual("invalid_config", result["reason"])
                self.assertFalse(marker.exists())

        self.config_path.write_text(json.dumps({"enabled": "maybe"}), encoding="utf-8")
        config_result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input())
        )
        self.assertEqual("invalid_config", config_result["reason"])
        self.assertFalse(marker.exists())

    def test_cmd_zdr_is_forwarded_to_stub_child(self):
        env_capture = self.root / "cmd-zdr.txt"
        self.install_cmd(response=self.valid_response(), env_capture_path=env_capture)
        env = dict(self.env, JEVCTL_ENABLED="1", CMD_ZDR="1")

        result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input(), env=env)
        )

        self.assertTrue(result["auto_apply"])
        self.assertEqual("1", env_capture.read_text(encoding="utf-8"))

    def test_deterministic_failure_short_circuits_without_cmd(self):
        marker = self.root / "invoked"
        self.install_cmd(response=self.valid_response(), invocation_marker=marker)
        env = dict(self.env, JEVCTL_ENABLED="1")

        result = self.parse_single_json(
            self.run_jevctl(
                "completion-gate",
                self.gate_input(deterministic_pass=False),
                env=env,
            )
        )

        self.assertEqual("unavailable", result["status"])
        self.assertEqual("deterministic_failure", result["reason"])
        self.assertEqual("orchestrator_review", result["action"])
        self.assertFalse(result["auto_apply"])
        self.assertEqual(0.0, result["completion_confidence"])
        self.assertFalse(marker.exists())

    def test_additive_fields_and_resolved_jev_model_are_accepted(self):
        response = self.valid_response(model="jev-1.13.0")
        response["future_metadata"] = {"provider_trace": "ignored"}
        response["answers"]["outcome_supported"]["confidence"] = 0.7
        response["answers"]["next_action"]["future_field"] = "ignored"
        response["answers"]["future_question"] = {"type": "future", "value": None}

        result = self.parse_single_json(self.run_gate(response))

        self.assertEqual("decided", result["status"])
        self.assertTrue(result["auto_apply"])

    def test_no_secret_leaks_from_environment_or_config(self):
        fake_secret = "FAKE_DO_NOT_PRINT_jev_key_123"
        env = dict(self.env, COMMAND_CODE_API_KEY=fake_secret, JEVCTL_ENABLED="1")
        self.config_path.write_text(
            json.dumps({"model": "typesafe/jev", "api_key": fake_secret}),
            encoding="utf-8",
        )

        config_result = self.run_jevctl("doctor", env=env)
        config_payload = self.parse_single_json(config_result)
        self.assertFalse(config_payload["ok"])
        self.assertNotIn(fake_secret, config_result.stdout)
        self.assertNotIn(fake_secret, config_result.stderr)

        self.config_path.unlink()
        self.install_cmd(response=self.valid_response())
        completed = self.run_jevctl("completion-gate", self.gate_input(), env=env)

        result = self.parse_single_json(completed)
        self.assertTrue(result["auto_apply"])
        self.assertNotIn(fake_secret, completed.stdout)
        self.assertNotIn(fake_secret, completed.stderr)


    def test_request_has_object_questions_and_truncated_settled_state(self):
        capture_path = self.root / "request.json"
        self.install_cmd(response=self.valid_response(), capture_path=capture_path)
        env = dict(self.env, JEVCTL_MAX_STATE_CHARS="100", JEVCTL_ENABLED="1")

        completed = self.run_jevctl("completion-gate", self.gate_input(), env=env)
        self.parse_single_json(completed)
        request = json.loads(capture_path.read_text(encoding="utf-8"))

        self.assertEqual({"state", "questions"}, set(request))
        self.assertIsInstance(request["questions"], dict)
        self.assertEqual(
            {"outcome_supported", "unresolved_issue", "scope_exceeded", "next_action"},
            set(request["questions"]),
        )
        self.assertLessEqual(len(request["state"]), 100)
        self.assertIn("[state truncated]", request["state"])

        for question_id in ("outcome_supported", "unresolved_issue", "scope_exceeded"):
            with self.subTest(question_id=question_id):
                question = request["questions"][question_id]
                self.assertEqual({"type", "instructions", "criteria"}, set(question))
                self.assertEqual("noul", question["type"])
                self.assertIsInstance(question["instructions"], str)
                self.assertEqual({"true", "false"}, set(question["criteria"]))
                self.assertTrue(all(isinstance(value, str) for value in question["criteria"].values()))

        choice = request["questions"]["next_action"]
        self.assertEqual({"type", "instructions", "criteria"}, set(choice))
        self.assertEqual("choice", choice["type"])
        self.assertIsInstance(choice["instructions"], str)
        self.assertEqual(
            {"complete", "retry_fix", "reinvestigate", "orchestrator_review"},
            set(choice["criteria"]),
        )
        self.assertTrue(all(isinstance(value, str) for value in choice["criteria"].values()))

        def keys_in(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from keys_in(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys_in(child)

        self.assertFalse({"id", "question", "options"}.intersection(keys_in(request)))

    def test_threshold_environment_override_is_accepted(self):
        self.install_cmd(response=self.valid_response(outcome=0.97))
        env = dict(self.env, JEVCTL_OUTCOME_MIN="0.98", JEVCTL_ENABLED="1")

        result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input(), env=env)
        )

        self.assertEqual("decided", result["status"])
        self.assertFalse(result["auto_apply"])

    def test_timeout_environment_override_is_accepted(self):
        self.install_cmd(response=self.valid_response())
        env = dict(self.env, JEVCTL_TIMEOUT="2", JEVCTL_ENABLED="1")

        result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input(), env=env)
        )

        self.assertTrue(result["auto_apply"])

    def test_unknown_subcommand_emits_usage_without_gate_json(self):
        completed = self.run_jevctl("parallel")

        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("", completed.stdout)
        self.assertIn("usage:", completed.stderr)


if __name__ == "__main__":
    unittest.main()
