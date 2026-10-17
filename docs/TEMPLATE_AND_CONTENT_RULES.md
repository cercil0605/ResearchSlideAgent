# 書式テンプレートと発表内容ルール

2026-10-17更新。ユーザー修正版「学会発表スケルトン.pptx」を書式の正本とする。
優先順位は今回のユーザー指示、修正版、教授の文章ガイドライン、過去PDFからの推定。
教授のガイドラインは目安であり、正本の中央揃えの表・最下段の黒罫線等を上書きしない。

## 正本と登録

`templates/lab-template.pptx` は修正版のバイト単位のコピーで、SHA-256は
`5f699f70dfa52726c17f6438cee84ece404ec852926b023f334f1a903f1832b5`。
`.profile.json` に各ページの役割、差し替え欄、段落とランの見本、固定要素を記録する。
この2ファイルをGit・Dockerに同梱するため、原本ファイルを別途用意しなくても生成できる。

```bash
uv run python scripts/prepare_skeleton_template.py
uv run python scripts/template_smoke.py
uv run python scripts/render_spec.py examples/eggs.slidespec.json --output artifacts/canonical-eggs
uv run python scripts/render_spec.py examples/research-format.slidespec.json --output artifacts/canonical-research
```

既定のコマンドは同梱済みの正本を検査するため、元の添付ファイルを必要としない。
新しい正本を登録するときは `--source /path/to/new-skeleton.pptx` を指定する。元ファイルやページの書式は変更しない。
登録時に旧プレビューを削除する。生成にプレビューは不要。
`scripts/prepare_lab_template.py` は旧コマンド名を維持する薄い入口。42枚専用の抽出コードは削除済み。
ルートの原本コピーは `reference_materials/local-inputs/` に保管し、実行用は `templates/` に一本化した。
別の正本へ差し替えるときは対応欄と書式版をレビューし、profileを再生成する。SHAが一致しなければ生成を停止する。

## 各ページの役割と固定要素

| 見本ページ | prototype_id | 差し替え対象 |
|---|---|---|
| 1 | cover | title、著者・所属 |
| 2 | overview | 目的、方法、結果の内容、図・図題 |
| 3 | background | 背景・動向の箇条書き |
| 4 | related | 研究例と未解決の課題 |
| 5 | objective | 研究目的、手段、根拠 |
| 6 | method | 手法の名称、図・図題、特徴、説明 |
| 7 | experiment | 実験目的、条件・手順、指標 |
| 8 | results_figure | 結果図・図題、結果の要点 |
| 9 | results_table | ネイティブ表の列見出しとセル、表の結果要点 |
| 10 | discussion | 達成、解釈、制約 |
| 11 | summary | 目的、方法、結果、今後の課題 |

固定するものはロゴ、区切り線、背景・装飾、位置・寸法、余白、フォント、色、揃え、箇条書き、段落／行間、罫線。
小見出しは文字だけ変更でき、省略した場合は正本のまま残る。未指定の内容欄は空にする。
表紙の番号非表示を保持し、後続ページの番号フィールドは生成順に更新する。

schema 1.1はページをレイアウトから作り直さず、見本ページのXMLと関係ファイルを複製する。
共有のマスター・レイアウト・テーマ・ロゴはそのまま保持する。
`prototype_paragraph`でその欄の段落見本を選び、`runs/style_run`で部分書式も選べる。
改行はa:brの継続行で、段落を追加するときは配列要素を追加する。
正本にはない全ページ共通の「要点」行を追加しない。

`research`モードは表紙→概要→背景→関連研究→目的→手法→実験方法→結果→考察→まとめを検査する。
必要なページは複製できる（現在のジョブ上限40枚）。結果は図／表の片方でも両方でもよい。
`general`モードは必要な見本だけ選び、研究発表に見せるための架空の研究内容を作らない。

## 表と図

表は見本9の3列（幅1847850/2143125/2143125 EMU）、見出し高329256、本文高538163 EMUを使う。
見出し15pt、本文16pt・太字、中央揃え、枠内余白、塗りなし、黒罫線をそのまま保持する。
本文1～3行に対応し、少ない行数では全体の高さだけを行高合計へ短くする。
最後の本文行は必ず見本の最下段を複製する。多い行数はページ分割し、列数を変える入力は拒否する。

図は見本の枠内で、元の画像、または正本の枠とラベルを使う簡単な編集可能な配置図に対応する。
配置図は最大4個のprocessノード。接続線・decision・独自強調を含む図は停止する。
正本にグラフの直接書式の見本がないため、1.1ではchart_specを受け付けない。
未対応の図やグラフを画像化して編集可能性を回避しない。

## 検証と出力の識別

正本と仕様から許される差し替え後のXMLを再構成し、出力の各ページと比較する。
表の存在だけで合格にせず、色・罫線・字形・文字サイズ・揃え・余白・行高・列幅・固定要素まで検査する。
表の青塗り、最下段の罫線削除、サイズ変更等の改変試験で失敗を確認する。

生成時のコミット、作業ツリー変更の有無、生成器ソースハッシュ、正本SHA、書式版、仕様版・digestを
`.manifest.json`とPPTXのカスタムプロパティに記録する。
ローカル未コミットの変更もソースハッシュで識別できる。Dockerはビルド引数RSA_CODE_COMMITを渡す。
コード・正本が変わった出力と過去の出力を、見た目や同じファイル名だけで取り違えない。

はみ出し判定はフォントと行間を使った保守的な見積りで、フォントの実描画測定ではない。
はみ出し時に枠拡張や文字縮小は行わず、短縮／分割を求める。
PPTX生成・構造検査の成功でcompletedとなり、`get_job.download_url` を提示する。
承認、PDF・PNGプレビューの生成・表示、モデルによる画像確認は生成手順に含めない。
visual_reviewはnot_performedであり、PowerPoint実機での表示確認済みとは扱わない。

## 内容ガイドラインの管理

- 教授の原文: `reference_materials/guidelines/professor-slide-guidelines-2025-12-02.txt`。
- 配布Skill: `plugins/research-slide-agent/skills/research-slides/SKILL.md`。
- 入力手順: 同Skillの `references/canonical-skeleton.md`。
- 教授の文章の整理: `references/professor-guidelines.md`。
- 過去PDFの推定: `references/presentation-guidelines.md`。

提供資料の根拠を新しい研究事実と取り違えない。教授の文章やPDFから内容ルールを更新する開発用Skillは
`.agents/skills/update-presentation-rules/SKILL.md`。書式の正本をこの処理で勝手に変更しない。
