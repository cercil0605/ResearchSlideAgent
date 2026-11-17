# Research Slide Agent

論文PDFから、研究室の正本テンプレートに沿った**編集可能なPPTX**を作るMCPサーバーです。追加のLLM APIは使いません。構成と文章は接続したAIエージェント（Claude Code・Codexなど）が作り、サーバーが配置・生成・検査を行います。

## 使い始める（ローカルモード）

サーバー公開・ログイン不要で、手元のDockerだけで動きます（約5分）。

```bash
git clone https://github.com/cercil0605/ResearchSlideAgent.git
cd ResearchSlideAgent
make setup      # claude / codex / agy を選択 → イメージ作成 → 登録 → 状態確認
                # 選んだCLIが未インストールならビルド前に中止。非対話は make setup AGENT=claude
```

エージェントを再起動し、論文のパスを伝えて頼みます。

> research-slides を使って、`~/Downloads/論文.pdf` から10分の研究室発表スライドを作って。

完成したPPTXは `~/ResearchSlides/outputs` に保存されます。論文は `~/Downloads`・`~/Documents`・`~/Desktop`・`~/ResearchSlides` のどこにあっても読めます。

| やりたいこと | コマンド |
|---|---|
| コードを更新した | `make update`（再登録は不要。エージェントを再起動） |
| 動かない | `make doctor`（Docker・イメージ・スクリプトを確認） |
| 登録前に動作確認 | `make smoke` |
| 別のエージェントにも登録 | `make register AGENT=agy`（`claude`・`codex` も可。省略すると選択） |
| 登録を外す | `make unregister AGENT=codex` |

`make` だけで一覧を表示します。

**使えるクライアント**

| クライアント | 状態 |
|---|---|
| Codex CLI | 動作確認済み |
| Antigravity CLI（agy） | 登録（`agy mcp list` で確認）のみ。生成は未確認 |
| Claude Code | 接続・生成まで確認。利用上限のため完走は未確認 |
| ChatGPTデスクトップ | Codex／Workモードのみ見込み。通常チャットではローカルMCPが公開されない既知の不具合あり（[openai/codex#38162](https://github.com/openai/codex/issues/38162)）。実機未確認 |
| ChatGPT Web・Claude Desktop・Gemini CLIなど | Webは不可。他は未検証。登録方法は [docs/LOCAL.md](docs/LOCAL.md) |

制作ルールはサーバーが配るため、Skillやプラグインのインストールは不要です。出来栄えは接続先モデルの能力に依存します。

## 詳しい文書

| 知りたいこと | 文書 |
|---|---|
| 他クライアントへの登録、Pythonで直接実行、開発・検証 | [docs/LOCAL.md](docs/LOCAL.md) |
| 公開サーバー（ChatGPT・Raspberry Pi・Portainer・環境変数） | [docs/REMOTE.md](docs/REMOTE.md) |
| 何ができるか・制約 | [docs/CAPABILITIES.md](docs/CAPABILITIES.md) |
| 利用の流れ | [docs/USER_USE_CASES.md](docs/USER_USE_CASES.md) |
| 全文書の案内 | [docs/README.md](docs/README.md) |
| API・設計・セキュリティ・試験 | [API.md](API.md) / [ARCHITECTURE.md](ARCHITECTURE.md) / [SECURITY.md](SECURITY.md) / [TESTING.md](TESTING.md) |

**未実施の受入試験**: Cloudflare Access／外部OAuth、リモートChatGPT内UI、Microsoft PowerPointでの確認（[TESTING.md](TESTING.md)）。PowerPointの互換性は [docs/POWERPOINT_COMPATIBILITY.md](docs/POWERPOINT_COMPATIBILITY.md)。
