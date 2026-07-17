#!/usr/bin/env python3
"""日本語技術文の定型表現と読みづらさの候補を検出する。

ファイルを渡すか、標準入力を表す - を渡す。front matter、引用、fenced code block は検査しない。
結果は文脈を見て判断する WARN であり、exit 0 を返す。
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


PATTERNS = (
    ("内容のない記事予告", re.compile(r"本記事では.{0,80}(?:解説|紹介|説明)します")),
    ("根拠のない結論の強調", re.compile(r"(?:と言えるでしょう|といえるでしょう)")),
    ("一般論から始める導入", re.compile(r"近年、.{0,80}注目されています")),
    ("抽象的な宣伝語", re.compile(r"(?:業界最高水準|最先端|ベストインクラス|シームレス(?:に連携)?|エンパワー|レバレッジ)")),
    ("根拠を要する形容詞", re.compile(r"(?:堅牢な|柔軟な)")),
    ("埋め草の前置き", re.compile(r"(?:前置きが長くなりましたが|ここで注意したいのは|言うまでもなく)")),
    ("コード直後の締め", re.compile(r"これだけ。\s*以上。")),
    ("em ダッシュ", re.compile(r"—")),
    ("太字による強調", re.compile(r"\*\*[^*]+\*\*")),
)
LINE_END_COLON_RE = re.compile(r"[:：]\s*$")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+] |\d+[.)] )")
SENTENCE_END_RE = re.compile(r"(?:した|です|ます|だった|である)[。！？]")
CONNECTIVE_RE = re.compile(r"(?:さらに|また|加えて)")


@dataclass(frozen=True)
class Candidate:
    line: int
    reason: str
    excerpt: str


def prose_lines(text):
    """対象外の行を空文字に置き換え、元の行番号を保つ。"""
    lines = text.splitlines()
    if lines and lines[0].strip() in ("---", "+++"):
        delimiter = lines[0].strip()
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == delimiter:
                lines[: index + 1] = [""] * (index + 1)
                break

    in_code_block = False
    for index, line in enumerate(lines):
        if re.match(r"^\s*(?:```|~~~)", line):
            lines[index] = ""
            in_code_block = not in_code_block
        elif in_code_block or re.match(r"^\s*>", line):
            lines[index] = ""
        else:
            lines[index] = re.sub(r"`[^`]*`", "", line)
    return lines


def candidates_for_patterns(lines):
    text = "\n".join(lines)
    candidates = []
    for label, pattern in PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            candidates.append(Candidate(line, label, match.group(0).replace("\n", " ")))
    for index, line in enumerate(lines, start=1):
        if line.strip() and LINE_END_COLON_RE.search(line):
            candidates.append(Candidate(index, "行末のコロン", line.strip()))
    return candidates


def long_paragraph_candidates(lines, max_paragraph_chars):
    candidates = []
    paragraph = []
    start_line = 0

    def flush():
        if not paragraph:
            return
        text = "".join(paragraph)
        length = len(re.sub(r"\s", "", text))
        if length > max_paragraph_chars:
            candidates.append(Candidate(start_line, f"{max_paragraph_chars}字を超える段落", f"{length}字"))

    for index, line in enumerate(lines + [""], start=1):
        is_paragraph_text = line.strip() and not line.startswith("#") and not LIST_ITEM_RE.match(line)
        if is_paragraph_text:
            if not paragraph:
                start_line = index
            paragraph.append(line)
            continue
        flush()
        paragraph = []
        start_line = 0
    return candidates


def list_run_candidates(lines, max_consecutive_list_items):
    candidates = []
    run_start = 0
    run_length = 0
    for index, line in enumerate(lines + [""], start=1):
        if LIST_ITEM_RE.match(line):
            if not run_length:
                run_start = index
            run_length += 1
            continue
        if run_length > max_consecutive_list_items:
            candidates.append(Candidate(run_start, f"{max_consecutive_list_items}項目を超える連続した箇条書き", f"{run_length}項目"))
        run_start = 0
        run_length = 0
    return candidates


def repeated_ending_candidates(lines):
    candidates = []
    for index in range(len(lines) - 2):
        endings = []
        for line in lines[index : index + 3]:
            match = SENTENCE_END_RE.search(line.strip())
            endings.append(match.group(0) if match and match.end() == len(line.strip()) else None)
        if endings[0] and endings[0] == endings[1] == endings[2]:
            candidates.append(Candidate(index + 1, "同じ語尾が3文連続", endings[0]))
    return candidates


def connective_density_candidates(lines, max_per_400_chars):
    text = "\n".join(lines)
    characters = len(re.sub(r"\s", "", text))
    count = len(CONNECTIVE_RE.findall(text))
    allowed = max_per_400_chars * max(1, (characters + 399) // 400)
    if count <= allowed:
        return []
    first_match = CONNECTIVE_RE.search(text)
    line = text.count("\n", 0, first_match.start()) + 1
    return [Candidate(line, "接続語の密度が高い", f"{characters}字中 {count}回（目安: {allowed}回以下）")]


def find_candidates(text, max_paragraph_chars=240, max_consecutive_list_items=3, max_connectives_per_400_chars=2):
    lines = prose_lines(text)
    candidates = candidates_for_patterns(lines)
    candidates.extend(long_paragraph_candidates(lines, max_paragraph_chars))
    candidates.extend(list_run_candidates(lines, max_consecutive_list_items))
    candidates.extend(repeated_ending_candidates(lines))
    candidates.extend(connective_density_candidates(lines, max_connectives_per_400_chars))
    return sorted(candidates, key=lambda candidate: (candidate.line, candidate.reason, candidate.excerpt))


def read_target(target):
    if target == "-":
        return "標準入力", sys.stdin.read()
    path = Path(target)
    return str(path), path.read_text(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="+", help="検査する UTF-8 テキストファイル。- は標準入力")
    parser.add_argument("--max-paragraph-chars", type=int, default=240, help="段落の文字数の目安 (既定: 240)")
    parser.add_argument("--max-consecutive-list-items", type=int, default=3, help="連続する箇条書き項目数の目安 (既定: 3)")
    parser.add_argument("--max-connectives-per-400-chars", type=int, default=2, help="接続語の400字あたりの目安 (既定: 2)")
    args = parser.parse_args()
    if min(args.max_paragraph_chars, args.max_consecutive_list_items, args.max_connectives_per_400_chars) < 0:
        parser.error("閾値は 0 以上にする")
    for target in args.targets:
        try:
            label, text = read_target(target)
        except OSError as error:
            print(f"ERROR  {target}: 読み込めない: {error}", file=sys.stderr)
            return 2
        for candidate in find_candidates(
            text,
            args.max_paragraph_chars,
            args.max_consecutive_list_items,
            args.max_connectives_per_400_chars,
        ):
            print(f"WARN  {label}:{candidate.line}: {candidate.reason}: {candidate.excerpt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
