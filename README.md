# Research Slide Agent

研究室の既存マスターを維持し、編集可能な研究発表PPTXを生成するPython/MCPアプリです。追加のLLM APIは呼びません。意味的な構成・文章はChatGPTが作り、サーバーが配置と承認・生成を管理します。

**修正版スケルトンを正本にしてページを複製し、内容を差し替えます。LibreOfficeプレビューと書式検査に対応しています。Google連携したOAuth、リモートChatGPT内UI、Microsoft PowerPointでの受入試験は未実施です。** 詳細は [TESTING.md](TESTING.md)。

Macで修復を求められたPPTXの不正XMLを修正し、Microsoft公式SDKによる検証をCIへ追加しました。
PiのPDFプレビューは参考表示です。正しいフォントと表を保つ最終PDFはPowerPointから書き出してください。
[原因・修正内容・見た目を保つ運用](docs/POWERPOINT_COMPATIBILITY.md)。

## フォルダとGit管理

| 場所 | 用途・扱い |
|---|---|
| `src/`、`ui/` | サーバーとビューアーの実装。Git管理 |
| `templates/` | 実行用の正本PPTXと対応表JSONをGit管理し、Dockerへ同梱。プレビューPDF／JSONは生成物でGit対象外 |
| `plugins/`、`.agents/` | 配布用Plugin・Skillと開発用Skill。Git管理 |
| `examples/` | 再生成できる入力JSON・出典メモ・試験CSV。Git管理。合成デモ用PPTXは実行時に生成 |
| `scripts/`、`tests/`、`schemas/`、`tools/` | 開発・検証用。ソースと仕様はGit管理、ビルド結果は対象外 |
| `reference_materials/` | 教授のガイドラインとルールの根拠。原文テキストはGit管理、提供されたPDF・PPTXは対象外 |
| `artifacts/` | ローカル生成PPTX・描画画像・検証ログ。READMEだけGit管理。サーバー実行には不要 |
| `var/` | ローカルサーバーの資料・ジョブ・DB。Git対象外。生成物の一時置き場とは分ける |

`artifacts/`のデータは必要な成果物を保存した後に削除できます。現在は修正版の生成例と検証記録だけを残しています。
詳細と再生成コマンドは [artifacts/README.md](artifacts/README.md)。
`.venv/`、Pythonのキャッシュ、`ui/node_modules/`、Open XML検証器の`bin/obj`もGit対象外です。

## Raspberry Piでの採用構成

Portainer Stackで `api` と `worker` を常駐。SQLite WALの永続キューとDocker volumeに状態・資料を保存します。Cloud Tasks/Firestore/Storageの代替です。生成とLibreOfficeはARM64コンテナで実行します。まずワーカー並列数1、研究室上限2を維持します。

GitHub Actionsはテストと `linux/arm64,linux/amd64` のイメージ作成・GHCR登録に使います。Portainerで検証済みコミットタグを指定して更新します。研究資料をActionsのジョブ入力や成果物に送る構成にはしていません。

推奨する開始条件はPi 5、64-bit OS、RAM 8 GB、SSD、冷却です。これは設計上の目安であり実測要件ではありません。Pi 4/4 GBでもワーカー1件なら試験対象になりますが、40枚のレンダリング時間とメモリは実機で測ってください。[運用方法の比較](docs/RASPBERRY_PI.md)。

## ローカル起動

プラグインなしで完成例を見るには、イメージをビルドした後に `bash scripts/try_eggs.sh` を実行します。
「美味しい卵の食べ方」5枚を実マスターで生成し、`artifacts/canonical-eggs/index.html` でページ切替、PDF閲覧、PPTX取得ができます。
OAuthやサーバー起動は不要です。[題材・出典・再実行方法](examples/eggs.sources.md)。

Pythonで開発・起動する場合は、Python 3.12以上、uv、Node.js 22、LibreOffice、Popplerが必要です。

```bash
uv sync --frozen
cd ui
npm ci --ignore-scripts
npm run build
cd ..
uv run python scripts/render_spec.py examples/research-format.slidespec.json --output artifacts/canonical-research --render
uv run pytest -q
```

`artifacts/canonical-research/` に正本書式のPPTX・PDF・全13ページの画像が生成されます。数値はソフトウェア試験用で、研究事実を主張するものではありません。
旧生成経路の合成デモが必要な場合だけ `uv run rsa demo --render` を使います。その合成テンプレートも `artifacts/` に生成されます。

