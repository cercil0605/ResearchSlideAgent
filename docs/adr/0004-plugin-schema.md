# ADR 0004: Portable package and real SDK validation

2026-10-16 / Accepted

公式OpenAI PluginドキュメントとAgent Plugins1.0 JSON schemaを確認。root plugin.json/mcp.jsonとskills/を採用。OpenAI interfaceはplugin.jsonのextensions.com.openai、MCP Apps標準ui.resourceUriとtext/html;profile=mcp-appを使う。

確認時、OpenAIページはmcp.jsonのserverにextensions.com.openai.authを置く例を含む一方、配布元mcp.schema.jsonのstreamableHttpServerはadditionalProperties:falseでextensionsを許容しなかった。実スキーマに通るportable mcp.jsonを採用し、OAuthの事前登録clientは接続管理画面で設定する。元スキーマをschemas/に保存しテストする。

MCP SDKはPyPIの最新安定2.3.0を確認しlock。MCPServer、注入Context、snake_caseの型、公式Clientのlegacy/auto両モードを実HTTPで試験する。Transport設定はstreamable_http_appへ渡す。MCP Appsは公式ext-apps Appで初期化/通知/tool call/messageを実装。ファイル入力は公式openai/fileParamsの4プロパティを宣言し、download_url/file_idのみrequired。構造化出力はdict[str,Any]または明示Modelで宣言する。

Sources: https://developers.openai.com/plugins/build/plugins , https://developers.openai.com/plugins/build/chatgpt-ui , https://developers.openai.com/plugins/reference , https://agent-plugins.org/schemas/1.0.0/mcp.schema.json , https://py.sdk.modelcontextprotocol.io/migration/
