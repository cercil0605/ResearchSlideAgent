# 検証記録

2026-10-16。これはローカル検証の記録です。全要件の受入完了を示しません。

## 実行した検証

- Python 3.13.7/macOSでpytest。MCP SDKは公式PyPIで最新安定2.3.0、python-pptxは1.0.2を確認。
- 公式MCP `Client` のlegacy/auto両モードで実際のloopback HTTPへ接続。tools/list、profile、project、spec、承認前生成拒否、承認後queue、worker生成、プレビューURL、UIリソース取得を試験。
- 5枚のネイティブPPTX、40枚PPTXの生成。LibreOffice→PDF→PNGで5/5頁、40/40頁を確認。
- 元のslideMaster/slideLayout/themeのXMLバイト一致。ネイティブ図形・接続先・表・chart・埋込XLSX・数値一致。
- フロー/システム/比較/タイムライン、棒/折れ線/散布図。
- 安全な領域拡張を最大2回実行し、承認済み文字列を維持。収まらない内容は拒否。
- 引用のネイティブテキストと対象図形近傍への配置。
- 手編集済み相当のPPTXから指定shapeのみを変更し、対象外OPCパーツのbyte一致と競合拒否を確認。
- 構成前・ページ前・新バージョン・テンプレート変更・別ユーザーでの生成拒否。
- 排他claim、全体並列上限、ユーザー1ジョブ、冪等性、lease失効、旧worker書込拒否、3試行上限。
- ファイル形式、外部Office参照、パストラバーサル、file quota、期限拒否と削除。
- 生成したRSA鍵によるJWTのissuer/audience/scope/期限/許可sub/ID-token拒否。
- Browser session/CSRF/Origin/単回approval/capabilityの検証。
- 公式Agent Plugins JSON SchemaでmanifestとMCP設定を検証。SlideSpec SchemaとPydantic定義の一致。
- React/TypeScript型検査とesbuild bundle。npm install時のauditは0 vulnerabilities。
- ARM64コンテナ内で合成データを使い、MCP→browser cookie/CSRF付き2段階承認→worker→全頁preview→PPTXダウンロードを通し検証。
- ARM64 Linux/Python 3.12のDocker build。非root・read-only・network noneで5枚生成と全頁LibreOffice/Poppler previewを実行。

pytestの最新件数と結果は `artifacts/test-results.txt` を参照。Piでの全体実行は49件成功（うち1件はローカル原本がある場合の実見本試験）。Starlette TestClient依存内のanyio BlockingPortalに関するDeprecationWarningが1件あります。

## 教授の見本を用いたPi実機検証

- 初回は `slide_sample.pptx` の全42枚をLibreOfficeでPDF化して確認したが、フォント・表の崩れをユーザーが指摘。現在の正本はユーザーが差し替えたPowerPoint出力の28ページ。29–42枚目は原本で非表示。
- 内容・構成の12項目の推奨を、根拠ページ付きで配布Skillの参照Markdownへ保存。
- 原本のマスター2つとテーマのXML・関係ファイルを保持した、5枚・5レイアウトのテンプレートを抽出。
- 未使用レイアウトを正規化し、本文・要点・引用・図表・左右列の固定枠を設定。原本の全配置を同一化したという意味ではない。
- 箇条書きの階層、和文/欧文フォント、枠位置の保持、未定義枠・溢れ・実際のマスター変更の拒否をテスト。
- 6枚の合成スライド（表紙、本文、図、二段組、表、グラフ）と全頁PDF/PNGを生成して確認。
- 同じ書式の40枚は生成4.11秒、PDF/1600px PNG化28.27秒。Python最大RSS 91,512 KiB、子プロセス最大RSS 270,920 KiB。
  これらは同時合計の最大メモリではない。Pi 4 ARM64、ホストPython 3.12/LibreOfficeによる合成内容の単発実測であり、本番コンテナや全研究資料への性能保証ではない。
- `artifacts/template-forty/presentation.metrics.json` に実測を保存。計測時点のテンプレートと成果物のmaster/layout/themeはバイト一致を確認。後述の引用欄修正前の実測値。
- 原本の研究タイトル等をアプリケーションメタデータからも削除。共有テンプレートに動画や研究本文を含めず、原本ファイルは変更していない。
- 游ゴシックがPiにないためプレビューは代替フォント。Mac/WindowsのMicrosoft PowerPointでの受入は未実施。

