# 認証: Cloudflare Access（1人利用の推奨構成）

Cloudflare TunnelでPiのAPIを公開し、Cloudflare Accessのポリシーで自分のメールだけを許可します。
MCP接続はAccessの **Managed OAuth**、ブラウザはAccessのログインを使います。
KeycloakやGoogle OAuthクライアントを別途用意する必要はありません。Googleをログイン手段に使う場合はAccess側で設定します。

## アプリ側の設定

`.env.example` をPortainerのStack環境変数へ設定します。

```dotenv
RSA_IMAGE=ghcr.io/cercil0605/researchslideagent:latest
RSA_BASE_URL=https://slides.example.org
RSA_AUTH_MODE=cloudflare
RSA_CF_TEAM_DOMAIN=https://YOUR_TEAM.cloudflareaccess.com
RSA_CF_AUDIENCE=<AccessアプリケーションのApplication Audience (AUD) Tag>
RSA_ALLOWED_EMAILS=you@example.org
RSA_SESSION_KEY=<32文字以上のランダム値>
```

`RSA_BASE_URL` はパス・末尾の `/` がない公開HTTPS origin。`RSA_CF_TEAM_DOMAIN` はZero Trustのチームドメインです。
AUDは公開URLではなくAccessアプリの識別子です。公開URLとチームドメイン、AUD、メールは秘密ではありません。
セッション鍵は `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'` で生成し、更新後も同じ値を維持します。
`RSA_ATTACHMENT_HOSTS` は最初は空でよく、資料は認証済みブラウザの登録ページからアップロードできます。
`RSA_OAUTH_*`、`RSA_JWKS_URL`、`RSA_WEB_CLIENT_ID`、`RSA_ALLOWED_SUBS` はこの方式では不要です。

## Cloudflare側の設定

1. Tunnelの公開ホスト名を `slides.example.org` とし、Piホスト上の `cloudflared` なら `http://127.0.0.1:8010` へ転送します。
   元のHostを保持します。別コンテナの `cloudflared` からは共有network上の `http://api:8000` を使います。
   アプリのポートをLAN／インターネットへ直接公開しません。
2. Zero Trust → Access controls → Applicationsで、このホスト名全体を保護するアプリを追加します。
   `/mcp` だけでなく `/project/*`、`/artifact/*`、`/upload/*` も同じアプリで保護します。
   AllowポリシーのEmailsには自分のメールだけを指定します。BypassやService AuthでMCP・資料登録を通す設定にはしません。
3. アプリのApplication Audience (AUD) Tagを `RSA_CF_AUDIENCE` へコピーします。
4. Advanced settings → **Managed OAuth** を有効にします。ChatGPT用にDynamic Client Registrationを有効にし、
   Allowed redirect URIsにはChatGPTのMCP管理画面に表示される正確なredirect URIを登録します。
   開発用localhost許可や広いワイルドカードは通常不要です。
5. アクセストークンは例15分、Grant session durationは例1週間に設定します。更新トークンが有効な間はクライアントが更新し、期限後に本人が再ログインします。
6. Tunnelのトークンは `cloudflared` の設定として管理します。`api`・`worker` やChatGPTへは渡しません。

Accessが公開する `https://slides.example.org/.well-known/oauth-authorization-server` と、
MCPのリソースメタデータが、外部クライアントから取得できることを確認します。
OAuth discoveryを自分のプロキシやWAFでログインHTMLに置き換えないでください。
アプリもリソースメタデータを返しますが、OAuthの認可・トークン・登録エンドポイントはCloudflareが担当します。

## ChatGPTと資料登録画面の動作

ChatGPTにはHTTPSの `/mcp` を **OAuth** 接続として登録します。No authenticationにはしません。
初回接続または初回ツール実行時の案内からAccessのログイン画面へ進み、本人が認証します。
Cloudflareから受け取ったOAuthトークンをChatGPTが後続のMCP要求へ添付し、Accessが検証します。

Managed OAuthのアクセストークンは不透明な文字列です。PiはそれをJWTとして解析しません。
Accessがoriginへ渡す `Cf-Access-Jwt-Assertion` のRS256署名、チームissuer、アプリAUD、iat/exp、
アプリトークン種別、許可メール、空でないユーザーsubを検証します。メールヘッダーだけは信用せず、service tokenは拒否します。
所有者IDは `cloudflare:<Accessのsub>` で固定し、MCPとブラウザで同じIDを使います。

資料登録ブラウザもAccessで本人認証します。アプリの `/login` は別のOAuthへ飛ばず、
検証した本人へSecure/HttpOnly/SameSite cookieを発行します。資料登録・引用情報更新はこのcookie、CSRF、Origin照合を引き続き要求します。
各要求で新しいAccess assertionを必要とするため、アプリのcookieだけでは認証を迂回できません。
署名付きアップロード・ダウンロードURLも同じAccess認証と所有者一致が必要です。
ChatGPTの埋め込みビューアーでブラウザのAccess cookieが利用できない場合は、外部ブラウザでダウンロードURLを開きます。

`/health` とリソースメタデータだけはoriginでassertionなしに応答し、Docker healthcheckを可能にします。
Cloudflareを経由したアクセスにはAccess側の設定が適用されます。

## 受入試験

