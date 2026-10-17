# 検証記録

2026-10-17更新。現行の正本は `templates/lab-template.pptx` と `.profile.json`。
提供原本や過去の `artifacts/` がなくても、新しいcloneでテスト・生成ができる構成とする。

整理後の全テストは **69 passed / スキップなし**。ruffと差分チェックも成功。
実行ログは `artifacts/canonical-review/cleanup-test-results.txt`。
ブラウザ承認から5枚の生成・描画・取得までのsmokeも成功（`cleanup-smoke.json`）。

## 現在の検証対象

- 正本と入力に基づくページ複製、直接書式、箇条書きの階層・継続行・段落／ラン書式。
- ネイティブ表の列幅、見出し／本文の行高・文字サイズ・太字・中央揃え・余白・罫線、本文1～3行。
- 表の青塗り、最下段罫線削除、文字サイズ、揃え、行高、列幅、余白、位置、表削除を検査が拒否すること。
- 40枚の複製とページ番号、はみ出し時の拒否、元ファイル保護、正本SHA・生成来歴。
- 所有権、期限、承認、バージョン競合、ジョブ管理、入力検査、ブラウザ認証・CSRF。
- MCPの実loopback HTTPで生成し、PNGをimageコンテンツとして取得。未完了／範囲外／期限切れを拒否。
- PluginとSlideSpec JSON Schemaの一致。旧1.0の合成テンプレートによる基本生成・部分編集も互換性試験として保持。

旧42枚専用の抽出コードは削除済み。その抽出処理だけを対象としていた1試験と、原本がないとスキップする1試験も削除した。
これらは現行正本の検査ではない。正本の書式破壊を含む現行の回帰試験は残している。

## ローカルの描画確認

卵5枚と研究発表形式の試験用13枚をLibreOfficeで画像化し、モデルが各ページを実際に確認した。
最終生成後の画像も、確認済み画像と全ページ一致した。試験用数値と未入力の研究内容は明示している。
Microsoft Open XML SDKは正本・卵出力・研究形式出力ともエラー0件。

成果物は `artifacts/canonical-eggs/`、`artifacts/canonical-research/`、
画像とPPTXのSHAを含む記録は `artifacts/canonical-review/` にローカル保存している。
これらはGit対象外であり、[artifacts/README.md](artifacts/README.md) のコマンドで再生成する。
旧解析画像・中間出力・ビルドログは整理済み。互換性問題の原因と対策は [技術記録](docs/POWERPOINT_COMPATIBILITY.md) に残す。

PowerPoint実機、外部OAuth、リモートChatGPTクライアントでの表示受入は未実施。
XML適合、画像配信、モデルによる画像確認、PowerPoint実機の確認は区別する。公開・デプロイは行っていない。

## 再実行

```bash
uv sync --frozen
uv run ruff check src tests
uv run pytest -q
uv run python scripts/prepare_skeleton_template.py --render-preview
uv run python scripts/template_smoke.py
uv run python scripts/container_smoke.py
```

`prepare_skeleton_template.py` は同梱正本の検査・プレビューで、ルートの提供原本は不要。
新しいスケルトンを取り込む場合だけ `--source /path/to/new-skeleton.pptx` を指定する。

`container_smoke.py` は一時ディレクトリとlocalhostだけを使い、実際のブラウザセッション・CSRF付き承認から生成・取得まで試験する。
コンテナ内では環境変数 `RSA_TEMPLATE` を使う。開発試験では `RSA_ENV=production` を指定しない。

Open XML SDK検証（.NET SDKが必要）:

```bash
dotnet run --project tools/pptx-validator --configuration Release -- templates/lab-template.pptx artifacts/template-check/presentation.pptx
```

UI変更時は `ui/` で `npm ci --ignore-scripts && npm run build` も実行する。
今回の整理ではUIや認証方式は変更していない。
