import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "evals" / "behavior" / "run_behavior_eval.py"
SUITE_PATH = ROOT / "evals" / "behavior" / "agent-orchestration.json"
SKILL_PATH = ROOT / "skills" / "agent-orchestration" / "SKILL.md"
SPEC = importlib.util.spec_from_file_location("run_behavior_eval_suite_test", SCRIPT)
run_behavior_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_behavior_eval)

EXPECTED_CASE_IDS = [
    "01-trivial-direct",
    "02-unknown-root-cause",
    "03-settled-root-cause",
    "04-independent-parallel",
    "05-dependent-investigations",
    "06-write-parallel-request",
    "07-context-leakage",
    "08-multi-unit",
    "09-fixer-uncertainty",
    "10-implementation-defect",
    "11-flawed-strategy",
    "12-destructive",
    "13-config-unavailable",
    "14-incomplete-verification",
    "15-stale-result",
]


class BehaviorEvalSuiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = run_behavior_eval.load_suite(SUITE_PATH)

    def test_suite_validates_with_behavior_runner(self):
        self.assertEqual([], run_behavior_eval.validate_suite(self.suite))

    def test_suite_has_exact_cases_in_required_order(self):
        self.assertEqual(EXPECTED_CASE_IDS, [case["id"] for case in self.suite["cases"]])

    def test_every_runner_axis_has_an_expectation_or_route_invariant(self):
        referenced = set()
        for case in self.suite["cases"]:
            referenced.add(case.get("route_invariant", "correct_route"))
            for collection in ("required", "forbidden"):
                referenced.update(item["invariant"] for item in case[collection])

        covered_axes = {self.suite["invariants"][item]["axis"] for item in referenced}
        self.assertTrue(set(run_behavior_eval.AXES).issubset(covered_axes))

    def test_every_critical_invariant_is_referenced_by_a_case(self):
        referenced = set()
        for case in self.suite["cases"]:
            referenced.add(case.get("route_invariant", "correct_route"))
            for collection in ("required", "forbidden"):
                referenced.update(item["invariant"] for item in case[collection])

        critical = {
            invariant_id
            for invariant_id, definition in self.suite["invariants"].items()
            if definition["critical"]
        }
        self.assertTrue(critical.issubset(referenced), f"Unreferenced critical invariants: {critical - referenced}")

    def test_handoff_leak_markers_appear_in_their_own_scenarios(self):
        for case in self.suite["cases"]:
            for marker_entry in case.get("handoff_must_not_contain", []):
                with self.subTest(case=case["id"], marker=marker_entry["marker"]):
                    self.assertIn(marker_entry["marker"], case["scenario"])

    def test_model_prompt_omits_required_and_forbidden_expectation_text(self):
        skill_text = SKILL_PATH.read_text(encoding="utf-8")
        for case in self.suite["cases"]:
            prompt = run_behavior_eval.build_decision_prompt(
                self.suite["context"], skill_text, "agent-orchestration", case
            )
            for collection in ("required", "forbidden"):
                for expectation in case[collection]:
                    with self.subTest(case=case["id"], collection=collection, text=expectation["text"]):
                        self.assertNotIn(expectation["text"], prompt)


if __name__ == "__main__":
    unittest.main()
