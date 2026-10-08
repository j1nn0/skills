import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL_DIR = ROOT / "skills" / "agent-orchestration"


def flat(text):
    return " ".join(text.split())


def section(text, heading):
    return text.split(f"\n{heading}\n", 1)[1].split("\n## ", 1)[0].split("\n### ", 1)[0]


class ResultTransportTextTest(unittest.TestCase):
    def setUp(self):
        self.skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.handoffs = flat(section(self.skill, "## Handoffs"))
        self.reading = flat(section(self.skill, "### Reading results"))

    def test_result_block_is_a_concise_transport_summary(self):
        self.assertIn("concise transport summary, not the full report", self.handoffs)
        self.assertIn("only the key evidence or verification review needs", self.handoffs)

    def test_detail_file_is_only_for_detail_that_does_not_fit(self):
        self.assertIn("Only when supporting detail would not fit safely", self.handoffs)
        self.assertIn("cite the path inside an existing field", self.handoffs)
        self.assertIn("this file under `/tmp`, outside the working tree, is its only permitted write", self.handoffs)
        for heading, field in (("## Explorer", "Evidence"), ("## Fixer", "Verification")):
            with self.subTest(section=heading):
                text = flat(self.skill.split(f"\n{heading}\n", 1)[1].split("\n## ", 1)[0])
                self.assertIn("/tmp/<descriptive-name>.md", text)
                self.assertIn(f"cite the path in {field}", text)

    def test_explorer_example_limits_the_transport_write(self):
        explorer = flat(self.skill.split("\n## Explorer\n", 1)[1].split("\n## ", 1)[0])
        self.assertIn("outside the repository and the only file you may write", explorer)
        self.assertIn("read-only investigation", explorer)

    def test_parallel_collection_reuses_the_transport_recovery(self):
        parallel = flat((SKILL_DIR / "references" / "parallel.md").read_text(encoding="utf-8"))
        self.assertIn('"Reading results" in `SKILL.md` rather than re-asking for the same long block', parallel)

    def test_scrolled_away_block_goes_to_a_file_without_reemitting_it_first(self):
        steps = self.reading.split("When the block is missing or truncated:", 1)[1]
        truncation = steps.split("When the block is short", 1)[0]
        self.assertIn("Raise `--lines` once", truncation)
        self.assertIn("Do not ask for the same long block again", truncation)
        self.assertIn("without redoing the work", truncation)
        self.assertIn("save its detailed response to a new temporary Markdown file", truncation)
        self.assertNotIn("re-emit", truncation)

    def test_short_reemit_remains_available_for_non_length_failures(self):
        short = self.reading.split("When the block is short", 1)[1]
        self.assertIn("re-emit only its final result", short)
        self.assertIn("same-unit recovery prompt that re-delivers finished work", short)
        self.assertIn("not new investigation or another Explorer round", short)
        self.assertIn("existing retry bounds", short)
        self.assertIn('"Waiting" freshness check', short)

    def test_extractor_guarantee_leaves_turn_attribution_to_the_orchestrator(self):
        self.assertIn("It proves position and structure, not which turn produced the block", self.reading)
        self.assertIn("Herdr output has no turn boundary", self.reading)
        self.assertIn("not that any block in the scrollback came from it", self.reading)
        self.assertIn("after you confirm it answers the current prompt", self.reading)
        self.assertIn("lost its opening or closing tag", self.reading)

    def test_minimal_example_is_valid_shell_without_placeholders(self):
        example = self.skill.split("\n### Minimal example\n", 1)[1].split("\n### ", 1)[0]
        script = example.split("```bash\n", 1)[1].split("\n```", 1)[0]
        syntax = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True, check=False)
        self.assertEqual(0, syntax.returncode, syntax.stderr)
        unquoted = re.sub(r"'[^']*'", "", re.sub(r"#.*", "", script))
        self.assertNotIn("<", unquoted)
        self.assertIn("scripts/result_extract --role explorer", script)

    def test_result_validate_has_no_size_limit(self):
        import json
        import subprocess
        import sys

        evidence = "\n".join(f"- src/module_{index}.py:{index}" for index in range(20000))
        block = (
            "<HERDR_RESULT>\nConclusion: done\nEvidence:\n"
            f"{evidence}\nImpact: none\nRecommendation: none\n"
            "Confidence: high — direct evidence\n</HERDR_RESULT>"
        )
        completed = subprocess.run(
            [sys.executable, str(SKILL_DIR / "scripts" / "result_validate")],
            input=json.dumps({"role": "explorer", "result": block}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode)
        self.assertTrue(json.loads(completed.stdout)["valid"])


if __name__ == "__main__":
    unittest.main()
