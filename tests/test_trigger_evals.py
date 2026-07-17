import json
import unittest
from pathlib import Path


EVALS = Path(__file__).parents[1] / "evals" / "trigger"


class TriggerEvalTest(unittest.TestCase):
    def test_each_skill_has_a_balanced_trigger_eval_set(self):
        expected_skills = {"writing-ja", "blog-writing-guide-ja", "blog-ops"}
        self.assertEqual(expected_skills, {path.stem for path in EVALS.glob("*.json")})
        for path in EVALS.glob("*.json"):
            with self.subTest(path=path):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(20, len(data))
                self.assertEqual(10, sum(item["should_trigger"] for item in data))
                self.assertEqual(10, sum(not item["should_trigger"] for item in data))
                self.assertTrue(all(isinstance(item["query"], str) and item["query"] for item in data))
