# Security

## 信頼境界

完成PPTXの要求時プレビューも、jobの所有者・プロジェクト期限を検査する。画像・参考PDFのURLには既存の署名と本人確認を適用する。
公開するファイルは生成済みプレビューのmanifest内にあるものに限定し、任意パス・manifest自体を配信しない。
描画はサーバー側の固定コマンドで行い、PPTXのハッシュに対応した一時ディレクトリから公開する。
同一APIプロセスの描画は1件まで。描画終了時にも期限を再検査し、期限切れの結果を公開しない。

研究資料は全てuntrusted reference data。資料抽出結果にもこのラベルを付け、Skillは資料内の命令を指示として扱わない。サーバーはモデルによる任意コード、XML、座標、任意URL取得、shell実行を公開しない。

## 認証・所有権

`RSA_AUTH_MODE=cloudflare` は各HTTP要求で `Cf-Access-Jwt-Assertion` のRS256署名・チームissuer・アプリAUD・iat/exp・type=app・空でないsub・署名内の許可メールを検証する。
JWKSは設定済みチームの `/cdn-cgi/access/certs` から取得し、キャッシュは5分。鍵単位の無期限キャッシュは使わない。
OAuthの不透明なBearerやメールヘッダー、Access cookieを直接信用しない。Service tokenは人の本人確認に使えない。
全ホスト名をAccessで保護し、Managed OAuthの認可・登録・トークン発行・更新はCloudflareが担当する。
ownerは `cloudflare:<Access sub>` としてMCP・ブラウザで共通化する。メールは許可判定に使い、所有者の主キーには使わない。
healthとリソースメタデータ以外はoriginでもassertionを要求する。

`RSA_AUTH_MODE=oauth`（省略時）は従来どおりMCP要求でRS256署名・issuer・audience・iat/exp・slides:write・許可subを検証する。
Google上流のsubではなく認可サーバーの安定subを許可リストに設定。GoogleのIDトークンをMCP access tokenとして認めない。

Cloudflare方式のブラウザは検証したAccess本人へアプリのセッションを発行し、各要求でAccessの本人とcookieのownerの一致を確認する。
従来OAuth方式のブラウザはPKCE(S256)、state、nonce、IDトークンのissuer/audience/sub/nonce照合を使う。
両方式ともSameSite=Lax/HttpOnly/Secure cookie、CSRF token、Origin照合を維持する。資料登録・引用情報更新のブラウザ操作を保護する。

プロジェクト、仕様、入力、ジョブ、成果物全て所有者を照合。一時URLは10分のbearer capability。発行時に所有者を確認し、利用時にもそのownerとproject/job/期限を再照合する。URLを知る人は期限内に利用できるので、共有は慎重にする。

Cloudflare方式ではcap URLにも現在のAccess assertionとowner一致を要求するため、URLだけでは取得・登録できない。
認証方式／Access組織を変更した際の既存ownerの自動移行は行わない。

## ファイル

20 MiB/件、10件、100 MiB/プロジェクト。ZIPの件数、重複、展開150 MiB、圧縮比、暗号化、パストラバーサル、DOCTYPE/ENTITY、VBA、ActiveX、OLE、外部relationshipを拒否する。埋込XLSXも1段まで検査し、深い入れ子と埋込binaryを拒否。XMLを安全パーサーで処理し任意展開しない。

PNG/JPEGはPillow verifyと25M pixel制限。PDFは非暗号化500頁以下、text onlyで参照し、PDF script/添付/URL actionを実行しない。CSVはUTF-8と行・列制限。XLSXはread-only/data-only/keep_links=False。ChartDataのワークブックに数式として書かれるラベルを拒否する。

ChatGPT添付は `RSA_ATTACHMENT_HOSTS` に明示した完全一致ホスト、または明示的な `*.suffix` 許可パターンだけをHTTPSで取得する。標準設定例は `*.oaiusercontent.com`。private/link-local IPを拒否し、redirectを追わず、環境proxyを使わず、streamで容量を制限する。許可設定がなければ直接取込不可。サーバーが任意のURLをfetchする機能は作らない。

## コンテナ

非root、read-only rootfs、cap_drop ALL、no-new-privileges、tmpfs、メモリ/CPU/PID上限。Docker socketをAPI/workerへmountしない。未知のPPTXを処理するため、ホストには信頼済み研究室ユーザー以外の負荷を混在させない。配布stackのworker network_modeはnone。

## 保持・ログ

アクセスを作成7日後から拒否。workerが毎時削除。SQLite secure_deleteとWAL切詰めを使用。物理SSD、スナップショット、外部バックアップの消去は管理者の保持設定に従う。共有テンプレートは削除対象外。cleanup失敗は内容を含めないエラーコードをログに記録する。

アプリは研究本文、実験値、スライド文章、トークン、URLをログに書かない。workerのJSONはjob_id/operation/attempt/duration、エラー時はerror_code。API access logは無効化。Docker local driverのサイズ制限だけでは7日保持を保証できないので、deploy/PORTAINER.mdのログローテーションを設定する。

## 既知の制限

これは侵入試験済み製品ではない。PDF/Office/Pillow/LibreOfficeに未知の脆弱性がないとは主張しない。依存はlockfileを更新し再試験する。
上流IdPの強制ログアウトやAccessポリシー変更が既存トークンへ直ちに反映されるとは限らない。トークンを短期発行にし、更新時にAccessがポリシーを再評価する。
Cloudflare方式のRSA_ALLOWED_EMAILSの除去はAPI設定反映後、各保護要求で拒否する。従来方式のRSA_ALLOWED_SUBSの除去も同様。

Cloudflare Managed OAuthとの初回接続・更新、OAuthプロバイダーとのGoogle login、CIMD/DCR/事前登録、resource indicator、issuer応答、ChatGPTホスト側の実動作は未検証。公開前にAUTH.mdの受入試験が必要。開発認証はloopback限定で本番環境では起動できない。
