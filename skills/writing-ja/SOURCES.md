# Sources and attribution

## humanizer-ja

Parts of this skill are based on `gonta223/humanizer-ja`.

- Source: https://github.com/gonta223/humanizer-ja
- License: MIT
- Changes: Reorganized for Japanese technical prose and integrated into an independent editing workflow.

The following MIT copyright notices are preserved in `LICENSE`:

- Copyright (c) 2025 Siqi Chen (original: blader/humanizer)
- Copyright (c) 2026 SuguruKun_ai (Japanese version: humanizer-ja)

Copyright (c) 2026 j1nn0 applies to the modifications and original additions
in this skill.

## natural-japanese

The readability principles in this skill are based on `coji/natural-japanese`.

- Source: https://github.com/coji/natural-japanese
- License: MIT
- Changes: Only the readability layer was taken (`references/readability-principles.md`
  and `references/readability-antipatterns.md`). Word order, comma placement,
  subject-predicate distance, the reader's three axes, and a subset of the bad-prose
  patterns were condensed and rewritten for Japanese technical prose. The full
  workflow, doctype templates, and the morphological-analysis lint were not adopted.

The MIT copyright notice is preserved in `LICENSE`:

- Copyright (c) 2026 coji

`natural-japanese` credits five works as the origin of its readability layer.
The list is reproduced as recorded in that repository and has not been checked
against the books themselves:

- 本多勝一『【新版】日本語の作文技術』朝日文庫
- 木下是雄『理科系の作文技術』中公新書
- 唐木元『新しい文章力の教室』インプレス
- 結城浩『数学文章作法 基礎編・推敲編』ちくま学芸文庫
- 石黒圭『文章は接続詞で決まる』光文社新書、『「接続詞」の技術』実務教育出版

Of these, two correspond to material adopted here: word order and comma placement
(本多), and the reader's three axes of knowledge, motivation, and purpose (結城).
The paragraph and connective rules in this skill predate this port and are not
derived from the other three.

## k16shikano public Gist

Parts of this skill were derived from a public Gist by k16shikano.

- Source: https://gist.github.com/k16shikano/fd287c3133457c4fd8f5601d34aa817d
- License declaration: https://gist.github.com/k16shikano/67625f2a7d96e3bbdfae8d571a936063
- License: The Unlicense
- Changes: Selected technical-writing concepts were reorganized and integrated into the editing workflow.

The Unlicense does not require retaining a copyright or license notice, so its
text is not included in `LICENSE`.

## Original work

Other portions, including project-specific rules and adaptations, were newly
created for this repository.
