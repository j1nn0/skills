import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SUITE_PATH = ROOT / "evals" / "behavior" / "assumption-expiry-audit.json"
FIXTURE_ROOT = ROOT / "evals" / "behavior" / "fixtures"
SKILL_PATH = ROOT / "skills" / "assumption-expiry-audit"
CHECKER = SKILL_PATH / "scripts" / "check_assumptions.py"
RUNNER_PATH = ROOT / "evals" / "behavior" / "run_behavior_eval.py"
SPEC = importlib.util.spec_from_file_location("assumption_expiry_audit_behavior_eval", RUNNER_PATH)
run_behavior_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_behavior_eval)

EXPECTED_CASE_IDS = [
    "unchanged-supported",
    "dependency-changed",
    "direct-contradiction",
    "missing-source",
    "unrelated-change",
    "historical-conditions",
    "external-offline",
    "audit-only-request",
]


class AssumptionExpiryAuditEvalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = run_behavior_eval.load_suite(SUITE_PATH)

    def test_suite_validates_with_behavior_runner(self):
        self.assertEqual([], run_behavior_eval.validate_suite(self.suite))

    def test_suite_has_exact_cases_in_required_order(self):
        self.assertEqual(EXPECTED_CASE_IDS, [case["id"] for case in self.suite["cases"]])
        self.assertTrue(all(case["evaluation_mode"] == "response" for case in self.suite["cases"]))

    def test_every_axis_and_critical_invariant_is_referenced_by_an_expectation(self):
        referenced = {
            expectation["invariant"]
            for case in self.suite["cases"]
            for collection in ("required", "forbidden")
            for expectation in case[collection]
        }
        covered_axes = {self.suite["invariants"][item]["axis"] for item in referenced}
        self.assertEqual(
            [
                "verdict_correctness",
                "evidence_traceability",
                "false_positive_resistance",
                "unsupported_claim_avoidance",
                "scope_preservation",
                "detection_judgment_separation",
            ],
            self.suite["axes"],
        )
        self.assertTrue(set(self.suite["axes"]).issubset(covered_axes))
        critical = {
            invariant_id
            for invariant_id, definition in self.suite["invariants"].items()
            if definition["critical"]
        }
        self.assertTrue(critical.issubset(referenced), f"Unreferenced critical invariants: {critical - referenced}")
        self.assertTrue(
            {"false_positive_resistance", "unsupported_claim_avoidance", "scope_preservation"}.issubset(critical)
        )
        for case in self.suite["cases"]:
            self.assertTrue(case["required"], case["id"])
            self.assertTrue(case["forbidden"], case["id"])

    def test_every_case_has_an_existing_plain_file_fixture_repository(self):
        for case in self.suite["cases"]:
            with self.subTest(case=case["id"]):
                fixture = FIXTURE_ROOT / case["fixture"]
                self.assertTrue(fixture.is_dir())
                self.assertFalse((fixture / ".git").exists())
                self.assertTrue((fixture / "assumptions.json").is_file())
                entries = list(fixture.rglob("*"))
                self.assertTrue(any(path.is_file() for path in entries))
                self.assertFalse(any(path.is_symlink() for path in entries))

    def test_checker_statuses_and_signals_are_deterministic_for_each_fixture(self):
        expected = {
            "unchanged-supported": ("unchanged", 0),
            "dependency-changed": ("changed", 1),
            "direct-contradiction": ("changed", 1),
            "missing-source": ("changed", 1),
            "unrelated-change": ("unchanged", 0),
            "historical-conditions": ("changed", 1),
            "external-offline": ("unchanged", 0),
            "audit-only-request": ("changed", 1),
        }
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        for case in self.suite["cases"]:
            with self.subTest(case=case["id"]):
                repo = FIXTURE_ROOT / case["fixture"]
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(CHECKER),
                        "check",
                        "--repo",
                        str(repo),
                        "--records",
                        str(repo / "assumptions.json"),
                    ],
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertTrue(completed.stdout, completed.stderr)
                result = json.loads(completed.stdout)
                record = result["assumptions"][0]
                status, exit_code = expected[case["id"]]
                self.assertEqual(exit_code, completed.returncode, completed.stderr)
                self.assertEqual(status, record["status"])
                signals = {(signal["type"], signal.get("path")) for signal in record["signals"]}

                if case["id"] == "unchanged-supported":
                    self.assertEqual(set(), signals)
                    stored_record = json.loads((repo / "assumptions.json").read_text(encoding="utf-8"))["assumptions"][0]
                    evidence_paths = [item["path"] for item in stored_record["evidence"] if item["kind"] == "file"]
                    self.assertIn("src/auth/middleware.py", evidence_paths)
                    self.assertEqual(
                        ["src/auth/middleware.py", "src/auth/session.py"],
                        sorted(stored_record["baseline"]["files"]),
                    )
                elif case["id"] == "dependency-changed":
                    self.assertIn(("modified", "package.json"), signals)
                    self.assertIn(("modified", "package-lock.json"), signals)
                    self.assertTrue(any(check["kind"] == "url" for check in record["agent_checks"]))
                elif case["id"] == "direct-contradiction":
                    for path in ("config/queue.yml", "package.json", "workers/jobs.js"):
                        self.assertIn(("modified", path), signals)
                elif case["id"] == "missing-source":
                    self.assertIn(("deleted", "docs/invoice-id-policy.md"), signals)
                    self.assertIn(("evidence_missing", "docs/invoice-id-policy.md"), signals)
                elif case["id"] == "unrelated-change":
                    self.assertEqual(set(), signals)
                    stored_record = json.loads((repo / "assumptions.json").read_text(encoding="utf-8"))["assumptions"][0]
                    files = stored_record["baseline"]["files"]
                    self.assertEqual(["config/session.yml"], sorted(files))
                elif case["id"] == "historical-conditions":
                    self.assertIn(("condition_changed", ".nvmrc"), signals)
                elif case["id"] == "external-offline":
                    self.assertEqual(set(), signals)
                    self.assertTrue(any(check["kind"] == "url" for check in record["agent_checks"]))
                    urls = [evidence["url"] for evidence in record["evidence"] if evidence["kind"] == "url"]
                    self.assertEqual(
                        ["https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14"], urls
                    )
                elif case["id"] == "audit-only-request":
                    self.assertIn(("condition_changed", ".nvmrc"), signals)

    def test_model_prompt_includes_only_the_scenario_not_rubric_or_fixture_contents(self):
        skill_text = (SKILL_PATH / "SKILL.md").read_text(encoding="utf-8")
        for case in self.suite["cases"]:
            prompt = run_behavior_eval.build_model_prompt(
                run_behavior_eval.prompt_context(self.suite, case),
                skill_text,
                "assumption-expiry-audit",
                case,
            )
            with self.subTest(case=case["id"]):
                self.assertIn(case["scenario"], prompt)
                self.assertIn("The fixture repository is at `repo/`", prompt)
                self.assertNotIn(case["fixture"], prompt)
                for collection in ("required", "forbidden"):
                    for expectation in case[collection]:
                        self.assertNotIn(expectation["text"], prompt)
                fixture = FIXTURE_ROOT / case["fixture"]
                for file_path in fixture.rglob("*"):
                    if file_path.is_file():
                        content = file_path.read_text(encoding="utf-8").strip()
                        if content:
                            self.assertNotIn(content, prompt, file_path.relative_to(fixture).as_posix())


if __name__ == "__main__":
    unittest.main()
