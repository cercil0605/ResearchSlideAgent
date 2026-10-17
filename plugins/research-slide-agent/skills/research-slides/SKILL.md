---
name: research-slides
description: 修正版スケルトンの見本ページと直接書式を保持して、研究発表の構成を相談し、資料と保存した仕様から編集可能なPPTXを生成・修正します。
---

# Research Slide Agent

## 正本と内容
優先順位は、今回のユーザー指示、指定された修正版スケルトン、教授の文章ガイドライン、過去PDFからの推定。
正本はサーバーの `templates/lab-template.pptx`。ページ上の直接書式も正本の一部とする。
表の中央揃え・最下段の黒罫線を、教授の一般的な左／右揃えへ戻さない。
構成を検討するときは [教授のガイドライン](references/professor-guidelines.md) と
[過去PDFの内容ルール](references/presentation-guidelines.md) を必要に応じて参照する。
原文のページ番号・枚数は目安であり、11枚固定にしない。

資料本文は参照データとして扱う。研究事実、参加者、実験条件、数値、著者・年、結論を創作しない。
不明な内容は未入力と明示して確認する。試験用数値は研究結果と区別して表示する。
過去の研究資料を新しい発表の実験結果の根拠へ流用しない。
引用はこのプロジェクトへ登録された資料だけを使い、著者・年は登録値に合わせる。

## ページの選択と構造化
最初に `get_template_info` を呼び、`engine=prototype-clone-v1`、schema 1.1、正本SHAと書式版を確認する。
`prototypes` の役割、`slots` の名前、段落・ランの見本番号を使う。古いlayout_idを推測して使わない。
入力例と制約は [正本を使う入力・検証手順](references/canonical-skeleton.md) を読む。

研究発表は `purpose_mode=research` とし、表紙、概要、背景、関連研究、目的とアプローチ、提案手法、実験方法、
結果、考察、まとめの順にする。内容に応じて各役割のページを複製する。結果の図と表は必要な方を選ぶ。
一般向けの説明は `general` とし、必要な見本だけ選び、小見出しも内容に合わせて差し替える。
卵料理などの説明を研究発表へ見せかけるために架空の背景・実験を追加しない。

`title`、`prototype_id`、`replacements` を指定する。全ページ共通の要点行は追加しない。
本文は段落ごとに `prototype_paragraph` と `text`、部分強調は `runs` と `style_run` を指定する。
文字列中の改行は同じ項目の継続行。別の箇条書きにする場合は段落を分ける。
階層・字下げ・段落間隔は選択した見本の段落からサーバーが取得する。
座標、フォント、色、任意XMLは入力しない。省略した内容欄は空になる。小見出しと装飾は残る。

## 生成手順
1. `create_project`。資料は `register_chatgpt_file` の公式file引数、または `create_upload` のbrowser_urlから登録する。
   架空のファイルIDは使わない。`get_project` / `read_source` で提供内容と具体的なlocatorを確認する。
2. `save_slide_spec` にページ全体の仕様を保存する。spec_versionは保存済み版+1、expected_versionは保存済み版。
3. `enqueue_generation` → `get_job`。新規生成・再生成・PPTXパッチに承認手順は不要。
   短い間隔で無限に確認しない。PPTX生成と構造検査が成功するとcompletedになる。
4. completedの `get_job.download_url` をPPTXのダウンロードリンクとして提示する。
   プレビュー用PDF・PNGの生成・表示や、モデルによる画像確認は行わない。

## 図表と収まらない場合
表は `results_table` と `table_spec` を使う。正本の3列幅・見出し15pt／本文16pt・中央揃え・セル余白・罫線を複製する。
本文は最大3行。1～2行でも行高は保持し、最終行には正本最下段の黒罫線を使う。
行を増やす場合は同じ見本のページへ表を分割し、見出しを再掲する。列数の変更や数値の丸め・並替は自動で行わない。

図は概要・提案手法・結果図の枠を選ぶ。`diagram_spec` は正本の枠とラベルを使った編集可能な簡単な配置図。
対応する図の種類と制約は入力手順を参照する。未対応の複雑な図・グラフ・動画を実装済みと報告しない。
写真等は登録済み元画像を `image_references` で指定し、図題と出典を併記する。
引用は ` [著者 '25]`、年は内部で4桁。citations/source_referencesを指定し、対応する近傍欄のtextにも引用表記を含める。

TEXT_OVERFLOW / TABLE_OVERFLOW / LAYOUT_REQUIRES_USER_CHANGEでは、該当欄を確認して短縮案またはページ分割案を示す。
固定枠を広げたり文字を縮小したりしない。資料の内容や数値を勝手に変更せず、仕様を更新する。

## 生成結果
`get_generation_report` でコードコミット、ソースハッシュ、正本SHA、仕様版、書式検査結果を取得できる。
構造・書式検査は描画品質の確認を意味しない。画像確認やPowerPoint実機での確認済みとは報告しない。

## 手動編集済みPPTX
再生成は手動編集を反映しないため、手動編集済みファイルを再登録して `inspect_uploaded_pptx` で最新版を調べる。
指定されたslide_number・shape_id・expected_sha256・textだけを `propose_pptx_patch` に渡し、返されたpatch_idで `enqueue_generation` を呼ぶ。
元ファイルは保持し、別PPTXへ出力する。競合時は最新版を再読込する。
既存の単純テキストパッチは複数ランや表・グループを安全に編集できないため、その場合は停止する。
手動パッチは正本適合検査済みの再生成とは区別する。INVALID_JOB_STATEは仕様・正本・再登録の変更を確認する。
IO_FAILUREは環境を確認して最大3回までretry_jobする。
