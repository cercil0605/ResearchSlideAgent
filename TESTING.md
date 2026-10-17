# 検証記録

2026-10-17更新。現行の正本は `templates/lab-template.pptx` と `.profile.json`。
提供原本や過去の `artifacts/` がなくても、新しいcloneでテスト・生成ができる構成とする。

承認・プレビュー必須の撤廃後、全テストは **99 passed / スキップなし**（依存ライブラリの非推奨警告1件）。ruff、差分チェック、UIビルド、Skill検証、template/container smokeも成功。
Cloudflareの自動試験は25件で、テスト用RS256鍵で署名したassertionを使う。
MCP経由の本人確認・プロジェクト作成→仕様保存→承認なしのPPTX生成・構造検査→completed時のリンク取得・ダウンロードを確認した。ブラウザ資料登録のcookie/CSRF/Origin検査は維持する。
別チーム／別AUD／期限切れ／改ざん／不足claim／service token／許可外メールを拒否し、古いcookieやcap URLだけではAccess認証を迂回できないことも確認した。
旧OAuth・loopback開発認証の既存テストも維持している。

以前の整理時は69 passed。実行ログは `artifacts/canonical-review/cleanup-test-results.txt`。
当時のブラウザ承認から5枚の生成・描画・取得までのsmokeも成功（`cleanup-smoke.json`）。

## 現在の検証対象

- 正本と入力に基づくページ複製、直接書式、箇条書きの階層・継続行・段落／ラン書式。
- ネイティブ表の列幅、見出し／本文の行高・文字サイズ・太字・中央揃え・余白・罫線、本文1～3行。
- 表の青塗り、最下段罫線削除、文字サイズ、揃え、行高、列幅、余白、位置、表削除を検査が拒否すること。
- 40枚の複製とページ番号、はみ出し時の拒否、元ファイル保護、正本SHA・生成来歴。
- 所有権、期限、バージョン競合、ジョブ管理、入力検査、ブラウザ認証・CSRF。
- 新規生成・再生成・PPTXパッチを承認なしで実行。完成PPTXのプレビューPDF・PNGは生成せず、構造検査失敗時はcompletedにならない。
- MCPの実loopback HTTPでcompleted時のdownload_urlからPPTXを取得。未完了時にはリンクを返さず、期限切れは拒否。
- 旧承認・review行のあるDBを再利用。再アップロードによるパッチ元変更、形状SHA不一致、正本変更の拒否。
- 登録した資料画像をPPTXへ挿入し、元画像バイトを保持。
- PluginとSlideSpec JSON Schemaの一致。旧1.0の合成テンプレートによる基本生成・部分編集も互換性試験として保持。

旧42枚専用の抽出コードは削除済み。その抽出処理だけを対象としていた1試験と、原本がないとスキップする1試験も削除した。
これらは現行正本の検査ではない。正本の書式破壊を含む現行の回帰試験は残している。

## 過去のローカル描画確認（現行の必須手順から除外）

卵5枚と研究発表形式の試験用13枚をLibreOfficeで画像化し、モデルが各ページを実際に確認した。
最終生成後の画像も、確認済み画像と全ページ一致した。試験用数値と未入力の研究内容は明示している。
Microsoft Open XML SDKは正本・卵出力・研究形式出力ともエラー0件。

成果物は `artifacts/canonical-eggs/`、`artifacts/canonical-research/`、
画像とPPTXのSHAを含む記録は `artifacts/canonical-review/` にローカル保存している。
これらはGit対象外であり、[artifacts/README.md](artifacts/README.md) のコマンドで再生成する。
旧解析画像・中間出力・ビルドログは整理済み。互換性問題の原因と対策は [技術記録](docs/POWERPOINT_COMPATIBILITY.md) に残す。

PowerPoint実機、Cloudflare Managed OAuthの初回認証／トークン更新、外部OAuth、リモートChatGPTクライアントでの表示受入は未実施。
Cloudflare実アカウントのポリシー・Tunnel・DCR・ChatGPT callback設定は自動試験には含めない。[受入手順](deploy/AUTH.md)に従って実施する。
XML適合、画像配信、モデルによる画像確認、PowerPoint実機の確認は区別する。公開・デプロイは行っていない。

## 再実行

```bash
uv sync --frozen
uv run ruff check src tests
uv run pytest -q
uv run python scripts/prepare_skeleton_template.py
uv run python scripts/template_smoke.py
uv run python scripts/container_smoke.py
```

`prepare_skeleton_template.py` は同梱正本の検査で、ルートの提供原本は不要。
新しいスケルトンを取り込む場合だけ `--source /path/to/new-skeleton.pptx` を指定する。

`container_smoke.py` は一時ディレクトリとlocalhostだけを使い、承認・プレビューなしの仕様保存から生成・取得まで試験する。
コンテナ内では環境変数 `RSA_TEMPLATE` を使う。開発試験では `RSA_ENV=production` を指定しない。

Open XML SDK検証（.NET SDKが必要）:

```bash
dotnet run --project tools/pptx-validator --configuration Release -- templates/lab-template.pptx artifacts/template-check/presentation.pptx
```

UI変更時は `ui/` で `npm ci --ignore-scripts && npm run build` も実行する。
状態・ダウンロードUIのビルド、Skill検証、template/container smokeを実行する。
# 制作ルール配布の受入確認

この変更では **110 passed / スキップなし**、ruff、Skill基本検証、wheel/sdistビルドを確認した。
GitHub Actionsの結果と、実ChatGPTでの品質比較は別に確認する。Dockerイメージのビルド・本番更新はこの作業では行っていない。

