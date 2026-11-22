# Research Slide Agent

論文 PDF から、研究室のテンプレートどおりの **編集できる PowerPoint** を作る MCP サーバーです。

```mermaid
flowchart LR
    U[あなた] -->|論文と依頼| L[AIエージェント<br/>Claude Code / Codex / agy]
    L <-->|MCP| S[このサーバー]
    S --> P[PPTX]
```

- **考えるのは AI エージェント**（論文を読み、構成と文章を作る）。
- **このサーバーは考えません**。資料の保存、PPTX の生成、検査だけをします。

## 使い始める

Docker だけで動きます。

```bash
git clone https://github.com/cercil0605/ResearchSlideAgent.git
cd ResearchSlideAgent
make setup        # claude / codex / agy を選ぶ → ビルド → 登録
```

エージェントを再起動して、こう頼みます。

> research-slides を使って、`~/Downloads/論文.pdf` から10分の研究室発表スライドを作って。

完成した PPTX は `~/ResearchSlides/outputs` に入ります。

| こんなとき | コマンド |
|---|---|
| コードを更新した | `make update` |
| 動かない | `make doctor` |
| 別のエージェントに登録 | `make register AGENT=codex` |

## 仕組みを知る

上から順に読むと、全体が分かります。

| 知りたいこと | ページ |
|---|---|
| 1論文を頼んだとき、AI が何を送り、どのコードが動くか | [01 処理の流れ](docs/01-flow.md) |
| 全ツールの辞書（渡すもの・返るもの・期待する動き） | [02 AI との約束](docs/02-llm-contract.md) |
| 各入口をどのコードが実装しているか | [03 実装の地図](docs/03-implementation.md) |
| リモートの認証はなぜ・いつ必要か | [04 認証](docs/04-auth.md) |
| テンプレートどおりの見た目をどう作るか | [05 デザイン](docs/05-design.md) |
| 内容をどう作り、どう確かめるか | [06 内容](docs/06-content.md) |
| 何が保存され、いつ消えるか | [07 データと状態](docs/07-state.md) |
| 導入・設定・リモート構築 | [08 運用](docs/08-operate.md) |
| エラーが出た | [09 トラブル対応](docs/09-troubleshoot.md) |
| どこまで確かめたか | [検証状況](docs/verified.md) |
| 図と内容の品質、往復の多さをどう直すか | [改善方針](docs/improvement-plan.md) |

## 名前の見分け方

ドキュメントに出てくる英語名は、書き方で種類が分かります。

| 書き方 | 種類 | 例 | どこにあるか |
|---|---|---|---|
| `小文字_つなぎ` | **ツール**（AI が呼ぶ MCP の入口） | `create_project`、`save_slide_spec` | 一覧は [02](docs/02-llm-contract.md) |
| `名前.py` | **ファイル** | `store.py`、`worker.py` | `src/research_slide_agent/` |
| `名前()` | **関数**（ファイルの中の処理） | `save_spec()`、`generate_prototypes()` | 「`store.py` の `save_spec()`」のように書く |
| `小文字_つなぎ`（設計書の中） | **設計書の項目** | `prototype_id`、`replacements` | [01](docs/01-flow.md) の③、`schemas/slidespec.json` |
| `大文字_つなぎ` | **エラー・指摘のコード** | `TEXT_OVERFLOW` | [09](docs/09-troubleshoot.md) |
| `RSA_大文字` | **環境変数**（設定） | `RSA_AUTH_MODE` | [08](docs/08-operate.md) |
| 日本語の枠名 | **見本ページの枠の名前** | `手法の特徴`、`図題` | 正本テンプレート（[05](docs/05-design.md)） |

よく出る言葉：

| 言葉 | 意味 |
|---|---|
| MCP | AI が外部の道具を呼ぶための共通の約束ごと |
| 見本ページ（prototype） | テンプレートにある11種類のお手本ページ |
| 枠（slot） | 見本ページの中の、文字を入れる場所 |
| 設計書（SlideSpec） | AI が書く「どの見本に何を入れるか」の JSON |
| 正本 | 研究室のテンプレート PPTX（`templates/lab-template.pptx`） |
| ジョブ | worker に頼む時間のかかる仕事（生成、画像化、部分修正） |
| worker | ジョブを順番に処理するプログラム（`worker.py`） |
| local / remote | 自分の PC で動かす方式 / 公開サーバーで動かす方式 |
