# ローカルモードと開発（詳細）

最短の導入は [README](../README.md)。ここは他クライアントへの登録、Python直接実行、開発・検証の詳細です。

## 他のクライアントへの登録

| クライアント | 登録方法 |
|---|---|
| Claude Code | `make register AGENT=claude` |
| Codex CLI・ChatGPTデスクトップ（Codex／Workモード） | `make register AGENT=codex` |
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` の `mcpServers` に `{"research-slides": {"command": "<scriptの絶対パス>"}}` を追加して再起動 |
| Gemini CLI | `~/.gemini/settings.json` の `mcpServers` に同じ形で追加（`gemini mcp add` も利用可。本リポジトリでは未検証） |
| Cursor等 | 各アプリのMCP設定（stdio / command）に同じ内容を追加 |
| ChatGPT（Web・通常チャット） | **不可**。ChatGPTのクラウドから手元のstdioは呼べません。[リモート構成](REMOTE.md)を使います |

- 制作ルールはサーバーが `get_authoring_context` で配るため、Skillやプラグインのインストールは不要です。
- 「プラグイン」として配るものはなく、上のMCP登録が接続のすべてです。結果の品質は接続先モデルの長文読解・画像入力・JSON作成能力に依存します。
- 動作確認済みはCodex CLIです。Claude Codeは接続・生成まで確認しましたが、利用上限により完走を確認できていません。Claude Desktop・Gemini CLIは未検証です（[TESTING.md](../TESTING.md)）。
- Dockerを使わない場合・フォルダ変更などの詳細は下記「ローカルモード（stdio MCP）」を参照してください。

## 開発者向けの起動と検証

プラグインなしで完成例を見るには、イメージをビルドした後に `bash scripts/try_eggs.sh` を実行します。
「美味しい卵の食べ方」5枚のPPTXを実マスターで生成します。
OAuthやサーバー起動は不要です。[題材・出典・再実行方法](../examples/eggs.sources.md)。

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
`uv run rsa demo` も同じ正本とSlideSpec 1.3を使う一般向けの試験例です。

ターミナルを2つ開いて、同じディレクトリで起動します。

```bash
RSA_DEV=1 uv run rsa serve
```

```bash
RSA_DEV=1 uv run rsa worker
```

MCP: `http://127.0.0.1:8000/mcp`。開発時のみloopbackから `dev-user` として利用できます。公開URLや `RSA_ENV=production` と開発認証の併用は起動を拒否します。

### ローカルモード（stdio MCP）

公開サーバー・Cloudflare・OAuthなしで、自分のPC上のMCPクライアントから使う方式です。
`rsa local` はMCP stdioサーバーとして起動し、同じプロセス内でworkerも動かします。クライアントが起動・終了を管理します。

```bash
uv sync --frozen
uv run rsa local --input-dir ~/ResearchSlides --output-dir ~/ResearchSlides/outputs
```

- 資料は `register_local_file` に絶対パスを渡して登録します。読めるのは `--input-dir` 配下だけです（既定 `~/ResearchSlides`、複数指定可）。
- 完成PPTX・参考PDF・PNGは `--output-dir/<presentation_id>/<job_id>/` へ保存され、`get_job` が `local_path` と `file://` の `download_url` を返します。
- 状態は `--data-dir`（既定 `~/.research-slide-agent`）に保存し、プロジェクトの7日期限も同じです。
- PPTX生成だけならPythonで動きます。PDFのページ画像・原図の切り出しにはPoppler、完成画像にはLibreOfficeが必要です（macOSなら `brew install poppler` と `brew install --cask libreoffice`）。

クライアントへの登録例（`/path/to/ResearchSlideAgent` は実際の場所に置き換えます。GUIアプリはPATHを引き継がないことがあるため、`uv` は `which uv` の絶対パスにすると確実です）。

```bash
# Claude Code
claude mcp add research-slides -- uv --directory /path/to/ResearchSlideAgent run rsa local
# Codex CLI
codex mcp add research-slides -- uv --directory /path/to/ResearchSlideAgent run rsa local
```

```json
{
  "mcpServers": {
    "research-slides": {
      "command": "uv",
      "args": ["--directory", "/path/to/ResearchSlideAgent", "run", "rsa", "local"]
    }
  }
}
```

JSON形式はClaude Desktop（`claude_desktop_config.json`）、Gemini CLI（`~/.gemini/settings.json`）、Cursor等の `mcpServers` 設定で共通です。
#### すべてコンテナで動かす（推奨）

Dockerイメージには Python・Poppler・LibreOffice・日本語フォント・正本テンプレートが入っているため、ホストに必要なのはDockerだけです。

`make setup`（選択・ビルド・登録）で導入します。手動で行う場合は `docker build -t research-slide-agent:local .` の後、`scripts/rsa-local-docker.sh` を各クライアントへ登録します。

JSON設定のクライアントでは `"command": "/path/to/ResearchSlideAgent/scripts/rsa-local-docker.sh"` とし、`args` は不要です。
`scripts/rsa-local-docker.sh` は `~/ResearchSlides`（`RSA_LOCAL_DIR` で変更可）を読み書き可、`~/Downloads`・`~/Documents`・`~/Desktop`（`RSA_INPUT_DIRS` にコロン区切りで指定して変更可）を読み取り専用で、いずれも同じ絶対パスでマウントします。論文は専用フォルダへ移さなくても、これらの下にあればパスを渡すだけで登録できます。パスが同じなので、LLMが渡すパスも返される `local_path` もホストのパスのままです。
状態は `~/ResearchSlides/.rsa-data`、成果物は `~/ResearchSlides/outputs` に保存されます。
コンテナは `--network none`・実行ユーザーのUID/GIDで動き、クライアントの終了とともに削除されます（`--rm`）。
GHCRのイメージを使う場合は `RSA_IMAGE=ghcr.io/cercil0605/researchslideagent:<commit SHA>` を指定します。