## 実マスターを同梱したコンテナの検証

- `templates/lab-template.pptx`（160,642 bytes）と `.profile.json`（2,756 bytes）をGit管理対象にし、Dockerイメージへ同梱。原本PPTX・参考PDF・生成プレビューはGitとビルド対象から除外。
- Pi上で `research-slide-agent:local` のARM64ビルド成功。ビルドコンテキストは約1.52 MB。原本やホストテンプレートのマウントなしで、同梱ファイルのSHA-256と5種類のレイアウトを使った生成を確認。
- UID 10001、read-only、network none、cap-drop ALLで6枚のPPTXと全6ページのPDF/PNG生成が成功。検証ログは `artifacts/docker-build.log` と `artifacts/docker-template-check.log`。
- ComposeとPortainer Stackの構文検証成功。永続データだけをvolumeへ保存し、ホスト公開ポートを8010へ変更。実サービスの配備は未実施。
- このPiのDockerは `MemoryLimit=false`、`SwapLimit=false`。検証時の `--memory 2g` は警告付きで無視されたため、メモリ上限が適用された条件での試験ではない。Stackの `mem_limit` もこのホストでは適用されない。
- CIに同梱マスターから6枚を生成・レンダリングする検証を追加。ローカル原本がないcheckoutでも書式テンプレートを利用する。

## プラグインなしの卵料理デモ

- `bash scripts/try_eggs.sh` で同梱マスターから5枚のPPTX、全5ページのPDF/PNG、一覧画像、簡易HTMLビューアーを生成。ホストのPython・uv、OAuth、サーバー起動は不要。
- `examples/eggs.slidespec.json` が文章・構成、`examples/eggs.sources.md` が出典と再実行手順。表2つ、手順図1つと接続線をネイティブ構造で生成し、master/layout/themeのバイト一致を検証。
- 初回生成で引用欄の高さ計算が10.5 ptを仮定し、実際の12 pt・行間130%と枠内余白に足りない不具合を検出。抽出レシピを実際の文字サイズ・行間・上下余白から算出するよう修正。原本マスター・テーマと文字書式は維持し、正規化した本文/引用の領域配分だけを修正した。
- 引用付き5枚を生成する回帰テストを追加し、44件成功。ビューアー用の生成物は `artifacts/eggs/` に保存し、Git対象外。

## Macでの修復警告と手本PDFの差し替え

- Microsoft公式 `DocumentFormat.OpenXml` 3.5.1（.NET SDK 8.0.426/ARM64）で原本を読み取り専用検証し、XMLエラー0件。修正前の抽出テンプレートは118件、卵デモは95件だった。
- 原因は文字書式を結合する際の `a:latin/a:ea/a:cs` の順序と `a:buClrTx` の重複。抽出処理を修正し、原本の両マスター・テーマのバイト一致を維持。18レイアウトの位置・文字・書式属性も変更せず、要素順序と同一重複だけを修正した。
- 追加検査でグラフ軸IDの負数を検出。棒・折れ線・散布図の定義と全参照を、UInt32とOfficeのInt32上限を満たす正整数へ揃えた。
- 修正後は抽出テンプレート、卵5枚、図表6枚、折れ線、散布図の5ファイル全てでSDKエラー0件。`artifacts/compatibility/openxml-before.json` / `openxml-after.json` に記録。
- 回帰テストを追加し、既存のグラフ3種類のテストを拡張。全45件成功。CIでもMicrosoft SDKによる検証を必須にした。これはOffice実機での無警告・描画一致の確認とは別。
- ユーザーの新PDFは28ページ、4,623,928 bytes、SHA-256 `b9547268fc0a86d077de6514bdcee3dd3701491be6a12f03851b72dcff179d16`。CreatorがPowerPoint、ProducerがmacOS Quartzで、游ゴシック等のサブセット埋め込みを確認。全28ページの本文・画像を確認し、内容ルール12項目のIDと根拠ページを維持して参照元を更新。
- LibreOffice出力には `fidelity: approximate` と `powerpoint_verified: false` を付け、ローカルビューアーでも参考表示を明示。最終PDFは正しく表示されるPowerPointから書き出す運用とする。詳細は [互換性調査](docs/POWERPOINT_COMPATIBILITY.md)。

## 教授の文章ガイドラインの取り込み

