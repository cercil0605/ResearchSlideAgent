# Research Slide Agent

研究室の既存マスターを維持し、編集可能な研究発表PPTXを生成するPython/MCPアプリです。追加のLLM APIは呼びません。意味的な構成・文章はChatGPTが作り、サーバーが配置と承認・生成を管理します。

**現状はローカル検証済みの初期実装です。実研究室マスター、Google連携したOAuth、ChatGPT内UI、Raspberry Pi実機、Microsoft PowerPointでの受入試験は未実施です。全要件の完成を宣言する段階ではありません。** 詳細は [TESTING.md](TESTING.md)。

## Raspberry Piでの採用構成

Portainer Stackで `api` と `worker` を常駐。SQLite WALの永続キューとDocker volumeに状態・資料を保存します。Cloud Tasks/Firestore/Storageの代替です。生成とLibreOfficeはARM64コンテナで実行します。まずワーカー並列数1、研究室上限2を維持します。

GitHub Actionsはテストと `linux/arm64,linux/amd64` のイメージ作成・GHCR登録に使います。Portainerで検証済みコミットタグを指定して更新します。研究資料をActionsのジョブ入力や成果物に送る構成にはしていません。

推奨する開始条件はPi 5、64-bit OS、RAM 8 GB、SSD、冷却です。これは設計上の目安であり実測要件ではありません。Pi 4/4 GBでもワーカー1件なら試験対象になりますが、40枚のレンダリング時間とメモリは実機で測ってください。[運用方法の比較](docs/RASPBERRY_PI.md)。

## ローカル起動

Python 3.12以上、uv、Node.js 22、LibreOffice、Popplerが必要です。

```bash
uv sync --frozen
cd ui
npm ci --ignore-scripts
npm run build
cd ..
uv run rsa demo --render
uv run pytest -q
```

`artifacts/demo.pptx` と `artifacts/preview/slide-1.png`〜5が生成されます。数値はソフトウェア試験用の合成データです。研究事実や架空の参考文献として使わないでください。

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

### 実マスターへの差し替え

`examples/lab-template.pptx` はマスターに検証用フッターを持つ合成テンプレートです。実際のPPTXを `templates/lab-template.pptx` などに配置し、`RSA_TEMPLATE` で指定してください。テンプレートからマスターを描き直す実装ではありません。

```bash
RSA_TEMPLATE=/absolute/path/lab-template.pptx RSA_DEV=1 uv run rsa serve
```

ワーカーにも同じ設定を指定。`get_template_info` が返す本文とタイトルのプレースホルダーを持つlayout_idを選びます。テンプレートを変更したら仕様を新しいバージョンで保存して再承認してください。内容が収まらない場合は自動縮小せず、最大2回の領域拡張後に停止してページ分割を求めます。

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
2. 実マスターをPiの `/srv/research-slide-agent/lab-template.pptx` へ配置。
3. [OAuth設定](deploy/AUTH.md) とHTTPSリバースプロキシを用意。
4. Portainerの **Stacks → Add stack → Web editor** に `deploy/portainer-stack.yml` を貼り付け、`.env.example` の値を環境変数として設定してDeploy。
5. サーバーと同じPiホストのリバースプロキシから `127.0.0.1:8000` に転送。別コンテナのプロキシを使う場合は同じDockerネットワークに接続し `api:8000` に転送するようStackを変更します。

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
| `RSA_TEMPLATE_HOST` | Piホスト上の実マスターパス |

## 対応範囲と制約

- 最大40枚、10ファイル、各20 MiB、合計100 MiB。ユーザー同時ジョブ1、研究室実行上限2。
- PDF/PPTX/PNG/JPEG/UTF-8 CSV/XLSX。資料抽出は1回24,000文字まで。画像PDFのOCRは未対応。
- 1枚1種の図表。フロー・システム・比較・タイムライン、ネイティブ表、棒/折れ線/散布図。
- 部分修正は、明示フォントを持つ単純なトップレベルのテキスト図形のみ。複数ラン・グループ・SmartArt・表/グラフの部分更新は停止する。
- 再生成はマスターから作り直します。手動編集を維持したいときは再アップロードと部分修正を使います。
- 文字幅検査は保守的な推定。図形接続・領域・重なり・引用・元データ・承認済み本文の構造検査とレンダリング実行を行いますが、図の意味や描画品質を完全自動判定しません。
- 構成・各ページ・部分修正の承認はバージョンとハッシュに紐付く。`approved=true` はスキーマ違反。
- プロジェクト作成から7日で拒否・削除。共有テンプレートは対象外。
- GCP版は今回のPi優先方針により未実装。[移行時の要件](deploy/GCP.md)。このSQLite版をそのままCloud Runに配置してはいけません。

設計: [ARCHITECTURE.md](ARCHITECTURE.md) / API: [API.md](API.md) / セキュリティ: [SECURITY.md](SECURITY.md) / 判断記録: [ADR](docs/adr/) / 検証: [TESTING.md](TESTING.md)。
