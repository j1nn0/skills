import json
import os
import stat
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
EXTRACTOR = ROOT / "skills" / "agent-orchestration" / "scripts" / "result_extract"
OPENING_TAG = "<HERDR_RESULT>"
CLOSING_TAG = "</HERDR_RESULT>"
EXPLORER_RESULT = (
    "<HERDR_RESULT>\n"
    "Conclusion: The behavior is confirmed.\n"
    "Evidence: src/module.py:12 shows the behavior.\n"
    "Impact: The scope is limited.\n"
    "Recommendation: Keep the existing implementation.\n"
    "Confidence: high — direct code evidence.\n"
    "</HERDR_RESULT>"
)
FIXER_RESULT = (
    "<HERDR_RESULT>\n"
    "Changes: Updated the implementation.\n"
    "Verification: The focused tests pass.\n"
    "Remaining issues: None.\n"
    "</HERDR_RESULT>"
)


class ResultExtractTest(unittest.TestCase):
    def setUp(self):
        self.env = {
            "PATH": os.path.dirname(sys.executable),
            "LANG": "C",
            "LC_ALL": "C",
        }

    def run_extractor(self, role="explorer", raw_text="", args=None):
        if args is None:
            args = ["--role", role]
        return subprocess.run(
            [str(EXTRACTOR), *args],
            input=raw_text,
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )

    def parse_response(self, completed):
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("", completed.stderr)
        self.assertTrue(completed.stdout.endswith("\n"))
        self.assertEqual(1, completed.stdout.count("\n"))
        response = json.loads(completed.stdout)
        self.assertEqual(
            {"valid", "reason", "role", "field", "checks", "result"},
            set(response),
        )
        return response

    def test_extractor_is_executable(self):
        self.assertTrue(EXTRACTOR.stat().st_mode & stat.S_IXUSR)

    def test_last_of_several_complete_blocks_is_selected(self):
        earlier = FIXER_RESULT.replace("Updated the implementation.", "Earlier result.")
        completed = self.run_extractor("fixer", earlier + "\nprogress\n" + FIXER_RESULT)
        response = self.parse_response(completed)
        self.assertTrue(response["valid"])
        self.assertEqual("fixer", response["role"])
        self.assertEqual(FIXER_RESULT, response["result"])

    def test_echoed_empty_template_before_real_block_is_ignored(self):
        empty_template = f"{OPENING_TAG}\n{CLOSING_TAG}"
        completed = self.run_extractor(
            "explorer", "prompt echo:\n" + empty_template + "\nagent output:\n" + EXPLORER_RESULT
        )
        response = self.parse_response(completed)
        self.assertTrue(response["valid"])
        self.assertEqual(EXPLORER_RESULT, response["result"])

    def test_valid_explorer_and_fixer_results(self):
        for role, result in (("explorer", EXPLORER_RESULT), ("fixer", FIXER_RESULT)):
            with self.subTest(role=role):
                response = self.parse_response(self.run_extractor(role, result))
                self.assertTrue(response["valid"])
                self.assertEqual("valid", response["reason"])
                self.assertEqual(role, response["role"])
                self.assertEqual(result, response["result"])

    def test_validation_failure_is_propagated_from_result_validate(self):
        invalid = EXPLORER_RESULT.replace("Recommendation: Keep the existing implementation.\n", "")
        response = self.parse_response(self.run_extractor("explorer", invalid))
        self.assertFalse(response["valid"])
        self.assertEqual("missing_field", response["reason"])
        self.assertEqual("Recommendation", response["field"])
        self.assertEqual(invalid, response["result"])

    def test_no_result_block_has_a_distinct_verdict(self):
        response = self.parse_response(self.run_extractor("explorer", "progress only\n"))
        self.assertFalse(response["valid"])
        self.assertEqual("missing_result_block", response["reason"])
        self.assertEqual("explorer", response["role"])
        self.assertIsNone(response["result"])

    def test_trailing_truncated_block_is_not_ignored_after_a_complete_block(self):
        raw_text = EXPLORER_RESULT + "\n" + OPENING_TAG + "\nConclusion: newer but incomplete"
        response = self.parse_response(self.run_extractor("explorer", raw_text))
        self.assertFalse(response["valid"])
        self.assertEqual("truncated_result_block", response["reason"])
        self.assertEqual("explorer", response["role"])
        self.assertIsNone(response["result"])

    def test_bordered_and_wrapped_tui_result_is_validated(self):
        fixture = (ROOT / "tests" / "fixtures" / "pi_tui_border_explorer_result.txt").read_text(
            encoding="utf-8"
        )
        response = self.parse_response(self.run_extractor("explorer", "read output:\n" + fixture))
        self.assertTrue(response["valid"], response)
        self.assertEqual("valid", response["reason"])
        self.assertTrue(response["result"].lstrip().startswith(OPENING_TAG))
        self.assertTrue(response["result"].rstrip().endswith(CLOSING_TAG))

    def test_usage_errors_return_two_and_do_not_emit_json(self):
        cases = (
            ("missing_role", []),
            ("missing_role_value", ["--role"]),
            ("invalid_role", ["--role", "reviewer"]),
            ("extra_argument", ["--role", "explorer", "extra"]),
        )
        for name, args in cases:
            with self.subTest(case=name):
                completed = self.run_extractor(args=args)
                self.assertEqual(2, completed.returncode)
                self.assertEqual("", completed.stdout)
                self.assertEqual(
                    "usage: result_extract --role {explorer|fixer}\n", completed.stderr
                )


if __name__ == "__main__":
    unittest.main()
