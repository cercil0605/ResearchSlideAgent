# 検証記録

## 現行の説明順・完成画像（2026-10-20）

ロック済み依存関係のローカル全体試験は **218 passed / スキップなし**。ruff、配備スクリプトのNode試験4件、正本smoke、1.3デモ、重要3ページの生成・描画、合成11枚の保存→生成→要求時プレビューも成功。
下記の過去時点の件数や受入記録とは区別する。Microsoft SDK検査はCIで実行する。

入力・生成経路・サンプル・試験をSlideSpec 1.3へ統一した。旧1.0/1.1/1.2、旧フィールドと合成テンプレート生成処理は廃止した。
`test_narrative.py`は、研究の節順、実験後の指標、まとめ後の補足、図付き見本の各節への再利用を確認する。
全体例は`examples/research-quality.slidespec.json`（合成11枚）。研究事実や発表品質の完成見本ではない。

`test_previews.py`はAPIが変換せず隔離workerへ依頼すること、要求の重複排除、キャッシュ、PPTXハッシュ不一致、版の分離、所有者・期限、描画中の期限切れ、同時実行制限、失敗後の再試行を確認する。
`test_mcp.py`は実HTTPのMCPから画像を取得し、画像・PDFの署名URL、改ざん・期限切れの拒否を確認する。
API/cache試験の描画は模擬処理。`scripts/preview_smoke.py`は実際の生成worker→描画job→LibreOffice・Popplerを確認し、
CIのMicrosoft SDK検証にも同じ1.3のPPTXを渡す。
一覧で読みにくい箇所は個別画像で確認する。既存のLibreOffice・Poppler描画処理を再利用する。

生成記録は同梱rules_digestも保持するが、作成側LLMの読解・遵守の証明とは扱わない。
描画済みでもサーバーのvisual_reviewはnot_performedで、画像の意味を確認して修正するのは接続先LLM。
実ChatGPTでの同じ短い依頼による初回品質比較、別論文・別モデル、Piの描画性能、PowerPoint実機は今回の自動試験に含めない。
以下の旧「プレビューなし」は当時の検証記録。現行は生成完了後に要求時プレビューを提供し、作成側LLMが仕上げる手順とする。

## 制作規約の内容評価（2026-10-24追加、実生成での受入は未実施）

R14–R16とF02・F06・F07の変更は、制作LLMの判断手順を具体化するもの。
参照PDFの該当箇所と編集後の規約、authoring_contextが編集元と同じ全文・SHAを返すことをローカルで照合した。
これをLLMの理解・遵守や生成品質の受入成功とは扱わない。次の実生成では、従来と同じ論文・聴衆・時間・モデル等で比較し、
作成LLM以外のレビュー者が、以下の観点で本文・図表と制作中の確認記録を評価する。

- 各ページがその題材の必要事項を説明しているか。文字数やcontent_mapのキー数だけで判定しない。
- 関連研究の方法・結果が研究ごとに対応し、今回の課題につながるか。
- ページをまとめた場合も図中文字と本文が読めるか。分割した場合は各ページの担当内容が明確か。
- 完成画像の具体的な確認結果と修正・残件が記録され、修正後の生成物で再確認されているか。

詳しい制作上の判断基準の正本はPluginのreferences。ここではその複製を管理しない。

## 初回制作ルールと説明図（2026-10-18）

追加LLM APIを使わず、同じ制作ルールをMCP単体・完全なPluginへ渡す改修。
F01–F06で、論文の読解、説明粒度、原図と説明図の選択、文章、実験結果の対応、保存前の自己点検を定義した。
サーバー側は箇条書き記号の重複を拒否し、Strictの図枠で手順・分岐・集約・比較の接続を描画する。
マスター、テーマ、元テンプレートのバイト列は変更しない。図枠内の描画規則は書式版2026-10-18.1。

