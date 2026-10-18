# Research Slide Agent

研究室の既存マスターを維持し、編集可能な研究発表PPTXを生成するPython/MCPアプリです。追加のLLM APIは呼びません。意味的な構成・文章は接続先LLMが作り、サーバーが配置と生成を管理します。

**修正版スケルトンを正本にしてページを複製し、内容を差し替えます。PPTX生成と構造検査の成功でcompletedとなり、ダウンロードリンクを返します。承認・プレビュー・モデルによる画像確認は不要です。Cloudflare Access／外部OAuth、リモートChatGPT内UI、Microsoft PowerPointでの受入試験は未実施です。** 詳細は [TESTING.md](TESTING.md)。

Macで修復を求められたPPTXの不正XMLを修正し、Microsoft公式SDKによる検証をCIへ追加しました。
正しいフォントと表を保つ最終PDFはPowerPointから書き出してください。
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
既存DBのリセットは不要です。旧承認テーブル／列を保持し、生成条件から除外しています。
詳細と再生成コマンドは [artifacts/README.md](artifacts/README.md)。
`.venv/`、Pythonのキャッシュ、`ui/node_modules/`、Open XML検証器の`bin/obj`もGit対象外です。

## Raspberry Piでの採用構成

Portainer Stackで `api` と `worker` を常駐。SQLite WALの永続キューとDocker volumeに状態・資料を保存します。Cloud Tasks/Firestore/Storageの代替です。生成はARM64コンテナで実行します。まずワーカー並列数1、研究室上限2を維持します。

GitHub Actionsはテストと `linux/arm64,linux/amd64` のイメージ作成・GHCR登録に使います。Portainerで検証済みコミットタグを指定して更新します。研究資料をActionsのジョブ入力や成果物に送る構成にはしていません。

1人利用はCloudflare Tunnel + AccessのManaged OAuthを推奨します。Accessで自分のメールだけを許可し、ChatGPTと資料登録ブラウザの本人確認をまとめます。
別のOAuthサーバーは不要です。`.env.example` にイメージ・公開URL・認証方式・Accessチームドメイン／AUD・許可メール・セッション鍵を設定します。
Cloudflareの画面設定と初回のChatGPTログインは [deploy/AUTH.md](deploy/AUTH.md) を参照してください。

推奨する開始条件はPi 5、64-bit OS、RAM 8 GB、SSD、冷却です。これは設計上の目安であり実測要件ではありません。Pi 4/4 GBでもワーカー1件なら試験対象になりますが、40枚の生成時間とメモリは実機で測ってください。[運用方法の比較](docs/RASPBERRY_PI.md)。

## ローカル起動

プラグインなしで完成例を見るには、イメージをビルドした後に `bash scripts/try_eggs.sh` を実行します。
「美味しい卵の食べ方」5枚のPPTXを実マスターで生成します。
OAuthやサーバー起動は不要です。[題材・出典・再実行方法](examples/eggs.sources.md)。

Pythonで開発・起動する場合は、Python 3.12以上、uv、Node.js 22が必要です。

```bash
uv sync --frozen
cd ui
npm ci --ignore-scripts
npm run build
cd ..
uv run python scripts/render_spec.py examples/research-format.slidespec.json --output artifacts/canonical-research
uv run pytest -q
```

