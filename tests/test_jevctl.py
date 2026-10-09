import importlib.util
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
        self.env.pop("JEVCTL_MODE", None)
        self.env.pop("JEVCTL_EXPLORER_ENABLED", None)
        self.env.pop("JEVCTL_EXPLORER_MODE", None)
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

    def run_gate(self, response=None, mode=None, **kwargs):
        self.install_cmd(response=response)
        payload = self.gate_input(**kwargs)
        env = dict(self.env, JEVCTL_ENABLED="1")
        if mode is not None:
            env["JEVCTL_MODE"] = mode
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
        self.assertEqual("active", result["mode"])
        self.assertEqual(result["auto_apply"], result["would_auto_apply"])
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
        self.assertEqual(result["auto_apply"], result["would_auto_apply"])

    def test_high_confidence_reinvestigate_is_decided_without_auto_apply(self):
        result = self.parse_single_json(
            self.run_gate(self.valid_response(action="reinvestigate", confidence=0.95))
        )

        self.assertEqual("decided", result["status"])
        self.assertEqual("reinvestigate", result["action"])
        self.assertFalse(result["would_auto_apply"])
        self.assertFalse(result["auto_apply"])

    def test_low_choice_confidence_is_uncertain(self):
        result = self.parse_single_json(self.run_gate(self.valid_response(confidence=0.79)))

        self.assertEqual("uncertain", result["status"])
        self.assertAlmostEqual(0.79, result["completion_confidence"])
        self.assertIn("would_auto_apply", result)
        self.assertFalse(result["would_auto_apply"])
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
        self.assertEqual("active", doctor_result["mode"])
        self.assertEqual("missing_command", doctor_result["reason"])

    def test_doctor_success_and_smoke_probe_failure_are_json(self):
        self.install_cmd()
        env = dict(self.env, JEVCTL_ENABLED="1")
        success = self.parse_single_json(self.run_jevctl("doctor", env=env))
        self.assertTrue(success["ok"])
        self.assertEqual("typesafe/jev", success["model"])
        self.assertEqual("cmd", success["transport"])
        self.assertTrue(success["enabled"])
        self.assertEqual("active", success["mode"])
        self.assertIn("cmd_path", success)

        self.install_cmd(version_code=1)
        failure = self.parse_single_json(self.run_jevctl("doctor", env=env))
        self.assertFalse(failure["ok"])
        self.assertTrue(failure["enabled"])
        self.assertEqual("active", failure["mode"])
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
        self.assertEqual("active", doctor["mode"])
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
        env = dict(self.env, JEVCTL_ENABLED="1", JEVCTL_MODE="shadow")

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
        self.assertFalse(result["would_auto_apply"])
        self.assertEqual("shadow", result["mode"])
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
        self.assertEqual("active", config_payload["mode"])
        self.assertNotIn(fake_secret, config_result.stdout)
        self.assertNotIn(fake_secret, config_result.stderr)

        self.config_path.unlink()
        self.install_cmd(response=self.valid_response())
        completed = self.run_jevctl("completion-gate", self.gate_input(), env=env)

        result = self.parse_single_json(completed)
        self.assertTrue(result["auto_apply"])
        self.assertEqual(result["auto_apply"], result["would_auto_apply"])
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

    def test_shadow_config_reports_would_apply_without_applying(self):
        self.install_cmd(response=self.valid_response())
        self.config_path.write_text(
            json.dumps({"enabled": True, "mode": "shadow"}), encoding="utf-8"
        )
        result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input())
        )

        self.assertEqual("shadow", result["mode"])
        self.assertTrue(result["would_auto_apply"])
        self.assertFalse(result["auto_apply"])

    def test_active_mode_config_preserves_active_behavior(self):
        self.install_cmd(response=self.valid_response())
        self.config_path.write_text(
            json.dumps({"enabled": True, "mode": "active"}), encoding="utf-8"
        )
        result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input())
        )

        self.assertEqual("active", result["mode"])
        self.assertTrue(result["would_auto_apply"])
        self.assertEqual(result["would_auto_apply"], result["auto_apply"])

    def test_mode_environment_overrides_config_in_both_directions(self):
        self.config_path.write_text(
            json.dumps({"enabled": True, "mode": "shadow"}), encoding="utf-8"
        )
        active = self.parse_single_json(
            self.run_gate(self.valid_response(), mode=" ACTIVE ")
        )
        self.assertEqual("active", active["mode"])
        self.assertTrue(active["auto_apply"])

        self.config_path.write_text(
            json.dumps({"enabled": True, "mode": "active"}), encoding="utf-8"
        )
        shadow = self.parse_single_json(
            self.run_gate(self.valid_response(), mode="ShAdOw")
        )
        self.assertEqual("shadow", shadow["mode"])
        self.assertTrue(shadow["would_auto_apply"])
        self.assertFalse(shadow["auto_apply"])

    def test_invalid_modes_fail_conservatively_without_spawning_cmd(self):
        marker = self.root / "invoked"
        self.install_cmd(response=self.valid_response(), invocation_marker=marker)
        for value in ("observe", "test", "on", "true", "production", "", "2"):
            with self.subTest(value=value):
                env = dict(self.env, JEVCTL_ENABLED="1", JEVCTL_MODE=value)
                result = self.parse_single_json(
                    self.run_jevctl("completion-gate", self.gate_input(), env=env)
                )
                self.assertEqual("unavailable", result["status"])
                self.assertEqual("invalid_config", result["reason"])
                self.assertEqual("active", result["mode"])
                self.assertFalse(result["would_auto_apply"])
                self.assertFalse(result["auto_apply"])
                self.assertFalse(marker.exists())

        self.config_path.write_text(
            json.dumps({"enabled": True, "mode": "observe"}), encoding="utf-8"
        )
        invalid_config = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input())
        )
        self.assertEqual("invalid_config", invalid_config["reason"])
        self.assertEqual("active", invalid_config["mode"])
        self.assertFalse(marker.exists())

    def test_disabled_shadow_config_short_circuits_and_reports_mode(self):
        self.config_path.write_text(
            json.dumps({"enabled": False, "mode": "shadow"}), encoding="utf-8"
        )
        marker = self.root / "invoked"
        self.install_cmd(response=self.valid_response(), invocation_marker=marker)

        doctor = self.parse_single_json(self.run_jevctl("doctor"))
        result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input())
        )

        self.assertFalse(doctor["ok"])
        self.assertFalse(doctor["enabled"])
        self.assertEqual("shadow", doctor["mode"])
        self.assertEqual("disabled", doctor["reason"])
        self.assertEqual("shadow", result["mode"])
        self.assertEqual("disabled", result["reason"])
        self.assertFalse(result["would_auto_apply"])
        self.assertFalse(result["auto_apply"])
        self.assertFalse(marker.exists())

    def test_shadow_retry_fix_never_applies_but_reports_would_apply_false(self):
        result = self.parse_single_json(
            self.run_gate(self.valid_response(action="retry_fix"), mode="shadow")
        )

        self.assertEqual("decided", result["status"])
        self.assertEqual("retry_fix", result["action"])
        self.assertFalse(result["would_auto_apply"])
        self.assertFalse(result["auto_apply"])

    def test_shadow_unavailable_reports_both_apply_fields_false(self):
        self.install_cmd(raw_stdout="not-json")
        env = dict(self.env, JEVCTL_ENABLED="1", JEVCTL_MODE="shadow")

        result = self.parse_single_json(
            self.run_jevctl("completion-gate", self.gate_input(), env=env)
        )

        self.assertEqual("shadow", result["mode"])
        self.assertEqual("unavailable", result["status"])
        self.assertFalse(result["would_auto_apply"])
        self.assertFalse(result["auto_apply"])

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

    def test_unexpected_gate_error_surfaces_instead_of_transport_error(self):
        import importlib.machinery

        loader = importlib.machinery.SourceFileLoader("jevctl_under_test", str(JEVCTL))
        spec = importlib.util.spec_from_loader("jevctl_under_test", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)

        def boom():
            raise RuntimeError("boom")

        original = module.completion_result
        module.completion_result = boom
        try:
            with self.assertRaises(RuntimeError):
                module.main(["jevctl", "completion-gate"])
        finally:
            module.completion_result = original

    def test_unexpected_doctor_error_surfaces_instead_of_transport_error(self):
        import importlib.machinery

        loader = importlib.machinery.SourceFileLoader("jevctl_under_test", str(JEVCTL))
        spec = importlib.util.spec_from_loader("jevctl_under_test", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)

        def boom():
            raise RuntimeError("boom")

        original = module.doctor_result
        module.doctor_result = boom
        try:
            with self.assertRaises(RuntimeError):
                module.main(["jevctl", "doctor"])
        finally:
            module.doctor_result = original

    def test_keyboard_interrupt_stays_normalized_for_both_paths(self):
        import contextlib
        import importlib.machinery
        import io

        loader = importlib.machinery.SourceFileLoader("jevctl_under_test", str(JEVCTL))
        spec = importlib.util.spec_from_loader("jevctl_under_test", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)

        def raise_keyboard_interrupt():
            raise KeyboardInterrupt

        original_gate = module.completion_result
        module.completion_result = raise_keyboard_interrupt
        try:
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(0, module.main(["jevctl", "completion-gate"]))
            self.assertIn("interrupted", stderr.getvalue())
            self.assertEqual("interrupted", json.loads(stdout.getvalue())["reason"])
        finally:
            module.completion_result = original_gate

        original_doctor = module.doctor_result
        module.doctor_result = raise_keyboard_interrupt
        try:
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(0, module.main(["jevctl", "doctor"]))
            self.assertIn("interrupted", stderr.getvalue())
            self.assertEqual("interrupted", json.loads(stdout.getvalue())["reason"])
        finally:
            module.doctor_result = original_doctor


