import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "skills" / "blog-ops" / "scripts" / "check_posts.py"
SPEC = importlib.util.spec_from_file_location("check_posts", SCRIPT)
check_posts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_posts)


def write_post(root, relative_path, front_matter, body="本文\n"):
    path = root / "content" / "posts" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front_matter}\n---\n{body}", encoding="utf-8")


class CheckPostsTest(unittest.TestCase):
    def inspect(self, root, **settings):
        return check_posts.inspect(root, check_posts.Settings(**settings))

    def test_accepts_datetime_and_page_bundle(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            front_matter = "title: Example\ndate: 2026-07-17T10:00:00+09:00\ndraft: false\ntags: [one, two, three]"
            write_post(root, "flat-post.md", front_matter)
            write_post(root, "bundle-post/index.md", front_matter)

            post_count, _, problems = self.inspect(root)

            self.assertEqual(2, post_count)
            self.assertFalse([problem for problem in problems if problem[0] == "ERROR"])
            self.assertFalse([problem for problem in problems if "date が" in problem[2]])

    def test_reports_toml_as_unsupported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "content" / "posts" / "toml-post.md"
            path.parent.mkdir(parents=True)
            path.write_text("+++\ntitle = 'Example'\n+++\n", encoding="utf-8")

            _, _, problems = self.inspect(root)

            self.assertIn(("ERROR", "content/posts/toml-post.md", "TOML front matter (+++) には未対応。YAML (---) を使用する"), problems)

    def test_allows_site_specific_tag_settings(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_post(root, "single-tag.md", "title: Example\ndate: 2026-07-17\ndraft: false\ntags: [custom-tag]")

            _, _, problems = self.inspect(root, min_tags=1, max_tags=1, tag_pattern=r"^[a-z-]+$")

            self.assertFalse([problem for problem in problems if problem[0] == "ERROR"])
            self.assertFalse([problem for problem in problems if "タグ数が" in problem[2]])

    def test_checks_images_and_internal_post_links(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            front_matter = "title: Example\ndate: 2026-07-17\ndraft: false\ntags: [one, two, three]"
            write_post(root, "target.md", front_matter)
            write_post(
                root,
                "source.md",
                front_matter,
                "![存在する画像](/images/source/present.webp)\n"
                "![ない画像](/images/source/missing.webp)\n"
                "[存在する記事](/posts/target/)\n"
                "[ない記事](/posts/missing/)\n",
            )
            image = root / "static" / "images" / "source" / "present.webp"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"image")

            _, _, problems = self.inspect(root)

            errors = [problem[2] for problem in problems if problem[0] == "ERROR"]
            self.assertIn("画像 /images/source/missing.webp が static/ に存在しない", errors)
            self.assertIn("内部リンク /posts/missing/ の記事が存在しない", errors)
            self.assertNotIn("内部リンク /posts/target/ の記事が存在しない", errors)

    def test_ignores_links_inside_fenced_code_blocks(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            front_matter = "title: Example\ndate: 2026-07-17\ndraft: false\ntags: [one, two, three]"
            write_post(root, "source.md", front_matter, "```md\n![画像](/images/nope.webp)\n[記事](/posts/nope/)\n```\n")

            _, _, problems = self.inspect(root)

            self.assertFalse([problem for problem in problems if problem[0] == "ERROR"])

    def test_warns_for_stale_draft(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_post(root, "draft.md", "title: Draft\ndate: 2000-01-01\ndraft: true\ntags: [one, two, three]")

            _, _, problems = self.inspect(root)

            self.assertIn(("WARN", "content/posts/draft.md", "draft: true のまま date が過去日付。公開予定または意図を確認する"), problems)
