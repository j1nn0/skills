#!/usr/bin/env python3
"""日本語技術文の定型表現と読みづらさの候補を検出する。

ファイルを渡すか、標準入力を表す - を渡す。front matter、引用、fenced code block は検査しない。
結果は文脈を見て判断する WARN であり、exit 0 を返す。
太字と行末のコロンは正当な用法が多いため、--strict を付けたときだけ報告する。
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
    (
        "日常語にできる硬い漢語",
        re.compile(
            r"(?:冪等|べき等|担保|齟齬|乖離|峻別|敷衍|惹起|勘案|払拭|凌駕|漸次|具備|枯渇|温存|迂回|意味論|昨今|所以|枚挙)"
        ),
    ),
    (
        "回りくどい言い回し",
        re.compile(
            r"(?:に(?:他|ほか)ならない|と言っても過言では|ということができ|ことが可能|を行(?:う|い|った|わ|え)|という形になる|に関して言えば|ではないだろうか)"
        ),
    ),
    ("コード直後の締め", re.compile(r"これだけ。\s*以上。")),
    ("em ダッシュ", re.compile(r"—")),
)
STRICT_PATTERNS = (("太字による強調", re.compile(r"\*\*[^*]+\*\*")),)
LINE_END_COLON_RE = re.compile(r"[:：]\s*$")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+] |\d+[.)] )")
TABLE_ROW_RE = re.compile(r"^\s*\|")
SENTENCE_RE = re.compile(r"[^。！？]*[。！？]")
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


def candidates_for_patterns(lines, strict):
    text = "\n".join(lines)
    candidates = []
    for label, pattern in PATTERNS + (STRICT_PATTERNS if strict else ()):
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            candidates.append(Candidate(line, label, match.group(0).replace("\n", " ")))
    if strict:
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
        is_paragraph_text = (
            line.strip()
            and not line.startswith("#")
            and not LIST_ITEM_RE.match(line)
            and not TABLE_ROW_RE.match(line)
        )
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


def paragraph_sentences(lines):
    """空行、見出し、表の行で区切った段落ごとに、(行番号, 文) の並びを返す。

    文は行ではなく句点で区切る。1行に複数の文を書く原稿でも、1文ごとに改行する
    原稿でも、同じ単位で語尾を数えるため。
    """
    paragraphs = []
    buffer = []

    def flush():
        if not buffer:
            return
        text = ""
        line_of = []
        for line_number, content in buffer:
            text += content
            line_of.extend([line_number] * len(content))
        sentences = []
        for match in SENTENCE_RE.finditer(text):
            sentence = match.group(0).strip()
            if sentence:
                sentences.append((line_of[match.start()], sentence))
        paragraphs.append(sentences)

    for index, line in enumerate(lines, start=1):
        if not line.strip() or line.startswith("#") or TABLE_ROW_RE.match(line):
            flush()
            buffer = []
            continue
        buffer.append((index, line))
    flush()
    return paragraphs


def repeated_ending_candidates(lines):
    candidates = []
    for sentences in paragraph_sentences(lines):
        run_ending = None
        run_lines = []
        for line_number, sentence in sentences:
            match = SENTENCE_END_RE.search(sentence)
            ending = match.group(0) if match and match.end() == len(sentence) else None
            if ending and ending == run_ending:
                run_lines.append(line_number)
            else:
                run_ending = ending
                run_lines = [line_number] if ending else []
            if len(run_lines) == 3:
                candidates.append(Candidate(run_lines[0], "同じ語尾が3文連続", ending))
                run_ending = None
                run_lines = []
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


def find_candidates(
    text,
    max_paragraph_chars=240,
    max_consecutive_list_items=3,
    max_connectives_per_400_chars=2,
    strict=False,
):
    lines = prose_lines(text)
    candidates = candidates_for_patterns(lines, strict)
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
    parser.add_argument(
        "--strict",
        action="store_true",
        help="太字による強調と行末のコロンも報告する。正当な用法が多く既定では報告しない",
    )
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
            args.strict,
        ):
            print(f"WARN  {label}:{candidate.line}: {candidate.reason}: {candidate.excerpt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
