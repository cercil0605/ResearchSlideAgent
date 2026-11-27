# 検証状況

「動く」と言える範囲です。新しく確かめたら、日付と方法を書き足してください。

```mermaid
flowchart LR
    subgraph OK[確認済み]
        A[自動テスト<br/>pytest 250件]
        B[PowerPoint形式の検証<br/>Microsoft公式SDK]
        C[Codex CLIで<br/>論文1本を完走]
    end
    subgraph PART[一部だけ]
        D[Claude Code<br/>生成まで]
        E[agy<br/>登録まで]
        F[PowerPointから保存したPDF<br/>表・改行の実測のみ]
    end
    subgraph NO[未確認]
        G[remote: Cloudflare / OAuth<br/>ChatGPTからの利用]
        H[ChatGPTデスクトップ<br/>Claude Desktop / Gemini CLI]
    end
```

## 自動テスト（CI で毎回実行、`.github/workflows/ci.yml`）

| 何を | どう |
|---|---|
| コード全体 | `ruff` と `pytest`（`tests/`） |
| 同梱の正本 | `scripts/template_smoke.py` |
| 生成した PPTX の形式 | Microsoft の Open XML SDK で検証（`tools/pptx-validator/`） |
| イメージ | ARM64 / AMD64 をビルドして GHCR に公開 |

テストが確かめていることの主なもの：

- 見本ページの複製、書式の保持、はみ出したときの拒否、40枚の生成、元ファイルを壊さないこと
- 表（1〜3列）の書式。色・罫線・文字サイズなどを変えた出力を検査が拒否すること
- 持ち主・期限・版番号の競合・ジョブ管理・入力検査・ブラウザ認証と CSRF
- 実際の HTTP 経由の MCP で、完成後に PPTX を取得できること
- local：許可フォルダ外・シンボリックリンク・`..`・相対パスの拒否。`rsa local` を実際に起動して完成まで進むこと

## 実際の AI エージェントでの確認

| 日付 | 内容 | 結果 |
|---|---|---|
| 2026-11-10 | Codex CLI、Docker の local、論文 He et al. "Deep Residual Learning"（CVPR 2016） | 登録→図の切り抜き→保存→生成→画像確認→修正まで完走。10枚 |
| 2026-11-10 | Claude Code、同じ条件 | 生成まで。利用上限で停止 |
| 2026-11 | agy | `make register AGENT=agy` で登録できることまで |
| 2026-11 | `make doctor` / `make smoke`、`mcp-agent.sh`（偽の codex で選択・中止を確認） | 動作 |

## 容量・はみ出し・矢印ラベル（2026-11-18）

`research-slide-agent:local` のコンテナに作業ツリーをマウントし、`RSA_ENV=development` で実行しました。

| 確認 | 結果・範囲 |
|---|---|
| `ruff check src tests` / `pytest -q` | 245件合格（2026-11-20）。Starlette依存の非推奨警告1件 |
| `tests/test_fit_capacity.py` | 英単語と禁則文字の折り返し、表の高さ超過と短縮後の生成、最小行高の保持、本文4行上限、配置ごとの容量、1ページ内の複数のはみ出し、縦横の合流ラベル、配置不能なラベルの拒否、1行より長い英単語の文字単位の折り返し、表の複数セル・図の複数の箱のはみ出しを全件返すこと |
| `tests/test_local.py` | 保存時の2ページ・計4枠の指摘が失敗ジョブの `output.problems` と一致。`get_job` / `get_preview` の `output` はオブジェクト、未完了では `null`。完成PPTXのローカル出力も確認 |
| `tests/test_state.py` | 240件の配置エラーを欠けずに保存。内部保存は従来のJSON文字列のまま |
| 同梱の作例 | `template_smoke.py`、卵の例、`preview_smoke.py`、research-quality、construction-regression の生成が成功。後者2つはLibreOfficeで画像化も成功 |
| PowerPointの形式 | .NET 8コンテナでMicrosoft Open XML SDKの検証を実行。正本・上記5出力・Transformer修正版の計7ファイルでエラー0件 |
| `scripts/container_smoke.py` | 実HTTPのMCP経由で5枚を生成し、PPTXをダウンロード。新しい `output` オブジェクトで成功 |
| Transformer論文の保存済み19枚 | 旧設計書の4枚目は表の必要高さ3.26インチ／使用可能2.95インチとして拒否。短縮済み設計書は生成・画像化が成功 |
| 修正版4・9枚目の画像を目視 | LibreOffice表示で、表と下の本文の重なり、K・VとQのラベル同士の重なりがないことを確認 |

