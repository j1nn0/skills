import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
VALIDATOR = ROOT / "skills" / "agent-orchestration" / "scripts" / "parallel_validate"


class ParallelValidateTest(unittest.TestCase):
    def setUp(self):
        self.env = {
            "PATH": os.path.dirname(sys.executable),
            "LANG": "C",
            "LC_ALL": "C",
        }

    @staticmethod
    def unit(unit_id, **overrides):
        value = {
            "unit_id": unit_id,
            "role": "explorer",
            "read_only": True,
            "objective": f"Investigate {unit_id} independently",
            "completion_criteria": f"Report evidence and conclusion for {unit_id}",
            "depends_on": [],
            "read_scope": ["src/shared/"],
        }
        value.update(overrides)
        return value

    def admission(self, units=None, **overrides):
        value = {
            "mode": "admission",
            "enabled": True,
            "max_explorers": 3,
            "objective": "Investigate the intermittent import failure",
            "active_batches": 0,
            "units": units if units is not None else [self.unit("unit-1"), self.unit("unit-2")],
        }
        value.update(overrides)
        return value

    @staticmethod
    def herdr_result(conclusion="Independent finding"):
        return (
            "<HERDR_RESULT>\n"
            f"Conclusion: {conclusion}\n"
            "Evidence: src/module.py:12 confirms the behavior.\n"
            "Impact: narrows the investigation.\n"
            "Recommendation: verify the related caller.\n"
            "Confidence: high — direct code evidence.\n"
            "</HERDR_RESULT>"
        )

    def run_validator(self, payload=None, args=(), raw_input=None):
        if raw_input is None:
            raw_input = "" if payload is None else json.dumps(payload)
        return subprocess.run(
            [sys.executable, str(VALIDATOR), *args],
            input=raw_input,
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )

    def parse_verdict(self, completed):
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stderr)
        self.assertTrue(completed.stdout.endswith("\n"))
        self.assertEqual(1, completed.stdout.count("\n"))
        value = json.loads(completed.stdout)
        self.assertIsInstance(value, dict)
        return value

    def test_admission_enabled_and_explorer_count_table(self):
        cases = (
            ("disabled", self.admission(enabled=False), False, "disabled"),
            (
                "one_sequential",
                self.admission(units=[self.unit("unit-1")]),
                False,
                "single_unit_sequential",
            ),
            ("two_normal", self.admission(), True, "admitted"),
            (
                "three_maximum",
                self.admission(units=[self.unit(f"unit-{i}") for i in range(3)]),
                True,
                "admitted",
            ),
            (
                "four_rejected",
                self.admission(units=[self.unit(f"unit-{i}") for i in range(4)]),
                False,
                "too_many_explorers",
            ),
        )
        for name, payload, admitted, reason in cases:
            with self.subTest(case=name):
                result = self.parse_verdict(self.run_validator(payload))
                self.assertEqual(admitted, result["admitted"])
                self.assertEqual(reason, result["reason"])

    def test_active_batch_count_is_current_existing_batch_count(self):
        cases = (
            ("none_active", 0, True, "admitted"),
            ("one_already_active", 1, False, "active_batch_limit"),
        )
        for name, active_batches, admitted, reason in cases:
            with self.subTest(case=name):
                result = self.parse_verdict(
                    self.run_validator(self.admission(active_batches=active_batches))
                )
                self.assertEqual(admitted, result["admitted"])
                self.assertEqual(reason, result["reason"])

    def test_enabled_defaults_to_disabled(self):
        payload = self.admission()
        del payload["enabled"]
        result = self.parse_verdict(self.run_validator(payload))
        self.assertFalse(result["admitted"])
        self.assertEqual("disabled", result["reason"])

    def test_read_only_is_required(self):
        payload = self.admission(
            units=[self.unit("unit-1", read_only=False), self.unit("unit-2")]
        )
        result = self.parse_verdict(self.run_validator(payload))
        self.assertFalse(result["admitted"])
        self.assertEqual("read_only_required", result["reason"])

    def test_admission_rejects_duplicate_ids_roles_writes_dependencies_nesting_and_second_batch(self):
        base_units = [self.unit("unit-1"), self.unit("unit-2")]
        cases = (
            (
                "duplicate_ids",
                self.admission(units=[self.unit("same"), self.unit("same")]),
                "duplicate_or_missing_unit_id",
            ),
            (
                "non_explorer_role",
                self.admission(units=[self.unit("unit-1", role="fixer"), self.unit("unit-2")]),
                "non_explorer_role",
            ),
            (
                "write_scope",
                self.admission(units=[self.unit("unit-1", write_scope=["src/"]), base_units[1]]),
                "write_intent_forbidden",
            ),
            (
                "write_intent",
                self.admission(units=[self.unit("unit-1", write_intent="edit source"), base_units[1]]),
                "write_intent_forbidden",
            ),
            (
                "sibling_strategy_dependency",
                self.admission(units=[self.unit("unit-1", depends_on=["unit-2"]), base_units[1]]),
                "sibling_dependency_forbidden",
            ),
            (
                "nested_batch",
                self.admission(nested=True),
                "nested_batch_forbidden",
            ),
            (
                "one_active_batch_already_exists",
                self.admission(active_batches=1),
                "active_batch_limit",
            ),
            (
                "multiple_active_batches",
                self.admission(active_batches=2),
                "active_batch_limit",
            ),
        )
        for name, payload, reason in cases:
            with self.subTest(case=name):
                result = self.parse_verdict(self.run_validator(payload))
                self.assertFalse(result["admitted"])
                self.assertEqual(reason, result["reason"])

    def test_shared_parent_objective_and_overlapping_read_scopes_are_allowed(self):
        units = [
            self.unit("import-path", read_scope=["src/shared/", "src/imports/"]),
            self.unit("runtime-path", read_scope=["src/shared/", "src/runtime/"]),
        ]
        result = self.parse_verdict(self.run_validator(self.admission(units=units)))
        self.assertTrue(result["admitted"])
        self.assertEqual("admitted", result["reason"])
        self.assertTrue(result["checks"]["shared_parent_objective"])
        self.assertTrue(result["checks"]["overlapping_read_scopes_allowed"])

    def test_max_explorers_is_limited_to_two_or_three_and_defaults_to_three(self):
        for value in (1, 4, True, "3"):
            with self.subTest(max_explorers=value):
                result = self.parse_verdict(
                    self.run_validator(self.admission(max_explorers=value))
                )
                self.assertFalse(result["admitted"])
                self.assertEqual("invalid_max_explorers", result["reason"])

        payload = self.admission(units=[self.unit(f"unit-{i}") for i in range(3)])
        del payload["max_explorers"]
        result = self.parse_verdict(self.run_validator(payload))
        self.assertTrue(result["admitted"])

    def test_fixer_only_input_is_not_reinterpreted_as_sequential_explorer(self):
        payload = self.admission(
            units=[self.unit("fix-a", role="fixer"), self.unit("fix-b", role="fixer")]
        )
        result = self.parse_verdict(self.run_validator(payload))
        self.assertFalse(result["admitted"])
        self.assertEqual("non_explorer_role", result["reason"])

    def test_admission_requires_explicit_active_batch_count_and_objectives(self):
        payload = self.admission()
        del payload["active_batches"]
        result = self.parse_verdict(self.run_validator(payload))
        self.assertEqual("invalid_active_batches", result["reason"])

        result = self.parse_verdict(
            self.run_validator(self.admission(objective="  "))
        )
        self.assertEqual("missing_objective", result["reason"])

    def convergence(self, units):
        return {
            "mode": "convergence",
            "objective": "Investigate the intermittent import failure",
            "units": units,
        }

    def test_all_accepted_units_are_ready_and_preserved_across_revalidation(self):
        payload = self.convergence(
            [
                {"unit_id": "unit-1", "status": "accepted", "accepted_result": self.herdr_result("Import path A")},
                {"unit_id": "unit-2", "status": "accepted", "accepted_result": self.herdr_result("Import path B")},
            ]
        )
        first = self.parse_verdict(self.run_validator(payload))
        second = self.parse_verdict(self.run_validator(payload))
        for result in (first, second):
            self.assertTrue(result["ready"])
            self.assertEqual("all_accepted", result["reason"])
            self.assertEqual(["unit-1", "unit-2"], result["accepted_units"])
            self.assertFalse(result["recoverable"])
        self.assertEqual(first["accepted_units"], second["accepted_units"])

    def test_failed_unit_with_explicit_gap_is_ready_with_gaps(self):
        result = self.parse_verdict(
            self.run_validator(
                self.convergence(
                    [
                        {"unit_id": "unit-1", "status": "accepted", "accepted_result": self.herdr_result()},
                        {"unit_id": "unit-2", "status": "failed", "gaps": ["The external test environment was unavailable."]},
                    ]
                )
            )
        )
        self.assertTrue(result["ready"])
        self.assertEqual("ready_with_gaps", result["reason"])
        self.assertEqual(["unit-1"], result["accepted_units"])
        self.assertEqual(["unit-2"], result["failed_units"])
        self.assertEqual(
            [{"unit_id": "unit-2", "gap": "The external test environment was unavailable."}],
            result["gaps"],
        )
        self.assertTrue(result["recoverable"])

    def test_failed_unit_without_explicit_gap_is_not_ready(self):
        result = self.parse_verdict(
            self.run_validator(
                self.convergence(
                    [
                        {"unit_id": "unit-1", "status": "accepted", "accepted_result": self.herdr_result()},
                        {"unit_id": "unit-2", "status": "failed", "gaps": []},
                    ]
                )
            )
        )
        self.assertFalse(result["ready"])
        self.assertEqual("failed_without_gaps", result["reason"])

    def test_invalid_accepted_result_is_not_ready(self):
        cases = (
            (
                "malformed",
                {
                    "unit_id": "unit-1",
                    "status": "accepted",
                    "accepted_result": "<HERDR_RESULT>missing close",
                },
            ),
            ("missing", {"unit_id": "unit-1", "status": "accepted"}),
        )
        for name, bad_unit in cases:
            with self.subTest(case=name):
                units = [
                    bad_unit,
                    {
                        "unit_id": "unit-2",
                        "status": "accepted",
                        "accepted_result": self.herdr_result(),
                    },
                ]
                result = self.parse_verdict(
                    self.run_validator(self.convergence(units))
                )
                self.assertFalse(result["ready"])
                self.assertEqual("invalid_result", result["reason"])
                self.assertEqual(["unit-2"], result["accepted_units"])
                self.assertEqual(["unit-1"], result["incomplete_units"])
                self.assertEqual(["unit-1"], result["recoverable_units"])
                self.assertTrue(result["recoverable"])

    def test_unknown_status_is_incomplete_and_recoverable(self):
        units = [
            {
                "unit_id": "unit-1",
                "status": "completed",
                "gaps": ["Unsupported status cannot count as a failed result."],
            },
            {
                "unit_id": "unit-2",
                "status": "accepted",
                "accepted_result": self.herdr_result(),
            },
        ]
        result = self.parse_verdict(self.run_validator(self.convergence(units)))
        self.assertFalse(result["ready"])
        self.assertEqual("invalid_input", result["reason"])
        self.assertEqual(["unit-2"], result["accepted_units"])
        self.assertEqual(["unit-1"], result["incomplete_units"])
        self.assertEqual(["unit-1"], result["recoverable_units"])
        self.assertTrue(result["recoverable"])

    def test_convergence_rejects_unit_counts_outside_parallel_batch_range(self):
        for count in (1, 4):
            with self.subTest(count=count):
                units = [
                    {
                        "unit_id": f"unit-{index}",
                        "status": "incomplete",
                    }
                    for index in range(count)
                ]
                result = self.parse_verdict(
                    self.run_validator(self.convergence(units))
                )
                self.assertFalse(result["ready"])
                self.assertEqual("invalid_batch_size", result["reason"])

    def test_unhashable_status_is_invalid_not_a_crash(self):
        units = [
            {
                "unit_id": "unit-1",
                "status": [],
            },
            {
                "unit_id": "unit-2",
                "status": "incomplete",
            },
        ]
        result = self.parse_verdict(self.run_validator(self.convergence(units)))
        self.assertFalse(result["ready"])
        self.assertEqual("invalid_input", result["reason"])

    def test_incomplete_unit_is_recoverable_and_accepted_sibling_stays_accepted(self):
        payload = self.convergence(
            [
                {"unit_id": "unit-1", "status": "accepted", "accepted_result": self.herdr_result()},
                {"unit_id": "unit-2", "status": "incomplete"},
            ]
        )
        result = self.parse_verdict(self.run_validator(payload))
        self.assertFalse(result["ready"])
        self.assertEqual("incomplete_units", result["reason"])
        self.assertEqual(["unit-1"], result["accepted_units"])
        self.assertEqual(["unit-2"], result["incomplete_units"])
        self.assertEqual(["unit-2"], result["recoverable_units"])
        self.assertTrue(result["recoverable"])

    def test_invalid_json_returns_json_verdict_and_usage_error_uses_stderr(self):
        invalid = self.parse_verdict(self.run_validator(raw_input="not-json"))
        self.assertFalse(invalid["admitted"])
        self.assertEqual("invalid_input", invalid["reason"])

        usage = self.run_validator(args=("unexpected",))
        self.assertEqual(2, usage.returncode)
        self.assertEqual("", usage.stdout)
        self.assertIn("usage:", usage.stderr)


if __name__ == "__main__":
    unittest.main()
