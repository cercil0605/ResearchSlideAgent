# MCP / HTTP API

MCPは `/mcp` のStreamable HTTP。公式SDKがinitialize、tools/list、tools/call、resources/readを処理する。schemaはPythonの型から生成。tool resultはstructuredContentとテキストを持ち、UI不要でも操作可能。

## MCPツール

| Tool | 入力・用途 |
|---|---|
| get_authoring_context | 引数なし。構成・本文作成前に必読。制作ワークフロー・教授ルール・過去資料ルール・正本入力手順の全文、文書SHAとrules_digest |
| get_profile | 引数なし。検証済み主体の安定したopaque id |
| get_template_info | 引数なし。正本SHA、書式版、prototype_idと差し替え欄・段落／ランの見本 |
| create_project | 引数なし。7日保持する個人project |
| get_project | presentation_id。現在版・資料一覧 |
| save_slide_spec | presentation_id, spec:SlideSpec, expected_version |
| patch_slide | presentation_id, slide_id, replacement:Slide, expected_version。仕様1枚を新バージョンで置換 |
| get_file_transfer_info | 引数なし。許可済み取得先ホスト・転送方法・上限。接続実績や疎通の証明ではない |
| create_upload | presentation_id。予備経路。10分のPUT URLとbrowser_url。Cloudflare方式はURLに加えてAccess本人認証が必要 |
| register_chatgpt_file | presentation_id, file:{download_url,file_id,mime_type?,file_name?}, author?, year?。論文PDFを一度登録 |
| set_source_metadata | presentation_id, source_id, author, year。確認済みの著者・年を設定。元PDFの派生画像へ継承 |
| read_source | presentation_id, source_id, page=1。PDF頁/PPTXスライド/XLSXシートを1始まりで取得 |
| render_pdf_page | presentation_id, source_id, page=1, dpi=144。元PDFのページをPNGのImageContentと寸法で返す。保存資料は増えない |
| crop_pdf_region | presentation_id, source_id, page, region:{left,top,right,bottom}, dpi=200。原図をPNG登録してsource_id・citation_source_id・実画像を返す |
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

## 制作ルールの取得

server instructionsは、構成・仕様保存・生成より先に `get_authoring_context` → `get_template_info` を呼ぶよう案内します。
ルール取得は読取専用です。返却値の `schema_version` はこのcontext形式の版であり、SlideSpecの版とは独立します。
`required_documents` は `workflow`、`professor`、`presentation`、`canonical`。
`documents[]` は `id`、`title`、`path`（Skillからの相対参照）、`sha256`、`text`（UTF-8全文）を持ち、要約や文字数切断をしません。
`rules_digest`は文書ID→SHAの集合を識別します。読込・理解の証明やユーザー承認トークンではありません。

Resource `research-slides://authoring-context`（application/json）も同一内容を提供します。
管理者が配布した制作規則と、`read_source`が返すuntrustedな論文本文は区別します。
必須文書の欠落・空本文・UTF-8不正は `AUTHORING_RULES_UNAVAILABLE` とし、部分的なルールを成功として返しません。
サーバーは読込済み状態や制作モードの承認状態をDBに追加せず、既存SlideSpecと生成APIの入力契約を維持します。

SlideSpec全体は `schemas/slidespec.json` と `examples/research-format.slidespec.json` を参照。スライド配置座標は入力しない。未知の入力フィールドは拒否する。references/citationsはプロジェクトの登録済みsource_idを要求。著者・年は論文と照合した登録値と一致させる。引用の意味的妥当性は資料と照合する。

## PDFの転送・原図

`register_chatgpt_file` はMCP認証されたツールからサーバーが添付取得先へGETする方式。
`download_url` と `file_id` は必須、`mime_type` と `file_name` は任意。名前がないPDF/PNG/JPEGはmagic bytes、
その他は対応MIMEから拡張子を決め、安全な内部名を付ける。ファイル名がある場合も既存の形式・パス検査を適用する。
取得先は `RSA_ATTACHMENT_HOSTS` の完全一致または明示した `*.suffix` パターン・HTTPS・公開IP・443番のみ。リダイレクトは追わず、MCP認証情報は送らない。
ChatGPT添付にはOpenAIが案内する `*.oaiusercontent.com` を指定する。空設定では拒否を維持する。
`ATTACHMENT_ORIGIN_NOT_ALLOWED` はホスト設定、`ATTACHMENT_HTTP_<status>` は添付取得元の応答、
`ATTACHMENT_DNS_FAILED/TIMEOUT/NETWORK_FAILED` は接続失敗を表す。URL・クエリ・レスポンス本文はエラーへ含めない。
403だけで有効期限切れか認証設定かは断定できない。新しいfile引数でも失敗するなら取得元・配備環境を調べる。

`render_pdf_page` は登録PDFのCropBoxを回転込みで表示する。`crop_pdf_region` はその画像の左上原点、
0～1の正規化座標を使う。left < right、top < bottom。ページは1始まり、DPIは72～300、長辺3200px上限。
上限によって実解像度が下がるため返却するpixel_width/pixel_heightを確認する。PNGは最大8 MiB。
Poppler `pdftoppm` をAPI側で使用（既存Dockerに同梱）。1ページずつ、同時描画1件、実行30秒上限。
PDFのJavaScriptや添付ファイル・外部リンクを実行せず、注釈は描画しない。
PDF処理の一次仕様: [Poppler pdftoppm](https://manpages.debian.org/bookworm/poppler-utils/pdftoppm.1.en.html)、
[OpenAI fileParams](https://developers.openai.com/plugins/reference#file-apis)。

両ツールはstructuredContentに寸法等のメタデータ、contentに実際のimage/pngを返す。URL文字列だけではない。
cropのsource_idをimage_referencesへ、citation_source_id（元PDF）を引用へ指定し、locatorにページ・図番号を記載する。
get_projectのfiles[].originに元PDFのsource_id/hash、ページ、領域、DPI、画素範囲、変換版を保存する。
同じ変換の再試行は同じ画像IDを返す。ページ閲覧は保存件数に含めない。切り出し図は資料10件とは別に80件まで。
各ファイル20 MiB、合計100 MiB、所有者・7日間の保持制限は共通。SQLiteのorigin列は既存DBへ追加する。
元PDFの著者・年は派生図に継承し、参照前ならset_source_metadataで一括更新できる。
派生図だけの引用情報変更は拒否し、元PDFまたは派生図が現在の仕様で参照済みなら元PDFの変更も拒否する。

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
完成PPTXのPDF・PNGプレビューは生成しない。原論文のページ表示・切り出し画像とは別機能。
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