新規試験は、横・縦の4種類の関係、ネイティブ接続先、接続の改ざん検出、未対応図の出力中止、
通常文・分割ランの箇条書き重複、数値の負号・本文途中の中黒の保持、対応機能の取得を確認する。
比較の2例は実際に`kind: "comparison"`を使い、2入力→共通要素→結果を誤って拒否しないことを確認する。
ノードと接続ラベルの両方について、文字色のfillがDrawingMLの規定順序（線の後、フォントの前）にあることも確認する。
これはMicrosoft SDK検証で発覚した文字色設定の要素順違反に対する回帰試験であり、CIのSDK検証も維持する。
既存のMCP通信試験で、toolとResourceの返すルール全文が一致することも検証する。
これらは説明の分かりやすさを自動採点する試験ではない。

### 接続先LLMによる初回品質の比較

実運用での効果は、次の受入試験で確認する。未実施の条件を合格済みと報告しない。

1. 本番と同じルール・生成器へ更新し、MCPメタデータをRefreshする。完全なPluginの同梱ルールも更新する。
2. 新しい会話で、同じ論文・聴衆・時間と「おまかせで作成して」の短い依頼だけを渡す。過去の修正会話を渡さない。
3. MCP単体と完全なPluginの両方で、各対応LLMの初回成果物を比較する。ばらつきは複数回の実行で確認する。
4. 原論文とユーザーが評価した完成例を人が参照し、以下を確認する。枚数・文言の完全一致は要求しない。
   - 目的・入力・処理・出力が具体的で、実験で何を確かめたかを追えるか。
   - 用語と具体例が適切な順序にあり、専門外の研究者・学生が理解できる粒度か。
   - 見込みの枚数を守るために必要な説明を削っていないか。増加が必要なら説明単位で分割されているか。
   - 見出しが具体的で、短い本文に行為・対象・条件の関係が残っているか。
   - 原図と自作説明図が適切に使われ、順序・分岐・集約・比較が正しく描かれているか。
   - 指標・単位・N・比較時点・検定と記述統計が原論文と一致するか。
   - 箇条書きの重複、本文切断、ダミー、文字の欠けや重なりがないか。
5. 論文版、モデル、依頼文、コードSHA、rules_digest、正本SHA、書式版、初回Specと出力を記録する。
   ユーザーの指摘後に修正した版を「初回」として集計しない。別の論文でも確認する。

サーバーは接続先LLMの理解や指示遵守を保証しない。品質差の有無を、ルール全文の配信テストや画像8例の描画だけから結論しない。

対話モードの受入では「構成と粒度を相談してから作成」と依頼し、合意前に仕様保存・生成しないこと、
合意した聴衆・粒度を既定値で上書きしないこと、主張や全体構成を変更する必要があれば相談へ戻ることを確認する。
このLLMとの実対話の受入は未実施。MCP通信の自動試験は、会話上の合意を保証するものではない。

2026-10-17更新。現行の正本は `templates/lab-template.pptx` と `.profile.json`。
提供原本や過去の `artifacts/` がなくても、新しいcloneでテスト・生成ができる構成とする。

承認・プレビュー必須の撤廃後、全テストは **99 passed / スキップなし**（依存ライブラリの非推奨警告1件）。ruff、差分チェック、UIビルド、Skill検証、template/container smokeも成功。
Cloudflareの自動試験はテスト用RS256鍵で署名したassertionを使う。
MCP経由の本人確認・プロジェクト作成→仕様保存→承認なしのPPTX生成・構造検査→completed時のリンク取得・ダウンロードを確認した。ブラウザ資料登録のcookie/CSRF/Origin検査は維持する。
別チーム／別AUD／期限切れ／改ざん／必須claim不足／service tokenを拒否する。メールclaimの有無や値にかかわらず署名済みユーザーassertionを受け入れ、古いcookieやcap URLだけではAccess認証を迂回できないことも確認する。
旧OAuth・loopback開発認証の既存テストも維持している。

