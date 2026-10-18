# 正本の差し替え仕様（SlideSpec 1.2推奨、1.1互換）

正本のSHA-256: `5f699f70dfa52726c17f6438cee84ece404ec852926b023f334f1a903f1832b5`。
書式版: `skeleton-2026-10-18.1`。正本バイト列は維持し、図枠内の描画規則を更新した。
実際の接続先のget_template_infoを優先し、不一致なら書式版・対応機能の違いを確認する。
サーバーは見本ページ全体を複製する。マスターだけから新規ページを作らない。

| prototype_id | 役割・代表的な差し替え先 |
|---|---|
| cover | 表紙。title、著者（正本には複数ランがありrunsを使う） |
| overview | 概要。目的の記入欄、方法の記入欄、結果の記入欄、図題、図 |
| background | 背景。背景の箇条書き（段落0と下位階層1）、動向の箇条書き |
| related | 関連研究。研究例、研究の課題 |
| objective | 目的とアプローチ。研究目的、手段（段落1は青色）、根拠の記入例 |
| method | 提案手法。小見出し：［提案手法の名称］、手法の特徴、手法の説明、図題、図 |
| experiment | 実験方法。実験目的、実験条件、指標 |
| results_figure | 結果図。図題、結果の要点、図 |
| results_table | 結果表。table_spec、表の結果要点 |
| discussion | 考察。達成、解釈、制約 |
| summary | まとめ。まとめ：目的、まとめ：方法、まとめ：結果、まとめ：今後の課題 |

小見出しも名前をget_template_infoから選んで文字を差し替えられるが、色や寸法は変わらない。
1.2では`section`を説明上の役割、`prototype_id`を表示見本として別々に指定する。
sectionはcover/overview/example/background/related/objective/method/experiment/metric/results/discussion/summary。
`part`はmain（既定）またはappendix。補足の後に本編へ戻らない。
研究の本編は表紙・概要で始め、背景・関連研究・目的・手法・実験・結果・考察を含み、まとめで終える。
具体例を背景より前へ、図付きの指標を実験説明より後へ置ける。複数実験の方法・結果・考察の反復も可能。
1.1はsection/partを使わず、旧来の見本順の検査を維持する。新規制作は1.2を使う。

methodは図と本文、results_figureは大きい図と短い説明、overviewは3群の本文とキー図。
これらを導入・背景・実験・まとめ・補足でも再利用し、小見出しは内容へ合わせる。
例えばまとめにoverviewを使い「目的」「方法」「結果と今後の課題」とすることができる。
各欄に収まらなければ意味を保ってページを分ける。coverの見本は表紙専用。
ロゴ、区切り線、タイトルの装飾、スライド番号の位置は固定。表紙に番号は出さず、後続ページは実際の順番を表示する。
本文の省略欄には正本のダミー文や架空の引用を残さない。空の見出しごと削除したい場合は別の役割を選ぶ。

1ページの指定例（全体にはmetadata、spec_version、schema_version="1.2"、purpose_mode等が必要）:

```json
{
  "slide_id": "background-a",
  "slide_order": 3,
  "prototype_id": "background",
  "section": "background",
  "part": "main",
  "title": "研究背景",
  "replacements": {
    "背景の箇条書き": [
      {"prototype_paragraph": 0, "text": "提供された課題"},
      {"prototype_paragraph": 1, "text": "根拠となる事実\n同じ項目の継続行"}
    ],
    "動向の箇条書き": [{"text": "資料に基づく説明"}]
  }
}
```

`prototype_paragraph`は0始まり。任意のレベル指定ではなく、その欄にある段落見本を選ぶ。
`text`と`runs`はどちらか一方。正本の段落内に異なる直接書式が混在する場合はrunsを明示する。
例: `{"runs":[{"text":"所属と著者名","style_run":0}]}`。
複数の強調ランは `style_run` をそれぞれ選ぶ。正本にない色や太字を勝手に足さない。
空にする場合は `"欄名": []`。titleは専用フィールドで指定する。
正本が箇条書き記号を付けるため、text/runsの項目頭に「・」「•」「- 」等を加えない。
DUPLICATE_BULLETでは先頭の記号だけを取り除き、段落の階層と本文途中の中黒は保持する。

表は3列、本文1～3行。列見出しも短くする。表の行をページ分割するときは見出し・単位・出典を各ページに残す。
枚数の見込みは目安。収容範囲を超えた説明を詰め込んだり削ったりせず、同じ見本ページを複製して分ける。
1ジョブ40枚は現行の技術上限であり、説明を圧縮する目標ではない。必要数が超える場合は構成を保ち制約を明示する。

`diagram_spec`は編集可能なノード・接続線で手順、分岐、集約、比較を表す。
nodes（最大12）に動作・判断を、edgesにsource/targetと必要な短いlabelを指定する。
processは四角、decisionは菱形、terminatorは角丸。独自emphasisは未対応。
配置はサーバーが決め、最大6段・同じ段の最大4ノード。小さい図枠ではさらに短縮・分割が必要になる。
接続は横なら右、縦なら下へ進む隣接段のみ。循環・逆向き・段を飛ばす接続は説明を分ける。
edgesなしは指定順の独立した要素を並べる。順序や集約がある場合はedgesを省略しない。
図枠内は正本の字形・15pt・テーマ色を用い、ノードは実線・黒い太字、接続は矢印にする。
短い接続ラベルは12pt。完成図と原図の外側に、編集用の破線枠を残さない。

例（研究データではなく、3回の採点を平均へ集約する説明図の指定）:

```json
{
  "kind": "flowchart",
  "direction": "horizontal",
  "nodes": [
    {"id": "run1", "text": "実行1の採点"},
    {"id": "run2", "text": "実行2の採点"},
    {"id": "run3", "text": "実行3の採点"},
    {"id": "mean", "text": "満点比率に換算\n3回分を平均"}
  ],
  "edges": [
    {"source": "run1", "target": "mean"},
    {"source": "run2", "target": "mean"},
    {"source": "run3", "target": "mean"}
  ]
}
```

ノードや接続ラベルのTEXT_OVERFLOWでは、意味を保って短くするか図を分割する。文字を途中で切らない。
データグラフの見本は正本にないため、chart_specは受け付けない。未対応の手法を自動で画像化して回避しない。
元画像は1枠1枚。captionと同じ内容を図題へ指定し、citationsの表記も適切な欄へ含める。

PPTX生成と構造検査の成功でcompletedになる。`get_job.download_url` を提示する。
保存時のauthoring_feedbackには、ページの役割・引継ぎ見出し・図の有無・図枠寸法と警告が含まれる。
これは内容や可読性の自動合格判定ではない。図を置けない見本への指定は生成時にも拒否される。
生成後はget_slide_previewを使い、overview=trueで6頁ずつ全体を確認してから重要ページを個別に見る。
画像はjob内のPPTXのハッシュと対応し、次版には新しいjobを使う。参考PDFは描画後のget_preview.pdf_url。
元画像と完成画像を混同しない。サーバーは画像を描画するだけで意味のレビューは行わない。
PowerPoint実機の表示保証とは別。実際に画像を見ていなければ確認済みと主張しない。
原論文は `render_pdf_page` で閲覧し、`crop_pdf_region` で選択領域をPNG登録できる。
image_referencesには返された画像source_id、出典には元PDFのcitation_source_idとページ・図番号を指定する。
本文切断や原図を短文だけで代替することはしない。Strictの枠と編集可能な図形の制約は維持する。
構造検査とPowerPoint実機の確認は区別する。
