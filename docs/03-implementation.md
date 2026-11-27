# 03 実装の地図

各入口を、どのファイルが実装しているかです。コードは `src/research_slide_agent/` にあります。

## ファイルのつながり

```mermaid
flowchart TD
    CLI[cli.py<br/>起動コマンド] --> APP[app.py<br/>HTTP・ログイン画面]
    CLI --> SRV
    APP --> AUTH[auth.py<br/>認証]
    APP --> SRV[server.py<br/>MCPの入口]
    SRV --> RULES[rules.py<br/>ルール配布]
    SRV --> STORE[store.py<br/>保存・版・ジョブ]
    SRV --> FILES[files.py<br/>資料の検査・抽出]
    SRV --> PDF[pdf_assets.py<br/>PDFの画像化・切り抜き]
    SRV --> PREV[previews.py<br/>完成画像]
    STORE --> MODELS[models.py<br/>設計書の型]
    STORE --> PROTO
    WORKER[worker.py<br/>ジョブ実行] --> STORE
    WORKER --> ENGINE[engine.py<br/>生成・画像化・部分修正]
    ENGINE --> PROTO[prototypes.py<br/>見本ページの複製・検査]
    RULES --> REF[(plugins/.../references/<br/>ルール4文書)]
    PROTO --> TPL[(templates/<br/>正本PPTX + 対応表)]
```

## 入口と実装

| 入口 | 主な実装 |
|---|---|
| `get_authoring_context` | `rules.py` の `authoring_context()` |
| `get_template_info` | `engine.py` の `template_info()` → `prototypes.py` の `capacity_catalog()`（配置ごとの容量、表の行数） |
| `create_project` / `get_project` | `store.py` の `create()` / `project()` |
| `register_local_file` | `server.py` の `read_local_file()` → `store.py` の `register()` → `files.py` の `validate_file()` |
| `register_chatgpt_file` | `server.py` の `download_attachment()` → `store.py` の `register()` |
| `create_upload` | `auth.py` の `sign()`、受け口は `app.py` の `upload()` |
| `set_source_metadata` | `store.py` の `source_metadata()` |
| `read_source` | `files.py` の `extract()` |
| `render_pdf_page` / `crop_pdf_region` | `pdf_assets.py` の `render_page()` |
| `save_slide_spec` | `models.py` の型チェック → `store.py` の `save_spec()`（`figures.py` の `number_captions()` が切り抜き図の図題へ図番号を付ける。なければ `FIGURE_NUMBER_REQUIRED`）→ `prototypes.py` の `authoring_feedback()` |
| `patch_slide` | `server.py` 内で1枚差し替え → `store.py` の `save_spec()` |
| `enqueue_generation` / `retry_job` | `store.py` の `enqueue()` / `retry()` |
| ジョブの実行 | `worker.py` の `process_one()` → `engine.py` の `generate()` → `prototypes.py` の `generate_prototypes()` |
| `get_job` / `get_preview` | `server.py` の `links()`（保存されたJSON文字列を `output` オブジェクトに戻す） |
| `get_slide_preview` | `previews.py` → worker が `engine.py` の `render()` |
| `get_generation_report` | 生成時に書いた `*.manifest.json` を返す |
| `inspect_uploaded_pptx` / `propose_pptx_patch` | `engine.py` の `inspect_pptx()` / `store.py` の `patch_plan()`、実行は `engine.py` の `patch_text()` |

## local と remote の違い

```mermaid
flowchart TB
    subgraph LOCAL[local: rsa local]
        direction LR
        LC[AIエージェント] -->|stdio| LP[1つのプロセス<br/>入口 + workerスレッド]
    end
    subgraph REMOTE[remote: rsa serve + rsa worker]
        direction LR
        RC[ChatGPTなど] -->|HTTPS| API[api<br/>入口・ログイン画面]
        API --- DB[(共有の保存場所)]
        DB --- WK[worker<br/>ネットワークなし]
    end
```

| | local | remote |
|---|---|---|
| つなぎ方 | 標準入出力（AI がプロセスを起動） | HTTPS の `/mcp` |
| 認証 | なし | あり（[04](04-auth.md)） |
| 資料の受け取り | 許可フォルダのパス | ChatGPT の添付、またはブラウザから |
| 成果物の渡し方 | 出力フォルダにコピーしてパスを返す | 10分有効のダウンロード URL |
| 無い入口 | `register_chatgpt_file`、`create_upload`、`show_viewer` | `register_local_file` |
| 共通 | 保存、生成、検査、テンプレート、ルール | 同左 |

local は `cli.py` の `run_local()` が、入口と worker を1つのプロセスで起動します。

保存時の `authoring_feedback()` は登録済み画像のパスも受け取り、生成と同じ `build_slide()` で配置を試します。枠・表・図の検査失敗は `engine.py` の `LayoutError.problems` に集めます。生成時は `generate_prototypes()` がページ番号を付け、`worker.py` の `process_one()` が `output.problems` に保存します。データベース内の `output` は従来どおりJSON文字列です。

## なぜこうしたか

- local と remote で中身（保存・生成・検査）を共通にし、違いを「入口と出口」だけにしています。片方だけ直して食い違うのを防ぐためです。
- AI に見せるデータと、生成に使うデータを分けています。`get_template_info` は `llm_view.py` の `template_info()` が `engine.py` の結果から書式 XML・位置・部品名を外して返し、生成は対応表の全データを使い続けます。返す量は `scripts/measure_llm_payload.py` で測れます。