前のセッションでユーザーがPowerPointから保存したTransformer資料と建設機械資料のPDFを使い、行高・折り返しを測りました。`prototypes.py` は本文の行高を文字サイズの1.1倍、表を1.17倍として見積もります。LibreOfficeでは表の行がより高く描かれるため、両者が一致するわけではありません。修正版PPTXのPowerPoint実機表示は未確認です。

これは保存済み設計書の再実行と回帰検査です。新規論文からの比較は次節に記録しています。「再生成2回以内」や「必要な事実の省略ゼロ」を保証する結果ではありません。Transformerの評価用資料には以前の内容面の指摘も残っています。

## DDPM論文からの比較（2026-11-20）

同じ論文・同じ依頼を別々のCodexワーカーに渡し、変更前と統合版で一度ずつ作成しました。依頼は「研究室の論文紹介として15分程度、おまかせで最後まで」。両者とも各サーバーのMCPだけを使い、リポジトリのコードは読まず、生成上限は8回、完成画像を全ページ確認して修正する条件です。

- 論文：Hoら『Denoising Diffusion Probabilistic Models』、arXiv:2006.11239v2、25ページ
- 変更前：`86270b3`（当時のmain）、`research-slide-agent:baseline`
- 統合版：`79037b7`（容量・重なり対応＋`get_template_info`軽量化）、`research-slide-agent:eval`
- 両DBに登録されたPDFのSHA-256は一致：`aee5e07a802e8dfd2a386374c94fd61d1d056cb7e1e0fec4f28e8120ff5d8505`

| 確認 | 変更前 | 統合版 | 根拠 |
|---|---:|---:|---|
| 保存成功 | 8回 | 6回 | DBの`specs` |
| 保存呼び出し（入力検証で未保存を含む） | 10回 | 8回 | ワーカー報告。未保存の呼び出しはDBに残らない |
| 生成ジョブ | 8回 | 3回 | DBの`jobs`、`payload.kind=generate`。各ジョブの`attempts`は1 |
| 失敗した生成ジョブ | 4回 | 0回 | DBの`state=failed` |
| 初めて生成に成功するまで | 3回 | 1回 | DBの生成ジョブの順序 |
| プレビュージョブ | 4回 | 3回 | DBの`payload.kind=preview`。生成回数には含めない |
| `patch_slide` | 0回 | 0回 | ワーカー報告とDBの`patches`が一致 |
| 最終枚数 | 17枚 | 本編17枚＋補足2枚 | 最終保存の設計書・PPTX |
| 最初のツール呼び出しから最終生成の完了確認まで | 9分58秒 | 8分32秒 | ワーカー報告。後続の最終画像確認時間を含まない |

変更前の失敗4件は全て`LAYOUT_REQUIRES_USER_CHANGE`でした。1回目は11〜13枚目の表脚注と14〜16枚目の画像caption不一致、2回目は11枚目の表の高さと14〜15枚目の本文、3回目は画像確認後に補足した15・17枚目の本文、4回目は17枚目の本文です。

統合版は保存時の指摘を読んで、最初の生成前に設計書を2回修正しました（生成対象は保存版3・5・6）。ワーカーは枠名と必要・許容行数を使って本文を再配分し、最終保存の`fit_problems`は0件と報告しています。引用表記の入力検証では、改行前後に半角スペースが必要という原因が文言から分からず、修正を繰り返した点も報告されました。統合版の保存呼び出し8回には、ワーカー自身の記録処理の失敗による重複1回が含まれます。

両ワーカーは個別の全ページ画像を確認済みと報告しました。引き継ぎ後にも、全36枚の縮小一覧を目視し、PPTXの全文と論文本文・Table 1〜3・実験条件を照合しました。

