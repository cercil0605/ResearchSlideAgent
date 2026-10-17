# ADR 0003: Versioned generation, federated authorization server

2026-10-17 / Approval requirement superseded; real-provider integration pending

新規生成・再生成・PPTXパッチは保存した仕様・パッチ計画から直接キューへ登録する。必須承認は撤廃。版・hash・所有権・正本照合・競合検出は維持し、旧DBの承認テーブルと列は互換性のため保持する。PPTX生成・構造検査の成功でcompletedとなり、プレビューやモデルの画像確認は不要。

Googleは上流IdP、専用OAuth認可サーバーがMCP用tokenを発行する。既存基盤またはKeycloak等を利用し、手製OAuth brokerは作らない。ブラウザとMCPのclientを分ける。productionで設定不足なら起動拒否。実GoogleログインとChatGPT連携は資格情報未提供のため未検証。