`tests/test_rules.py`は必須4文書の全文・文書SHA、正本変更時のdigest更新、欠落/空本文/UTF-8不正時の失敗を検査する。
`tests/test_mcp.py`はlegacy/autoの実HTTPでserver instructions受信、読取専用tool、Resourceとtoolの全文一致を検査する。
これはルールを配信できることの検査であり、ChatGPTが読解・適用したことの保証ではない。

wheel単体でも正本を含むことを確認する（ソースチェックアウトがない場所からimportして取得する）。Dockerは
referencesをビルド入力に含め、同じwheelとしてインストールする。教授ルール用の別コピーを手編集しない。

ChatGPTでの手動受入はMCP単体と完全なPluginを分ける。

1. サーバーを更新し、カスタムMCP接続をRefreshして新しいチャットを開始する。
2. 「この論文を専門外の研究者・学生向けに10分で、おまかせで作成して」と依頼する。
3. 構成やsaveより前に `get_authoring_context` の必須4文書全文→`get_template_info` の取得があることを、ツール履歴で確認する。
4. 同じ論文・聴衆・時間・モデル・テンプレートで、ルールを明示読込した現行Strictの結果と比較する。
5. 「構成と説明粒度を相談してから作成」と依頼した場合は、会話での合意前に生成しないことも確認する。

比較時は論文版、コードSHA、文書SHA/rules_digest、テンプレートSHA、プロンプト、入力Spec、job/reportを記録する。
原図を事前にPNG登録する場合は両条件で同じ画像を使い、ルール読込と図表取得能力の差を混同しない。
文中切断、ダミー見出し、図題だけの代替がないか、用語導入・具体例・実験条件・結果解釈が改善したかを人が確認する。
現在のStrictには図を追加できない見本等の制約がある。ルール配信だけの比較と、下記PDF操作の比較を区別する。
Adaptiveはこの段階には含めない。

## PDF転送・原図登録

ローカルでは全体137件、ruff、wheelビルド、テンプレートsmoke、配備スクリプトのNodeテスト4件を確認。
SOCKSプロキシを避けるローカルHTTP試験ではproxy環境変数を外し、wheel試験はキャッシュ済み依存を使う
UV_OFFLINE=1で実行した。製品の通信・依存設定は変更していない。

前提: APIホストとテスト環境に `pdftoppm` が必要。Debian/Ubuntuでは `apt-get install poppler-utils`。
既存DockerとCIには同梱済み。新しいPython描画依存は追加しない。

自動試験:

- 公式fileParamsでfile_name/mime_typeが省略されたPDFを、モック添付HTTP→実MCP HTTP→登録まで処理。
- 取得ホストの空設定・完全一致・HTTPS・公開IP・ポート・資格情報なし・リダイレクト拒否を検証。
- HTTP 401/403/404/500、timeout/network errorを区別し、署名URLのqueryやレスポンス本文をエラーに含めない。
- 色分けした既知PDFで、0/90/180/270度回転と非ゼロCropBoxの表示・切り出し座標を画素単位で検証。
- 範囲外ページ、負／反転／非有限座標、DPI、最大辺3200px、描画タイムアウト・stderr秘匿を検証。
- ページ閲覧は登録件数を増やさず、同じcropの再試行は同じ画像ID。元PDFの著者・年を後から設定しても派生図へ反映。
- 10資料＋12派生図でも資料件数上限を消費しない。元PDF・派生図への他ユーザー／別プロジェクト／期限切れアクセスを拒否。
- 旧DBのfilesへorigin列を追加して既存行・IDを維持。参照済みの引用情報変更を拒否。
- PDF登録→ページのImageContent→cropのImageContent→元PDF引用→既存Strictジョブ→PPTXの画像バイト一致。
- 手動登録ページの複数選択とファイル名のHTMLエスケープ。既存cookie/CSRF/Access試験を維持。

実資料のローカル確認:

- 提供された17ページ論文の10ページ目Figure 7を、表示座標
  `{left:0.085,top:0.104,right:0.915,bottom:0.322}`、200 DPIで切り出し、画像を目視確認。
- 元PDFに紐づけたPNGを正本results_figureへ配置し、StrictジョブのcompletedとPPTX内のPNGバイト一致を確認。
- 論文・切り出し画像・検証用PPTXはGitへ含めない。発表全体の内容品質や本番転送の確認とは区別する。

配備後の受入:

1. APIを更新し、MCP接続をRefreshして新しいチャットでget_authoring_contextとget_file_transfer_infoを確認。
2. 実際の論文PDFを添付しregister_chatgpt_fileを呼ぶ。失敗時はツール名・エラーコード・HTTP状態で分類する。
   ORIGIN_NOT_ALLOWEDなら管理者が示されたホストの正当性を確認し、RSA_ATTACHMENT_HOSTSへ完全一致で設定してAPIを再作成。
   署名URLやトークンを公開せず、Cloudflare/所有者認証は解除しない。
3. 添付の新しいfile引数で再試行し、get_projectにPDFが1件、read_sourceが17ページと本文を返すことを確認。
4. 原図6/7/8等をrender→crop。図ごとのアップロード・著者年入力なしで出典が元PDFに対応することを確認。
5. 同じ発表条件で生成し、失敗PDFと原図の有無・切断・説明内容を比較。原図取得とSkillの効果は別々に記録する。

本番の添付取得先・実際のエラー応答はこの作業環境では確認していないため、設定変更や再ログインだけで
今回の本番障害が解消したとは報告しない。Dockerビルド・PowerPoint実機・実ChatGPT添付の受入も別途確認する。
