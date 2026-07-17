import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "skills" / "writing-ja" / "scripts" / "check_style.py"
SPEC = importlib.util.spec_from_file_location("check_style", SCRIPT)
check_style = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_style)


class CheckStyleTest(unittest.TestCase):
    def reasons(self, text):
        return [candidate.reason for candidate in check_style.find_candidates(text)]

    def test_excludes_front_matter_quotes_and_fenced_code(self):
        text = "---\ntitle: **対象外**\n---\n> **引用**：\n```md\n**コード**：\n```\n本文は**強調**する。\n"

        candidates = check_style.find_candidates(text)

        self.assertEqual(["太字による強調"], [candidate.reason for candidate in candidates])
        self.assertEqual(8, candidates[0].line)

    def test_reports_structure_and_repetition_candidates(self):
        text = (
            "確認した。\n保存した。\n公開した。\n\n"
            + "あ" * 241
            + "\n\n- one\n- two\n- three\n- four\n\nさらに、確認する。また、保存する。加えて、公開する。\n"
        )

        reasons = self.reasons(text)

        self.assertIn("同じ語尾が3文連続", reasons)
        self.assertIn("240字を超える段落", reasons)
        self.assertIn("3項目を超える連続した箇条書き", reasons)
        self.assertIn("接続語の密度が高い", reasons)
