# ローカルの生成物と検証記録

このフォルダはPPTX・PDF・ページ画像・検証ログの出力先です。
**Git管理するのはこのREADMEだけ**で、サーバー実行やDockerイメージには不要です。
新しいcloneに既存の成果物は含まれません。入力例から再生成できます。

| 残している出力 | 内容 |
|---|---|
| `canonical-eggs/` | 正本書式による卵の説明例5枚、画像、PDF、仕様と生成来歴 |
| `canonical-research/` | 試験用の研究発表形式13枚、画像、PDF、仕様と生成来歴 |
| `canonical-review/` | 今回の画像確認・書式比較・テスト・整理の記録 |

古い42枚資料の解析画像、旧テンプレートの生成例、途中の互換性調査・ビルドログは整理済みです。
提供原本は `reference_materials/local-inputs/` に保管し、このフォルダの生成物と分けています。

再生成例（Python 3.12以上、uvが必要）:

```bash
uv run python scripts/render_spec.py examples/eggs.slidespec.json --output artifacts/canonical-eggs
uv run python scripts/render_spec.py examples/research-format.slidespec.json --output artifacts/canonical-research
uv run python scripts/template_smoke.py
```

プレビューは `templates/lab-template.pptx` を使います。
更新前の成果物を再生成で上書きする場合は、必要なPPTXや検証記録を先に別の場所へ保存してください。
このフォルダのローカルデータは不要になったら削除できます。
`var/` は資料・ジョブ・DBを持つ実行データなので、同じ感覚で削除しないでください。
