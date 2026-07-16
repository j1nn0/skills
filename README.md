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
| [`writing-ja`](skills/writing-ja/SKILL.md) | 日本語記事の執筆・推敲・リライトの規範。文体、書式、論証の組み立て、AI臭い表現の除去までを1ファイルで完結させている。ブログ記事と技術記事が主対象で、メールや報告書などのですます調文書にも差分ルールで対応する。 |
| [`blog-writing-guide-ja`](skills/blog-writing-guide-ja/SKILL.md) | 日本語技術ブログの企画・構成・品質基準・レビューのガイド。読者の疑問に沿った記事構成、タイトルと見出しの付け方、SEO、公開前レビューの観点を定める。文レベルの文体は `writing-ja` の担当なので、記事を書くときは併用する。 |
| [`blog-ops`](skills/blog-ops/SKILL.md) | Hugo ブログ(PaperMod テーマ想定)の運用と執筆フロー全体の入口となるスキル。企画・執筆スキルへの振り分け、新規記事のセットアップ、公開前チェック、タグ管理、作業規約をまとめる。ブログリポジトリで記事やタグ・設定に触れる作業はここから始める。 |

## リポジトリ構成

`skills/` 直下の各ディレクトリが1つのスキル。
それぞれ `SKILL.md` を起点とし、単体でコピーして使える状態を保つ。

```text
skills/
├── writing-ja/
│   └── SKILL.md
├── blog-writing-guide-ja/
│   └── SKILL.md
└── blog-ops/
    ├── SKILL.md
    ├── references/
    └── scripts/
```