`artifacts/canonical-research/` に正本書式のPPTXが生成されます。数値はソフトウェア試験用で、研究事実を主張するものではありません。
旧生成経路の合成デモが必要な場合だけ `uv run rsa demo` を使います。その合成テンプレートも `artifacts/` に生成されます。

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
uv run python scripts/prepare_skeleton_template.py
uv run python scripts/render_spec.py examples/eggs.slidespec.json --output artifacts/canonical-eggs
uv run python scripts/render_spec.py examples/research-format.slidespec.json --output artifacts/canonical-research
```

正本とprofileはGit管理してDockerに同梱するため、生成時に元の添付ファイルは不要です。
元の「学会発表スケルトン.pptx」と旧卵例は、内容を変えず `reference_materials/local-inputs/` へ保管しています（Git対象外）。
新しいスケルトンを登録する場合だけ `--source /path/to/new-skeleton.pptx` を指定します。
`RSA_TEMPLATE`で変更する場合は対応するprofileも指定先に置き、サーバーとワーカーで同じ正本を使います。
旧schema 1.0と合成テンプレートは従来試験用に保持しますが、新しい正本では1.1を要求します。
詳細なページ対応・入力・制約は [書式テンプレートと発表内容ルール](docs/TEMPLATE_AND_CONTENT_RULES.md)。

`get_generation_report`でコードコミット・ソースハッシュ・正本SHA・仕様版と書式検査を取得できます。
`get_job` はcompleted時に期限付き `download_url` を返します。
プレビューの生成・表示・モデルによる画像確認は行いません。構造検査はPowerPoint実機での表示確認を意味しません。

## ChatGPTとPlugin

`plugins/research-slide-agent/` にportable `plugin.json`、`mcp.json`、Skillがあります。`.agents/plugins/marketplace.json` はこのリポジトリ内のローカルカタログです。個人設定や他のPluginは変更しません。

文書の読み分けは [ドキュメント案内](docs/README.md)、作成・更新の流れは [利用シーン](docs/USER_USE_CASES.md) を参照してください。

### MCPだけを接続する場合

1. Cloudflare TunnelでPiのAPIを公開HTTPSにし、Accessで本人だけを許可してManaged OAuthを有効にします。`localhost` はChatGPTのクラウドから到達できません。
2. [ChatGPT Plugins](https://chatgpt.com/plugins) の **Add custom MCP server** でHTTPSの `/mcp` をOAuth接続として登録します。CloudflareのDCRと、画面に表示された正確なredirect URIの許可を設定します。初回接続／ツール利用時にAccessの画面でログインします。
3. サーバー更新後は接続の **Refresh** を実行し、新しいチャットで `get_authoring_context` が利用できることを確認します。
4. 構成作成より先に同ツールを呼び、`required_documents` の4文書を全文取得してから `get_template_info` →仕様保存→生成を試します。

MCP URLの登録は、GitHubにあるSkillパッケージを自動インストールしません。MCP単体の利用者にはserver instructionsと
`get_authoring_context`が制作手順・教授ルール・過去資料の説明規則・正本の入力手順を提供します。
`get_profile`は本人ID、`get_template_info`は書式情報であり、制作ルールの取得には使いません。

### Skillを含む完全なPluginを使う場合

1. `uv run python scripts/configure_plugin.py --url https://slides.example.org/mcp` で配布パッケージの接続先を更新します。登録済み技術IDが得られた場合だけ `--app-id plugin_asdk_app...` を追加し、既存接続のmappingを生成します。このスクリプトはSkillのインストール・公開を行いません。
2. 対応クライアントでこのリポジトリをローカルmarketplaceとして追加し、Research Labから完全なPluginをインストールします。利用できる面はアカウント・クライアントに依存します。
3. 新しいチャットでSkillを呼び、まず `get_authoring_context` の全文取得が実行されることを確認します。同梱Skillは取得手順を教える入口で、接続中はサーバー返却版を使います。

教授・過去資料・正本入力手順・制作ワークフローの編集上の正本は、Skillの `references/` です。
サーバーの開発実行は同じファイルを読み、wheel/Dockerにはビルド時に同じ内容を同梱します。別のルールコピーを手編集しません。
`research-slides://authoring-context` Resourceも同じloaderの結果を返しますが、Resourceの自動読込は前提にしません。
文書SHA・`rules_digest`は取得した版の識別用で、モデルが理解・遵守した証明ではありません。

