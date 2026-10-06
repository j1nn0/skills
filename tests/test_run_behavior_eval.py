import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "evals" / "behavior" / "run_behavior_eval.py"
SPEC = importlib.util.spec_from_file_location("run_behavior_eval", SCRIPT)
run_behavior_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_behavior_eval)


def synthetic_suite():
    return {
        "skill": "synthetic-skill",
        "context": "You are an agent deciding the next step.",
        "invariants": {
            "correct_route": {
                "axis": "routing",
                "critical": True,
                "description": "Choose an appropriate route.",
            },
            "handoff_shape": {
                "axis": "role_boundary",
                "critical": True,
                "description": "Match handoff count to the route.",
            },
            "required_behavior": {
                "axis": "context_discipline",
                "critical": False,
                "description": "Preserve an important behavior.",
            },
            "marker_rule": {
                "axis": "safety_escalation",
                "critical": True,
                "description": "Keep restricted text out of handoffs.",
            },
        },
        "cases": [
            {
                "id": "synthetic-case",
                "title": "A synthetic decision",
                "scenario": "Review the proposed change and choose the next step.",
                "environment": ["The working tree is clean."],
                "expected_routes": ["explorer"],
                "required": [
                    {
                        "text": "Include the private expectation phrase.",
                        "invariant": "required_behavior",
                    }
                ],
                "forbidden": [
                    {
                        "text": "Never expose the forbidden expectation phrase.",
                        "invariant": "marker_rule",
                    }
                ],
                "handoff_must_not_contain": [
                    {"marker": "CASE-SENSITIVE-MARKER", "invariant": "marker_rule"}
                ],
            }
        ],
    }


def response_case_fixture():
    return {
        "id": "synthetic-response",
        "title": "A synthetic response",
        "evaluation_mode": "response",
        "scenario": "Summarize the collected evidence for the user.",
        "environment": [],
        "required": [
            {"text": "Include the private response expectation.", "invariant": "required_behavior"}
        ],
        "forbidden": [],
    }


def decision(route="explorer", handoffs=None):
    return {
        "route": route,
        "rationale": "A focused investigation will reduce uncertainty.",
        "handoffs": handoffs if handoffs is not None else ["Inspect the change and report findings."],
        "user_message": "",
        "next_actions": ["Review the report."],
    }