| 内容・見た目 | 確認できたことと残件 |
|---|---|
| 内容 | 両版とも目的→順過程→ノイズ予測の学習→生成→評価→限界の説明がある。FID 3.17、テスト集合基準5.24、損失比較13.22／13.51／3.17、LSUNの比較値は論文と一致 |
| 評価の条件 | 無条件生成、1000段、各最終実験は学習1回・最小FID時点での報告を記載。統合版は大型モデルと通常モデルの違い、バッチ全体の生成時間も明記 |
| 省略 | 両版とも比較表は原表の抜粋で、全行は載せていない。統合版の損失の重み変更は定性的な説明。補足に式があるが、導出や補間実験の詳細は本編にない |
| 重なり・欠け | 一覧の目視では、目立つ重なりや本文の欠けは見当たらない。画素単位の自動検出やPowerPoint実機での確認ではない |
| 残る体裁 | 両版に欧文の不自然な字間。統合版12枚目の`L`・18枚目の語尾だけの改行、15枚目の小さいグラフ軸文字。変更前5枚目の画像と14枚目のコラージュも細部が小さい |

証拠はローカルの`~/ResearchSlides/eval/`に保持しています。`baseline/.rsa-data/state.sqlite3`と`eval/.rsa-data/state.sqlite3`を読み取り専用で集計し、`review/server-evidence.json`にジョブごとの結果・最終PPTXのSHA-256を保存しました。最終出力は次の組み合わせの`outputs/<project>/<job>/presentation.pptx`です。

| 版 | project | 最終job |
|---|---|---|
| 変更前 | `0c121e7a98f445f9b8519a9d9b64fe1f` | `bff0f730185e4c938f9526a6b70de96b` |
| 統合版 | `ce07b43463b548839c6ab458bd8d837b` | `ebadb465af4d455f874d839c2c7b4e66` |

今回の1回では失敗生成が減りました。ただし容量対応と軽量化を同時に入れており、個々の効果は分離できません。生成内容・配置・枚数も異なり、モデルの厳密な同一設定は記録されていません。総トークン使用量・費用・弱いモデルでの成功率・15分の通し練習は未計測です。

追加の[内容照合](ddpm-content-review.md)では、統合版19枚の可視テキスト・表・式と論文の根拠箇所を対応付けました。主要数値・学習と生成の手順に明白な誤りは見つかりませんでしたが、10枚目の「5万枚でスコアを計算」の対象が曖昧で、9・12・15枚目にも説明を明確にする余地があります。測定に使ったPPTXは修正していません。

引き継ぎ後の統合版確認では、読み取り専用で作業ツリーをDockerへマウントし、`uv sync --frozen --no-editable`後に`ruff check src tests scripts/measure_llm_payload.py`が成功、`pytest -q -p no:cacheprovider`は250件合格（Starlette依存の非推奨警告1件）でした。

## 未確認

- **修正版のPowerPoint実機表示**と、全ページ・各種フォントでの表示（完成画像は LibreOffice の近似表示です）
- **remote 一式**：Cloudflare Access の初回ログインとトークン更新、OAuth 方式、ChatGPT からの添付取り込みと表示
- ChatGPT デスクトップ（Codex / Work モード）、Claude Desktop、Gemini CLI での生成
- DDPM比較の反復試行、別の論文・別のモデルに広げた品質や再現性
- `make build` / `make update` の通し実行

## LLM に渡す量（2026-11-20）

`scripts/measure_llm_payload.py` で、ツールを実際に呼んだときの返事の長さを測りました。トークン数は「全角1文字=1、それ以外4文字=1」の概算です。

| 返事 | 変更前 | `get_template_info` 軽量化後 |
|---|---|---|
| ツール定義（remote 23個、毎回） | 24,065字（約6.0k） | 同じ |
| `get_authoring_context` | 35,959字（約27.0k） | 同じ |
| `get_template_info` | 85,666字（約23.0k） | 24,969字（約7.3k） |
| `save_slide_spec` の返事（合成8枚） | 4,844字（約1.3k） | 同じ |

`pytest -q` は、`pdftoppm` が無い macOS で PDF 描画の11件を除き合格しました（変更前も同じ11件が失敗）。

容量の目安（`slot_capacity`）を加えた統合版では、`get_template_info` は 41,453字（約11.7k）でした。引き継ぎ後にも両イメージで再測定し、変更前の85,666字（概算22,966トークン）に対して51.6%減、統合版の概算は11,700トークンでした。容量の表のぶん、軽量化だけの場合より約16,500字増えています。

統合版のツール定義は24,632字（約6.2k）、`get_authoring_context`は35,959字（約27.0k）、合成8枚の`save_slide_spec`の返事は5,068字（約1.4k）でした。上の表の「同じ」は軽量化だけの変更に対する結果です。DDPMの生成比較は前節の範囲で実施しましたが、実際の会話全体の入力トークンや品質改善を示す測定ではありません。