成果物URLの共有は `test_cloudflare_artifact_links_allow_another_access_user` で検証する。
作成者のMCPが発行したPPTX・参考PDF・PNGのURLを別のAccess利用者がアプリcookieなしで取得できること、署名なし／改ざん／期限切れ／別job・ファイル名／署名内ownerとjobの不一致／Access assertionなし／未完了job／期限切れプロジェクトを拒否することを確認する。別利用者によるプロジェクト操作・URL発行は引き続き拒否する。これはテスト用assertionでの自動検証であり、本番ブラウザでの取得成功の保証ではない。
2026-10-24に `test_cloudflare_auth.py`・`test_web_auth.py`・`test_mcp.py`・`test_previews.py` を実行し、42 passed（依存ライブラリの非推奨警告1件）。変更したPythonファイルのruffと差分チェックも成功。

以前の整理時は69 passed。実行ログは `artifacts/canonical-review/cleanup-test-results.txt`。
当時のブラウザ承認から5枚の生成・描画・取得までのsmokeも成功（`cleanup-smoke.json`）。

## 現在の検証対象

- 正本と入力に基づくページ複製、直接書式、箇条書きの階層・継続行・段落／ラン書式。
- ネイティブ表の1～3列、改行に応じた行高・文字サイズ・太字・中央揃え・余白・罫線、4行以上の配置。
- 表の青塗り、最下段罫線削除、文字サイズ、揃え、行高、列幅、余白、位置、表削除を検査が拒否すること。
- 40枚の複製とページ番号、はみ出し時の拒否、元ファイル保護、正本SHA・生成来歴。
- 所有権、期限、バージョン競合、ジョブ管理、入力検査、ブラウザ認証・CSRF。
- 新規生成・再生成・PPTXパッチを承認なしで実行。構造検査失敗時はcompletedにならない。完成後の要求時プレビューは所有者・期限の検査を通して提供する。
- MCPの実loopback HTTPでcompleted時のdownload_urlからPPTXを取得。未完了時にはリンクを返さず、期限切れは拒否。
- 旧承認・review行のあるDBを再利用。再アップロードによるパッチ元変更、形状SHA不一致、正本変更の拒否。
- 登録した資料画像をPPTXへ挿入し、元画像バイトを保持。
- ローカルモード：in-processのMCPで許可フォルダ外・シンボリックリンク・`..`・相対パスの拒否、生成と出力フォルダへの保存。`rsa local` を実際にstdioで起動し、同一プロセスのworkerでcompletedになること（`tests/test_local.py`）。
- ローカルモードの導入スクリプト（`Makefile`、`scripts/mcp-agent.sh`、`scripts/rsa-local-docker.sh`）：偽の `codex` コマンドで登録（`agy` は実機で `agy mcp add`／`agy mcp list` による登録まで確認、生成は未確認）・CLI未インストール時の中止・不正値・非対話時の中止、ptyでの番号選択、docker引数の組み立て（読み取り専用マウント）を手動確認。`make build`・`make update`の全体と、実際の `claude`/`codex` への登録、ChatGPTデスクトップからの利用は未確認。
- 実クライアントでの確認（2026-11-10、`scripts/rsa-local-docker.sh`でDockerコンテナのみ使用、論文はCVPR 2016のHe et al. "Deep Residual Learning for Image Recognition"）：Codex CLI（gpt-5.6-sol）は資料登録→原図切り出し→仕様保存→生成→完成画像確認→修正まで完走し、10枚のPPTXを作成した。Claude Codeは同じ手順で生成まで進んだが、利用上限に達して完成前に停止した。両方とも生成時のはみ出しが1件ずつ・slide_idなしで返り、再生成を繰り返した（Codexは16回）。この結果を受けて全ページを一度に返すよう変更した。Claude Desktop・Gemini CLI・PowerPoint実機での確認は未実施。
- PluginとSlideSpec JSON Schemaの一致。一般向けデモ・40枚生成・部分編集も同じ正本と1.3で検証。

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
   ORIGIN_NOT_ALLOWEDならChatGPTの取得先が `*.oaiusercontent.com` 配下か確認し、許可設定後にAPIを再作成。
   署名URLやトークンを公開せず、Cloudflare/所有者認証は解除しない。
