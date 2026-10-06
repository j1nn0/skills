import importlib.util
import re
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
    "16-parallel-convergence",
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

    def test_critical_invariants_keep_their_critical_flag(self):
        critical = {
            invariant_id
            for invariant_id, definition in self.suite["invariants"].items()
            if definition["critical"]
        }
        self.assertEqual(
            {
                "explorer_read_only",
                "no_fixer_with_unresolved_uncertainty",
                "no_parallel_fixers",
                "no_raw_context_copy",
                "no_sibling_output_sharing",
                "no_unapproved_destructive_action",
                "no_silent_config_fallback",
                "no_completion_without_verification",
            },
            critical,
        )

    def test_settled_fix_scope_allows_verifying_tests_but_forbids_migration(self):
        case = self.case("03-settled-root-cause")
        scope_required = [
            item["text"] for item in case["required"] if item["invariant"] == "fixer_bounded_scope"
        ]
        scope_forbidden = [
            item["text"] for item in case["forbidden"] if item["invariant"] == "fixer_bounded_scope"
        ]

        self.assertTrue(scope_required)
        self.assertTrue(all("test" in text.lower() for text in scope_required))
        self.assertFalse(any("test" in text.lower() for text in scope_forbidden))
        self.assertTrue(any("migrat" in text.lower() for text in scope_forbidden))

    def test_incomplete_verification_requires_reassessment_before_completion(self):
        case = self.case("14-incomplete-verification")
        required_text = " ".join(item["text"] for item in case["required"])
        forbidden_invariants = {item["invariant"] for item in case["forbidden"]}

        self.assertEqual(["reassess"], case["expected_routes"])
        self.assertNotIn("complete", case["expected_routes"])
        for outstanding_check in ("pytest tests/integration", "ruff check"):
            self.assertIn(outstanding_check, case["scenario"])
            self.assertIn(outstanding_check, required_text)
        self.assertIn("no_completion_without_verification", forbidden_invariants)
        self.assertIn("review_actual_diff", {item["invariant"] for item in case["required"]})

    def test_config_unavailable_judges_actions_not_restated_explorer_config(self):
        case = self.case("13-config-unavailable")
        invariants = self.suite["invariants"]

        self.assertFalse(any("explorer" in item["text"].lower() for item in case["required"]))
        self.assertTrue(any("explorer" in item["text"].lower() for item in case["forbidden"]))
        self.assertTrue(any("replacement" in item["text"].lower() for item in case["required"]))
        self.assertTrue(invariants["no_silent_config_fallback"]["critical"])
        self.assertFalse(invariants["escalate_when_required"]["critical"])
        self.assertEqual("escalate_when_required", case["route_invariant"])
        self.assertTrue(all(item["invariant"] == "escalate_when_required" for item in case["required"]))
        self.assertEqual(2, len(case["forbidden"]))
        self.assertTrue(all(item["invariant"] == "no_silent_config_fallback" for item in case["forbidden"]))

    def test_trivial_direct_judges_the_route_decision_not_a_performed_edit(self):
        case = self.case("01-trivial-direct")
        invariants = self.suite["invariants"]

        self.assertEqual(["direct"], case["expected_routes"])
        self.assertEqual("correct_route", case.get("route_invariant", "correct_route"))
        self.assertFalse(invariants["correct_route"]["critical"])
        self.assertTrue(all("direct" in item["text"].lower() for item in case["required"]))
        self.assertTrue(any("decision-only" in item["text"].lower() for item in case["required"]))
        self.assertTrue(
            any(
                "explorer" in item["text"].lower() and "fixer" in item["text"].lower()
                for item in case["forbidden"]
            )
        )

    def test_parallel_write_request_reserves_critical_for_concurrent_writes(self):
        case = self.case("06-write-parallel-request")
        invariants = self.suite["invariants"]
        parallel_items = [item for item in case["forbidden"] if item["invariant"] == "no_parallel_fixers"]

        self.assertTrue(invariants["no_parallel_fixers"]["critical"])
        self.assertEqual("correct_route", case["route_invariant"])
        self.assertTrue(all(not invariants[item["invariant"]]["critical"] for item in case["required"]))
        self.assertEqual(1, len(parallel_items))
        self.assertIn("overlapping writes", parallel_items[0]["text"].lower())

    def test_route_taxonomy_counts_handoffs_and_accepts_fixer_re_emit_request(self):
        self.assertTrue(run_behavior_eval.expected_handoff_count("reassess", 0))
        self.assertFalse(run_behavior_eval.expected_handoff_count("reassess", 1))
        self.assertTrue(run_behavior_eval.expected_handoff_count("fixer", 1))
        self.assertIn("- reassess:", self.suite["context"])
        self.assertIn("re-emit", self.suite["context"])

        case = self.case("15-stale-result")
        self.assertEqual({"reassess", "fixer"}, set(case["expected_routes"]))
        re_emit_request = {
            "route": "fixer",
            "rationale": "",
            "handoffs": ["Re-emit only your current final result for the pagination unit."],
            "user_message": "",
            "next_actions": [],
        }
        checks = run_behavior_eval.deterministic_checks(case, re_emit_request)
        self.assertTrue(all(check["passed"] for check in checks))

    def test_dependent_investigation_scenario_makes_the_second_target_depend_on_the_first(self):
        case = self.case("05-dependent-investigations")
        scenario = case["scenario"].lower()

        self.assertEqual(["explorer"], case["expected_routes"])
        self.assertEqual("sequential_when_dependent", case["route_invariant"])
        self.assertIn("trace", scenario)
        self.assertIn("allowlist", scenario)
        self.assertLess(scenario.index("trace"), scenario.rindex("allowlist"))
        self.assertTrue(any("enabled" in item.lower() for item in case["environment"]))
        self.assertTrue(
            any(item["invariant"] == "sequential_when_dependent" for item in case["forbidden"])
        )

    def test_multi_unit_scenario_settles_the_current_unit_and_its_verification(self):
        case = self.case("08-multi-unit")
        commands = re.findall(r"pytest [\w/.-]+", case["scenario"])
        settled_text = " ".join(
            item["text"] for item in case["required"] if item["invariant"] == "settled_state_handoff"
        )

        self.assertIn("ConfirmDialog", case["scenario"])
        self.assertIn("ConfirmDialog", {item["marker"] for item in case["handoff_must_not_contain"]})
        self.assertIn("current unit", case["scenario"].lower())
        self.assertIn("settled", case["scenario"].lower())
        self.assertTrue(commands)
        self.assertTrue(all(command in settled_text for command in commands))

    def test_parallel_dispatch_judges_dispatch_without_future_convergence(self):
        case = self.case("04-independent-parallel")
        required_invariants = {item["invariant"] for item in case["required"]}
        forbidden_invariants = {item["invariant"] for item in case["forbidden"]}

        self.assertEqual(["parallel_explorers"], case["expected_routes"])
        self.assertNotIn("orchestrator_convergence", required_invariants)
        self.assertIn("explorer_read_only", required_invariants)
        self.assertIn("no_sibling_output_sharing", forbidden_invariants)
        self.assertIn("no_parallel_fixers", forbidden_invariants)

    def test_parallel_convergence_judges_orchestrator_synthesis_after_the_batch(self):
        case = self.case("16-parallel-convergence")
        required_text = " ".join(item["text"].lower() for item in case["required"])
        forbidden_by_invariant = {item["invariant"]: item["text"].lower() for item in case["forbidden"]}
        reassess_without_prompt = {
            "route": "reassess",
            "rationale": "",
            "handoffs": [],
            "user_message": "",
            "next_actions": [],
        }

        self.assertEqual(["reassess"], case["expected_routes"])
        self.assertTrue(
            all(check["passed"] for check in run_behavior_eval.deterministic_checks(case, reassess_without_prompt))
        )
        self.assertIn("orchestrator_convergence", {item["invariant"] for item in case["required"]})
        for element in ("synthesis", "provenance", "tension", "gap"):
            self.assertIn(element, required_text)
        self.assertIn("fixer", forbidden_by_invariant["no_fixer_with_unresolved_uncertainty"])
        self.assertIn("no_sibling_output_sharing", forbidden_by_invariant)
        self.assertEqual(3, case["scenario"].count("<HERDR_RESULT>"))

    def test_orchestrator_convergence_is_still_evaluated(self):
        referenced = {
            item["invariant"]
            for case in self.suite["cases"]
            for item in case["required"] + case["forbidden"]
        }
        self.assertIn("orchestrator_convergence", referenced)
        self.assertFalse(self.suite["invariants"]["orchestrator_convergence"]["critical"])

    def case(self, case_id):
        return next(case for case in self.suite["cases"] if case["id"] == case_id)

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
