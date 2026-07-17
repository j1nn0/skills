---
name: blog-ops
description: Hugo ブログ(PaperMod テーマ想定)の運用と執筆フロー全体の入口となるスキル。ブログリポジトリで記事・タグ・レイアウト・設定に触れる作業を始めるときは、内容を問わず必ず最初にこのスキルを読む。記事アイデアを育てる `blog-idea-grilling` への導線、記事の構成・執筆・推敲(blog-writing-guide-ja + writing-ja への導線)、新規記事のセットアップ(スラッグ命名、front matter、タグ選定、画像配置)、公開前チェック(ビルド検証、front matter・タグ規約・OGP・URL の確認)、タグの追加・改名・削除とリダイレクト管理、作業規約(スコープ制御、コーディングスタイル、コミット規約)を扱う。「記事を書きたい」「ネタを相談したい」「下書きを見て」「公開前チェックして」「タグを整理して」と言われたとき、明示的に頼まなくても記事ファイルの作成・編集や公開・コミット直前の場面で使用する。
---

# blog-ops — Hugo ブログ作業の入口

Hugo ブログのリポジトリでの作業はすべてここから始める。段階と目的に応じて、他のスキルとこのスキルのリファレンスに振り分ける。

## 適用範囲と優先順位

このスキルは汎用の既定を定める。対象は Hugo + PaperMod のブログを想定しているが、大半は Hugo 一般に通用する。

- **リポジトリの AGENTS.md(または CLAUDE.md)が優先。** サイト固有の事実(ホスティング、リダイレクト方式、独自の規約や逸脱)はそちらに書かれている。作業を始める前に必ず確認する。
- AGENTS.md に記載がない事項は、このスキルの既定に従う。
- 執筆系スキル(後述)は文章の質を担当し、リポジトリ固有の技術的制約を上書きしない。

## ワークフローの選択

| 段階・やること | 使うもの |
|--------------|---------|
| 記事アイデアを育て、企画を固める | `blog-idea-grilling` で企画の芯を決め、企画カードにまとめる |
| 記事の企画・構成・タイトル・SEO・記事単位のレビュー | `blog-writing-guide-ja` スキル |
| 本文の執筆・文単位の推敲・文体 | `writing-ja` スキル(blog-writing-guide-ja と併用する) |
| 新規記事のファイル準備(スラッグ、front matter、タグ選定、画像配置) | `references/new-post.md` |
| 記事の公開・コミット前の確認 | `references/publish-check.md` |
| 記事公開後の SNS 告知文 | `references/social-announcement.md` |
| タグの追加・改名・削除、リダイレクト管理 | `references/tags.md` |
| 作業規約(スコープ制御、コーディングスタイル、コミット、セキュリティ) | `references/conventions.md` |

該当するものを読んでから作業を始める。ファイルを変更する作業では `references/conventions.md` のスコープ制御に必ず従う。
連携先のスキルがその環境に無い場合は、その段階を自力で丁寧にこなす(スキップしない)。

## 記事を出すまでの典型的な流れ

1. **企画** — アイデアがまだ固まっていないときは `blog-idea-grilling` で企画の芯を育て、企画カードにまとめる。そこから `blog-writing-guide-ja` で構成を作る。
2. **準備** — `references/new-post.md` の手順でファイル・front matter・タグを整える。
3. **執筆** — `blog-writing-guide-ja` で構成を作り、`writing-ja` の文体規範で本文を書く・推敲する。
4. **公開** — `references/publish-check.md` のチェックを通してからコミットする。

途中の段階から頼まれたら(例: 下書きがすでにある)、その段階から入って以降の流れに乗せる。

## 執筆スキルの優先順位

- 記事の企画・構成・SEO・記事単位レビューは `blog-writing-guide-ja` が正。
- 文レベルの文体・言い回し・書式は `writing-ja` が正。
- `japanese-tech-writing`、`human-writing-ja`、`humanizer-ja` は直接使わない。常に `writing-ja` を使う。

## 検査スクリプト

front matter とタグ規約の機械的な検査は、このスキルディレクトリ内の `scripts/check_posts.py` が行う。対象ブログのリポジトリルートをカレントディレクトリにして実行する。

```bash
python3 "$SKILL_DIR/scripts/check_posts.py"
```

`SKILL_DIR` はこのスキルをインストールした `blog-ops` ディレクトリを指す。

既定の検査内容: front matter の必須フィールド、フラット記事とページバンドルのスラッグ規約、タグの表記規約(小文字+アンダースコア)、タグ数(3〜5個)、タグページ `content/tags/<tag>/_index.md` の有無、孤児タグページ、スラッグ重複、本文の inline Markdown 形式の `/images/...` と `/posts/<slug>/` の実在、過去日付の `draft: true`。
タグ数とタグ表記は汎用の既定であり、サイト側の `AGENTS.md` に別規約があれば CLI オプションで合わせる。`--min-tags`、`--max-tags`、`--tag-pattern` の使い方は `--help` で確認する。

ERROR は修正必須、WARN は判断のうえ対応する(既存記事の WARN を頼まれていないのに直さない — スコープ制御)。

## 既定のリポジトリ構造

リポジトリが別の構成を定めていない限り、以下を前提とする。

- 記事: `content/posts/<slug>.md`(小文字ハイフン区切り)
- タグページ: `content/tags/<内部タグ値>/_index.md`(`title:` に表示名)
- 画像: `static/images/<slug>/` に置き、記事からは `/images/<slug>/ファイル名` で参照
- リダイレクト: ホスティング依存。AGENTS.md で方式を確認する(例: Cloudflare Pages なら `static/_redirects`)
- サイト設定: `hugo.yaml`(または `config.toml` など)

詳細は `references/conventions.md`。
