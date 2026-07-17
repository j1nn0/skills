import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class SkillMetadataTest(unittest.TestCase):
    def test_all_skills_have_name_and_description(self):
        for skill_file in ROOT.joinpath("skills").rglob("SKILL.md"):
            with self.subTest(skill_file=skill_file):
                lines = skill_file.read_text(encoding="utf-8").splitlines()
                self.assertEqual("---", lines[0])
                closing_index = lines[1:].index("---") + 1
                front_matter = "\n".join(lines[1:closing_index])
                self.assertIn("name:", front_matter)
                self.assertIn("description:", front_matter)
