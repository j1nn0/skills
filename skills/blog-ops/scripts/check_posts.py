#!/usr/bin/env python3
"""content/posts の front matter とタグ規約を検査する。

リポジトリルートで実行する:
    python3 .agents/skills/blog-ops/scripts/check_posts.py

ERROR は修正必須(exit 1)、WARN は判断のうえ対応する。
外部依存なし(PyYAML 不要の簡易パーサ)。
"""

import re
import sys
from pathlib import Path

TAG_RE = re.compile(r"^[a-z0-9_]+$")
FILENAME_RE = re.compile(r"^[a-z0-9-]+\.md$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

problems = []


def error(path, msg):
    problems.append(("ERROR", path, msg))


def warn(path, msg):
    problems.append(("WARN", path, msg))


def parse_front_matter(text):
    """簡易 YAML front matter パーサ。スカラーとブロック/インラインのリストのみ対応。

    このリポジトリの front matter は単純な構造なので、これで十分。
    パースできない行があっても落とさず、読めたところまで返す。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm = {}
    current_list_key = None
    closed = False
    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        if not line.strip() or line.strip().startswith("#"):
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and current_list_key:
            fm[current_list_key].append(item.group(1).strip().strip("\"'"))
            continue
        kv = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if kv:
            key, value = kv.group(1), kv.group(2).strip()
            if value == "":
                fm[key] = []
                current_list_key = key
            elif value.startswith("[") and value.endswith("]"):
                fm[key] = [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
                current_list_key = None
            else:
                fm[key] = value.strip("\"'")
                current_list_key = None
    if not closed:
        return None
    return fm


def main():
    root = Path.cwd()
    posts_dir = root / "content" / "posts"
    tags_dir = root / "content" / "tags"
    if not posts_dir.is_dir():
        print("content/posts/ が見つからない。リポジトリルートで実行すること。", file=sys.stderr)
        return 2

    used_tags = {}  # tag -> [posts]
    slugs = {}      # slug -> [posts]
    post_count = 0

    for post in sorted(posts_dir.glob("*.md")):
        post_count += 1
        rel = str(post.relative_to(root))

        if not FILENAME_RE.match(post.name):
            error(rel, "ファイル名は小文字ハイフン区切りの <slug>.md にする")

        fm = parse_front_matter(post.read_text(encoding="utf-8"))
        if fm is None:
            error(rel, "front matter がない、または --- で閉じられていない")
            continue

        for field in ("title", "date"):
            if not fm.get(field):
                error(rel, f"front matter に {field} がない")
        if fm.get("date") and not DATE_RE.match(str(fm["date"])):
            warn(rel, f"date が YYYY-MM-DD 形式でない: {fm['date']}")
        if "draft" not in fm:
            warn(rel, "draft フィールドがない(公開状態が不明瞭になる)")
        if not fm.get("slug"):
            warn(rel, "slug フィールドがない(ファイル名から生成される URL を確認すること)")

        slug = str(fm.get("slug") or post.stem)
        slugs.setdefault(slug, []).append(rel)

        tags = fm.get("tags")
        if not isinstance(tags, list) or not tags:
            warn(rel, "tags がない")
            tags = []
        elif not 3 <= len(tags) <= 5:
            warn(rel, f"タグ数が {len(tags)} 個(規約は 3〜5 個)")
        for tag in tags:
            if not TAG_RE.match(tag):
                error(rel, f"タグ '{tag}' が規約違反(小文字+アンダースコアのみ。ハイフン・スペース禁止)")
            used_tags.setdefault(tag, []).append(rel)

    for slug, files in slugs.items():
        if len(files) > 1:
            error(", ".join(files), f"スラッグ '{slug}' が重複している")

    # タグページの検査
    existing_tag_pages = set()
    if tags_dir.is_dir():
        for tag_dir in sorted(p for p in tags_dir.iterdir() if p.is_dir()):
            existing_tag_pages.add(tag_dir.name)
            index = tag_dir / "_index.md"
            rel = str(tag_dir.relative_to(root))
            if not index.is_file():
                warn(rel, "_index.md がない(表示名が定義されない)")
            else:
                fm = parse_front_matter(index.read_text(encoding="utf-8"))
                if not fm or not fm.get("title"):
                    warn(str(index.relative_to(root)), "title(表示名)がない")
            if tag_dir.name not in used_tags:
                warn(rel, "孤児タグページ(どの記事からも使われていない)")

    for tag, files in sorted(used_tags.items()):
        if tag not in existing_tag_pages:
            warn(f"content/tags/{tag}/",
                 f"タグページがない(使用記事: {', '.join(files)})。表示名を定義するなら _index.md を作る")

    errors = [p for p in problems if p[0] == "ERROR"]
    warns = [p for p in problems if p[0] == "WARN"]
    for level, path, msg in errors + warns:
        print(f"{level}  {path}: {msg}")
    print(f"\n{post_count} 記事 / {len(used_tags)} タグを検査: ERROR {len(errors)} 件, WARN {len(warns)} 件")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
