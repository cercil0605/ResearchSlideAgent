# 正本の差し替え仕様（SlideSpec 1.3のみ）

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
## 1.3：構成・掲載内容・本文領域の配置

2026-10-20のユーザーフィードバックを反映した仕様。教授原文への新しい追記とは扱わない。
旧1.0/1.1/1.2と旧入力フィールドは拒否する。旧保存仕様の自動変換は行わず、必要事項を補って1.3として新しい版を保存する。

研究の本編は表紙→概要→背景→関連研究→目的→手法→実験→結果→考察→まとめ。
同じ節で複数ページを使える。exampleは手法の途中、metricは実験の後に置く。
複数実験では実験→指標→結果→考察を繰り返せる。本編の後に補足を置く。

cover以外の本編には`paper_section`（論文の節・小節）と`content_map`を指定する。
表示タイトルはsectionに対応する発表の構成名（概要・研究背景・関連研究・研究目的・提案手法・実験方法・実験結果・考察・まとめ）を残す。
複数枚ある節は「構成名：具体的な題材」とする。exampleは提案手法、metricは実験方法に含め、補足は「補足：題材」。
paper_sectionには根拠の原論文節を記録し、その翻訳を表示タイトルに使うという意味にはしない。
作成側LLMがこの制作規約を適用し、保存前にタイトルと本文の役割が一致するかを自己点検する。
サーバーの固定タイトル付与・自動改名を前提にしない。原文のページ・図番号などの根拠は既存のsource_references/citationsへ記録する。
content_mapは内容の役割→掲載する本文欄名の配列。複数ページの役割を節ごとに集め、
get_template_info.required_content_rolesを満たすか検査する。metricはexperimentかmetric節に必要。
対象は空でないreplacementsの本文欄、またはデータのある`table`。題名・小見出し・図題・図だけでは代用しない。
同じ本文欄で複数の役割を説明することはできるが、各内容を本当に説明しているかは制作LLMが原文と掲載本文を照合する。
役割の対応は節全体の機械検査だけで満たした扱いにせず、F02のページごとの必要事項とF06の自己点検を適用する。
関連研究を表へ載せる場合も、各研究の目的・方法・結果が対応し、本研究の未解決点へつながるようにする。

```json
{
  "section": "objective",
  "prototype_id": "objective",
  "paper_section": "I. Introduction：研究目的と貢献",
  "content_map": {
    "purpose": ["研究目的"],
    "approach": ["手段"],
    "novelty": ["根拠の記入例"]
  }
}
```

これはページ指定の一部。実際にはtitle、本文replacements、出典等も必要。
全文の合成試験例はexamples/research-quality.slidespec.json。実際の研究データではない。

`composition`の既定値canonicalは見本の配置。以下はmethod見本の本文領域だけを配置する。
座標・色・フォントは引き続き入力不可。マスター・ロゴ・タイトル・スライド番号・文字書式は維持する。

| composition | 内容と使用する欄 |
|---|---|
| text_visual | 左に手法の説明、右に原図1点または説明図、下に小見出し：特徴と手法の特徴。図を小さくして本文を確保 |
| table_visual | 左にtable_spec、右に原図1点または説明図、下に手法の特徴。手法の説明は空にする（表のための領域） |
| two_images | 左の図領域へ原図2点を順番に並べ、右の本文欄で説明。図題には両方のcaptionを含める |

各image_referencesのIDをtarget_idに指定したcitationsが必要。原図2点でも両方の引用を指定する。画像・元PDFの引用、著者・年も検査する。2点とも元バイト列と比率を保ち、個別の関係IDで埋め込む。
1.3の表は1～3列。正本の見出し15pt／本文16pt、揃え、余白、罫線を保ち、必要な行を複製する。
列幅はサーバーが本文領域へ配分し、長いセルには行高を確保する。4部位などを同じ表に載せられるが、
行数・文字量が本文領域を超える場合はTABLE_OVERFLOW。欄を広げたり小図にした後も収まらなければ、意味単位で分割する。

