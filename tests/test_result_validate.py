import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
VALIDATOR = ROOT / "skills" / "agent-orchestration" / "scripts" / "result_validate"
OPENING_TAG = "<HERDR_RESULT>"
CLOSING_TAG = "</HERDR_RESULT>"
VERDICT_KEYS = {"valid", "reason", "role", "field", "checks"}
EXPLORER_CHECKS = [
    "envelope",
    "required_fields",
    "unique_fields",
    "field_order",
    "nonempty_fields",
    "confidence",
]
FIXER_CHECKS = [
    "envelope",
    "required_fields",
    "unique_fields",
    "field_order",
    "nonempty_fields",
]
EXPLORER_FIELDS = (
    "Conclusion",
    "Evidence",
    "Impact",
    "Recommendation",
    "Confidence",
)
FIXER_FIELDS = ("Changes", "Verification", "Remaining issues")
DEFAULT_EXPLORER = {
    "Conclusion": "Independent finding",
    "Evidence": "src/module.py:12 confirms the behavior.",
    "Impact": "Narrows the investigation.",
    "Recommendation": "Verify the related caller.",
    "Confidence": "high — direct code evidence.",
}
DEFAULT_FIXER = {
    "Changes": "Updated the implementation.",
    "Verification": "python3 -m unittest passed.",
    "Remaining issues": "None.",
}