- 未ログインのMCP要求がログインHTMLではなく、OAuth discoveryを指す401を返す。
- ChatGPTから初回接続→Accessで本人認証→`get_profile`→プロジェクト作成ができる。
- MCPと資料登録ブラウザの利用者が一致し、資料登録→仕様保存→生成→PPTX取得ができる。
- アプリ独自のログイン画面／Keycloakへ遷移しない。
- 許可外メール、別AUD、別チーム、改ざん／期限切れJWT、JWTなし、Service Authを拒否する。
- cookieや署名付きURLだけではoriginへ直接アクセスできず、別の許可利用者でも他人の成果物を取得できない。
- トークン更新と期限後の再ログイン、Pi再起動、同一ユーザーでの再接続後も所有者が維持される。
- ChatGPTの実際のOAuth callback、MCP discovery、埋め込みビューアー表示まで確認する。

自動テストは署名したAccess assertionとMCP／ブラウザHTTPを使います。Cloudflareの管理画面設定や外部ChatGPT接続の成功を保証するものではありません。
認証方式やAccess組織を変更すると所有者IDも変わるため、以前のOAuth利用者のデータを自動で引き継ぎません。

根拠: [Cloudflare Managed OAuth](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/managed-oauth/)、
[Access JWT検証](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/)、
[Access application token](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/application-token/)、
[OpenAI MCP認証](https://developers.openai.com/plugins/build/auth)。

# 既存の認可サーバーを使う場合（従来方式）

`RSA_AUTH_MODE=oauth` と `.env.oauth.example` を使います。省略時も互換性のため `oauth` です。
この方式をCloudflare経由で公開する場合、AccessのManaged OAuthは併用せず、独自OAuthのchallengeを保持します。

MCPはOAuth resource server、Googleは上流login IdPです。このアプリがGoogle IDトークンをMCP bearer tokenとして使うことはありません。認可サーバーにGoogleを連携し、専用audienceのaccess tokenを発行します。

## 認可サーバー

Keycloak等のOAuth/OIDC broker、または同等のmanaged authorization serverを用意します。既に研究室の認証基盤があるならそれを使います。Google client secret、認可サーバー管理者資格情報、公開ドメインは提供されていないため、この開発では外部の認証設定やユーザー登録を行っていません。

Keycloakを使う場合の設定項目:

1. HTTPSのrealm `lab` を作成。Google Identity Providerを登録。Google Cloud ConsoleでWeb application用OAuth clientを作り、KeycloakのGoogle callbackを登録する。
2. `research-slide-mcp` public client: authorization code、PKCE S256必須、password grant/service accountは無効。ChatGPT管理画面が表示する正確なcallbackを登録。wildcardを使わない。
3. `research-slide-web` public client: code + PKCE S256、redirectを `https://slides.example.org/oauth/callback` に限定。
4. 両クライアントに `slides:write` scopeを許可し、access tokenにscope文字列を含める。
5. access tokenに audience `https://slides.example.org/mcp` を追加するmapperを設定。ID tokenにはこのaudienceを追加しない。RS256、access tokenの有効期限は短く（例5分）。
6. 認可サーバー側で `resource` の対象制限を確認。MCPのOAuthクライアントから渡されるresource indicatorを検証し、別のresource向けtokenを発行しないこと。固定audience mapperだけでプロバイダーの全てのMCP仕様対応を満たしたと判断しない。
7. authorization responseのiss、discoveryのissuerを一致させる。Googleのbroker連携ではメールを主キーにせず、上流Googleの安定subの対応を保持する。アプリ側はbrokerの安定subを使う。
8. 許可するGoogle利用者にログインしてもらい、brokerが発行するsubを管理者が確認しRSA_ALLOWED_SUBSへ追加。メール文字列はここに入れない。

Google federation/認可サーバーをPi自身に置くとRAMとDB運用が追加されるため、既存基盤の利用を優先。別途置くなら公式Keycloak imageと永続DB、HTTPS、backupを備える。アプリ用Docker stackに未設定の認証サーバーを同梱して公開しない。

## アプリ設定

```
RSA_BASE_URL=https://slides.example.org
RSA_OAUTH_ISSUER=https://auth.example.org/realms/lab
RSA_JWKS_URL=https://auth.example.org/realms/lab/protocol/openid-connect/certs
RSA_OAUTH_AUDIENCE=https://slides.example.org/mcp
RSA_WEB_CLIENT_ID=research-slide-web
RSA_ALLOWED_SUBS=<broker-sub-1>,<broker-sub-2>
RSA_SESSION_KEY=<32文字以上のランダム値>
```

両コンテナに同じ設定を渡す。MCP client IDとbrowser client IDを混同しない。MCPのclient ID/認証方法はChatGPT接続画面で事前登録clientとして指定する。アプリのmetadataは認可サーバーをadvertiseする。CIMD/DCRは本アプリでは実装しないため、使用するプロバイダーとクライアントの事前登録対応を確認する。

## 公開前の受入試験（未実施）

- InspectorのOAuth画面からPKCE、discovery、resource、code exchangeを確認。
- Googleログインでbrokerの安定sub、正しいiss/aud/scopeを確認。
- 許可外ユーザー、他audience、ID token、期限切れ、別projectのアクセス拒否。
- ChatGPTで事前登録clientを接続。管理画面の実際のredirect URIを登録。
- ツールschemaのScan Tools、fileParams、get_profileのoutputSchemaを確認。
- 承認なしで生成し、completed時のPPTXダウンロードを確認。
- cookieが無い/CSRFが無い/別originからの資料登録拒否を確認。
- ChatGPT UIの初期化、進捗、再実行、ダウンロードを確認。

[OpenAI公式認証ガイド](https://developers.openai.com/plugins/build/auth)、[MCP Authorization](https://modelcontextprotocol.io/specification/latest/basic/authorization)、[Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect)、[Keycloak OIDC](https://www.keycloak.org/securing-apps/oidc-layers)。