class ExplorerGateTest(unittest.TestCase):
    install_cmd = JevctlTest.install_cmd
    run_jevctl = JevctlTest.run_jevctl
    parse_single_json = JevctlTest.parse_single_json

    def setUp(self):
        JevctlTest.setUp(self)

    @staticmethod
    def explorer_input(**overrides):
        data = {
            "task_summary": "Investigate the intermittent order failure.",
            "investigation_goal": "Determine whether the retry path drops updates.",
            "explorer_claim": "The retry path omits the version predicate.",
            "evidence_supporting_claim": [
                {"source": "src/orders/retry.py:42", "observation": "The update omits expected_version."}
            ],
            "contradictory_evidence": [],
            "remaining_unknowns": [],
            "orchestrator_reviewed": True,
        }
        data.update(overrides)
        return data

    @staticmethod
    def explorer_response(
        grounded=0.95,
        supported=0.93,
        gap=0.05,
        action="proceed_to_fix",
        confidence=0.95,
        model="typesafe/jev",
    ):
        return {
            "model": model,
            "answers": {
                "evidence_grounded": {"type": "noul", "noul": grounded},
                "claim_supported": {"type": "noul", "noul": supported},
                "material_gap": {"type": "noul", "noul": gap},
                "next_step": {
                    "type": "choice",
                    "choice": action,
                    "confidence": confidence,
                    "probabilities": {action: confidence},
                },
            },
            "usage": {},
        }

    def run_explorer(
        self,
        response=None,
        payload=None,
        env_overrides=None,
        raw_stdout=None,
        exit_code=0,
        invocation_marker=None,
        capture_path=None,
    ):
        self.install_cmd(
            response=response,
            raw_stdout=raw_stdout,
            exit_code=exit_code,
            invocation_marker=invocation_marker,
            capture_path=capture_path,
        )
        env = dict(self.env, JEVCTL_ENABLED="1", JEVCTL_EXPLORER_ENABLED="1")
        if env_overrides:
            env.update(env_overrides)
        if payload is None:
            payload = self.explorer_input()
        return self.run_jevctl("explorer-gate", payload, env=env)

    def test_old_config_without_gates_preserves_completion_behavior(self):
        self.config_path.write_text(
            json.dumps({"enabled": True, "mode": "shadow"}), encoding="utf-8"
        )
        self.install_cmd(response=JevctlTest.valid_response())
        result = self.parse_single_json(
            self.run_jevctl("completion-gate", JevctlTest.gate_input(), env=self.env)
        )
        self.assertEqual("shadow", result["mode"])
        self.assertTrue(result["would_auto_apply"])
        self.assertFalse(result["auto_apply"])

    def test_explorer_defaults_disabled_and_shadow_mode(self):
        marker = self.root / "invoked"
        self.install_cmd(response=self.explorer_response(), invocation_marker=marker)
        result = self.parse_single_json(
            self.run_jevctl("explorer-gate", self.explorer_input(), env=self.env)
        )
        self.assertEqual("unavailable", result["status"])
        self.assertEqual("disabled", result["reason"])
        self.assertEqual("shadow", result["mode"])
        self.assertFalse(marker.exists())

    def test_global_disabled_forces_explorer_off(self):
        self.config_path.write_text(
            json.dumps({
                "enabled": False,
                "gates": {"explorer": {"enabled": True, "mode": "active"}},
            }),
            encoding="utf-8",
        )
        marker = self.root / "invoked"
        self.install_cmd(response=self.explorer_response(), invocation_marker=marker)
        result = self.parse_single_json(
            self.run_jevctl("explorer-gate", self.explorer_input(), env=self.env)
        )
        self.assertEqual("disabled", result["reason"])
        self.assertEqual("active", result["mode"])
        self.assertFalse(marker.exists())

    def test_gate_specific_disable_short_circuits_without_transport(self):
        self.config_path.write_text(
            json.dumps({
                "enabled": True,
                "gates": {"explorer": {"enabled": False, "mode": "active"}},
            }),
            encoding="utf-8",
        )
        marker = self.root / "invoked"
        self.install_cmd(response=self.explorer_response(), invocation_marker=marker)
        result = self.parse_single_json(
            self.run_jevctl("explorer-gate", self.explorer_input(), env=self.env)
        )
        self.assertEqual("disabled", result["reason"])
        self.assertEqual("active", result["mode"])
        self.assertFalse(marker.exists())

    def test_gate_environment_overrides_config_in_both_directions(self):
        self.config_path.write_text(
            json.dumps({
                "enabled": True,
                "gates": {"explorer": {"enabled": False, "mode": "active"}},
            }),
            encoding="utf-8",
        )
        enabled = self.parse_single_json(
            self.run_explorer(
                response=self.explorer_response(),
                env_overrides={
                    "JEVCTL_EXPLORER_ENABLED": " YES ",
                    "JEVCTL_EXPLORER_MODE": "shadow",
                },
            )
        )
        self.assertEqual("decided", enabled["status"])
        self.assertEqual("shadow", enabled["mode"])

        self.config_path.write_text(
            json.dumps({
                "enabled": True,
                "gates": {"explorer": {"enabled": True, "mode": "shadow"}},
            }),
            encoding="utf-8",
        )
        marker = self.root / "env-disabled"
        disabled = self.parse_single_json(
            self.run_explorer(
                response=self.explorer_response(),
                env_overrides={
                    "JEVCTL_EXPLORER_ENABLED": "OFF",
                    "JEVCTL_EXPLORER_MODE": "active",
                },
                invocation_marker=marker,
            )
        )
        self.assertEqual("disabled", disabled["reason"])
        self.assertEqual("active", disabled["mode"])
        self.assertFalse(marker.exists())

    def test_invalid_explorer_mode_is_conservative_without_spawning_cmd(self):
        marker = self.root / "invoked"
        result = self.parse_single_json(
            self.run_explorer(
                response=self.explorer_response(),
                env_overrides={"JEVCTL_EXPLORER_MODE": "observe"},
                invocation_marker=marker,
            )
        )
        self.assertEqual("unavailable", result["status"])
        self.assertEqual("invalid_config", result["reason"])
        self.assertEqual("shadow", result["mode"])
        self.assertFalse(marker.exists())

    def test_explorer_thresholds_parse_and_control_confidence_status(self):
        self.config_path.write_text(
            json.dumps({
                "enabled": True,
                "gates": {
                    "explorer": {
                        "enabled": True,
                        "thresholds": {
                            "grounded_min": 0.9,
                            "supported_min": 0.9,
                            "material_gap_max": 0.1,
                            "action_conf_min": 0.9,
                        },
                    }
                },
            }),
            encoding="utf-8",
        )
        # Use the local cmd stub while keeping the config-derived thresholds active.
        self.install_cmd(response=self.explorer_response(action="explore_more", confidence=0.85))
        result = self.parse_single_json(
            self.run_jevctl("explorer-gate", self.explorer_input(), env=self.env)
        )
        self.assertEqual("uncertain", result["status"])
        self.assertFalse(result["would_block"])
        self.assertEqual("shadow", result["mode"])

    def test_invalid_explorer_threshold_configuration_is_rejected(self):
        for thresholds in ({"unknown": 0.5}, {"grounded_min": 1.1}):
            with self.subTest(thresholds=thresholds):
                self.config_path.write_text(
                    json.dumps({
                        "enabled": True,
                        "gates": {"explorer": {"enabled": True, "thresholds": thresholds}},
                    }),
                    encoding="utf-8",
                )
                marker = self.root / "invalid-threshold"
                result = self.parse_single_json(
                    self.run_explorer(
                        response=self.explorer_response(), invocation_marker=marker
                    )
                )
                self.assertEqual("invalid_config", result["reason"])
                self.assertFalse(marker.exists())

    def test_completion_gate_thresholds_keep_specific_override_and_legacy_config(self):
        self.config_path.write_text(
            json.dumps({
                "enabled": True,
                "mode": "active",
                "thresholds": {"outcome_min": 0.99},
                "gates": {"completion": {"thresholds": {"outcome_min": 0.9}}},
            }),
            encoding="utf-8",
        )
        self.install_cmd(response=JevctlTest.valid_response(outcome=0.97))
        result = self.parse_single_json(
            self.run_jevctl("completion-gate", JevctlTest.gate_input(), env=self.env)
        )
        self.assertTrue(result["auto_apply"])
        self.assertTrue(result["would_auto_apply"])

    def test_disabled_result_is_normalized_and_does_not_spawn_transport(self):
        marker = self.root / "invoked"
        self.install_cmd(response=self.explorer_response(), invocation_marker=marker)
        result = self.parse_single_json(
            self.run_jevctl("explorer-gate", env=self.env)
        )
        self.assertEqual(
            {
                "schema_version", "gate", "status", "action", "auto_apply",
                "would_block", "mode", "answers", "next_step",
                "next_step_confidence", "evidence_sufficient", "reason",
            },
            set(result),
        )
        self.assertEqual("explorer", result["gate"])
        self.assertEqual({"evidence_grounded", "claim_supported", "material_gap"}, set(result["answers"]))
        self.assertFalse(result["auto_apply"])
        self.assertFalse(result["would_block"])
        self.assertFalse(result["evidence_sufficient"])
        self.assertNotIn("completion_confidence", result)
        self.assertNotIn("would_auto_apply", result)
        self.assertFalse(marker.exists())

    def test_orchestrator_reviewed_false_or_missing_short_circuits(self):
        for reviewed in (False, None):
            with self.subTest(reviewed=reviewed):
                marker = self.root / f"review-{reviewed}"
                payload = self.explorer_input()
                if reviewed is None:
                    payload.pop("orchestrator_reviewed")
                else:
                    payload["orchestrator_reviewed"] = reviewed
                result = self.parse_single_json(
                    self.run_explorer(
                        response=self.explorer_response(),
                        payload=payload,
                        invocation_marker=marker,
                    )
                )
                self.assertEqual("review_incomplete", result["reason"])
                self.assertEqual("orchestrator_review", result["action"])
                self.assertFalse(result["evidence_sufficient"])
                self.assertFalse(marker.exists())

    def test_doctor_reports_gate_settings_without_model_request(self):
        self.config_path.write_text(
            json.dumps({
                "enabled": True,
                "gates": {"explorer": {"enabled": True, "mode": "active"}},
            }),
            encoding="utf-8",
        )
        captured_prompt = self.root / "model-prompt.json"
        self.install_cmd(response=self.explorer_response(), capture_path=captured_prompt)
        doctor = self.parse_single_json(self.run_jevctl("doctor", env=self.env))
        self.assertTrue(doctor["ok"])
        self.assertEqual(
            {
                "completion": {"enabled": True, "mode": "active"},
                "explorer": {"enabled": True, "mode": "active"},
            },
            doctor["gates"],
        )
        self.assertFalse(captured_prompt.exists())

    def test_disabled_doctor_reports_boolean_gate_enablement_for_routing(self):
        (self.bin_dir / "python3").symlink_to(sys.executable)
        env = dict(self.env, JEVCTL_ENABLED="0")
        completed = subprocess.run(
            [str(JEVCTL), "doctor"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        doctor = self.parse_single_json(completed)

        for gate in ("completion", "explorer"):
            with self.subTest(gate=gate):
                enabled = doctor["gates"][gate]["enabled"]
                self.assertIs(type(enabled), bool)
                self.assertFalse(enabled)

    def test_request_uses_restricted_settled_state_and_system_one_questions(self):
        capture_path = self.root / "request.json"
        payload = self.explorer_input(untrusted_metadata="must not be forwarded")
        self.install_cmd(response=self.explorer_response(), capture_path=capture_path)
        completed = self.run_jevctl(
            "explorer-gate",
            payload,
            env=dict(self.env, JEVCTL_ENABLED="1", JEVCTL_EXPLORER_ENABLED="1"),
        )
        self.parse_single_json(completed)
        request = json.loads(capture_path.read_text(encoding="utf-8"))
        self.assertEqual({"state", "questions"}, set(request))
        self.assertNotIn("untrusted_metadata", request["state"])
        self.assertEqual(
            {"evidence_grounded", "claim_supported", "material_gap", "next_step"},
            set(request["questions"]),
        )
        self.assertEqual("noul", request["questions"]["evidence_grounded"]["type"])
        self.assertEqual("choice", request["questions"]["next_step"]["type"])
        self.assertIn("root cause confirmed", request["questions"]["evidence_grounded"]["instructions"])

    def test_shadow_action_matrix_only_confident_explore_more_would_block(self):
        cases = (
            ("proceed", "proceed_to_fix", 0.95, "decided", False, True),
            ("explore", "explore_more", 0.95, "decided", True, False),
            ("uncertain", "explore_more", 0.74, "uncertain", False, False),
            ("review", "orchestrator_review", 0.95, "decided", False, False),
        )
        for name, action, confidence, status, would_block, sufficient in cases:
            with self.subTest(case=name):
                result = self.parse_single_json(
                    self.run_explorer(
                        response=self.explorer_response(action=action, confidence=confidence),
                        env_overrides={"JEVCTL_EXPLORER_MODE": "shadow"},
                    )
                )
                self.assertEqual(status, result["status"])
                self.assertEqual(action, result["action"])
                self.assertEqual(action, result["next_step"])
                self.assertEqual(would_block, result["would_block"])
                self.assertEqual(sufficient, result["evidence_sufficient"])
                self.assertFalse(result["auto_apply"])
                self.assertEqual("shadow", result["mode"])


    def test_proceed_recommendation_exposes_threshold_qualified_sufficiency(self):
        positive = self.parse_single_json(
            self.run_explorer(
                response=self.explorer_response(
                    grounded=0.90,
                    supported=0.90,
                    gap=0.10,
                    action="proceed_to_fix",
                    confidence=0.90,
                ),
                env_overrides={"JEVCTL_EXPLORER_MODE": "shadow"},
            )
        )
        case1 = self.parse_single_json(
            self.run_explorer(
                response=self.explorer_response(
                    grounded=0.95,
                    supported=0.91,
                    gap=0.24,
                    action="proceed_to_fix",
                    confidence=0.91,
                ),
                env_overrides={"JEVCTL_EXPLORER_MODE": "shadow"},
            )
        )

        self.assertEqual("decided", positive["status"])
        self.assertTrue(positive["evidence_sufficient"])
        self.assertEqual("decided", case1["status"])
        self.assertEqual("proceed_to_fix", case1["action"])
        self.assertFalse(case1["evidence_sufficient"])
        for field in ("status", "action", "next_step", "would_block", "auto_apply", "mode"):
            self.assertEqual(positive[field], case1[field], field)
        self.assertNotEqual(positive["answers"], case1["answers"])
        self.assertAlmostEqual(0.10, positive["answers"]["material_gap"])
        self.assertAlmostEqual(0.24, case1["answers"]["material_gap"])
        self.assertFalse(positive["would_block"])
        self.assertFalse(case1["would_block"])
        self.assertFalse(positive["auto_apply"])
        self.assertFalse(case1["auto_apply"])

    def test_low_confidence_proceed_is_uncertain_and_not_sufficient(self):
        result = self.parse_single_json(
            self.run_explorer(
                response=self.explorer_response(
                    grounded=0.86,
                    supported=0.81,
                    gap=0.51,
                    action="proceed_to_fix",
                    confidence=0.29,
                )
            )
        )
        self.assertEqual("uncertain", result["status"])
        self.assertEqual("proceed_to_fix", result["action"])
        self.assertFalse(result["evidence_sufficient"])
        self.assertFalse(result["would_block"])
        self.assertFalse(result["auto_apply"])

    def test_active_proceed_never_applies_and_confident_explore_more_blocks(self):
        proceed = self.parse_single_json(
            self.run_explorer(
                response=self.explorer_response(action="proceed_to_fix"),
                env_overrides={"JEVCTL_EXPLORER_MODE": "active"},
            )
        )
        self.assertEqual("active", proceed["mode"])
        self.assertFalse(proceed["auto_apply"])
        self.assertFalse(proceed["would_block"])
        self.assertTrue(proceed["evidence_sufficient"])

        explore = self.parse_single_json(
            self.run_explorer(
                response=self.explorer_response(action="explore_more"),
                env_overrides={"JEVCTL_EXPLORER_MODE": "active"},
            )
        )
        self.assertTrue(explore["would_block"])
        self.assertFalse(explore["auto_apply"])
        self.assertFalse(explore["evidence_sufficient"])

    def test_malformed_response_falls_back_conservatively(self):
        completed = self.run_explorer(raw_stdout="not-json")
        result = self.parse_single_json(completed)
        self.assertEqual("unavailable", result["status"])
        self.assertEqual("invalid_response", result["reason"])
        self.assertEqual("orchestrator_review", result["action"])
        self.assertEqual("orchestrator_review", result["next_step"])
        self.assertFalse(result["auto_apply"])
        self.assertFalse(result["would_block"])
        self.assertFalse(result["evidence_sufficient"])
        self.assertEqual(1, completed.stdout.count("\n"))

    def test_bad_probability_ranges_wrong_action_missing_answer_and_types_are_rejected(self):
        def wrong_action(response):
            response["answers"]["next_step"]["choice"] = "complete"

        def missing_answer(response):
            del response["answers"]["material_gap"]

        def wrong_answer_type(response):
            response["answers"]["evidence_grounded"]["noul"] = "0.9"

        def wrong_choice_type(response):
            response["answers"]["next_step"] = []

        def wrong_usage_type(response):
            response["usage"] = []

        cases = (
            ("negative", lambda response: response["answers"]["evidence_grounded"].update(noul=-0.01)),
            ("above_one", lambda response: response["answers"]["claim_supported"].update(noul=1.01)),
            ("boolean", lambda response: response["answers"]["material_gap"].update(noul=True)),
            ("wrong_action", wrong_action),
            ("missing_answer", missing_answer),
            ("wrong_answer_type", wrong_answer_type),
            ("wrong_choice_type", wrong_choice_type),
            ("wrong_usage_type", wrong_usage_type),
        )
        for name, mutate in cases:
            with self.subTest(case=name):
                response = self.explorer_response()
                mutate(response)
                result = self.parse_single_json(self.run_explorer(response=response))
                self.assertEqual("unavailable", result["status"])
                self.assertEqual("invalid_response", result["reason"])

    def test_invalid_input_types_and_forbidden_fields_are_invalid_request(self):
        cases = (
            {"explorer_claim": "  "},
            {"evidence_supporting_claim": "not-a-list"},
            {"orchestrator_reviewed": "true"},
            {"raw_transcript": "private history"},
            {"explorer_confidence": {"level": [], "reason": "bad type"}},
        )
        for update in cases:
            with self.subTest(update=update):
                marker = self.root / "invalid-input"
                result = self.parse_single_json(
                    self.run_explorer(
                        response=self.explorer_response(),
                        payload=self.explorer_input(**update),
                        invocation_marker=marker,
                    )
                )
                self.assertEqual("invalid_request", result["reason"])
                self.assertFalse(marker.exists())

    def test_missing_cmd_and_exit_code_mapping_return_unavailable(self):
        empty_path = self.root / "empty-path"
        empty_path.mkdir()
        env = dict(
            self.env,
            PATH=str(empty_path),
            JEVCTL_ENABLED="1",
            JEVCTL_EXPLORER_ENABLED="1",
        )
        missing = self.parse_single_json(
            self.run_jevctl("explorer-gate", self.explorer_input(), env=env)
        )
        self.assertEqual("missing_command", missing["reason"])
        self.assertEqual("orchestrator_review", missing["next_step"])
        self.assertFalse(missing["evidence_sufficient"])

        rate_limited = self.parse_single_json(
            self.run_explorer(response=self.explorer_response(), exit_code=5)
        )
        self.assertEqual("rate_limited", rate_limited["reason"])
        self.assertEqual("orchestrator_review", rate_limited["action"])
        self.assertFalse(rate_limited["evidence_sufficient"])

    def test_unexpected_gate_exception_propagates_and_interrupt_is_normalized(self):
        import contextlib
        import importlib.machinery
        import io

        loader = importlib.machinery.SourceFileLoader("jevctl_explorer_test", str(JEVCTL))
        spec = importlib.util.spec_from_loader("jevctl_explorer_test", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        module.load_settings = lambda: {"gates": {"explorer": {"mode": "active"}}}

        def boom():
            raise RuntimeError("boom")

        module.explorer_result = boom
        with self.assertRaises(RuntimeError):
            module.main(["jevctl", "explorer-gate"])

        def interrupt():
            raise KeyboardInterrupt

        module.explorer_result = interrupt
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(0, module.main(["jevctl", "explorer-gate"]))
        result = json.loads(stdout.getvalue())
        self.assertEqual("interrupted", result["reason"])
        self.assertEqual("active", result["mode"])
        self.assertIn("jevctl: interrupted", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
