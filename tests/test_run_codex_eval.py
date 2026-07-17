import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "evals" / "trigger" / "run_codex_eval.py"
SPEC = importlib.util.spec_from_file_location("run_codex_eval", SCRIPT)
run_codex_eval = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_codex_eval)


class RunCodexEvalTest(unittest.TestCase):
    def test_build_prompt_includes_only_routing_context(self):
        prompt = run_codex_eval.build_prompt("writing-ja", "日本語本文を推敲する", ["本文を短くして"])

        self.assertIn("Candidate skill name: writing-ja", prompt)
        self.assertIn("Candidate skill description: 日本語本文を推敲する", prompt)
        self.assertIn("User requests, in order:\n1. 本文を短くして", prompt)
        self.assertIn("Do not perform any request", prompt)

    def test_response_schema_requires_one_decision_per_query(self):
        schema = run_codex_eval.response_schema(2)

        self.assertEqual(2, schema["properties"]["decisions"]["minItems"])
        self.assertEqual(2, schema["properties"]["decisions"]["maxItems"])

    def test_split_indices_preserves_the_trigger_balance(self):
        eval_set = [{"should_trigger": True}] * 10 + [{"should_trigger": False}] * 10

        train_indices, test_indices = run_codex_eval.split_indices(eval_set, 0.4)

        self.assertEqual(12, len(train_indices))
        self.assertEqual(8, len(test_indices))
        self.assertEqual(4, sum(eval_set[index]["should_trigger"] for index in test_indices))

    def test_summarize_uses_the_trigger_threshold(self):
        item = {"query": "本文を推敲して", "should_trigger": True}
        result = run_codex_eval.summarize(
            item,
            [{"run": 1, "triggered": True, "error": None}, {"run": 2, "triggered": False, "error": None}],
            0.5,
        )

        self.assertEqual(1.0 / 2.0, result["trigger_rate"])
        self.assertTrue(result["selected"])
        self.assertTrue(result["pass"])

    def test_reads_a_multiline_description(self):
        skill_dir = Path(__file__).parents[1] / "skills" / "blog-writing-guide-ja"

        name, description = run_codex_eval.read_skill_metadata(skill_dir)

        self.assertEqual("blog-writing-guide-ja", name)
        self.assertNotEqual(">", description)
        self.assertIn("日本語の技術ブログ記事全体", description)