おまかせ制作はAutonomous（中間承認なし）、相談する制作はCollaborative（会話で構成・粒度に合意してから生成）です。
初回制作は、読解→説明設計→図表選定→文章化→保存前の自己点検を共通手順とします。
専門外の研究者・学生を既定の聴衆とし、手法の入力・処理・出力、実験の目的・比較・指標を説明します。
作成枚数は見込みの目安です。説明の粒度を優先し、必要な説明は削らずページを分けます。
厳密な枚数指定・発表時間・処理上限は、それぞれ別の制約として扱います。
見出しと本文の良い例・避ける例、原図と説明図の使い分けは、[制作ワークフローのF01–F06](plugins/research-slide-agent/skills/research-slides/references/authoring-workflow.md#初回制作の手順)にまとめています。
同じ4文書をMCP単体・完全なPluginへ配信し、追加のLLM APIは使いません。個々のLLMの理解・遵守や品質の一致を保証するものではありません。
文字の文中切断、図題だけで原図を置いた扱い、ダミー見出しの放置を避け、収まらなければ説明を保って分割します。
本文先頭の箇条書き記号は正本と重複する場合に拒否します。項目テキストだけを入力してください。
Strictの図枠内では、手順・分岐・集約を編集可能なノードと接続線で表せます。
図枠・共有マスター・本文書式は維持し、図枠内の描画規則だけを更新しました。原論文のPDFページ画像化・cropにも対応しています。

制作ルールの更新はサーバーの再ビルド・再配置で反映します。MCPメタデータ変更時はRefreshし、Skillの入口やツール契約を変える場合は
完全なPluginも更新します。公開済みPluginは配布先の版更新・審査手順に従います。

新規生成・再生成・PPTXパッチに承認は不要です。MCP Apps UIは状態とPPTX取得を表示します。

ファイル連携は公式 `openai/fileParams` を使います。`get_file_transfer_info` で設定を確認し、
`register_chatgpt_file` で論文PDFを一度登録します。著者・年は論文から確認して同時に渡すか、
`set_source_metadata` で設定できます。図ごとに入力する必要はありません。
`render_pdf_page` の実画像を見て接続先LLMが図の領域を選び、`crop_pdf_region` がPNGを登録します。
画像IDは既存の `image_references` でPPTXへ配置し、元PDFを引用します。切り直しでもPDFの再転送は不要です。

Compose/Portainerは `RSA_ATTACHMENT_HOSTS` が未設定なら `*.oaiusercontent.com` を使い、明示的な空文字なら直接取込を無効化します。ChatGPT添付には `*.oaiusercontent.com` を指定します。
これはOpenAIがChatGPTのファイル用として案内するドメイン配下に限定され、URLごとの追加は不要です。
サーバーはHTTPS・443番・公開IPのみ許可し、リダイレクトは拒否します。Amazon/Azure全体等の広い許可や認証の解除はしないでください。
エラーをMCPログインの失敗と一括りにせず、[転送エラーの切り分け](API.md#pdfの転送原図)を参照します。
予備の `create_upload.browser_url` は複数ファイルの手動登録に対応します。Cloudflare方式のPUT URLは別途Access本人認証も必要です。
配備後は接続をRefreshし、新しいチャットで実際の添付PDF転送を確認してください。コード試験は本番疎通を保証しません。

## Portainerへの配置

詳細は [deploy/PORTAINER.md](deploy/PORTAINER.md)。最短の流れ:

1. `.github/workflows/ci.yml` で作成するイメージを使うか、Piで `docker build -t research-slide-agent:local .`。
2. 実マスターはイメージ同梱のものを使用。ホストへの別配置は不要です。
3. [Cloudflare Access設定](deploy/AUTH.md) とTunnelを用意。既存の認可サーバーを使う場合は同文書の従来OAuth方式を参照。
4. Portainerの **Stacks → Add stack → Web editor** に `deploy/portainer-stack.yml` を貼り付け、`.env.example` の値を環境変数として設定してDeploy。
5. サーバーと同じPiホストのリバースプロキシまたはCloudflare Tunnelから `127.0.0.1:8010` に転送。Portainerの8000番との競合を避けています。別コンテナのプロキシを使う場合は同じDockerネットワークに接続し `api:8000` に転送するようStackを変更します。

この変更でCloudflareの管理画面設定、GitHubへのpush、Portainerの更新は実施していません。外部接続の受入試験も別途必要です。

## 環境変数

| 変数 | 内容 |
|---|---|
| `RSA_DEV` | `1` はloopback限定開発モード。既定`0` |
| `RSA_ENV` | Dockerでは`production`固定 |
| `RSA_AUTH_MODE` | `cloudflare`でAccess認証。省略時`oauth`で従来方式を維持 |
| `RSA_CF_TEAM_DOMAIN` | Cloudflare方式のチームURL。例`https://lab.cloudflareaccess.com` |
| `RSA_CF_AUDIENCE` | Cloudflare AccessアプリのAUD Tag。公開URLとは別 |
| `RSA_ALLOWED_EMAILS` | Cloudflare方式の許可メール。1人利用は自分の1件を指定 |
| `RSA_DATA_DIR` | 状態DB・資料・出力の保存場所。既定`var` |
| `RSA_TEMPLATE` | 固定マスターのPPTXパス |
| `RSA_BASE_URL` | 公開HTTPSのorigin。開発は`http://127.0.0.1:8000` |
| `RSA_OAUTH_ISSUER` | 従来OAuth方式のみ。認可サーバーの正確なissuer |
| `RSA_JWKS_URL` | 従来OAuth方式のみ。同サーバーのHTTPS JWKS |
| `RSA_OAUTH_AUDIENCE` | 従来OAuth方式のみ。MCP用のaudience |
| `RSA_WEB_CLIENT_ID` | 従来OAuth方式のみ。資料登録ブラウザ用OAuthクライアントID |
| `RSA_ALLOWED_SUBS` | 従来OAuth方式のみ。認可サーバーの許可済み安定sub |
| `RSA_SESSION_KEY` | 32文字以上のランダム値。API再起動でも維持する |
| `RSA_ATTACHMENT_HOSTS` | 添付取得元のホスト許可リスト。完全一致名または `*.oaiusercontent.com` 形式。空なら直接取込不可 |
| `RSA_WORKER_LIMIT` | 1または2。Piは1を推奨 |
| `RSA_IMAGE` | Compose/Portainerで利用するイメージ |

## 対応範囲と制約

- 1ジョブの技術上限は40枚（推奨枚数ではない）。必要な説明が超える場合は省略せず制約を明示する。アップロード資料10件＋派生画像80件、各20 MiB、両者合計100 MiB。ユーザー同時ジョブ1、研究室実行上限2。
- PDF/PPTX/PNG/JPEG/UTF-8 CSV/XLSX。資料抽出は1回24,000文字まで。画像PDFのOCRは未対応。
- 正本の1.1経路は、3列・本文最大3行のネイティブ表、簡単な配置図、元画像に対応します。旧1.0経路のグラフ等は合成デモ・互換性試験用です。
- 部分修正は、明示フォントを持つ単純なトップレベルのテキスト図形のみ。複数ラン・グループ・SmartArt・表/グラフの部分更新は停止する。
- 再生成は正本の見本ページを複製します。手動編集を維持したいときは再アップロードと部分修正を使います。
- 文字幅検査は保守的な推定。図形接続・領域・重なり・引用・元データ・保存した本文の構造検査を行いますが、図の意味や描画品質を完全自動判定しません。
- 仕様・部分修正はバージョンとハッシュに紐付く。`approved=true` はスキーマ違反。
- プロジェクト作成から7日で拒否・削除。共有テンプレートは対象外。
- GCP版は今回のPi優先方針により未実装。[移行時の要件](deploy/GCP.md)。このSQLite版をそのままCloud Runに配置してはいけません。

設計: [ARCHITECTURE.md](ARCHITECTURE.md) / API: [API.md](API.md) / セキュリティ: [SECURITY.md](SECURITY.md) / 判断記録: [ADR](docs/adr/) / 検証: [TESTING.md](TESTING.md)。
