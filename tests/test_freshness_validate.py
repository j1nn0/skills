import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
VALIDATOR = ROOT / "skills" / "agent-orchestration" / "scripts" / "freshness_validate"
VERDICT_KEYS = {"fresh", "reason", "progress"}
MISSING = object()


class FreshnessValidateTest(unittest.TestCase):
    def setUp(self):
        self.env = {
            "PATH": os.path.dirname(sys.executable),
            "LANG": "C",
            "LC_ALL": "C",
        }

    @staticmethod
    def snapshot(agent_status="idle", state_change_seq=0, completion_seq=MISSING, **extra):
        value = {
            "agent_status": agent_status,
            "state_change_seq": state_change_seq,
        }
        if completion_seq is not MISSING:
            value["completion_seq"] = completion_seq
        value.update(extra)
        return value

    @classmethod
    def payload(cls, baseline=None, current=None):
        if baseline is None:
            baseline = cls.snapshot()
        if current is None:
            current = cls.snapshot()
        return {"baseline": baseline, "current": current}

    def run_validator(self, payload=None, args=(), raw_input=None):
        if raw_input is None:
            raw_input = json.dumps(payload, ensure_ascii=False)
        return subprocess.run(
            [sys.executable, str(VALIDATOR), *args],
            input=raw_input,
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )

    def assert_verdict(self, completed, fresh, reason, progress):
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stderr)
        self.assertTrue(completed.stdout.endswith("\n"))
        self.assertEqual(1, completed.stdout.count("\n"))
        value = json.loads(completed.stdout)
        self.assertIsInstance(value, dict)
        self.assertEqual(VERDICT_KEYS, set(value))
        self.assertIs(fresh, value["fresh"])
        self.assertEqual(reason, value["reason"])
        self.assertIs(progress, value["progress"])
        return value

    def test_completed_turn_advances_are_fresh(self):
        cases = (
            (
                "idle_completion",
                self.snapshot("idle", 10, 10),
                self.snapshot("idle", 11, 11),
            ),
            (
                "done_completion",
                self.snapshot("done", 10, 10),
                self.snapshot("done", 11, 11),
            ),
            (
                "fast_completion_without_observed_working",
                self.snapshot("idle", 38, 38),
                self.snapshot("done", 40, 40),
            ),
            (
                "large_sequence_jump",
                self.snapshot("idle", 1, 1),
                self.snapshot("idle", 10**100, 10**100),
            ),
            (
                "zero_baseline",
                self.snapshot("idle", 0, 0),
                self.snapshot("done", 1, 1),
            ),
            (
                "fresh_baseline_without_completion",
                self.snapshot("idle", 0),
                self.snapshot("idle", 2, 2),
            ),
            (
                "null_baseline_completion",
                self.snapshot("idle", 0, None),
                self.snapshot("done", 1, 1),
            ),
            (
                "missing_baseline_completion",
                self.snapshot("idle", 0),
                self.snapshot("done", 1, 1),
            ),
        )
        for name, baseline, current in cases:
            with self.subTest(case=name):
                self.assert_verdict(
                    self.run_validator(self.payload(baseline, current)),
                    True,
                    "completion_advanced",
                    True,
                )

    def test_unchanged_and_stale_snapshots_are_not_fresh(self):
        cases = (
            (
                "unchanged_snapshot",
                self.snapshot("idle", 12, 12),
                self.snapshot("idle", 12, 12),
                False,
            ),
            (
                "old_completion_still_present_after_progress",
                self.snapshot("idle", 12, 12),
                self.snapshot("idle", 13, 12),
                True,
            ),
            (
                "no_completion_after_progress",
                self.snapshot("idle", 12, 12),
                self.snapshot("idle", 13),
                True,
            ),
        )
        for name, baseline, current, progress in cases:
            with self.subTest(case=name):
                self.assert_verdict(
                    self.run_validator(self.payload(baseline, current)),
                    False,
                    "no_progress",
                    progress,
                )

    def test_working_status_reports_only_observed_sequence_progress(self):
        cases = (
            (
                "working_with_progress",
                self.snapshot("idle", 12, 12),
                self.snapshot("working", 13),
                "progress_observed",
                True,
            ),
            (
                "working_without_progress",
                self.snapshot("done", 12, 12),
                self.snapshot("working", 12),
                "no_progress",
                False,
            ),
        )
        for name, baseline, current, reason, progress in cases:
            with self.subTest(case=name):
                self.assert_verdict(
                    self.run_validator(self.payload(baseline, current)),
                    False,
                    reason,
                    progress,
                )

    def test_blocked_and_unknown_current_statuses_have_stable_reasons(self):
        cases = (
            (
                "blocked_after_prompt",
                self.snapshot("idle", 4, 4),
                self.snapshot("blocked", 5),
                "blocked",
                True,
            ),
            (
                "unknown_current",
                self.snapshot("idle", 4, 4),
                self.snapshot("unknown", 5),
                "unknown_status",
                True,
            ),
        )
        for name, baseline, current, reason, progress in cases:
            with self.subTest(case=name):
                self.assert_verdict(
                    self.run_validator(self.payload(baseline, current)),
                    False,
                    reason,
                    progress,
                )

    def test_baseline_must_be_ready_before_prompting(self):
        for status in ("working", "blocked", "unknown"):
            with self.subTest(status=status):
                baseline = self.snapshot(status, 5)
                current = self.snapshot("idle", 5)
                self.assert_verdict(
                    self.run_validator(self.payload(baseline, current)),
                    False,
                    "baseline_not_ready",
                    False,
                )

    def test_regressed_state_sequence_requires_rebaselining(self):
        self.assert_verdict(
            self.run_validator(
                self.payload(
                    self.snapshot("idle", 8, 8),
                    self.snapshot("working", 7),
                )
            ),
            False,
            "sequence_regressed",
            False,
        )

    def test_invalid_json_and_top_level_inputs(self):
        cases = (
            ("malformed_json", None, "{"),
            ("nonstandard_constant", None, "NaN"),
            ("non_object_list", None, "[]"),
            ("non_object_null", None, "null"),
            ("missing_baseline", {"current": self.snapshot()}, None),
            ("missing_current", {"baseline": self.snapshot()}, None),
            ("non_object_baseline", {"baseline": [], "current": self.snapshot()}, None),
            ("non_object_current", {"baseline": self.snapshot(), "current": None}, None),
        )
        for name, payload, raw_input in cases:
            with self.subTest(case=name):
                self.assert_verdict(
                    self.run_validator(payload, raw_input=raw_input),
                    False,
                    "invalid_input",
                    False,
                )

    def test_invalid_snapshot_fields_are_rejected_before_evaluation(self):
        invalid_values = (
            ("missing_state_change_seq", "state_change_seq", MISSING),
            ("negative_state_change_seq", "state_change_seq", -1),
            ("string_state_change_seq", "state_change_seq", "1"),
            ("float_state_change_seq", "state_change_seq", 1.0),
            ("bool_state_change_seq", "state_change_seq", True),
            ("negative_completion_seq", "completion_seq", -1),
            ("float_completion_seq", "completion_seq", 1.0),
            ("bool_completion_seq", "completion_seq", True),
            ("string_completion_seq", "completion_seq", "1"),
        )
        for side in ("baseline", "current"):
            for name, field, invalid_value in invalid_values:
                with self.subTest(side=side, case=name):
                    payload = self.payload(
                        self.snapshot("idle", 2, 1),
                        self.snapshot("idle", 2, 1),
                    )
                    snapshot = payload[side]
                    if invalid_value is MISSING:
                        snapshot.pop(field, None)
                    else:
                        snapshot[field] = invalid_value
                    self.assert_verdict(
                        self.run_validator(payload),
                        False,
                        "invalid_input",
                        False,
                    )

        completion_past_state = self.payload(
            self.snapshot("idle", 2, 3),
            self.snapshot("idle", 2, 1),
        )
        self.assert_verdict(
            self.run_validator(completion_past_state),
            False,
            "invalid_input",
            False,
        )

    def test_invalid_or_missing_agent_status_is_rejected(self):
        cases = (
            ("missing_status", MISSING),
            ("unexpected_status", "sleeping"),
            ("non_string_status", 1),
        )
        for side in ("baseline", "current"):
            for name, status in cases:
                with self.subTest(side=side, case=name):
                    payload = self.payload()
                    if status is MISSING:
                        payload[side].pop("agent_status")
                    else:
                        payload[side]["agent_status"] = status
                    self.assert_verdict(
                        self.run_validator(payload),
                        False,
                        "invalid_input",
                        False,
                    )

    def test_extra_herdr_agent_metadata_is_ignored(self):
        baseline = self.snapshot(
            "idle",
            20,
            20,
            name="researcher-日本語",
            pane_id="%7",
            agent_session="session-baseline",
            agent_id="agent-42",
            status="unrelated-status",
            result={"text": "not read"},
            task={"prompt": "not read"},
        )
        current = self.snapshot(
            "done",
            21,
            21,
            name="researcher-日本語",
            pane_id="%7",
            agent_session="session-current",
            agent_id="agent-42",
            status="also-ignored",
            result={"text": "not read"},
            task={"prompt": "not read"},
        )
        self.assert_verdict(
            self.run_validator(self.payload(baseline, current)),
            True,
            "completion_advanced",
            True,
        )

    def test_cli_usage_error_writes_usage_to_stderr_without_a_verdict(self):
        completed = self.run_validator(self.payload(), args=("unexpected",))
        self.assertEqual(2, completed.returncode)
        self.assertEqual("", completed.stdout)
        self.assertEqual(
            "usage: freshness_validate (read one JSON object from stdin)\n",
            completed.stderr,
        )


if __name__ == "__main__":
    unittest.main()