class ResultValidateTest(unittest.TestCase):
    def setUp(self):
        self.env = {
            "PATH": os.path.dirname(sys.executable),
            "LANG": "C",
            "LC_ALL": "C",
        }

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

    def parse_verdict(self, completed):
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stderr)
        self.assertTrue(completed.stdout.endswith("\n"))
        self.assertEqual(1, completed.stdout.count("\n"))
        value = json.loads(completed.stdout)
        self.assertIsInstance(value, dict)
        self.assertEqual(VERDICT_KEYS, set(value))
        return value

    def assert_verdict(self, completed, valid, reason, field=None, role=None, checks=None):
        value = self.parse_verdict(completed)
        self.assertIs(valid, value["valid"])
        self.assertEqual(reason, value["reason"])
        self.assertEqual(field, value["field"])
        self.assertEqual(role, value["role"])
        if checks is not None:
            self.assertEqual(checks, value["checks"])
        return value

    @staticmethod
    def result_block(role, values=None, omitted=(), order=None, label_indent=""):
        labels = EXPLORER_FIELDS if role == "explorer" else FIXER_FIELDS
        selected_values = dict(DEFAULT_EXPLORER if role == "explorer" else DEFAULT_FIXER)
        if values:
            selected_values.update(values)
        if order is None:
            order = [label for label in labels if label not in omitted]
        lines = [f"{label_indent}{label}: {selected_values[label]}" for label in order]
        return f"{OPENING_TAG}\n" + "\n".join(lines) + f"\n{CLOSING_TAG}"

    def validate_result(self, role, result):
        return self.run_validator({"role": role, "result": result})

    def test_common_invalid_json_object_role_and_result_inputs(self):
        cases = (
            ("malformed_json", None, "{", "invalid_input", None, None),
            ("nonstandard_json_constant", None, "NaN", "invalid_input", None, None),
            ("non_object", None, "[]", "invalid_input", None, None),
            (
                "missing_role",
                {"result": self.result_block("explorer")},
                None,
                "invalid_role",
                None,
                None,
            ),
            (
                "unknown_role",
                {"role": "reviewer", "result": self.result_block("explorer")},
                None,
                "invalid_role",
                None,
                None,
            ),
            ("missing_result", {"role": "explorer"}, None, "invalid_result", None, "explorer"),
            (
                "non_string_result",
                {"role": "fixer", "result": None},
                None,
                "invalid_result",
                None,
                "fixer",
            ),
            ("empty_result", {"role": "explorer", "result": ""}, None, "empty_result", None, "explorer"),
            (
                "whitespace_result",
                {"role": "fixer", "result": " \t\n"},
                None,
                "empty_result",
                None,
                "fixer",
            ),
        )
        for name, payload, raw_input, reason, field, role in cases:
            with self.subTest(case=name):
                completed = self.run_validator(payload, raw_input=raw_input)
                self.assert_verdict(completed, False, reason, field=field, role=role, checks=[])

    def test_cli_usage_error_writes_usage_to_stderr_without_a_verdict(self):
        completed = self.run_validator(
            {"role": "explorer", "result": self.result_block("explorer")},
            args=("unexpected",),
        )
        self.assertEqual(2, completed.returncode)
        self.assertEqual("", completed.stdout)
        self.assertEqual("usage: result_validate (read one JSON object from stdin)\n", completed.stderr)

    def test_envelope_rejections_have_stable_reasons_and_exit_zero(self):
        valid = self.result_block("explorer")
        cases = (
            ("missing_opening", valid.replace(OPENING_TAG, "", 1), "missing_opening_tag"),
            ("missing_closing", valid.replace(CLOSING_TAG, "", 1), "missing_closing_tag"),
            ("duplicate_opening", OPENING_TAG + valid, "duplicate_opening_tag"),
            ("duplicate_closing", valid + CLOSING_TAG, "duplicate_closing_tag"),
            (
                "closing_before_opening",
                f"{CLOSING_TAG}{OPENING_TAG}\ncontent",
                "tag_order",
            ),
            ("empty_block", f"{OPENING_TAG}\n \t{CLOSING_TAG}", "empty_block"),
            ("text_before_block", "outside text\n" + valid, "text_outside_block"),
            ("text_after_block", valid + "\noutside text", "text_outside_block"),
        )
        for name, result, reason in cases:
            with self.subTest(case=name):
                self.assert_verdict(
                    self.validate_result("explorer", result),
                    False,
                    reason,
                    role="explorer",
                    checks=[],
                )

    def test_explorer_canonical_block_passes_all_checks(self):
        self.assert_verdict(
            self.validate_result("explorer", self.result_block("explorer")),
            True,
            "valid",
            role="explorer",
            checks=EXPLORER_CHECKS,
        )

    def test_explorer_accepts_multiline_evidence_and_unrelated_lines_inside_a_field(self):
        cases = (
            (
                "multiline_evidence",
                {"Evidence": "\n- src/a.py:10\n- src/b.py:20"},
            ),
            (
                "unrelated_note_line",
                {"Evidence": "src/a.py:10 is relevant.\nNote: additional context."},
            ),
        )
        for name, values in cases:
            with self.subTest(case=name):
                result = self.result_block("explorer", values=values)
                self.assert_verdict(
                    self.validate_result("explorer", result),
                    True,
                    "valid",
                    role="explorer",
                    checks=EXPLORER_CHECKS,
                )

    def test_explorer_labels_allow_leading_spaces_and_tabs(self):
        result = self.result_block("explorer", label_indent=" \t")
        self.assert_verdict(
            self.validate_result("explorer", result),
            True,
            "valid",
            role="explorer",
            checks=EXPLORER_CHECKS,
        )

    def test_explorer_missing_each_required_field(self):
        for field in EXPLORER_FIELDS:
            with self.subTest(field=field):
                result = self.result_block("explorer", omitted=(field,))
                self.assert_verdict(
                    self.validate_result("explorer", result),
                    False,
                    "missing_field",
                    field=field,
                    role="explorer",
                    checks=["envelope"],
                )

    def test_explorer_duplicate_field_and_wrong_order(self):
        duplicate_order = [
            "Conclusion",
            "Evidence",
            "Evidence",
            "Impact",
            "Recommendation",
            "Confidence",
        ]
        duplicate = self.result_block("explorer", order=duplicate_order)
        self.assert_verdict(
            self.validate_result("explorer", duplicate),
            False,
            "duplicate_field",
            field="Evidence",
            role="explorer",
            checks=["envelope", "required_fields"],
        )

        wrong_order = self.result_block(
            "explorer",
            order=("Evidence", "Conclusion", "Impact", "Recommendation", "Confidence"),
        )
        self.assert_verdict(
            self.validate_result("explorer", wrong_order),
            False,
            "field_order",
            role="explorer",
            checks=["envelope", "required_fields", "unique_fields"],
        )

    def test_explorer_empty_each_field(self):
        for field in EXPLORER_FIELDS:
            with self.subTest(field=field):
                result = self.result_block("explorer", values={field: ""})
                self.assert_verdict(
                    self.validate_result("explorer", result),
                    False,
                    "empty_field",
                    field=field,
                    role="explorer",
                    checks=["envelope", "required_fields", "unique_fields", "field_order"],
                )

    def test_explorer_rejects_non_whitespace_content_before_first_field(self):
        result = self.result_block("explorer").replace(
            f"{OPENING_TAG}\n",
            f"{OPENING_TAG}\nUnexpected preamble.\n",
            1,
        )
        self.assert_verdict(
            self.validate_result("explorer", result),
            False,
            "unexpected_content",
            role="explorer",
            checks=["envelope"],
        )

    def test_explorer_confidence_level_separator_and_reason_validation(self):
        cases = (
            ("certain_level", "certain — reason", "invalid_confidence_level"),
            ("uppercase_level", "High — reason", "invalid_confidence_level"),
            ("space_hyphen_separator", "high - reason", "invalid_confidence_separator"),
            ("colon_separator", "high: reason", "invalid_confidence_separator"),
            ("no_separator_space", "high—reason", "invalid_confidence_separator"),
            ("bare_level", "high", "invalid_confidence_separator"),
            ("missing_reason", "high —", "missing_confidence_reason"),
            ("whitespace_reason", "high —   ", "missing_confidence_reason"),
        )
        for name, confidence, reason in cases:
            with self.subTest(case=name):
                result = self.result_block("explorer", values={"Confidence": confidence})
                self.assert_verdict(
                    self.validate_result("explorer", result),
                    False,
                    reason,
                    field="Confidence",
                    role="explorer",
                    checks=EXPLORER_CHECKS[:-1],
                )

    def test_explorer_confidence_accepts_optional_post_dash_whitespace(self):
        for confidence in ("high —reason", "medium \t—reason", "low — some reason"):
            with self.subTest(confidence=confidence):
                result = self.result_block("explorer", values={"Confidence": confidence})
                self.assert_verdict(
                    self.validate_result("explorer", result),
                    True,
                    "valid",
                    role="explorer",
                    checks=EXPLORER_CHECKS,
                )

    def test_fixer_canonical_block_and_multiline_fields_are_valid(self):
        result = self.result_block(
            "fixer",
            values={
                "Changes": "Updated the implementation.\n- src/a.py\n- src/b.py",
                "Verification": "Ran the focused test.\nRan the full suite.",
                "Remaining issues": "None.",
            },
        )
        self.assert_verdict(
            self.validate_result("fixer", result),
            True,
            "valid",
            role="fixer",
            checks=FIXER_CHECKS,
        )

    def test_fixer_missing_each_required_field(self):
        for field in FIXER_FIELDS:
            with self.subTest(field=field):
                result = self.result_block("fixer", omitted=(field,))
                self.assert_verdict(
                    self.validate_result("fixer", result),
                    False,
                    "missing_field",
                    field=field,
                    role="fixer",
                    checks=["envelope"],
                )

    def test_fixer_duplicate_field_and_wrong_order(self):
        duplicate = self.result_block(
            "fixer",
            order=("Changes", "Verification", "Verification", "Remaining issues"),
        )
        self.assert_verdict(
            self.validate_result("fixer", duplicate),
            False,
            "duplicate_field",
            field="Verification",
            role="fixer",
            checks=["envelope", "required_fields"],
        )

        wrong_order = self.result_block(
            "fixer",
            order=("Verification", "Changes", "Remaining issues"),
        )
        self.assert_verdict(
            self.validate_result("fixer", wrong_order),
            False,
            "field_order",
            role="fixer",
            checks=["envelope", "required_fields", "unique_fields"],
        )

    def test_fixer_empty_each_field(self):
        for field in FIXER_FIELDS:
            with self.subTest(field=field):
                result = self.result_block("fixer", values={field: ""})
                self.assert_verdict(
                    self.validate_result("fixer", result),
                    False,
                    "empty_field",
                    field=field,
                    role="fixer",
                    checks=["envelope", "required_fields", "unique_fields", "field_order"],
                )

    def test_role_specific_labels_are_not_reused_across_roles(self):
        explorer_as_fixer = self.result_block("explorer")
        self.assert_verdict(
            self.validate_result("fixer", explorer_as_fixer),
            False,
            "missing_field",
            field="Changes",
            role="fixer",
            checks=["envelope"],
        )

        fixer_as_explorer = self.result_block("fixer")
        self.assert_verdict(
            self.validate_result("explorer", fixer_as_explorer),
            False,
            "missing_field",
            field="Conclusion",
            role="explorer",
            checks=["envelope"],
        )


if __name__ == "__main__":
    unittest.main()