ターミナルを2つ開いて、同じディレクトリで起動します。

```bash
RSA_DEV=1 uv run rsa serve
```

```bash
RSA_DEV=1 uv run rsa worker
```

MCP: `http://127.0.0.1:8000/mcp`。開発時のみloopbackから `dev-user` として利用できます。公開URLや `RSA_ENV=production` と開発認証の併用は起動を拒否します。

### MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

Inspectorで **Streamable HTTP**、URL `http://127.0.0.1:8000/mcp` を指定し接続します。公式MCP SDK 2.3.0のClientによるlegacy/auto両方式の実HTTP接続試験は `tests/test_mcp.py` で実行できます。Inspector UIの手操作は未実施です。

### 修正版スケルトンを使う生成

正本はユーザー修正版「学会発表スケルトン.pptx」。同一バイトのコピーを `templates/lab-template.pptx` として同梱しています。
マスターだけでなく見本ページ全体を複製し、直接書式・段落・表を保持します。
仕様はSlideSpec 1.1。`get_template_info.prototypes` から役割と差し替え欄を選びます。
研究発表は表紙→概要→背景→関連研究→目的→手法→実験→結果→考察→まとめを維持し、必要なページを複製できます。

優先順位はユーザー指示、修正版、教授のガイドライン、過去PDFの推定です。
表は修正版の中央揃え・最下段黒罫線・見出し／本文の行高と文字書式を保持し、少ない行数でも引き伸ばしません。
収まらない場合は短縮・分割を求めます。表の色・罫線・文字サイズ等の改変を検査で検出します。

```bash
uv run python scripts/prepare_skeleton_template.py --render-preview
uv run python scripts/render_spec.py examples/eggs.slidespec.json --output artifacts/canonical-eggs --render
uv run python scripts/render_spec.py examples/research-format.slidespec.json --output artifacts/canonical-research --render
```

正本とprofileはGit管理してDockerに同梱するため、生成時に元の添付ファイルは不要です。
元の「学会発表スケルトン.pptx」と旧卵例は、内容を変えず `reference_materials/local-inputs/` へ保管しています（Git対象外）。
新しいスケルトンを登録する場合だけ `--source /path/to/new-skeleton.pptx` を指定します。
`RSA_TEMPLATE`で変更する場合は対応するprofileも指定先に置き、サーバーとワーカーで同じ正本を使います。
旧schema 1.0と合成テンプレートは従来試験用に保持しますが、新しい正本では1.1を要求します。
詳細なページ対応・入力・制約は [書式テンプレートと発表内容ルール](docs/TEMPLATE_AND_CONTENT_RULES.md)。

`get_generation_report`でコードコミット・ソースハッシュ・正本SHA・仕様版と書式検査を取得できます。
`get_preview_image`はURLではなくPNGのMCP imageコンテンツをモデルへ返します。
全ページの画像を実際に確認し、修正が必要なら短縮／分割して再生成します。URLの表示だけでは確認済みと扱いません。
LibreOfficeは参考表示で、PowerPoint実機による確認は別途必要です。

## ChatGPTとPlugin

`plugins/research-slide-agent/` にportable `plugin.json`、`mcp.json`、Skillがあります。`.agents/plugins/marketplace.json` はこのリポジトリ内のローカルカタログです。個人設定や他のPluginは変更しません。

