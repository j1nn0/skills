import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL_DIR = ROOT / "skills" / "agent-orchestration"


def flat(text):
    return " ".join(text.split())


class TraceSkillTextTest(unittest.TestCase):
    def setUp(self):
        self.skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.trace = flat(self.skill.split("\n### Trace\n", 1)[1].split("\n## ", 1)[0])

    def test_trace_is_recorded_only_at_settled_boundaries(self):
        self.assertIn("`scripts/tracectl record`", self.trace)
        self.assertIn("only at these settled boundaries", self.trace)
        for boundary in ("final disposition", "recovery route entered", "`parallel_validate` verdict"):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, self.trace)
        self.assertIn("`transport_fallback`", self.trace)

    def test_trace_is_best_effort_and_content_free(self):
        self.assertIn("best-effort", self.trace)
        self.assertIn("never changes the task flow", self.trace)
        self.assertIn("enums only, so never pass task content", self.trace)

    def test_trace_rule_lives_in_one_place(self):
        self.assertEqual(1, self.skill.count("tracectl"))
        for heading in ("## Explorer", "## Fixer", "## Waiting"):
            with self.subTest(section=heading):
                text = self.skill.split(f"\n{heading}\n", 1)[1].split("\n## ", 1)[0]
                self.assertNotIn("tracectl", text)

    def test_trace_is_separate_from_session_configuration(self):
        sessionctl = (SKILL_DIR / "scripts" / "sessionctl").read_text(encoding="utf-8")
        self.assertNotIn("trace", sessionctl.lower())
        readme = flat((SKILL_DIR / "README.md").read_text(encoding="utf-8"))
        self.assertIn("never prompts, results, or task content", readme)

    def test_behavior_eval_does_not_grade_trace_calls(self):
        suite = (ROOT / "evals" / "behavior" / "agent-orchestration.json").read_text(encoding="utf-8")
        self.assertNotIn("tracectl", suite)
        self.assertEqual(18, len(json.loads(suite)["cases"]))


if __name__ == "__main__":
    unittest.main()
