# 公開前チェック

記事の公開・コミット前に、変更の種類に応じたチェックを実行する。
専用のテストスイートはないので、これが品質ゲートになる。

## 全変更共通

1. 機械検査を実行する:
   ```bash
   python3 .agents/skills/blog-ops/scripts/check_posts.py
   ```
   ERROR があれば修正する。WARN は内容を確認し、今回の変更に関係するものだけ対応する。
2. ビルドを確認する:
   ```bash
   hugo --minify
   ```
   エラーと想定外の警告がないこと。`public/` は意図的に追跡していない限りコミットしない。

## 変更の種類ごとの追加チェック

該当するものをすべて実行する。ひとつの変更が複数に該当することは多い(例: 新記事の公開はコンテンツ+front matter+タグに該当)。

### コンテンツ変更(本文の追加・修正)

- `hugo server -D` で対象ページを実際に表示する。
- 見出し、コードブロック、リンク、表、記事メタデータを目視確認する。
- 画像を追加したなら、参照パス(`/images/<slug>/...`)と alt テキストを確認する。

### front matter 変更

- title、date、summary、tags、draft、生成される URL を確認する。
- YAML として妥当であること(check_posts.py が検証する)。
- 公開する記事は `draft: false` になっていること。

### タグ変更

`references/tags.md` の手順とチェックに従う。最低限:

- 内部タグ値が小文字+アンダースコアであること。
- `content/tags/<内部値>/_index.md` に表示名(`title:`)があること。
- 記事フッター・タグ一覧ページ・タグ URL・SNS シェア値を確認する。SNS シェアは表示名ではなく内部値(アンダースコア区切り)を使う。
- 重複・孤児タグページを作っていないこと(check_posts.py が検出する)。

### summary / description 変更

- トップページと記事一覧に意図しない本文が露出していないこと。
- メタデータが意図した summary / description を使っていること。

### OGP・メタデータ変更

- `hugo --minify` 後に `public/` 配下の生成 HTML を見る。
- title、description、canonical URL、Open Graph、X/Twitter メタデータを確認する。
- 対象ページ例: `public/posts/<slug>/index.html` の `<head>` 内。

### レイアウト・CSS 変更

デスクトップとモバイルの両方で最低限これらを表示確認する: トップページ、記事ページ、記事一覧、タグ一覧、個別タグページ、About ページ。

### URL に影響する変更(スラッグ・タグ改名・削除)

1. 影響する新旧 URL を列挙して報告する。
2. リダイレクトの要否を判断する(`references/tags.md` 参照)。必要なら 301 を追加する(方式はホスティング依存。AGENTS.md で確認する)。
3. 内部リンクと canonical URL を確認する。

## 公開直前の最終確認

- [ ] check_posts.py が ERROR なし
- [ ] `hugo --minify` が警告なしで成功
- [ ] `draft: false`、date が公開日
- [ ] `hugo server` で記事ページを目視確認済み
- [ ] コミットメッセージは英語の Conventional Commits、件名 72 文字未満