1. ローカルクライアントではこのリポジトリをローカルmarketplaceとして追加し、Research Labからインストールします。利用できる面はアカウント・クライアントに依存します。
2. ChatGPTからリモート接続する場合は、PiのAPIを公開HTTPSにし、OAuthを設定します。`localhost` はChatGPTのクラウドから到達できません。
3. [ChatGPT Plugins](https://chatgpt.com/plugins) の **Add custom MCP server** でHTTPSの `/mcp`、事前登録したOAuthクライアントIDなどを設定。画面に表示された正確なredirect URIを認可サーバーに登録します。
4. `uv run python scripts/configure_plugin.py --url https://slides.example.org/mcp` で配布パッケージの接続先を更新。登録済み技術IDが得られた場合だけ `--app-id plugin_asdk_app...` を追加すると `.app.json` を生成します。
5. 新しいチャットでSkillを呼び、構成承認→各ページ承認→生成→プレビュー→部分修正を受入試験します。

サーバーが返す承認URLはユーザー自身の認証済みブラウザで開きます。モデルは承認APIを呼びません。UI非対応クライアントはツール結果にある状態・プレビュー・ダウンロードURLを利用できます。

ファイル連携は公式 `openai/fileParams` を宣言しています。ただし実際のChatGPTから渡されるホストは未確認です。`RSA_ATTACHMENT_HOSTS` に管理者が確認した正確なホスト名を設定するまで外部ダウンロードを拒否します。代わりに `create_upload` の `browser_url` で直接アップロードできます。著者・年は同じページでユーザーが確認して保存します。

## Portainerへの配置

詳細は [deploy/PORTAINER.md](deploy/PORTAINER.md)。最短の流れ:

1. `.github/workflows/ci.yml` で作成するイメージを使うか、Piで `docker build -t research-slide-agent:local .`。
2. 実マスターはイメージ同梱のものを使用。ホストへの別配置は不要です。
3. [OAuth設定](deploy/AUTH.md) とHTTPSリバースプロキシを用意。
4. Portainerの **Stacks → Add stack → Web editor** に `deploy/portainer-stack.yml` を貼り付け、`.env.example` の値を環境変数として設定してDeploy。
5. サーバーと同じPiホストのリバースプロキシまたはCloudflare Tunnelから `127.0.0.1:8010` に転送。Portainerの8000番との競合を避けています。別コンテナのプロキシを使う場合は同じDockerネットワークに接続し `api:8000` に転送するようStackを変更します。

GitHubへのpush、GHCRへの公開、Piへの接続、Portainer更新、Google認証設定はこの開発では実施していません。

## 環境変数

| 変数 | 内容 |
|---|---|
| `RSA_DEV` | `1` はloopback限定開発モード。既定`0` |
| `RSA_ENV` | Dockerでは`production`固定 |
| `RSA_DATA_DIR` | 状態DB・資料・出力の保存場所。既定`var` |
| `RSA_TEMPLATE` | 固定マスターのPPTXパス |
| `RSA_BASE_URL` | 公開HTTPSのorigin。開発は`http://127.0.0.1:8000` |
| `RSA_OAUTH_ISSUER` | Google連携する認可サーバーの正確なissuer |
| `RSA_JWKS_URL` | 同サーバーのHTTPS JWKS |
| `RSA_OAUTH_AUDIENCE` | MCP用のaudience。例`https://slides.example.org/mcp` |
| `RSA_WEB_CLIENT_ID` | ブラウザ承認用OAuthクライアントID |
| `RSA_ALLOWED_SUBS` | 認可サーバーの許可済み安定subをカンマ区切り |
| `RSA_SESSION_KEY` | 32文字以上のランダム値。API再起動でも維持する |
| `RSA_ATTACHMENT_HOSTS` | 添付ファイルの取得元ホストの完全一致リスト。空なら直接取込不可 |
| `RSA_WORKER_LIMIT` | 1または2。Piは1を推奨 |
| `RSA_IMAGE` | Compose/Portainerで利用するイメージ |

## 対応範囲と制約

- 最大40枚、10ファイル、各20 MiB、合計100 MiB。ユーザー同時ジョブ1、研究室実行上限2。
- PDF/PPTX/PNG/JPEG/UTF-8 CSV/XLSX。資料抽出は1回24,000文字まで。画像PDFのOCRは未対応。
- 正本の1.1経路は、3列・本文最大3行のネイティブ表、簡単な配置図、元画像に対応します。旧1.0経路のグラフ等は合成デモ・互換性試験用です。
- 部分修正は、明示フォントを持つ単純なトップレベルのテキスト図形のみ。複数ラン・グループ・SmartArt・表/グラフの部分更新は停止する。
- 再生成は正本の見本ページを複製します。手動編集を維持したいときは再アップロードと部分修正を使います。
- 文字幅検査は保守的な推定。図形接続・領域・重なり・引用・元データ・承認済み本文の構造検査とレンダリング実行を行いますが、図の意味や描画品質を完全自動判定しません。
- 構成・各ページ・部分修正の承認はバージョンとハッシュに紐付く。`approved=true` はスキーマ違反。
- プロジェクト作成から7日で拒否・削除。共有テンプレートは対象外。
- GCP版は今回のPi優先方針により未実装。[移行時の要件](deploy/GCP.md)。このSQLite版をそのままCloud Runに配置してはいけません。

設計: [ARCHITECTURE.md](ARCHITECTURE.md) / API: [API.md](API.md) / セキュリティ: [SECURITY.md](SECURITY.md) / 判断記録: [ADR](docs/adr/) / 検証: [TESTING.md](TESTING.md)。
