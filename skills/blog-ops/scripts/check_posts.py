#!/usr/bin/env python3
"""Hugo 記事の front matter、本文リンク、画像、タグ規約を検査する。

対象ブログのリポジトリルートで、このスキルディレクトリ内のスクリプトを実行する:
    python3 "$SKILL_DIR/scripts/check_posts.py"

ERROR は修正必須(exit 1)、WARN は判断のうえ対応する。
外部依存なし(PyYAML 不要の簡易 YAML パーサ)。
"""

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote


FILENAME_RE = re.compile(r"^[a-z0-9-]+\.md$")
DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:[Tt ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)
IMAGE_RE = re.compile(r"!\[[^\]]*]\((/images/[^\s)#]+)(?:\s+[^)]*)?\)")
POST_LINK_RE = re.compile(r"(?<!!)\[[^\]]*]\(/posts/([^/?#)]+)(?:/|[?#)])")


@dataclass(frozen=True)
class Settings:
    min_tags: int = 3
    max_tags: int = 5
    tag_pattern: str = r"^[a-z0-9_]+$"


def parse_yaml_front_matter(text):
    """簡易 YAML front matter パーサ。スカラーとリストだけを扱う。"""
    lines = text.splitlines()
    if not lines:
        return "missing", None
    if lines[0].strip() == "+++":
        return "toml", None
    if lines[0].strip() != "---":
        return "missing", None

    front_matter = {}
    current_list_key = None
    for line in lines[1:]:
        if line.strip() == "---":
            return "yaml", front_matter
        if not line.strip() or line.strip().startswith("#"):
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and current_list_key:
            front_matter[current_list_key].append(item.group(1).strip().strip("\"'"))
            continue
        key_value = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if key_value:
            key, value = key_value.group(1), key_value.group(2).strip()
            if value == "":
                front_matter[key] = []
                current_list_key = key
            elif value.startswith("[") and value.endswith("]"):
                front_matter[key] = [
                    item.strip().strip("\"'")
                    for item in value[1:-1].split(",")
                    if item.strip()
                ]
                current_list_key = None
            else:
                front_matter[key] = value.strip("\"'")
                current_list_key = None
    return "unclosed", None


def markdown_body(text):
    """front matter と fenced code block を空行に置き換え、行番号を保つ。"""
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
        elif in_code_block:
            lines[index] = ""
    return "\n".join(lines)


def post_files(posts_dir):
    """フラット記事と leaf page bundle の index.md を返す。"""
    flat_posts = (path for path in posts_dir.glob("*.md") if path.name != "_index.md")
    bundled_posts = (
        path
        for path in posts_dir.rglob("index.md")
        if path.parent != posts_dir
    )
    return sorted({*flat_posts, *bundled_posts})


def default_slug(post):
    return post.parent.name if post.name == "index.md" else post.stem


def is_past_date(value):
    """Hugo で一般的な日付を解釈し、今日以前かを返す。"""
    try:
        normalized = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).date() <= date.today()
    except ValueError:
        return False


def is_valid_iso_date(value):
    """DATE_RE に合う日付が実在する日時かを返す。"""
    try:
        normalized = str(value).replace("Z", "+00:00")
        datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return True


def static_image_path(root, url):
    """/images/ URL を static 内の安全なパスへ対応付ける。"""
    static_dir = (root / "static").resolve()
    candidate = (static_dir / unquote(url.lstrip("/"))).resolve()
    try:
        candidate.relative_to(static_dir)
    except ValueError:
        return None
    return candidate


def inspect_content_links(root, rel, body, slugs, problems):
    for match in IMAGE_RE.finditer(body):
        url = match.group(1)
        target = static_image_path(root, url)
        if target is None or not target.is_file():
            problems.append(("ERROR", rel, f"画像 {url} が static/ に存在しない"))

    for match in POST_LINK_RE.finditer(body):
        slug = unquote(match.group(1))
        if slug not in slugs:
            problems.append(("ERROR", rel, f"内部リンク /posts/{slug}/ の記事が存在しない"))


