# skills

個人用の agent skills 集。
Claude Code をはじめ、SKILL.md 形式に対応した各種エージェントで使える。

## インストール

[skills CLI](https://github.com/vercel-labs/skills) でインストールする。

```sh
npx skills@latest add j1nn0/skills
```

特定のスキルだけ入れる場合は `-s` で指定する。

```sh
npx skills@latest add j1nn0/skills -s writing-ja
```

プロジェクト単位ではなくユーザー全体で使う場合は `-g` を付ける。

```sh
npx skills@latest add j1nn0/skills -g
```

## スキル一覧

| スキル | 説明 |
| --- | --- |
| [`writing-ja`](skills/writing-ja/SKILL.md) | 日本語の技術記事、ブログ記事、解説文の本文を執筆・推敲するスキル。事実関係と書き手の声を保ちながら、論理、具体性、文の読みやすさを整える。 |
| [`blog-writing-guide-ja`](skills/blog-writing-guide-ja/SKILL.md) | 日本語技術ブログの企画・構成・品質基準・レビューのガイド。読者の疑問に沿った記事構成、タイトルと見出しの付け方、SEO、公開前レビューの観点を定める。文レベルの文体は `writing-ja` の担当なので、記事を書くときは併用する。 |
| [`blog-ops`](skills/blog-ops/SKILL.md) | Hugo ブログ(PaperMod テーマ想定)の運用と執筆フロー全体の入口となるスキル。企画・執筆スキルへの振り分け、新規記事のセットアップ、公開前チェック、タグ管理、作業規約をまとめる。ブログリポジトリで記事やタグ・設定に触れる作業はここから始める。 |

## License

Original repository content is licensed under the MIT License unless a skill
directory specifies a different license. This includes `blog-ops`.

Some skills are derived from third-party works and are subject to their own
license and attribution requirements. See the `LICENSE`, `SOURCES.md`, and,
where present, `NOTICE` files in each skill directory for the applicable terms.

## 開発時の検証

外部依存なしで、スキルの front matter と同梱スクリプトを検証できる。

```sh
python3 -m unittest discover -s tests
```

GitHub Actions でも同じテストを実行する。ブログリポジトリに適用する `blog-ops` の記事検査は、スキルディレクトリ内の `scripts/check_posts.py` を実行する。タグ数とタグ表記の既定は、対象リポジトリの規約に合わせて CLI オプションで変更できる。

`evals/trigger/` には、各スキルの description を評価するための should-trigger / should-not-trigger のテストセットを置く。description を変更する前に内容をレビューし、skill-creator の評価ループへ渡す。

## リポジトリ構成

`skills/` 直下の各ディレクトリが1つのスキル。
それぞれ `SKILL.md` を起点とし、単体でコピーして使える状態を保つ。

```text
skills/
├── writing-ja/
│   ├── SKILL.md
│   ├── references/
│   ├── scripts/
│   ├── LICENSE
│   └── SOURCES.md
├── blog-writing-guide-ja/
│   ├── SKILL.md
│   ├── LICENSE
│   └── SOURCES.md
└── blog-ops/
    ├── SKILL.md
    ├── references/
    └── scripts/
tests/
└── ...
```
