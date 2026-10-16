# Architecture

## 実行経路

ChatGPT/互換MCPクライアント → HTTPSプロキシ → API (`Starlette` + 公式MCP Python SDK)。
APIと生成ワーカーは同一Piの共有Docker volumeを使い、SQLite WALを通じて連携する。React MCP Apps UIは `ui://research-slide-agent/viewer.html` に登録され、ホストがiframeを表示する。ブラウザでの資料登録・承認はAPIの通常ページ。

認可サーバーはGoogleを上流IdPとして連携し、MCP専用audience/scopeのアクセストークンを発行する。APIはissuer/audience/署名/期限/scope/sub許可を検証する。Google IDトークンはMCPで受け付けない。ブラウザは独立したPKCEフローで認可サーバーにログインする。

## モジュール

| モジュール | 責務 |
|---|---|
| models.py | SlideSpec 1.0、意味的図表、参照、引用、JSON Schema |
| engine.py | マスター解析、配置、ネイティブ生成、構造検査、最大2回の領域拡張、LibreOffice/Poppler、OPC差分編集 |
| files.py | 容量・拡張子・マジック・ZIP・XML・外部参照検査、ページ単位の資料抽出 |
| store.py | 所有権、7日期限、仕様スナップショット、承認、キュー、lease、削除 |
| auth.py | トークン検証、署名済み一時URL、ブラウザセッション、MCPリクエスト認証 |
| server.py | MCPツール/リソース、公式ファイルパラメーター、構造化結果 |
| app.py | HTTP入口、ログイン、資料登録、人による承認、成果物配信 |
| worker.py | ジョブ実行、プレビュー、失敗分類、3試行上限、定期削除 |
| ui/ | React/TypeScript、標準MCP Apps SDK、一覧・拡大・状態・再実行・修正メッセージ |

## 仕様と承認

実見本から抽出したテンプレートでは、`rsa:`で役割を示すレイアウトのプレースホルダーを使う。
layout_idは全マスターのレイアウトを順に並べたID。Blockのlevel/bullet/slotは意味的な指定だけを受け付け、
座標・寸法・和文/欧文フォント・段落の書式はPPTXから取得する。固定枠では縮小・拡張せず溢れを拒否する。
python-pptxの再保存でXML宣言やrelationship順が変わるため、構造上同一であることを検査してから
master/layout/themeの元バイト列を復元し、最後にバイト一致を確認する。実際の書式変更を復元で隠さない。

`spec_version` は単調増加。保存時にexpected_versionを照合する。承認は(project, version, stage, target, digest)で保存。仕様を書き換えると新バージョンとなり、旧承認は新規ジョブに使えない。

構成承認前はページ承認を作れない。生成には構成と全ページの現在版の承認が必要。承認URLのGETは承認しない。認証済みブラウザのPOSTだけがCSRFとoriginを確認して承認を記録する。レビュー要求は30分・1回限り。OAuthセッションも30分。MCPに承認実行ツールは公開しない。

テンプレートハッシュを仕様保存時と生成登録時・ワーカー実行時に照合する。テンプレート差し替え時は仕様を再保存・再承認。

## キューと冪等性

BEGIN IMMEDIATE内でclaimと全体上限を判定。1ユーザーのqueued/running/validatingを部分unique indexで制約。ジョブdigestは仕様全体またはパッチ計画に対して一意。重複登録は既存ジョブを返す。各試行は別のlease_tokenディレクトリに出力し、完了書込も同トークン・有効leaseを要求する。

queued → running → validating → completed。内容/配置エラーはfailed。I/O/レンダリングの一時失敗は待ち時間を設けqueuedへ戻し、初回含め3回。プロセス停止時もlease期限後に回収。lease30分、各LibreOffice/Popplerプロセスは240秒制限。Piでこれを超える実測が出るならlease延長またはheartbeat追加が必要。

## 部分修正

再アップロードPPTXはimmutable inputとして保持し、latest_pptxを更新する。shape_idとXMLのSHA256を照合し、パッチ計画にbefore/afterと元ファイルhashを保存。人が承認後にキューへ登録する。XMLを直接差し替え、対象外OPCエントリーは元のバイト列をそのまま保存。未知の形状・複数装飾ランは拒否する。

再アップロードがパッチ承認後に変わると登録/実行を拒否。ワーカー完了後の出力は別の成果物であり、元入力を上書きしない。次の編集は完成PPTXを再アップロードする。

## 保存

プロジェクト作成から7日。アクセス時に期限を判定し、物理削除遅延中もアクセスを拒否する。ワーカーは開始時および毎時cleanup。DBのsecure_deleteとWAL checkpointを使用するが、SSDの物理消去や管理者バックアップまで保証しない。共有テンプレートはプロジェクト外のread-only mountで保持。共有過去資料の管理UI/全ユーザー共有機能は未実装。個人資料と暗黙に混ぜない。
