# 修正版スケルトン対応の実装・検証記録（履歴資料）

> これは作業時点の変更・検証記録です。本文中には当時のAPI、プレビュー、承認、試験結果の記述が含まれます。現在の動作は[製品仕様](PRODUCT_SPEC.md)、[機能と制約](CAPABILITIES.md)、[API](../API.md)、[Testing](../TESTING.md)を参照してください。

2026-10-17。GitHubのmainと作業開始時のHEADは `2f57a77d766424ac696667ca90fa8baaa8cc26eb`。
ユーザーの修正版を正本とし、元ファイルと旧出力は変更していない。公開・デプロイ・pushは行っていない。

現行フローでは必須承認・プレビュー生成・画像確認を撤廃済み。以下の描画・承認の検証記録は当時の履歴。現在のAPIは [API.md](../API.md) を参照。

## 原因と変更

旧経路は42枚専用の抽出レシピから作ったレイアウトへ本文を配置しており、見本ページの直接書式を継承できなかった。
表は全高を行数で等分し、旧verifyは書式の改変を検出しなかった。
作業フォルダの旧卵例 `artifacts/eggs/presentation.pptx` は既に塗りなしだったため、青塗り修正を重複実装していない。
整理後は `reference_materials/local-inputs/eggs-original.pptx` に同じ内容で保管している。
そのファイルのSHAは `37ed9f63b3bf69a96674779042e0f7242de48083d9fa582083bdb253f4bc6e96`。
添付として言及された青塗り版と、このローカルファイルが同一版とは断定していない。

修正版を同一バイトのテンプレートとして登録し、見本ページ全体のXML・関係ファイルを複製する経路を追加した。
各ページの役割・可変欄・固定要素はprofileと [対応表](TEMPLATE_AND_CONTENT_RULES.md) に明記した。
マスター・テーマ・レイアウト・ロゴを保持し、段落／ランの直接書式を選んでテキストだけ差し替える。
研究発表の流れを検査するが11枚固定にはせず、40枚の複製も検証した。

表は見本の3列幅、見出し／本文の行高・15pt／16pt・太字・中央揃え・余白・罫線を複製する。
少ない行数でも引き伸ばさず、最下段の黒罫線を維持する。はみ出しは短縮／分割を求め、黙って縮小・枠拡張しない。
正本＋仕様から期待ページを再構成して比較する適合検査と、書式破壊の回帰試験を追加した。
認証とキューの構造は維持し、レイアウト失敗時のguidanceを追加した。

配布 [Skill](../plugins/research-slide-agent/skills/research-slides/SKILL.md) も正本選択、構造化、収まり、画像の実確認へ更新した。
当時の `get_preview_image` はPNGをMCP imageコンテンツで返し、URL提示とモデルの画像確認を区別する。
`get_generation_report` は生成来歴・正本適合検査を返す。画像配信成功だけで視覚確認済みとは記録しない。

## 生成物と来歴

- [卵の例・5枚](../artifacts/canonical-eggs/presentation.pptx): 一般向けの料理説明。架空の研究背景・実験は追加していない。
- [研究発表形式の検証例・13枚](../artifacts/canonical-research/presentation.pptx): 概要、階層と継続行、青色段落、ネイティブ図、1行／3行の表。試験用数値と未入力の研究内容を明示。
- [表の比較画像](../artifacts/canonical-review/table-before-after.png)、[数値による書式比較](../artifacts/canonical-review/table-comparison.json)。
- [卵の全頁一覧](../artifacts/canonical-eggs/overview.png)、[研究形式の全頁一覧](../artifacts/canonical-research/overview.png)。

正本SHA-256: `5f699f70dfa52726c17f6438cee84ece404ec852926b023f334f1a903f1832b5`。
書式版: `skeleton-2026-10-17.1`。仕様schema 1.1、spec_version 1。
生成コードはベースコミット `2f57a77d766424ac696667ca90fa8baaa8cc26eb` ＋今回の未コミット変更。
生成器のソースSHA-256: `23c0a8c1dcec039222a838fd48bf09cbbe54cde13e4ddc2952f41df9b0459b44`。
コミットだけで実装済み版と誤認しないよう、dirty=trueとソースハッシュもmanifestとPPTX内に記録した。

## 検証結果

生成方式変更時の全テストは **70 passed / 1 skipped**。その後の整理で42枚専用の抽出処理とその2試験を削除した。
現在の試験結果は [TESTING.md](../TESTING.md) を参照。
ruff、git diff --check、Skillのquick_validateに成功。
表の青塗り・最下段罫線削除・文字サイズ・揃え・行高・列幅・余白・位置・表の削除で検査が失敗することを確認した。

全18枚をLibreOfficeで描画し、モデルがview_imageで各ページの画像を実際に確認した。
最終コードで再生成・再描画した画像も、確認済み画像と全ページ一致した。
書式検査自体のvisual_reviewはpendingのままにし、今回の実確認は出力PPTXと画像のSHAに結び付けた別記録へ保存した。
[実行ログ](../artifacts/canonical-review/test-results.txt)、[全頁の実確認記録](../artifacts/canonical-review/visual-review.json)。

ローカルStreamable HTTPで、承認→ジョブ→描画→PNG imageコンテンツの取得を通し検証した。
PNGの画像SHA、未完了／範囲外／期限切れの拒否も検証済み。
Microsoft Open XML SDKは正本・両生成物とも **エラー0件**。
[SDK結果](../artifacts/canonical-review/openxml-validation.json)。

## 残る制約

- PowerPoint実機は未検証。LibreOfficeの画像ではフォント代替が起こりうる。XMLのYu Gothic等の指定は保持している。
- 外部公開を行っていないため、リモートChatGPTクライアントでのimageブロック表示受入は未検証。ローカルMCPの実画像配信まで検証した。
- 表は正本の3列・本文最大3行。多い行数はページを複製して分割する。文章の自動要約は行わない。
- 図は正本の枠・ラベルを使う簡単な配置図、または元画像に対応する。複雑な接続図・動画と、正本に書式見本がない独立グラフは1.1で受け付けない。
- 手動パッチは既存の単純テキスト編集の範囲で、正本適合検査済みの再生成とは区別する。
