import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL_PATH = ROOT / "skills" / "agent-orchestration" / "SKILL.md"


def flat(text):
    return " ".join(text.split())


def top_section(text, heading):
    marker = f"\n## {heading}\n"
    start = text.index(marker) + 1
    return text[start:].split("\n## ", 1)[0]


class ContextRoutingTextTest(unittest.TestCase):
    def setUp(self):
        self.skill = SKILL_PATH.read_text(encoding="utf-8")
        marker = "\n## Context routing and unit sizing\n"
        start = self.skill.index(marker) + 1
        end = self.skill.index("\n## ", start + 1)
        self.section = flat(self.skill[start:end]).lower()
        self.outside = self.skill[: start - 1] + self.skill[end:]

    def test_section_keeps_the_three_subsections_in_order(self):
        headings = (
            "### context contract",
            "### a well-sized unit",
            "### progressive handoff",
        )
        positions = [self.section.index(heading) for heading in headings]
        self.assertEqual(sorted(positions), positions)
        self.assertNotIn("### strong split signals", self.section)

    def test_handoff_contract_keeps_its_inputs_and_exclusions(self):
        for concept in (
            "settled state, not reasoning history",
            "role boundary",
            "objective or question",
            "overall objective only when it explains",
            "scope by relevant paths",
            "apis, or interfaces rather than preloading code",
            "current constraints and cross-unit invariants",
            "settled strategy when delegating implementation",
            "validated evidence distilled from investigation history",
            "completion criteria or the required conclusion",
            "conversation transcripts",
            "raw tool or agent output",
            "repeated findings",
            "already-resolved discussion",
            "sibling raw results",
            "detailed instructions for later units",
        ):
            with self.subTest(concept=concept):
                self.assertIn(concept, self.section)
        self.assertEqual(1, self.section.count("settled state, not reasoning history"))

    def test_rejected_alternatives_are_not_reintroduced_as_prohibitions(self):
        for concept in (
            "omit rejected alternatives and findings unrelated to this unit",
            "do not restate them as prohibitions",
            "naming discarded or unrelated items to forbid them still copies them",
            "positive scope",
            "tempting but unsafe path",
            "current constraints still belong in the handoff",
        ):
            with self.subTest(concept=concept):
                self.assertIn(concept, self.section)

    def test_long_handoffs_are_sized_by_working_context(self):
        for concept in (
            "expected working context",
            "not prompt length, file count, or a fixed token threshold",
            "prompt size is only a weak proxy",
            "a long handoff does not automatically mean the unit is too large",
            "apply this contract first",
            "several independent working sets",
        ):
            with self.subTest(concept=concept):
                self.assertIn(concept, self.section)

    def test_unit_properties_include_their_split_signals(self):
        for concept in (
            "one coherent outcome",
            "one cohesive boundary",
            "before delegation, confirm",
            "one immediate problem",
            "even across several files",
            "independent verification",
            "no detailed future dependency",
            "focused working set",
            "split mechanically by number of files",
            "prompt characters",
            "intermediate state that cannot be meaningfully verified",
            "rediscovered immediately",
            "atomically for correctness",
        ):
            with self.subTest(concept=concept):
                self.assertIn(concept, self.section)
        self.assertIn("requested as one task", self.section)

    def test_progressive_handoff_uses_validated_results_and_resets_context(self):
        for concept in (
            "ordered internal plan of independently reviewable units",
            "delegate only the current unit",
            "validated result as input for the next unit",
            "confirm, change",
            "merge, split, or eliminate",
            "context reset mechanism",
        ):
            with self.subTest(concept=concept):
                self.assertIn(concept, self.section)

    def test_workflow_handoffs_and_fixer_still_reference_the_contract(self):
        workflow = flat(top_section(self.outside, "Workflow")).lower()
        handoffs = flat(top_section(self.outside, "Handoffs")).lower()
        fixer = flat(top_section(self.outside, "Fixer")).lower()

        self.assertIn("context routing and unit sizing", workflow)
        self.assertIn("context routing and unit sizing", handoffs)
        self.assertIn("context contract", fixer)


if __name__ == "__main__":
    unittest.main()