save_slide_specとpatch_slideのauthoring_feedbackにはpaper_section、compositionとcontent_evidence（役割ごとの掲載本文・表）を返す。
content_review/visual_reviewはnot_performedのまま。対応付けの存在は意味的な正しさや可読性の合格を意味しない。
制作LLMが各ページの内容と生成後の完成画像を確認し、修正したら新しいjobの画像で再確認する。

## 入力と図表制約

`section`を説明上の役割、`prototype_id`を表示見本として別々に指定する。
sectionはcover/overview/example/background/related/objective/method/experiment/metric/results/discussion/summary。
`part`はmain（既定）またはappendix。補足の後に本編へ戻らない。
研究の本編の節順は上記のとおり。具体例は手法内に、図付きの指標は実験説明より後に置く。複数実験の方法・結果・考察の反復も可能。

methodは図と本文、results_figureは大きい図と短い説明、overviewは3群の本文とキー図。
これらを導入・背景・実験・まとめ・補足でも再利用し、小見出しは内容へ合わせる。
例えばまとめにoverviewを使い「目的」「方法」「結果と今後の課題」とすることができる。
1.3では適したcompositionと本文・図表の配分を選び、可読性と説明のまとまりを保てない場合にページを分ける。coverの見本は表紙専用。
ロゴ、区切り線、タイトルの装飾、スライド番号の位置は固定。表紙に番号は出さず、後続ページは実際の順番を表示する。
本文の省略欄には正本のダミー文や架空の引用を残さない。空の見出しごと削除したい場合は別の役割を選ぶ。

1ページの指定例（全体にはmetadata、spec_version、schema_version="1.3"、purpose_mode等が必要）:

```json
{
  "slide_id": "background-a",
  "slide_order": 3,
  "prototype_id": "background",
  "section": "background",
  "part": "main",
  "title": "研究背景",
  "paper_section": "1. はじめに",
  "content_map": {"problem": ["背景の箇条書き"], "context": ["動向の箇条書き"]},
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

表は1～3列で本文領域内に収める。列見出しも短くする。表の行をページ分割するときは見出し・単位・出典を各ページに残す。
枚数の見込みは目安。収容範囲を超えた場合はF02の順序で言い回し・重複・本文と図表の配分を見直す。
それでも説明と可読性を保てなければ、必要事項を削らず意味単位で同じ見本ページを複製して分ける。
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
元画像はcanonical/text_visual/table_visualで1点、two_imagesで2点。各captionを図題へ指定し、各画像IDへのcitationsの表記も適切な欄へ含める。

PPTX生成と構造検査の成功でcompletedになる。`get_job.download_url` を提示する。
保存時のauthoring_feedbackには、ページの役割・引継ぎ見出し・図の有無・図枠寸法と警告が含まれる。
これは内容や可読性の自動合格判定ではない。図を置けない見本への指定は生成時にも拒否される。
生成後はget_slide_previewを使い、overview=trueで6頁ずつ全体を確認してから全ページを個別に見る。
F07に従い、見た目に加えて題材の説明充足・反復・細分化を点検し、確認内容・修正・残件を短く記録する。
初回は隔離workerの描画jobを返す。queued/runningなら待って同じ画像取得を繰り返し、失敗時はpreview_job_idでretry_jobする。
画像はjob内のPPTXのハッシュと対応し、次版には新しいjobを使う。参考PDFは描画後のget_preview.pdf_url。
元画像と完成画像を混同しない。サーバーは画像を描画するだけで意味のレビューは行わない。
PowerPoint実機の表示保証とは別。実際に画像を見ていなければ確認済みと主張しない。
原論文は `read_paper` で全文と図・表の一覧を読み、`crop_pdf_region(figure="Fig. 3")` で図全体をPNG登録できる。範囲を選ぶときだけ `render_pdf_page` で閲覧する。
image_referencesには返された画像source_id、出典には元PDFのcitation_source_idとページ・図番号を指定する。
本文切断や原図を短文だけで代替することはしない。Strictの枠と編集可能な図形の制約は維持する。
構造検査とPowerPoint実機の確認は区別する。
