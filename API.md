# MCP / HTTP API

MCPは `/mcp` のStreamable HTTP。公式SDKがinitialize、tools/list、tools/call、resources/readを処理する。schemaはPythonの型から生成。tool resultはstructuredContentとテキストを持ち、UI不要でも操作可能。

## MCPツール

| Tool | 入力・用途 |
|---|---|
| get_profile | 引数なし。検証済み主体の安定したopaque id |
| get_template_info | 引数なし。固定マスター、layout、theme、hash |
| create_project | 引数なし。7日保持する個人project |
| get_project | presentation_id。現在版・承認・資料一覧 |
| save_slide_spec | presentation_id, spec:SlideSpec, expected_version |
| patch_slide | presentation_id, slide_id, replacement:Slide, expected_version。仕様1枚を新バージョンで置換 |
| request_approval | presentation_id, stage:"outline"/"slide", slide_id。ユーザーに示すレビューURL |
| create_upload | presentation_id。10分のPUT URLとbrowser_url |
| register_chatgpt_file | presentation_id, file:{download_url,file_id,mime_type?,file_name?} |
| read_source | presentation_id, source_id, page=1。PDF頁/PPTXスライド/XLSXシートを1始まりで取得 |
| enqueue_generation | presentation_id, patch_id?。承認・上限をサーバーで検査 |
| get_job | job_id。queued/running/validating/completed/failed |
| retry_job | job_id。最大3回まで |
| get_preview | job_id。10分のページ画像・PPTX URL |
| show_viewer | job_id。同じ結果とMCP Apps UIメタデータ |
| inspect_uploaded_pptx | presentation_id, source_id。slide_number/shape_id/name/sha256 |
| propose_pptx_patch | presentation_id, source_id, changes。パッチ計画とレビューURL |

changesの要素:

```json
{"slide_number":1,"shape_id":3,"expected_sha256":"returned-by-inspect","text":"ユーザーと合意した新しい文章"}
```

SlideSpec全体は `schemas/slidespec-1.0.json` と `artifacts/demo.spec.json` を参照。座標は入力しない。出力専用のapproval_statusを入力に混ぜると拒否する。references/citationsはプロジェクトの登録済みsource_idを要求。著者・年はユーザー登録値と一致させる。引用の意味的妥当性は人が承認する。

## HTTP

- `GET /health`: 起動状態。秘密情報なし。
- `GET /.well-known/oauth-protected-resource[/mcp]`: RFC9728 metadata。
- `GET /login`, `GET /oauth/callback`: browser PKCE/OIDC login。
- `GET /project/{id}`: 認証済み資料登録・引用メタデータ確認ページ。
- `PUT /project/{id}/upload`: cookie/CSRF/Origin、raw bytes、X-Filename(UTF-8 percent encoded)、X-Author/X-Year任意。
- `PUT /upload/{id}?cap=...`: 期限付きのupload capability。資料本文のみ、引用メタデータはブラウザで確認。
- `POST /project/{id}/source/{source}/metadata`: browser cookie/CSRF/Origin、JSON `{author,year}`。仕様で参照済みの資料の変更は拒否。
- `GET /review/{id}`: 保存済み仕様を表示。
- `POST /review/{id}`: browser cookie、X-CSRF、正確なOriginが必要。モデル用のBearerだけでは承認不可。
- `GET /artifact/{job}/{name}?cap=...`: 所有権確認済みの署名URL。期限切れプロジェクトは拒否。

ファイル本文とトークンをログに含めない。proxyにもクエリ文字列・Cookie・Authorizationを記録させない。

## エラー

STATE/SPEC_VERSION_CONFLICT、APPROVAL_REQUIRED、OUTLINE_APPROVAL_REQUIRED、TEMPLATE_CHANGED_REAPPROVAL_REQUIRED、USER_JOB_LIMIT、PROJECT_NOT_FOUND_OR_EXPIRED、EDIT_CONFLICT等。HTTPには状態に応じて400/401、MCPにはisErrorを返す。ジョブは失敗状態と短いエラーコードを返す。内容不足をLLM APIで補完する処理はない。
