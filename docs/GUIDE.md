# 全体ガイド（図で理解する）

このシステムが何をして、どこで何が動くかを図で示します。細かい仕様は末尾の表から各文書へ進んでください。

**要点**: 論文を読み、構成と文章を作るのは接続した AI エージェント（LLM）です。サーバーは LLM を呼ばず、資料の保存と検査、PPTX の生成と検査だけを行います。

## 1. 誰が何をするか

```mermaid
flowchart LR
    U[ユーザー] -->|論文PDFと依頼| A

    subgraph Client[クライアント側]
      A[AIエージェント<br/>Claude Code / Codex / agy<br/>読解・構成・文章・図表選定]
    end

    subgraph Server[MCPサーバー ※LLMは呼ばない]
      M[server.py<br/>MCPツールの入口]
      S[(Store<br/>SQLite)]
      F[files.py / pdf_assets.py<br/>資料検査・本文抽出・図切り出し]
      W[worker.py<br/>PPTX生成・構造検査・画像化]
      T[[正本テンプレート<br/>lab-template.pptx]]
    end

    A <-->|MCP| M
    M --> S
    M --> F
    S -->|キュー| W
    W --> T
    W -->|PPTX / PNG / PDF| S
```

## 2. local と remote の違い

```mermaid
flowchart TB
    subgraph L[ローカルモード rsa local]
      direction TB
      LC[Claude Code / Codex / agy] -->|stdio<br/>docker run -i| LP
      subgraph LP[1コンテナ --network none]
        LM[MCP入口]
        LW[workerスレッド]
        LS[(SQLite)]
        LM --- LS --- LW
      end
      LIN["読み取り専用<br/>Downloads・Documents・Desktop"] --> LP
      LP --> LOUT["~/ResearchSlides/outputs<br/>local_pathを返す"]
    end

    subgraph R[リモート rsa serve + rsa worker]
      direction TB
      RC[ChatGPT など] -->|HTTPS /mcp<br/>Cloudflare Access / OAuth| API
      subgraph PI[Raspberry Pi]
        API[api コンテナ<br/>MCP入口・ログイン・登録画面]
        VOL[(共有volume<br/>SQLite WAL)]
        WK[worker コンテナ<br/>network none]
        API --- VOL --- WK
      end
      ATT[ChatGPT添付<br/>oaiusercontent.com] -->|register_chatgpt_file| API
      API --> DL[10分有効の<br/>ダウンロードURL]
    end
```

| | local | remote |
|---|---|---|
| 接続 | stdio（クライアントがコンテナを起動） | HTTPS |
| 認証 | なし（所有者は固定の `local-user`） | Cloudflare Access または OAuth |
| 資料の入口 | `register_local_file`（許可フォルダのパス） | 添付の取得、またはブラウザからの登録 |
| 成果物 | 出力フォルダへ複製し `local_path` を返す | 期限付きダウンロード URL |
| 公開しないツール | `create_upload`、`register_chatgpt_file`、`show_viewer` | なし |
| 共通 | SQLite、生成エンジン、正本テンプレート、制作ルール | 同左 |

## 3. 一回の生成の流れ

```mermaid
sequenceDiagram
    autonumber
    participant U as ユーザー
    participant L as LLM（クライアント）
    participant M as MCP入口
    participant S as Store/SQLite
    participant W as worker

    U->>L: 論文を渡して依頼
    L->>M: get_authoring_context / get_template_info
    M-->>L: 制作ルール4文書・テンプレート情報
    L->>M: create_project
    L->>M: register_local_file（path）
    M->>S: 検査して保存
    loop 読解
      L->>M: read_source / render_pdf_page
      M-->>L: 本文・ページ画像
      L->>M: crop_pdf_region（図の領域）
    end
    L->>L: 構成・文章・SlideSpec 1.3を作る
    L->>M: save_slide_spec
    L->>M: enqueue_generation
    M->>S: ジョブ登録
    S->>W: 取り出し
    W->>W: 見本ページを複製して差し替え・構造検査
    W->>S: PPTX保存
    L->>M: get_job / get_slide_preview
    M-->>L: 完成画像
    opt 直す
      L->>M: patch_slide → enqueue_generation
    end
    M-->>L: local_path または download_url
    L-->>U: 完成PPTX
```

## 4. ジョブの状態

```mermaid
stateDiagram-v2
    [*] --> queued: enqueue_generation
    queued --> running: workerが取得
    running --> validating: PPTX生成
    validating --> completed: 構造検査OK
    running --> failed: 失敗
    validating --> failed: 検査NG
    failed --> queued: retry_job（最大3回）
    completed --> [*]
```

## 5. MCPツールの役割

| 段階 | ツール |
|---|---|
| ルール取得 | `get_authoring_context`、`get_template_info`、`get_profile` |
| 作業枠 | `create_project`、`get_project`（7日間保持） |
| 資料登録 | `register_local_file`（local）、`register_chatgpt_file`・`create_upload`（remote）、`set_source_metadata` |
| 資料を読む | `read_source`、`render_pdf_page`、`crop_pdf_region` |
| 仕様 | `save_slide_spec`、`patch_slide` |
| 生成 | `enqueue_generation`、`get_job`、`retry_job` |
| 確認 | `get_slide_preview`、`get_preview`、`get_generation_report`、`show_viewer`（remote のみ） |
| 手編集 PPTX | `inspect_uploaded_pptx`、`propose_pptx_patch` |

引数と返り値は [API.md](../API.md)。

## 6. 処理を担う場所

| 処理 | 主体 | モジュール |
|---|---|---|
| 論文の読解、構成、文章、図表の選定 | **LLM（クライアント）** | — |
| 仕様の検査、版管理、7日の期限、所有権 | MCP プロセス | `store.py`、`models.py` |
| 資料の検査と本文抽出 | MCP プロセス | `files.py` |
| ページの画像化、図の切り出し | MCP プロセス（Poppler） | `pdf_assets.py` |
| PPTX 生成、構造検査、完成画像（LibreOffice） | **worker** | `worker.py`、`prototypes.py`、`engine.py` |
| ジョブのキュー、再試行、期限切れの削除 | worker | `store.py` |

## 7. 注意

- 品質は、接続した LLM の長文読解、画像入力、JSON 作成の能力に依存します。サーバーはスライド内容を補いません。
- 検査は構造と体裁の検査です。内容の正しさや PowerPoint 実機での見え方は保証しません（[TESTING.md](../TESTING.md)）。

## 次に読む文書

| 知りたいこと | 文書 |
|---|---|
| 使い始める | [README](../README.md) |
| 他クライアントの登録、開発 | [LOCAL.md](LOCAL.md) |
| 公開サーバーの構築 | [REMOTE.md](REMOTE.md) |
| できること・制約 | [CAPABILITIES.md](CAPABILITIES.md) |
| ツールの引数・返り値 | [API.md](../API.md) |
| 構成の詳細 | [ARCHITECTURE.md](../ARCHITECTURE.md) |
| セキュリティ | [SECURITY.md](../SECURITY.md) |
| 試験と未検証事項 | [TESTING.md](../TESTING.md) |
| 全文書の案内 | [docs/README.md](README.md) |
