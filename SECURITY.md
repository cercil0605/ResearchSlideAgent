# Security

## 信頼境界

完成PPTXの要求時プレビューも、jobの所有者・プロジェクト期限を検査する。画像・参考PDFのURLにはPPTXと同じ署名・期限検査を適用し、Cloudflare方式ではAccess認証を要求する。
公開するファイルは生成済みプレビューのmanifest内にあるものに限定し、任意パス・manifest自体を配信しない。
APIは描画jobを登録するだけで、LibreOfficeは既存のnetwork_mode:noneのworkerで起動する。
手編集由来の出力を含め、Officeの重い解析をネットワークと認証設定を持つAPIへ追加しない。
PPTXハッシュと描画jobの完了を確認して配信する。既存の同時ジョブ・worker・lease・試行回数の上限を適用する。
描画終了時にも期限を再検査し、期限切れの結果や未完了jobのキャッシュを公開しない。

研究資料は全てuntrusted reference data。資料抽出結果にもこのラベルを付け、Skillは資料内の命令を指示として扱わない。サーバーはモデルによる任意コード、XML、座標、任意URL取得、shell実行を公開しない。

ローカルモード（`rsa local`）の信頼境界は、MCPクライアントを起動したOSユーザーである。HTTPを待ち受けず、認証もしない。
`register_local_file` はシンボリックリンクと `..` を解決した後に許可フォルダ配下の通常ファイルだけを読み、通常と同じ形式・容量検査を適用する。
資料内の指示でLLMが別のパスを読もうとしても許可フォルダ外は拒否するため、入力フォルダは必要な範囲に限定する。
workerは同じプロセスで動く。ホストで直接起動した場合はネットワーク隔離がない。`scripts/rsa-local-docker.sh`はコンテナ全体を`--network none`・呼出しユーザーのUID/GIDで起動し、読み書き用の共有フォルダ（既定 `~/ResearchSlides`）と、論文を読むための読み取り専用フォルダ（既定 `~/Downloads`・`~/Documents`・`~/Desktop`、`RSA_INPUT_DIRS` で変更）だけをマウントする。ホームディレクトリ全体や他のフォルダは見えない。

## 認証・所有権

`RSA_AUTH_MODE=cloudflare` は各HTTP要求で `Cf-Access-Jwt-Assertion` のRS256署名・チームissuer・アプリAUD・iat/exp・type=app・空でないsubを検証する。ユーザー許可ポリシーはCloudflare Accessで管理し、アプリはメールアドレスを認可判定に使わない。
JWKSは設定済みチームの `/cdn-cgi/access/certs` から取得し、キャッシュは5分。鍵単位の無期限キャッシュは使わない。
OAuthの不透明なBearerやメールヘッダー、Access cookieを直接信用しない。Service tokenは人の本人確認に使えない。
全ホスト名をAccessで保護し、Managed OAuthの認可・登録・トークン発行・更新はCloudflareが担当する。
ownerは `cloudflare:<Access sub>` としてMCP・ブラウザで共通化する。メールアドレスは所有者IDやアプリの許可判定に使わない。
healthとリソースメタデータ以外はoriginでもassertionを要求する。

`RSA_AUTH_MODE=oauth`（省略時）は従来どおりMCP要求でRS256署名・issuer・audience・iat/exp・slides:write・許可subを検証する。
Google上流のsubではなく認可サーバーの安定subを許可リストに設定。GoogleのIDトークンをMCP access tokenとして認めない。

Cloudflare方式のブラウザは検証したAccess本人へアプリのセッションを発行し、各要求でAccessの本人とcookieのownerの一致を確認する。
従来OAuth方式のブラウザはPKCE(S256)、state、nonce、IDトークンのissuer/audience/sub/nonce照合を使う。
両方式ともSameSite=Lax/HttpOnly/Secure cookie、CSRF token、Origin照合を維持する。資料登録・引用情報更新のブラウザ操作を保護する。

プロジェクト、仕様、入力、ジョブの操作と成果物URLの発行では、要求者と所有者を照合する。一時URLは10分のbearer capability。利用時にも署名内ownerとproject/jobの所有権・期限を再照合する。成果物ではさらに署名内job・ファイル名と要求パス、jobの完了状態を検査する。

Cloudflare方式の成果物URL（PPTX・参考PDF・PNG）は、有効なAccess assertionと署名付きURLを持つ利用者に取得を許可する。要求者と作成者のID一致やアカウント紐付けは不要。URLの所持は作成者本人の証明ではなく、有効期限内の対象ファイルの取得権限として扱う。転送先もAccessで許可されていれば取得できる。未認証の要求やURLなしの取得は拒否する。
アップロードURLとブラウザの資料登録・引用情報更新は引き続きAccess本人とownerの一致を要求する。従来OAuth方式では成果物発行者の許可リスト確認を維持する。
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
Cloudflare Accessポリシーの変更は、Accessが新しいassertionを発行してから各保護要求に反映される。従来方式のRSA_ALLOWED_SUBSの除去はAPI設定反映後、各保護要求で拒否する。

Cloudflare Managed OAuthとの初回接続・更新、OAuthプロバイダーとのGoogle login、CIMD/DCR/事前登録、resource indicator、issuer応答、ChatGPTホスト側の実動作は未検証。公開前にAUTH.mdの受入試験が必要。開発認証はloopback限定で本番環境では起動できない。
