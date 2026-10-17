# MCP / HTTP API

MCPは `/mcp` のStreamable HTTP。公式SDKがinitialize、tools/list、tools/call、resources/readを処理する。schemaはPythonの型から生成。tool resultはstructuredContentとテキストを持ち、UI不要でも操作可能。

## MCPツール

| Tool | 入力・用途 |
|---|---|
| get_profile | 引数なし。検証済み主体の安定したopaque id |
| get_template_info | 引数なし。正本SHA、書式版、prototype_idと差し替え欄・段落／ランの見本 |
| create_project | 引数なし。7日保持する個人project |
| get_project | presentation_id。現在版・資料一覧 |
| save_slide_spec | presentation_id, spec:SlideSpec, expected_version |
| patch_slide | presentation_id, slide_id, replacement:Slide, expected_version。仕様1枚を新バージョンで置換 |
| create_upload | presentation_id。10分のPUT URLとbrowser_url |
| register_chatgpt_file | presentation_id, file:{download_url,file_id,mime_type?,file_name?} |
| read_source | presentation_id, source_id, page=1。PDF頁/PPTXスライド/XLSXシートを1始まりで取得 |
| enqueue_generation | presentation_id, patch_id?。正本・パッチ元・上限をサーバーで検査 |
| get_job | job_id。queued/running/validating/completed/failed。completed時は10分のdownload_urlを返す |
| retry_job | job_id。最大3回まで |
| get_preview | job_id。互換用。10分のPPTX URL、imagesは空配列 |
| get_generation_report | job_id。正本適合検査と生成来歴 |
| show_viewer | job_id。状態・ダウンロード用MCP Apps UI（ページ画像なし） |
| inspect_uploaded_pptx | presentation_id, source_id。slide_number/shape_id/name/sha256 |
| propose_pptx_patch | presentation_id, source_id, changes。保存したパッチ計画のpatch_id |

changesの要素:

```json
{"slide_number":1,"shape_id":3,"expected_sha256":"returned-by-inspect","text":"ユーザーと合意した新しい文章"}
```

SlideSpec全体は `schemas/slidespec.json` と `examples/research-format.slidespec.json` を参照。座標は入力しない。未知の入力フィールドは拒否する。references/citationsはプロジェクトの登録済みsource_idを要求。著者・年はユーザー登録値と一致させる。引用の意味的妥当性は資料と照合する。

引用の可視表記は教授指定の ` [著者 '25]`（半角スペース＋半角角括弧＋ASCIIアポストロフィ＋年下2桁）。
入力と保存データの `year` は4桁のまま保持する。「ら」はauthorに含まれる場合だけ表示し、推測して補わない。
正本の表は3列固定、本文1～3行。中央揃え、見出し15pt／本文16pt、見本の行高・余白・罫線を複製する。
最下段は黒罫線を保持する。数値の丸め・並替は行わない。

## SlideSpec 1.1

`schema_version="1.1"`、`purpose_mode="research"`（または一般向けの`general`）。
各ページは`prototype_id`、`title`、`replacements`を指定する。
replacementsは見本の欄名→段落配列。各段落は`prototype_paragraph`と`text`、または`runs`の`text/style_run`。
改行は継続行となり、別段落は配列を分ける。任意の書式・座標は受け付けない。
旧key_message/body_blocks/chart_specは1.1で拒否する。正本には独立したグラフの見本がない。
表はtable_spec、図は対応するdiagram_specまたは登録済みimage_references。
引用表記は対応する近傍のreplacementsにも含める。詳細は [入力手順](plugins/research-slide-agent/skills/research-slides/references/canonical-skeleton.md)。

新規生成・再生成・PPTXパッチに承認は不要。PPTX生成・構造検査の成功でcompletedとなる。
PDF・PNGプレビューの生成・表示とモデルによる画像確認は行わない。
既存DBはそのまま利用でき、旧承認テーブル／列は互換性のため保持する。旧ジョブの出力もPPTXを取得できる。
`get_generation_report`はコミット・ソースhash・正本SHA・書式版・仕様版／digestと書式適合検査を返す。
手動パッチには生成レポートがない場合があり、正本適合済みとして報告しない。

schema 1.0の合成／旧テンプレート経路は互換性試験用に保持する。
新しい正本でlayout_idや共通の要点行を指定する旧仕様は拒否する。

## HTTP

- `GET /health`: 起動状態。秘密情報なし。
- `GET /.well-known/oauth-protected-resource[/mcp]`: RFC9728 metadata。
- `GET /login`: Cloudflare方式は検証済みAccess本人へブラウザcookieを発行。従来OAuth方式はPKCE/OIDC loginへ遷移。
- `GET /oauth/callback`: 従来OAuth方式のcallback。Cloudflare方式では使用せず404。
- `GET /project/{id}`: 認証済み資料登録・引用メタデータ確認ページ。
- `PUT /project/{id}/upload`: cookie/CSRF/Origin、raw bytes、X-Filename(UTF-8 percent encoded)、X-Author/X-Year任意。
- `PUT /upload/{id}?cap=...`: 期限付きのupload capability。資料本文のみ、引用メタデータはブラウザで確認。
- `POST /project/{id}/source/{source}/metadata`: browser cookie/CSRF/Origin、JSON `{author,year}`。仕様で参照済みの資料の変更は拒否。
- `GET /artifact/{job}/{name}?cap=...`: 所有権確認済みの署名URL。期限切れプロジェクトは拒否。

ファイル本文とトークンをログに含めない。proxyにもクエリ文字列・Cookie・Authorizationを記録させない。

Cloudflare方式ではhealth／リソースメタデータ以外の全要求に、有効な `Cf-Access-Jwt-Assertion` が必要。
MCP用の不透明なOAuthアクセストークンはCloudflare側が検証し、originは署名付きAccess assertionを検証する。
upload／artifactのcapもAccess本人とのowner一致を要求する。ブラウザ操作は同じ本人のアプリcookieとCSRFも必要。
Cloudflare方式のMCPツールは `oauth2`、`scopes: []` を宣言し、独自の `slides:write` scopeをCloudflareへ要求しない。
認可サーバーメタデータ `/.well-known/oauth-authorization-server` はCloudflareが公開する。

## エラー

SPEC_VERSION_CONFLICT、TEMPLATE_CHANGED_RESAVE_REQUIRED、PATCH_NOT_FOUND_OR_BASE_CHANGED、USER_JOB_LIMIT、PROJECT_NOT_FOUND_OR_EXPIRED、EDIT_CONFLICT等。HTTPには状態に応じて400/401、MCPにはisErrorを返す。ジョブは失敗状態と短いエラーコードを返す。内容不足をLLM APIで補完する処理はない。