class RunBehaviorEvalTest(unittest.TestCase):
    def test_valid_synthetic_suite_has_no_validation_errors(self):
        self.assertEqual([], run_behavior_eval.validate_suite(synthetic_suite()))

    def test_loader_raises_value_error_with_all_suite_errors(self):
        suite = synthetic_suite()
        del suite["context"]
        suite["cases"] = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            suite_path = Path(temporary_directory) / "suite.json"
            suite_path.write_text(json.dumps(suite), encoding="utf-8")

            with self.assertRaises(ValueError) as error:
                run_behavior_eval.load_suite(suite_path)

        self.assertIn("missing required top-level key: context", str(error.exception))
        self.assertIn("cases must be non-empty", str(error.exception))

    def test_case_selection_rejects_unknown_ids(self):
        with self.assertRaisesRegex(ValueError, "unknown case id.*missing-case"):
            run_behavior_eval.select_cases(synthetic_suite(), "missing-case")
        with self.assertRaisesRegex(ValueError, "must contain at least one"):
            run_behavior_eval.select_cases(synthetic_suite(), "")

    def test_validation_reports_missing_key(self):
        suite = synthetic_suite()
        del suite["context"]

        self.assertIn(
            "missing required top-level key: context",
            run_behavior_eval.validate_suite(suite),
        )

    def test_validation_reports_duplicate_case_id(self):
        suite = synthetic_suite()
        suite["cases"].append(copy.deepcopy(suite["cases"][0]))

        self.assertIn("duplicate case id: synthetic-case", run_behavior_eval.validate_suite(suite))

    def test_validation_reports_unknown_route(self):
        suite = synthetic_suite()
        suite["cases"][0]["expected_routes"] = ["unknown-route"]

        self.assertIn(
            "case 'synthetic-case' expected_routes contains an unknown route",
            run_behavior_eval.validate_suite(suite),
        )

    def test_validation_reports_unknown_invariant(self):
        suite = synthetic_suite()
        suite["cases"][0]["required"][0]["invariant"] = "missing-invariant"

        self.assertIn(
            "case 'synthetic-case' required[1] references unknown invariant: missing-invariant",
            run_behavior_eval.validate_suite(suite),
        )

    def test_validation_rejects_cases_without_expectations(self):
        suite = synthetic_suite()
        suite["cases"][0]["required"] = []
        suite["cases"][0]["forbidden"] = []

        self.assertIn(
            "case 'synthetic-case' must define at least one required or forbidden expectation",
            run_behavior_eval.validate_suite(suite),
        )

    def test_validation_reports_bad_axis(self):
        suite = synthetic_suite()
        suite["invariants"]["correct_route"]["axis"] = "quality"

        self.assertIn(
            "invariant 'correct_route' has an invalid axis",
            run_behavior_eval.validate_suite(suite),
        )

    def test_decision_prompt_contains_skill_and_scenario_but_not_expectations(self):
        suite = synthetic_suite()
        case = suite["cases"][0]
        skill_text = "# Synthetic skill\nAlways inspect before deciding."

        prompt = run_behavior_eval.build_decision_prompt(
            suite["context"], skill_text, "synthetic-skill", case
        )

        self.assertIn(skill_text, prompt)
        self.assertIn(case["scenario"], prompt)
        self.assertIn("The working tree is clean.", prompt)
        self.assertNotIn("private expectation phrase", prompt)
        self.assertNotIn("forbidden expectation phrase", prompt)
        self.assertNotIn("CASE-SENSITIVE-MARKER", prompt)
        self.assertIn("do not start agents", prompt)
        self.assertIn("skills/synthetic-skill/references/", prompt)

    def test_decision_schema_is_strict_and_has_route_enum(self):
        schema = run_behavior_eval.decision_schema()

        self.assertEqual(list(run_behavior_eval.ROUTES), schema["properties"]["route"]["enum"])
        self.assertEqual(
            ["route", "rationale", "handoffs", "user_message", "next_actions"],
            schema["required"],
        )
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(3, schema["properties"]["handoffs"]["maxItems"])

    def test_route_mismatch_fails_deterministic_route_check(self):
        case = synthetic_suite()["cases"][0]

        checks = run_behavior_eval.deterministic_checks(case, decision(route="complete", handoffs=[]))

        self.assertFalse(checks[0]["passed"])
        self.assertEqual("correct_route", checks[0]["invariant"])
        self.assertEqual("route", checks[0]["name"])

    def test_handoff_count_rules_cover_every_route(self):
        cases = [
            ("direct", 0, True),
            ("direct", 1, False),
            ("explorer", 1, True),
            ("explorer", 0, False),
            ("parallel_explorers", 2, True),
            ("parallel_explorers", 3, True),
            ("parallel_explorers", 1, False),
            ("fixer", 1, True),
            ("fixer", 2, False),
            ("reassess", 0, True),
            ("reassess", 1, False),
            ("escalate", 0, True),
            ("escalate", 1, False),
            ("complete", 0, True),
            ("complete", 1, False),
        ]
        case = synthetic_suite()["cases"][0]

        for route, handoff_count, expected in cases:
            with self.subTest(route=route, handoff_count=handoff_count):
                checks = run_behavior_eval.deterministic_checks(
                    case, decision(route=route, handoffs=["task"] * handoff_count)
                )
                self.assertEqual(expected, checks[1]["passed"])
                self.assertEqual("handoff_shape", checks[1]["invariant"])

    def test_marker_check_is_case_insensitive(self):
        case = synthetic_suite()["cases"][0]

        checks = run_behavior_eval.deterministic_checks(
            case,
            decision(handoffs=["Please avoid the case-sensitive-marker in this handoff."]),
        )

        self.assertFalse(checks[2]["passed"])
        self.assertEqual("marker_rule", checks[2]["invariant"])

    def test_grader_output_validation_rejects_missing_and_extra_ids(self):
        expectations = run_behavior_eval.decision_expectations(synthetic_suite()["cases"][0])
        missing = {"required": [{"id": "required-1", "satisfied": True, "evidence": "quoted"}], "forbidden": []}
        extra = {
            "required": [{"id": "required-1", "satisfied": True, "evidence": "quoted"}],
            "forbidden": [
                {"id": "forbidden-1", "violated": False, "evidence": "quoted"},
                {"id": "forbidden-2", "violated": False, "evidence": "none"},
            ],
        }

        with self.assertRaisesRegex(ValueError, "ids mismatch"):
            run_behavior_eval.validate_grader_output(missing, expectations)
        with self.assertRaisesRegex(ValueError, "ids mismatch"):
            run_behavior_eval.validate_grader_output(extra, expectations)

    def grade_synthetic(self, satisfied, violated):
        suite = synthetic_suite()
        case = suite["cases"][0]
        skill_path = Path(__file__).parents[1] / "skills" / "agent-orchestration"

        def fake_codex(prompt, schema, model, effort, cwd, timeout):
            if "required" not in schema["properties"]:
                return decision()
            return {
                "required": [{"id": "required-1", "satisfied": satisfied, "evidence": "quoted"}],
                "forbidden": [{"id": "forbidden-1", "violated": violated, "evidence": "quoted"}],
            }

        run = run_behavior_eval.run_case_once(
            case, suite["invariants"], skill_path, suite["context"], "m", "low", "g", "low", 15,
            codex_runner=fake_codex,
        )
        case_result = run_behavior_eval.build_case_result(case, [run])
        return run, run_behavior_eval.summarize_results([case_result], suite["invariants"])

    def test_required_polarity_maps_satisfied_to_final_pass(self):
        run, _ = self.grade_synthetic(satisfied=True, violated=False)
        self.assertTrue(run["expectations"][0]["passed"])
        self.assertEqual({"satisfied": True}, run["expectations"][0]["judgment"])

        run, _ = self.grade_synthetic(satisfied=False, violated=False)
        self.assertFalse(run["expectations"][0]["passed"])

    def test_forbidden_polarity_maps_absent_behavior_to_final_pass(self):
        run, summary = self.grade_synthetic(satisfied=True, violated=False)
        forbidden = run["expectations"][1]
        self.assertTrue(forbidden["passed"])
        self.assertEqual({"violated": False}, forbidden["judgment"])
        self.assertTrue(run["pass"])
        self.assertEqual({}, summary["critical_violations"])

        run, summary = self.grade_synthetic(satisfied=True, violated=True)
        self.assertFalse(run["expectations"][1]["passed"])
        self.assertFalse(run["pass"])
        self.assertEqual({"marker_rule": 1}, summary["critical_violations"])

    def test_grader_schema_and_prompt_separate_required_and_forbidden_polarity(self):
        case = synthetic_suite()["cases"][0]
        expectations = run_behavior_eval.decision_expectations(case)
        schema = run_behavior_eval.grader_schema(expectations)
        prompt = run_behavior_eval.build_grader_prompt(case, decision())

        self.assertEqual(["required", "forbidden"], schema["required"])
        self.assertFalse(schema["additionalProperties"])
        required_item = schema["properties"]["required"]["items"]
        forbidden_item = schema["properties"]["forbidden"]["items"]
        self.assertIn("satisfied", required_item["required"])
        self.assertNotIn("passed", required_item["properties"])
        self.assertIn("violated", forbidden_item["required"])
        self.assertNotIn("passed", forbidden_item["properties"])
        self.assertFalse(forbidden_item["additionalProperties"])
        self.assertEqual(["forbidden-1"], forbidden_item["properties"]["id"]["enum"])
        self.assertIn("forbidden behavior absent => violated = false", prompt)
        self.assertIn("## Forbidden expectations\nforbidden-1:", prompt)

    def test_grader_output_rejects_the_old_shared_passed_field(self):
        expectations = run_behavior_eval.decision_expectations(synthetic_suite()["cases"][0])
        old_shape = {
            "required": [{"id": "required-1", "passed": True, "evidence": "quoted"}],
            "forbidden": [{"id": "forbidden-1", "passed": True, "evidence": "quoted"}],
        }

        with self.assertRaisesRegex(ValueError, "exactly id, satisfied, and evidence"):
            run_behavior_eval.validate_grader_output(old_shape, expectations)

    def test_case_and_summary_aggregation_includes_errors_and_critical_violations(self):
        case = synthetic_suite()["cases"][0]
        passed_run = {
            "run": 1,
            "checks": [{"name": "route", "passed": True, "invariant": "correct_route"}],
            "expectations": [
                {"id": "required-1", "passed": True, "invariant": "required_behavior"}
            ],
            "pass": True,
            "error": None,
        }
        failed_run = {
            "run": 2,
            "checks": [{"name": "route", "passed": False, "invariant": "correct_route"}],
            "expectations": [
                {"id": "forbidden-1", "passed": False, "invariant": "marker_rule"}
            ],
            "pass": False,
            "error": None,
        }
        errored_run = {
            "run": 3,
            "checks": [{"name": "handoff_shape", "passed": False, "invariant": "handoff_shape"}],
            "expectations": [],
            "pass": False,
            "error": "grader call failed",
        }
        case_result = run_behavior_eval.build_case_result(
            case, [errored_run, passed_run, failed_run]
        )
        second_case = {"id": "other-case", "title": "Another case"}
        passing_case_result = run_behavior_eval.build_case_result(
            second_case,
            [
                {
                    "run": 1,
                    "checks": [],
                    "expectations": [],
                    "pass": True,
                    "error": None,
                }
            ],
        )

        summary = run_behavior_eval.summarize_results(
            [case_result, passing_case_result], synthetic_suite()["invariants"]
        )

        self.assertEqual(1 / 3, case_result["pass_rate"])
        self.assertFalse(case_result["pass"])
        self.assertEqual(
            {"passed": 2, "failed": 1, "errored": 1, "total": 4},
            {key: summary[key] for key in ("passed", "failed", "errored", "total")},
        )
        self.assertEqual({"synthetic-case": False, "other-case": True}, summary["by_case"])
        self.assertEqual(1, summary["critical_violations"]["correct_route"])
        self.assertEqual(1, summary["critical_violations"]["marker_rule"])
        self.assertEqual(1, summary["critical_violations"]["handoff_shape"])
        self.assertEqual(1, summary["by_axis"]["routing"]["failed"])
        self.assertEqual(1, summary["by_axis"]["safety_escalation"]["failed"])

    def test_run_case_once_keeps_skill_workspace_separate_and_grades(self):
        suite = synthetic_suite()
        case = suite["cases"][0]
        skill_path = Path(__file__).parents[1] / "skills" / "agent-orchestration"
        calls = []

        def fake_codex(prompt, schema, model, effort, cwd, timeout):
            calls.append((prompt, schema, Path(cwd), model, effort, timeout))
            if len(calls) == 1:
                copied_skill = Path(cwd) / "skills" / skill_path.name
                self.assertTrue((copied_skill / "SKILL.md").is_file())
                self.assertFalse((copied_skill / "__pycache__").exists())
                return decision()
            return {
                "required": [{"id": "required-1", "satisfied": True, "evidence": "A quoted rationale."}],
                "forbidden": [{"id": "forbidden-1", "violated": False, "evidence": "Not present."}],
            }

        result = run_behavior_eval.run_case_once(
            case,
            suite["invariants"],
            skill_path,
            suite["context"],
            "test-model",
            "low",
            "grader-model",
            "medium",
            15,
            codex_runner=fake_codex,
        )

        self.assertTrue(result["pass"])
        self.assertEqual(2, len(calls))
        self.assertIn(suite["context"], calls[0][0])
        self.assertNotIn("private expectation phrase", calls[0][0])
        self.assertIn("private expectation phrase", calls[1][0])
        self.assertNotEqual(calls[0][2], calls[1][2])
        self.assertEqual("correct_route", result["checks"][0]["invariant"])
        self.assertEqual("required_behavior", result["expectations"][0]["invariant"])
        self.assertEqual("context_discipline", result["expectations"][0]["axis"])

    def test_evaluation_mode_defaults_to_decision_and_scopes_decision_context(self):
        suite = synthetic_suite()
        suite["decision_context"] = "Choose one next route."
        decision_case = suite["cases"][0]
        response_case = response_case_fixture()

        self.assertEqual("decision", run_behavior_eval.evaluation_mode(decision_case))
        self.assertEqual("response", run_behavior_eval.evaluation_mode(response_case))
        self.assertIn("Choose one next route.", run_behavior_eval.prompt_context(suite, decision_case))
        self.assertNotIn("Choose one next route.", run_behavior_eval.prompt_context(suite, response_case))

    def test_validation_accepts_response_cases_without_route_fields(self):
        suite = synthetic_suite()
        suite["cases"].append(response_case_fixture())

        self.assertEqual([], run_behavior_eval.validate_suite(suite))

    def test_validation_rejects_unknown_modes_and_route_fields_in_response_mode(self):
        suite = synthetic_suite()
        unknown_mode = copy.deepcopy(suite["cases"][0])
        unknown_mode["id"] = "unknown-mode"
        unknown_mode["evaluation_mode"] = "execute"
        routed_response = response_case_fixture()
        routed_response["expected_routes"] = ["reassess"]
        suite["cases"].extend([unknown_mode, routed_response])

        errors = run_behavior_eval.validate_suite(suite)

        self.assertTrue(any("evaluation_mode must be one of" in error for error in errors))
        self.assertTrue(any("expected_routes is not used in response mode" in error for error in errors))

    def test_response_schema_is_strict_and_separate_from_decision_schema(self):
        schema = run_behavior_eval.response_schema()

        self.assertEqual(["response"], schema["required"])
        self.assertFalse(schema["additionalProperties"])
        self.assertNotIn("route", schema["properties"])
        self.assertIn("route", run_behavior_eval.decision_schema()["properties"])

    def test_prompts_state_their_mode_contract(self):
        decision_case = synthetic_suite()["cases"][0]
        response_case = response_case_fixture()

        decision_prompt = run_behavior_eval.build_model_prompt("Context.", "Skill text.", "demo", decision_case)
        response_prompt = run_behavior_eval.build_model_prompt("Context.", "Skill text.", "demo", response_case)

        self.assertIn("decision-only evaluation", decision_prompt)
        self.assertNotIn("response evaluation", decision_prompt)
        self.assertIn("response evaluation", response_prompt)
        self.assertIn("actual non-mutating answer or synthesis", response_prompt)
        self.assertIn("completed answer or synthesis", response_prompt)
        self.assertNotIn("decision-only", response_prompt)
        self.assertNotIn("execute the task", response_prompt)
        self.assertIn("Do not start agents, run commands, modify files", response_prompt)
        self.assertNotIn("private response expectation", response_prompt)

    def test_validate_response_rejects_extra_keys_and_empty_text(self):
        self.assertEqual({"response": "Synthesis."}, run_behavior_eval.validate_response({"response": "Synthesis."}))
        for payload in ({"response": "Synthesis.", "route": "reassess"}, {"response": "  "}, {"text": "x"}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    run_behavior_eval.validate_response(payload)

    def test_run_case_once_grades_response_text_without_route_checks(self):
        suite = synthetic_suite()
        case = response_case_fixture()
        skill_path = Path(__file__).parents[1] / "skills" / "agent-orchestration"
        calls = []

        def fake_codex(prompt, schema, model, effort, cwd, timeout):
            calls.append((prompt, schema))
            if len(calls) == 1:
                return {"response": "The documentation shows X; the code shows Y."}
            return {
                "required": [{"id": "required-1", "satisfied": True, "evidence": "X and Y."}],
                "forbidden": [],
            }

        result = run_behavior_eval.run_case_once(
            case,
            suite["invariants"],
            skill_path,
            suite["context"],
            "test-model",
            "low",
            "grader-model",
            "medium",
            15,
            codex_runner=fake_codex,
        )

        self.assertTrue(result["pass"])
        self.assertEqual([], result["checks"])
        self.assertIsNone(result["decision"])
        self.assertEqual("The documentation shows X; the code shows Y.", result["response"])
        self.assertEqual(run_behavior_eval.response_schema(), calls[0][1])
        self.assertIn("## Response\nThe documentation shows X; the code shows Y.", calls[1][0])
        self.assertNotIn("Decision JSON", calls[1][0])

    def test_codex_environment_preserves_configured_codex_home(self):
        base_environment = {
            "HOME": "/real/user-home",
            "CODEX_HOME": "/auth/codex-home",
            "PRESERVED_SETTING": "value",
        }
        with tempfile.TemporaryDirectory() as temporary_home:
            environment = run_behavior_eval.codex_environment(base_environment, temporary_home)

        self.assertEqual(str(Path(temporary_home).resolve()), environment["HOME"])
        self.assertEqual("/auth/codex-home", environment["CODEX_HOME"])
        self.assertEqual("value", environment["PRESERVED_SETTING"])
        self.assertEqual("/real/user-home", base_environment["HOME"])

    def test_codex_environment_defaults_codex_home_from_original_home(self):
        base_environment = {"HOME": "/real/user-home", "PRESERVED_SETTING": "value"}
        expected_codex_home = str((Path("/real/user-home") / ".codex").resolve())
        with tempfile.TemporaryDirectory() as temporary_home:
            environment = run_behavior_eval.codex_environment(base_environment, temporary_home)

        self.assertEqual(str(Path(temporary_home).resolve()), environment["HOME"])
        self.assertEqual(expected_codex_home, environment["CODEX_HOME"])
        self.assertEqual("/real/user-home", base_environment["HOME"])

    def test_cli_rejects_non_positive_run_worker_and_timeout_values(self):
        invalid_arguments = [
            ["--runs", "0"],
            ["--max-workers", "0"],
            ["--timeout", "0.5"],
        ]
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises(SystemExit) as error:
                    run_behavior_eval.parse_args(arguments)
                self.assertEqual(2, error.exception.code)


if __name__ == "__main__":
    unittest.main()
