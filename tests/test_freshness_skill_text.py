import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL_DIR = ROOT / "skills" / "agent-orchestration"


def section(text, heading):
    return text.split(f"\n{heading}\n", 1)[1].split("\n## ", 1)[0].split("\n### ", 1)[0]


def flat(text):
    return " ".join(text.split())


class FreshnessSkillTextTest(unittest.TestCase):
    def setUp(self):
        self.skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.waiting = flat(section(self.skill, "## Waiting"))

    def test_baseline_is_taken_from_a_ready_agent_before_prompting(self):
        before_prompt = self.waiting.split(" 2. ", 1)[0]
        self.assertIn("Before prompting, run `herdr agent get <name>`", before_prompt)
        self.assertIn("prompt only an `idle` or `done` agent", before_prompt)
        self.assertIn("baseline", before_prompt)
        self.assertIn("`state_change_seq`", before_prompt)
        self.assertIn("`completion_seq`", before_prompt)

    def test_sequences_are_rechecked_after_the_wait(self):
        after_wait = self.waiting.split(" 2. ", 1)[1]
        self.assertIn("After the wait returns, whatever it returned", after_wait)
        self.assertIn("`scripts/freshness_validate`", after_wait)
        self.assertIn("`completion_advanced`", after_wait)
        self.assertIn("even if `working` was never observed", after_wait)

    def test_prompt_wait_alone_is_not_freshness_proof(self):
        self.assertIn("tells you when to look, not which prompt produced", self.waiting)
        self.assertIn("not the text", self.waiting)

    def test_non_completion_verdicts_are_not_read_as_results(self):
        for reason in ("`blocked`", "`no_progress`", "`progress_observed`", "`sequence_regressed`"):
            with self.subTest(reason=reason):
                self.assertIn(reason, self.waiting)
        self.assertIn("go to `recovery.md`", self.waiting)

    def test_freshness_is_separate_from_structure(self):
        self.assertIn("Freshness and `result_validate` structure are separate checks", self.waiting)
        reading = flat(section(self.skill, "### Reading results"))
        self.assertIn('"Waiting" freshness check', reading)
        self.assertNotIn("state_change_seq", reading)
        validator = (SKILL_DIR / "scripts" / "result_validate").read_text(encoding="utf-8")
        for term in ("completion_seq", "state_change_seq", "prompt_id"):
            self.assertNotIn(term, validator)

    def test_baselines_are_not_persisted_and_no_prompt_id_is_invented(self):
        self.assertIn("never persist them in session state", self.waiting)
        self.assertIn("no prompt or turn id", self.waiting)
        sessionctl = (SKILL_DIR / "scripts" / "sessionctl").read_text(encoding="utf-8")
        for term in ("completion_seq", "state_change_seq", "baseline"):
            self.assertNotIn(term, sessionctl)

    def test_role_sections_do_not_copy_the_freshness_procedure(self):
        for heading in ("## Explorer", "## Fixer"):
            with self.subTest(section=heading):
                text = self.skill.split(f"\n{heading}\n", 1)[1].split("\n## ", 1)[0]
                self.assertNotIn("freshness_validate", text)
                self.assertNotIn("completion_seq", text)

    def test_recovery_and_parallel_reuse_the_shared_check(self):
        recovery = flat((SKILL_DIR / "references" / "recovery.md").read_text(encoding="utf-8"))
        parallel = flat((SKILL_DIR / "references" / "parallel.md").read_text(encoding="utf-8"))
        self.assertIn('"Waiting" freshness check', recovery)
        self.assertIn('"Waiting" freshness check', parallel)
        self.assertNotIn("sequence_regressed", parallel)


if __name__ == "__main__":
    unittest.main()
