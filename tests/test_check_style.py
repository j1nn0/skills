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

        candidates = check_style.find_candidates(text, strict=True)

        self.assertEqual(["太字による強調"], [candidate.reason for candidate in candidates])
        self.assertEqual(8, candidates[0].line)

    def test_bold_and_line_end_colon_need_strict(self):
        text = "これは**重要**な点だ。\n手順は次のとおり:\n"

        self.assertEqual([], self.reasons(text))
        self.assertEqual(
            ["太字による強調", "行末のコロン"],
            sorted(candidate.reason for candidate in check_style.find_candidates(text, strict=True)),
        )

    def test_reports_hard_words_and_roundabout_phrasing(self):
        text = "destroy()は冪等だ。\n検証を行うことが可能だ。\n`冪等` は対象外。\n"

        candidates = check_style.find_candidates(text)

        self.assertEqual(
            [(1, "日常語にできる硬い漢語"), (2, "回りくどい言い回し"), (2, "回りくどい言い回し")],
            [(candidate.line, candidate.reason) for candidate in candidates],
        )

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

    def test_table_rows_are_not_paragraph_text(self):
        row = "| " + "あ" * 120 + " | " + "い" * 120 + " |\n"
        text = "| 見出し | 内容 |\n| --- | --- |\n" + row

        self.assertEqual([], self.reasons(text))

    def test_counts_repeated_endings_by_sentence_not_by_line(self):
        text = "設定を変更した。ログを確認した。原因を特定した。\n"

        candidates = check_style.find_candidates(text)

        self.assertEqual([(1, "同じ語尾が3文連続", "した。")], [tuple(vars(candidates[0]).values())])

    def test_repeated_endings_reset_at_paragraph_and_heading_breaks(self):
        text = "確認した。保存した。\n\n公開した。\n\n## 見出し\n記録した。\n"

        self.assertEqual([], self.reasons(text))

    def test_repeated_endings_span_lines_within_a_paragraph(self):
        text = "確認した。\n保存した。公開した。\n"

        candidates = check_style.find_candidates(text)

        self.assertEqual([(1, "同じ語尾が3文連続")], [(c.line, c.reason) for c in candidates])