3. 添付の新しいfile引数で再試行し、get_projectにPDFが1件、read_sourceが17ページと本文を返すことを確認。
4. 原図6/7/8等をrender→crop。図ごとのアップロード・著者年入力なしで出典が元PDFに対応することを確認。
5. 同じ発表条件で生成し、失敗PDFと原図の有無・切断・説明内容を比較。原図取得とSkillの効果は別々に記録する。

本番の添付取得先・実際のエラー応答はこの作業環境では確認していないため、設定変更や再ログインだけで
今回の本番障害が解消したとは報告しない。Dockerビルド・PowerPoint実機・実ChatGPT添付の受入も別途確認する。

## 添付ドメイン設定と文書整理の確認（2026-10-18）

- 添付転送・PDF操作・MCPの関連テストは38件成功（依存ライブラリの非推奨警告1件）。
- ワイルドカード配下と多段サブドメインの許可、親ドメイン・類似ドメイン・別ドメイン接尾辞の拒否、明示的な空設定での取得拒否を確認。
- ComposeとPortainer Stackの両方で、未設定時は `*.oaiusercontent.com`、明示的な空文字は空、完全一致ホスト指定はその値を維持することを `docker compose config` で確認。
- ruffと差分の空白検査に成功。実ChatGPT添付の転送、本番配備、PowerPoint実機の受入は今回の検証に含めない。

## SlideSpec 1.3：構成と掲載内容、複合配置

`tests/test_research_quality.py` は次を回帰試験にする。

- 背景・関連研究・目的・手法の順序、背景より先の独立した具体例の拒否。
- 目的・アプローチ・新規性の欠落、空の本文、存在しない欄、見出し・図題だけを内容とする指定の拒否。
- paper_section、節ごとのcontent_mapと実際のcontent_evidence。意味の審査はnot_performedのまま。
- 表示titleとpaper_sectionの併記、ページ内の未指定役割・同じ本文への役割重複の見直し情報。
- 同じ節・paper_section・列見出しの隣接表で片方が1行の場合の統合検討警告。異なる節・出典節・列・本編/補足は候補にしない。
- 複数実験と補足、旧1.0/1.1/1.2と旧入力フィールドの拒否。
- 本文＋小図、表＋原図／説明図、原図2点の配置。各画像の元バイト列、関係ID、図題、比率の保持。
- 改行に応じた表の行高、4部位を同じネイティブ表に載せる処理、文字サイズ・共有パーツの維持。
- 過密な表、未対応配置、表の裏へ本文が隠れる指定は完成ファイルを公開せず拒否。

`test_research_quality.py`は原図2点の各IDへの引用がない指定を拒否する。
`test_mcp.py`は見出しをcontent_mapに指定した1枚差し替えが保存前に拒否され、仕様と版が変わらないこと、有効な差し替えが保存・生成できることを実HTTPで検証する。
旧保存仕様をそのまま生成すると失敗し、1.3で新しい版を保存すれば生成できることも`test_state.py`で検証する。
`Store.save_spec`の直接呼び出しも同じ検査を通す。全体保存と1枚差し替えに別の検査経路を作らない。

合成試験と、改善版の重要3ページに対応する回帰入力を生成・描画する手順：

```sh
uv run python scripts/render_spec.py examples/research-quality.slidespec.json --output artifacts/quality-check --render
uv run python scripts/render_spec.py tests/fixtures/construction-regression.slidespec.json --output artifacts/construction-check --render
```

CIは両PPTXもMicrosoft Open XML SDKへ渡す。画像を返すことは内容レビューの成功ではない。
受入済み24枚の全体をLLMが原論文から再生成する試験と、別論文での品質・再現性の評価は未実施。
その試験では旧本文を答えとして渡さず複数回生成し、必要事項、原文の根拠、全ページの可読性を比較する。
枚数・文字列の完全一致や自己申告のチェック済みフラグを合格条件にしない。
