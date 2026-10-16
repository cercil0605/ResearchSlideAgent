# Google federation / OAuth

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
- 構成承認URL、ページ承認URLを別ブラウザで開き、生成前の拒否を確認。
- cookieが無い/CSRFが無い/別originからの承認拒否を確認。
- ChatGPT UIの初期化、進捗、画像、再実行、ダウンロード、修正メッセージを確認。

[OpenAI公式認証ガイド](https://developers.openai.com/plugins/build/auth)、[MCP Authorization](https://modelcontextprotocol.io/specification/latest/basic/authorization)、[Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect)、[Keycloak OIDC](https://www.keycloak.org/securing-apps/oidc-layers)。