ローカルモードでは `register_chatgpt_file`・`create_upload`・`show_viewer`（MCP Apps UI）を公開しません。
制作ルールは同じ `get_authoring_context` から取得します。結果の品質は接続先モデルの長文読解・画像入力・JSON作成能力に依存します。

### MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

Inspectorで **Streamable HTTP**、URL `http://127.0.0.1:8000/mcp` を指定し接続します。公式MCP SDK 2.3.0のClientによるlegacy/auto両方式の実HTTP接続試験は `tests/test_mcp.py` で実行できます。Inspector UIの手操作は未実施です。

### 修正版スケルトンを使う生成

正本はユーザー修正版「学会発表スケルトン.pptx」。同一バイトのコピーを `templates/lab-template.pptx` として同梱しています。
マスターだけでなく見本ページ全体を複製し、直接書式・段落・表を保持します。
対応する入力はSlideSpec 1.3のみ。`section`で説明上の役割、`part`で本編・補足、`prototype_id`で表示見本を選びます。
研究の本編は表紙→概要→背景→関連研究→目的→手法→実験→結果→考察→まとめの順です。
`paper_section`で論文の節との対応、`content_map`で必要事項を実際の本文・表へ結び付けます。
手法内の具体例、実験後の指標、複数実験と補足に対応します。
method（図と本文）、results_figure（大きい図）、overview（本文3群とキー図）を各節で再利用できます。

優先順位はユーザー指示、修正版、教授のガイドライン、過去PDFの推定です。
methodの本文領域には本文＋小図、表＋図、原図2点の配置を選べます。
表は1～3列。修正版の中央揃え・最下段黒罫線・文字書式・最低行高を保持し、改行に必要な行高を確保します。
収まらない場合は配置と図表比率を見直し、それでも収まらなければ意味を保った短縮・分割を求めます。表の色・罫線・文字サイズ等の改変を検査で検出します。

```bash
uv run python scripts/prepare_skeleton_template.py
uv run python scripts/render_spec.py examples/eggs.slidespec.json --output artifacts/canonical-eggs
uv run python scripts/render_spec.py examples/research-format.slidespec.json --output artifacts/canonical-research
uv run python scripts/render_spec.py examples/research-quality.slidespec.json --output artifacts/quality-check --render
```

正本とprofileはGit管理してDockerに同梱するため、生成時に元の添付ファイルは不要です。
元の「学会発表スケルトン.pptx」と旧卵例は、内容を変えず `reference_materials/local-inputs/` へ保管しています（Git対象外）。
新しいスケルトンを登録する場合だけ `--source /path/to/new-skeleton.pptx` を指定します。
`RSA_TEMPLATE`で変更する場合は対応するprofileも指定先に置き、サーバーとワーカーで同じ正本を使います。
旧1.0/1.1/1.2、layout_id・key_message・body_blocks・chart_specと旧生成エンジンは廃止しました。
旧版の保存済み仕様を再生成する場合は、1.3の必要事項を補って新しい仕様版として保存してください。自動変換は行いません。
既存DBのリセットは不要で、保持期限内の生成済みPPTXは引き続き取得できます。
詳細なページ対応・入力・制約は [書式テンプレートと発表内容ルール](TEMPLATE_AND_CONTENT_RULES.md)。

`get_generation_report`でコードコミット・ソースハッシュ・正本SHA・仕様版と書式検査を取得できます。
`get_job` はcompleted時に期限付き `download_url` を返します。
`get_slide_preview`は要求時に完成画像を返し、overview=trueなら最大6頁の一覧、falseなら個別頁です。
初回は隔離workerの描画jobを返すため、準備後に同じjob_idで画像を取得します。失敗時はpreview_job_idでretry_jobできます。
同じPPTXはキャッシュを再利用し、描画後の`get_preview.pdf_url`から参考PDFも取得できます。
描画は近似表示です。構造検査や画像の取得だけを、読解やPowerPoint実機の表示確認の合格と扱いません。

## フォルダとGit管理（開発者向け）

| 場所 | 用途・扱い |
|---|---|
| `src/`、`ui/` | サーバーとビューアーの実装。Git管理 |
| `templates/` | 実行用の正本PPTXと対応表JSONをGit管理し、Dockerへ同梱。プレビューPDF／JSONは生成物でGit対象外 |
| `plugins/`、`.agents/` | 配布用Plugin・Skillと開発用Skill。Git管理 |
| `examples/` | 再生成できる入力JSON・出典メモ・試験CSV。Git管理。デモも同梱の正本で生成 |
| `scripts/`、`tests/`、`schemas/`、`tools/` | 開発・検証用。ソースと仕様はGit管理、ビルド結果は対象外 |
| `reference_materials/` | 教授のガイドラインとルールの根拠。原文テキストはGit管理、提供されたPDF・PPTXは対象外 |
| `artifacts/` | ローカル生成PPTX・描画画像・検証ログ。READMEだけGit管理。サーバー実行には不要 |
| `var/` | ローカルサーバーの資料・ジョブ・DB。Git対象外。生成物の一時置き場とは分ける |

`artifacts/`のデータは必要な成果物を保存した後に削除できます。現在は修正版の生成例と検証記録だけを残しています。
既存DBのリセットは不要です。旧承認テーブル／列を保持し、生成条件から除外しています。
詳細と再生成コマンドは [artifacts/README.md](../artifacts/README.md)。
`.venv/`、Pythonのキャッシュ、`ui/node_modules/`、Open XML検証器の`bin/obj`もGit対象外です。
