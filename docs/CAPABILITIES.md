# 機能と制約

この一覧は、現行コードで確認できる利用者向けの範囲を示します。テンプレート固有の挙動は[テンプレート詳細](TEMPLATE_AND_CONTENT_RULES.md)、MCP契約は[API](../API.md)が詳しい説明です。

## PowerPointの生成

| 機能 | 現在の範囲 |
|---|---|
| テンプレート | 同梱の正本テンプレートを使い、見本ページを複製して内容を差し替える |
| 枚数 | 仕様全体で最大40枚。研究発表の章立ては固定順を保ち、必要な章はページを複製できる |
| 研究発表の構成 | 表紙、概要、背景、関連研究、目的、手法、実験、結果、考察、まとめを含め、結果は図または表のページを少なくとも一つ含める |
| 一般向け構成 | 正本のページ見本から必要なものを選ぶ。研究発表用の架空の背景・実験は作らない |
| 表 | 正本の3列、本文1～3行。列幅、文字、行高、余白、罫線は見本に従う。超える表はページ分割が必要 |
| 図 | 1ページにつき原図1点、または最大4個の処理ボックスを順に配置。ボックス間の接続線、分岐、独自強調は未対応 |
| グラフ | 正本を使う現行SlideSpec 1.1では未対応。旧1.0のグラフ経路は合成テンプレートの互換性・試験用 |
| 文字の収まり | フォント幅の保守的な見積もりで検査する。内容を黙って切ったり、文字を縮小したりせず、短縮またはページ分割を求める |
| 生成後の画像 | 通常の生成ではPPTXのページプレビューを作らない。MCP Apps UIは状態とダウンロードを表示する |

## 入力資料と保存

| 項目 | 現在の範囲 |
|---|---|
| 形式 | PDF、PPTX、PNG、JPEG、CSV、XLSX |
| ファイル数 | 元資料10件まで。PDFから派生した画像は別枠で80件まで |
| 容量 | 1ファイル20 MiBまで、プロジェクト合計100 MiBまで |
| PDF | 最大500ページ。テキスト抽出とページ画像表示、領域切り出しに対応。スキャン画像のOCRはしない |
| 抽出 | 参照元のテキストをページ・シート単位で最大24,000文字返す。長い場合は切り詰め状態を返す |
| 保持 | プロジェクトは作成後7日でアクセス拒否・削除の対象になる |

入力の安全性確保のため、マクロ、有効な外部Office参照、暗号化PDF、危険な圧縮構造などは拒否します。詳しくは[Security](../SECURITY.md)を参照してください。

## 更新・修正

| 機能 | 現在の範囲 |
|---|---|
| 仕様からの再生成 | 保存した仕様の新しい版から、正本テンプレートを使って発表全体を再生成する |
| PowerPointで手編集した資料 | 最新版として再登録し、検査で特定できる単純なテキスト図形を差し替える |
| 部分修正の対象外 | 図形の移動・サイズ変更、表・グラフ・SmartArt、複雑な書式付きテキストなど |
| 競合検出 | 仕様版、対象テキストのハッシュ、パッチ元ファイルを照合し、変更後の対象には適用しない |
| 再試行・同時実行 | 利用者ごとに同時ジョブ1件。失敗ジョブは上限内で再試行できる。worker上限は設定で1または2 |

## 認証・運用状況

Cloudflare Access方式と、既存OAuth認可サーバーを使う方式を実装しています。開発用の認証なしモードはloopback接続に限定されます。外部サービスの設定やChatGPTとの実接続が受け入れ済みかどうかは[Testing](../TESTING.md)を参照してください。

現在の保存・ジョブ構成はSQLiteとAPI／workerです。GCP版は未実装で、[GCP資料](../deploy/GCP.md)は移行時の検討事項です。

## 実装上の確認先

機能一覧を更新するときは、記述を以下と照合してください。

- 仕様と入力制約: [`models.py`](../src/research_slide_agent/models.py)、[`schemas/slidespec.json`](../schemas/slidespec.json)
- 正本テンプレートの生成と適合検査: [`prototypes.py`](../src/research_slide_agent/prototypes.py)、[`test_prototypes.py`](../tests/test_prototypes.py)
- 入力資料・抽出: [`files.py`](../src/research_slide_agent/files.py)、[`pdf_assets.py`](../src/research_slide_agent/pdf_assets.py)、[`test_inputs.py`](../tests/test_inputs.py)、[`test_pdf_assets.py`](../tests/test_pdf_assets.py)
- 部分修正・ジョブ・保持: [`store.py`](../src/research_slide_agent/store.py)、[`worker.py`](../src/research_slide_agent/worker.py)、[`test_state.py`](../tests/test_state.py)
- MCPツールとHTTP契約: [`server.py`](../src/research_slide_agent/server.py)、[API](../API.md)、[`test_mcp.py`](../tests/test_mcp.py)