def inspect(root, settings):
    """検査結果を (記事数, 使用タグ, problems) として返す。"""
    posts_dir = root / "content" / "posts"
    tags_dir = root / "content" / "tags"
    if not posts_dir.is_dir():
        return None, {}, [("ERROR", "content/posts/", "が見つからない。リポジトリルートで実行すること。")]

    tag_re = re.compile(settings.tag_pattern)
    problems = []
    used_tags = {}
    slugs = {}
    valid_posts = []
    posts = post_files(posts_dir)

    for post in posts:
        rel = str(post.relative_to(root))
        is_bundle = post.name == "index.md"
        if is_bundle:
            if not FILENAME_RE.match(f"{post.parent.name}.md"):
                problems.append(("ERROR", rel, "ページバンドルのディレクトリ名は小文字ハイフン区切りの slug にする"))
        elif not FILENAME_RE.match(post.name):
            problems.append(("ERROR", rel, "ファイル名は小文字ハイフン区切りの <slug>.md にする"))

        text = post.read_text(encoding="utf-8")
        format_name, front_matter = parse_yaml_front_matter(text)
        if format_name == "toml":
            problems.append(("ERROR", rel, "TOML front matter (+++) には未対応。YAML (---) を使用する"))
            continue
        if front_matter is None:
            problems.append(("ERROR", rel, "YAML front matter がない、または --- で閉じられていない"))
            continue

        for field in ("title", "date"):
            if not front_matter.get(field):
                problems.append(("ERROR", rel, f"front matter に {field} がない"))
        if front_matter.get("date"):
            date_value = str(front_matter["date"])
            if not DATE_RE.match(date_value) or not is_valid_iso_date(date_value):
                problems.append(("WARN", rel, f"date が Hugo で一般的な ISO 8601 形式でない: {front_matter['date']}"))
        if "draft" not in front_matter:
            problems.append(("WARN", rel, "draft フィールドがない(公開状態が不明瞭になる)"))
        elif str(front_matter["draft"]).lower() == "true" and is_past_date(front_matter.get("date")):
            problems.append(("WARN", rel, "draft: true のまま date が過去日付。公開予定または意図を確認する"))
        if not front_matter.get("slug"):
            problems.append(("WARN", rel, "slug フィールドがない(ファイル名またはバンドル名から生成される URL を確認すること)"))

        slug = str(front_matter.get("slug") or default_slug(post))
        slugs.setdefault(slug, []).append(rel)
        valid_posts.append((rel, text))

        tags = front_matter.get("tags")
        if not isinstance(tags, list) or not tags:
            problems.append(("WARN", rel, "tags がない"))
            tags = []
        elif not settings.min_tags <= len(tags) <= settings.max_tags:
            problems.append(("WARN", rel, f"タグ数が {len(tags)} 個(設定は {settings.min_tags}〜{settings.max_tags} 個)"))
        for tag in tags:
            if not tag_re.match(tag):
                problems.append(("ERROR", rel, f"タグ '{tag}' が規約違反(パターン: {settings.tag_pattern})"))
            used_tags.setdefault(tag, []).append(rel)

    for slug, files in slugs.items():
        if len(files) > 1:
            problems.append(("ERROR", ", ".join(files), f"スラッグ '{slug}' が重複している"))

    existing_slugs = set(slugs)
    for rel, text in valid_posts:
        inspect_content_links(root, rel, markdown_body(text), existing_slugs, problems)

    existing_tag_pages = set()
    if tags_dir.is_dir():
        for tag_dir in sorted(path for path in tags_dir.iterdir() if path.is_dir()):
            existing_tag_pages.add(tag_dir.name)
            index = tag_dir / "_index.md"
            rel = str(tag_dir.relative_to(root))
            if not index.is_file():
                problems.append(("WARN", rel, "_index.md がない(表示名が定義されない)"))
            else:
                _, front_matter = parse_yaml_front_matter(index.read_text(encoding="utf-8"))
                if not front_matter or not front_matter.get("title"):
                    problems.append(("WARN", str(index.relative_to(root)), "title(表示名)がない"))
            if tag_dir.name not in used_tags:
                problems.append(("WARN", rel, "孤児タグページ(どの記事からも使われていない)"))

    for tag, files in sorted(used_tags.items()):
        if tag not in existing_tag_pages:
            problems.append(("WARN", f"content/tags/{tag}/", f"タグページがない(使用記事: {', '.join(files)})。表示名を定義するなら _index.md を作る"))

    return len(posts), used_tags, problems


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="対象ブログのリポジトリルート (既定: カレントディレクトリ)")
    parser.add_argument("--min-tags", type=int, default=3, help="タグ数の下限 (既定: 3)")
    parser.add_argument("--max-tags", type=int, default=5, help="タグ数の上限 (既定: 5)")
    parser.add_argument("--tag-pattern", default=r"^[a-z0-9_]+$", help="タグ値に許可する正規表現 (既定: ^[a-z0-9_]+$)")
    args = parser.parse_args()
    if args.min_tags < 0 or args.max_tags < args.min_tags:
        parser.error("--min-tags と --max-tags は 0 <= min <= max にする")
    try:
        re.compile(args.tag_pattern)
    except re.error as error:
        parser.error(f"--tag-pattern が不正: {error}")
    return args


def main():
    args = parse_args()
    settings = Settings(args.min_tags, args.max_tags, args.tag_pattern)
    post_count, used_tags, problems = inspect(args.root.resolve(), settings)
    errors = [problem for problem in problems if problem[0] == "ERROR"]
    warnings = [problem for problem in problems if problem[0] == "WARN"]
    for level, path, message in errors + warnings:
        print(f"{level}  {path}: {message}")
    if post_count is None:
        return 2
    print(f"\n{post_count} 記事 / {len(used_tags)} タグを検査: ERROR {len(errors)} 件, WARN {len(warnings)} 件")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
