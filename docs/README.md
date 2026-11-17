# ドキュメント案内

Research Slide Agentの文書を、読む目的ごとに案内します。

## まず読む

- [はじめての人向けの全体像](OVERVIEW.md): 何をする仕組みか、どこで動くかを図で短く説明。
- [README](../README.md): 製品概要とローカルモードの最短導入。
- [ローカルモードと開発（詳細）](LOCAL.md): 他クライアントへの登録、Python直接実行、開発・検証、フォルダ構成。
- [リモート構成](REMOTE.md): ChatGPT・Raspberry Pi・Portainer・環境変数。
- [製品仕様](PRODUCT_SPEC.md): 誰が何に使い、生成処理が何をするか。
- [機能と制約](CAPABILITIES.md): 現在できること、条件、未対応の範囲。
- [利用シーン](USER_USE_CASES.md): 作成・更新・手編集PPTXの再編集の流れ。

## 開発・運用

- [API](../API.md): MCPツール、HTTP、SlideSpec、入出力契約。
- [Architecture](../ARCHITECTURE.md): サービス構成、生成、ジョブ、保存の仕組み。
- [Security](../SECURITY.md): 認証、所有権、入力検査、保持、ログ。
- [Testing](../TESTING.md): 自動検証、手動受入、未検証事項。
- `deploy/`: Portainer、認証、将来のGCP移行に関する運用手順。
- [Raspberry Pi運用判断](RASPBERRY_PI.md): Piを選んだ理由と初期の実機確認項目。具体的な配置手順は`deploy/PORTAINER.md`。
- `docs/adr/`: 技術判断とその理由。
- [確認した公式資料](SOURCES.md): 実装・設計判断を調べるときの参照先。

## 制作ルールとテンプレート

発表の内容・構成に関するChatGPT向けルールの編集上の正本は、Plugin Skillの`references/`です。
MCPはその文書を全文配布します。`docs/`へ同じ本文を複製せず、制作の根拠は[制作ルール](../plugins/research-slide-agent/skills/research-slides/SKILL.md)から確認してください。

テンプレートの機械的な制約や実装詳細は[テンプレートと内容ルール](TEMPLATE_AND_CONTENT_RULES.md)、
互換性の限界は[PowerPoint互換性](POWERPOINT_COMPATIBILITY.md)を参照してください。

## 文書の更新

仕様・実装を変えるときは、コード、Schema、テストとこの文書案内を照合し、関係する文書を同じ変更で更新します。
[文書更新ルール](DOCUMENTATION_POLICY.md)に、どの変更がどの文書へ波及するかを定めています。

## 履歴資料

以下は当時の指示・実装・調査記録です。既存リンクを保つため現在の場所に残し、履歴資料として明示しています。現行仕様ではありません。

- [当初の開発指示](ORIGINAL_REQUIREMENTS.md): 旧GCP案や初期の広い機能要件を含む。
- [正本テンプレートへの切り替え記録](CANONICAL_TEMPLATE_CHANGE.md): 作業時点の変更・生成物・検証結果を記録。
- [PowerPoint互換性の調査記録](POWERPOINT_COMPATIBILITY.md): 旧経路の問題と現在の互換性上の制約。
- [2026-10-24生成物監査](GENERATED_DECK_AUDIT_2026-10-24.md): 添付PPTXと稼働版の同定、前回指摘の反映状況、保存履歴からの原因調査。

現行の仕様や機能を判断するときは、製品仕様、機能一覧、API、コード、テストを参照してください。
