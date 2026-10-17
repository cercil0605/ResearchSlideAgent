# Architecture

## 実行経路

ChatGPT/互換MCPクライアント → HTTPSプロキシ → API (`Starlette` + 公式MCP Python SDK)。
APIと生成ワーカーは同一Piの共有Docker volumeを使い、SQLite WALを通じて連携する。React MCP Apps UIは `ui://research-slide-agent/viewer.html` に登録され、ホストがiframeを表示する。ブラウザでの資料登録はAPIの通常ページ。

認可サーバーはGoogleを上流IdPとして連携し、MCP専用audience/scopeのアクセストークンを発行する。APIはissuer/audience/署名/期限/scope/sub許可を検証する。Google IDトークンはMCPで受け付けない。ブラウザは独立したPKCEフローで認可サーバーにログインする。

## モジュール

| モジュール | 責務 |
|---|---|
| models.py | SlideSpec 1.0/1.1、見本・段落／ラン選択、意味的図表、参照、引用、JSON Schema |
| pdf_assets.py | 登録PDFのCropBox画像化、表示に沿った正規化領域の切り出し。既存PopplerをAPI側で再利用 |
| engine.py | 生成経路の選択、旧テンプレート互換処理、LibreOffice/Poppler、OPC差分編集 |
| prototypes.py | 正本ページの複製、直接書式と表の保持、適合検査、生成来歴 |
| files.py | 容量・拡張子・マジック・ZIP・XML・外部参照検査、ページ単位の資料抽出 |
| store.py | 所有権、7日期限、仕様スナップショット、キュー、lease、削除 |
| auth.py | トークン検証、署名済み一時URL、ブラウザセッション、MCPリクエスト認証 |
| server.py | MCPツール/リソース、公式ファイルパラメーター、ダウンロードURL・生成レポート |
| rules.py | Skillの正本referencesを読込、全文・文書SHA・bundle digestをMCP tool/Resourceへ提供 |
| app.py | HTTP入口、ログイン、資料登録、成果物配信 |
| worker.py | ジョブ実行、構造検査、失敗分類、3試行上限、定期削除 |
| ui/ | React/TypeScript、標準MCP Apps SDK、状態・再実行・ダウンロード |

## 仕様と生成

MCP単体接続はGitHubのSkillを自動配布しないため、server instructionsから `get_authoring_context` へ誘導する。
同ツールと `research-slides://authoring-context` Resourceは同じloaderを使い、必須4文書を全文返す。
正本は配布Skillのreferences。開発時は正本を直接読み、wheelにはHatch force-include、Dockerにはそのビルド入力を含める。
文書欠落時は取得を失敗させる。hashは版の監査用で、モデルの読解・遵守の保証やジョブ承認には使わない。
完全なPluginのSkillは取得手順を教える入口とし、接続中はサーバー返却版を適用する。
Autonomous/CollaborativeはChatGPTの制作手順で区別し、生成キュー・DB・SlideSpecへ承認状態を追加しない。

既定の正本は修正版スケルトンの同一バイトコピー。SlideSpec 1.1のprototype_idで見本ページを選び、
replacementsで段落とランの見本を選択する。位置・色・字形は正本に固定され、入力で任意指定できない。
`prototypes.py`はOPCの共有パーツを保持し、見本のページXML・関係ファイルを複製する。
表は行高を保って必要な行を複製し、最終行に正本の最下段罫線を残す。
固定枠を拡張せず、あふれは短縮／分割を求める。既存の1.0経路は合成／過去テンプレートの試験用に保持する。

正本と仕様から期待XMLを再構成して出力を検証し、コードコミット・ソースhash・正本SHA・仕様版を
manifestとPPTX内へ記録する。生成は検査済みの一時ファイルを完成後に置換する。
PPTX生成・構造検査の成功でcompletedとなり、get_jobは期限付きダウンロードURLを返す。
完成PPTXのPDF・PNGプレビューは生成しない。原論文のページ画像・図の切り出しはAPI側の独立した処理とする。
get_generation_reportは書式適合と来歴を返す。

`spec_version` は単調増加。保存時にexpected_versionを照合する。
新規生成・再生成・PPTXパッチに承認は不要。旧承認テーブルとpatches.approved列はDB互換用に保持し、生成判定には使わない。既存DBのリセットは不要。
テンプレートハッシュを仕様保存時と生成登録時・ワーカー実行時に照合する。差し替え時は仕様を再保存する。

## キューと冪等性

BEGIN IMMEDIATE内でclaimと全体上限を判定。1ユーザーのqueued/running/validatingを部分unique indexで制約。ジョブdigestは仕様全体またはパッチ計画に対して一意。重複登録は既存ジョブを返す。各試行は別のlease_tokenディレクトリに出力し、完了書込も同トークン・有効leaseを要求する。

queued → running → validating → completed。内容/配置エラーはfailed。I/Oの一時失敗は待ち時間を設けqueuedへ戻し、初回含め3回。プロセス停止時もlease期限後に回収。lease30分。Piでこれを超える実測が出るならlease延長またはheartbeat追加が必要。

## 部分修正

再アップロードPPTXはimmutable inputとして保持し、latest_pptxを更新する。shape_idとXMLのSHA256を照合し、パッチ計画にbefore/afterと元ファイルhashを保存。patch_idでキューへ登録する。XMLを直接差し替え、対象外OPCエントリーは元のバイト列をそのまま保存。未知の形状・複数装飾ランは拒否する。

再アップロードがパッチ計画保存後に変わると登録/実行を拒否。ワーカー完了後の出力は別の成果物であり、元入力を上書きしない。次の編集は完成PPTXを再アップロードする。

## 保存

プロジェクト作成から7日。アクセス時に期限を判定し、物理削除遅延中もアクセスを拒否する。ワーカーは開始時および毎時cleanup。DBのsecure_deleteとWAL checkpointを使用するが、SSDの物理消去や管理者バックアップまで保証しない。共有テンプレートはプロジェクト外のread-only mountで保持。共有過去資料の管理UI/全ユーザー共有機能は未実装。個人資料と暗黙に混ぜない。
