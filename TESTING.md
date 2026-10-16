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

pytestの最新件数と結果は `artifacts/test-results.txt` を参照。最終実行は39件成功。Starlette TestClient依存内のanyio BlockingPortalに関するDeprecationWarningが1件あります。

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
| 実研究室マスター/フォント/多様なレイアウト | 未提供のため未検証。合成マスターを使用 |
| Microsoft PowerPointで開く・図形やグラフを手編集 | 実機未検証。OPC構造とLibreOfficeで確認 |
| Raspberry Pi本体での40枚の時間・最大RSS・熱 | 未計測。ARM64 Linuxコンテナまで確認 |
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
2 マスター保持: 合成fixtureで検証済み、実マスター待ち。
3 編集可能性: native構造は検証済み、PowerPoint実機待ち。
4 ChatGPT承認フロー: サーバー自動試験済み、ChatGPT接続待ち。
5 指定ページ修正: 単純text shapeで検証済み。
6 ユーザー分離: 所有権/トークン/URLを試験済み、実IdP待ち。
7 非同期生成・再試行: SQLite backendで検証済み。
8 全ページpreview: 5枚/40枚を検証済み。
9 自動検査・安全な修正: 実装範囲は検証済み、全品質項目の自動判定には未到達。
10 自動テスト: 実行済み。

Phase 1のPoCとPi向けの基礎実装が動く状態であり、外部認証・実クライアント・実機を含む製品完成ではありません。