- 2025-12-02更新の提供テキストを `reference_materials/guidelines/` に原文のまま保存。19,270 bytes、SHA-256 `65a51981aa99ffd2867f665858d9c33986c7b1c784950a33d33fd0b21482451e`。
- 明示事項を19項目に整理し、必須・目安・推奨・条件付き指示を区別。研究発表の表紙直後の概要を採用し、例示のp1～p22を固定枚数にはしない。
- 旧引用表記を教授指定の ` [著者 '25]` に変更し、内部の4桁年と著者情報は保持。複数引用間の空白も統一。
- ネイティブ表を塗りなし・見出し上下の黒罫線・本文の白罫線・文字左/数値右へ変更。数値の丸めや並替を行わない。本文・図形・表のテキスト自動調整はオフを明示。
- 引用の3ケースと表のネイティブ構造・罫線・数値保持・左右揃えの回帰試験を追加。全49件成功。両Skillの公式quick_validate成功。
- テンプレート・卵デモ・図表デモをMicrosoft Open XML SDKで検証し、全て0件。テンプレートはダミー引用文字列のみ更新し、マスター・テーマ・レイアウトは維持。
- Dockerイメージを更新し、表・引用を反映した5枚のPPTXと全頁PDF/PNGを確認。`artifacts/eggs-guidelines/` はこの2点の見本で、研究発表用の全指示への自動適合を示すものではない。
- 動画編集、グラフの直接ラベル等の未対応機能、PowerPointでの最終仕上げ、人による発表練習・発表可の確認は別途必要として記録。

## 再実行

```bash
uv sync --frozen
cd ui
npm ci --ignore-scripts
npm run build
cd ..
uv run ruff check src tests scripts
uv run pytest -q
uv run rsa demo --render
uv run rsa demo --slides 40 --output artifacts/forty.pptx --render
```

HTTP試験はloopbackのlisten権限が必要です。ネットワーク禁止sandboxでは実接続試験だけがPermissionErrorになります。この開発では許可されたローカル環境で実行しました。

## 未検証・未実装

| 項目 | 状態 |
|---|---|
| 実研究室マスター/フォント/多様なレイアウト | 実見本から5種類を抽出しPiで検証。フォント代替とOffice実機の確認は残る |
| Microsoft PowerPointで開く・図形やグラフを手編集 | 実機未検証。OPC構造とLibreOfficeで確認 |
| Raspberry Pi本体での40枚の時間・最大RSS・熱 | 合成40枚の時間とプロセス別最大RSSを実測。熱・本番コンテナは未計測 |
| Google login→認可サーバー→ChatGPT OAuth | 認証情報/公開endpoint未提供のため未検証 |
| MCP Inspector画面での手動接続 | 未実施。公式Python Clientの実HTTP試験で代替 |
| ChatGPTのScan Tools、fileParamsの実添付、MCP Apps iframe | 未検証。fallback uploadあり |
| ChatGPTから自然言語の2段階承認一連フロー | 実ChatGPT接続は未検証。サーバーの状態遷移を自動試験 |
| Portainer既存環境への配置・TLS・DNS・回線 | 配置手順とStackを作成。実deployは未実施 |
| native表/グラフ/SmartArt/複数runの部分編集 | 未対応。安全に拒否 |
| 共通過去資料の共有管理UI | 未実装。共有テンプレートのみ別領域 |
| 高度な描画差異・接続線交差・図表の意味の完全自動検査 | 未実装。構造検査・保守的文字fit・レンダリング・人のレビュー |
| GCP Run/Tasks/Firestore/Storage連携 | Pi優先につき未実装。deploy/GCP.mdに移行境界 |

## 完了条件との対応

1 ローカルMCP実接続: 検証済み。
2 マスター保持: 合成fixtureと教授の実見本で検証。原本の両マスター・テーマをバイト単位で保持。
3 編集可能性: native構造は検証済み、PowerPoint実機待ち。
4 ChatGPT承認フロー: サーバー自動試験済み、ChatGPT接続待ち。
5 指定ページ修正: 単純text shapeで検証済み。
6 ユーザー分離: 所有権/トークン/URLを試験済み、実IdP待ち。
7 非同期生成・再試行: SQLite backendで検証済み。
8 全ページpreview: 5枚/40枚を検証済み。
9 自動検査・安全な修正: 実装範囲は検証済み、全品質項目の自動判定には未到達。
10 自動テスト: 実行済み。

Phase 1のPoCとPi向けの基礎実装が動く状態であり、外部認証・実クライアント・実機を含む製品完成ではありません。
