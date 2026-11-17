# リモート構成（ChatGPT・Raspberry Pi・Portainer）

公開サーバーとして運用する場合の手順です。自分のPCだけで使うなら [README](../README.md) のローカルモードで足ります。

## Raspberry Piでの採用構成

Portainer Stackで `api` と `worker` を常駐。SQLite WALの永続キューとDocker volumeに状態・資料を保存します。Cloud Tasks/Firestore/Storageの代替です。生成はARM64コンテナで実行します。まずワーカー並列数1、研究室上限2を維持します。

GitHub Actionsはテストと `linux/arm64,linux/amd64` のイメージ作成・GHCR登録に使います。Portainerで検証済みコミットタグを指定して更新します。研究資料をActionsのジョブ入力や成果物に送る構成にはしていません。

1人利用はCloudflare Tunnel + AccessのManaged OAuthを推奨します。Accessで自分のメールだけを許可し、ChatGPTと資料登録ブラウザの本人確認をまとめます。
別のOAuthサーバーは不要です。`.env.example` にイメージ・公開URL・認証方式・Accessチームドメイン／AUD・セッション鍵を設定します。利用者の許可はCloudflare Accessポリシーで管理します。
Cloudflareの画面設定と初回のChatGPTログインは [deploy/AUTH.md](../deploy/AUTH.md) を参照してください。

推奨する開始条件はPi 5、64-bit OS、RAM 8 GB、SSD、冷却です。これは設計上の目安であり実測要件ではありません。Pi 4/4 GBでもワーカー1件なら試験対象になりますが、40枚の生成時間とメモリは実機で測ってください。[運用方法の比較](RASPBERRY_PI.md)。

## ChatGPTとPlugin

`plugins/research-slide-agent/` にportable `plugin.json`、`mcp.json`、Skillがあります。`.agents/plugins/marketplace.json` はこのリポジトリ内のローカルカタログです。個人設定や他のPluginは変更しません。

文書の読み分けは [ドキュメント案内](README.md)、作成・更新の流れは [利用シーン](USER_USE_CASES.md) を参照してください。

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
見出しと本文の良い例・避ける例、原図と説明図の使い分けは、[制作ワークフローのF01–F06](../plugins/research-slide-agent/skills/research-slides/references/authoring-workflow.md#初回制作の手順)にまとめています。
同じ4文書をMCP単体・完全なPluginへ配信し、追加のLLM APIは使いません。個々のLLMの理解・遵守や品質の一致を保証するものではありません。
文字の文中切断、図題だけで原図を置いた扱い、ダミー見出しの放置を避け、収まらなければ説明を保って分割します。
本文先頭の箇条書き記号は正本と重複する場合に拒否します。項目テキストだけを入力してください。
Strictの図枠内では、手順・分岐・集約を編集可能なノードと接続線で表せます。
共有マスター・本文書式は維持し、本文領域の配置はサーバーが定義します。原論文のPDFページ画像化・cropにも対応しています。

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
エラーをMCPログインの失敗と一括りにせず、[転送エラーの切り分け](../API.md#pdfの転送原図)を参照します。
予備の `create_upload.browser_url` は複数ファイルの手動登録に対応します。Cloudflare方式のPUT URLは別途Access本人認証も必要です。
配備後は接続をRefreshし、新しいチャットで実際の添付PDF転送を確認してください。コード試験は本番疎通を保証しません。

## Portainerへの配置

詳細は [deploy/PORTAINER.md](../deploy/PORTAINER.md)。最短の流れ:

1. `.github/workflows/ci.yml` で作成するイメージを使うか、Piで `docker build -t research-slide-agent:local .`。
2. 実マスターはイメージ同梱のものを使用。ホストへの別配置は不要です。
3. [Cloudflare Access設定](../deploy/AUTH.md) とTunnelを用意。既存の認可サーバーを使う場合は同文書の従来OAuth方式を参照。
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
