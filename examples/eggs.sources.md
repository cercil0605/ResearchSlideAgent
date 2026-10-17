# 「美味しい卵の食べ方」の出典メモ

2026-10-16作成。プラグインなしのローカル生成デモ用。
原本の研究内容を利用せず、新しい題材の文章・構成を作成した。

| source_id | 参照資料 | 年の扱い |
|---|---|---|
| kikkoman-fried-egg | [キッコーマン：目玉焼きの基本のつくり方](https://www.kikkoman.co.jp/homecook/tsushin/tips0066/) | 公開2024-09-03、更新2024-09-18 |
| kikkoman-rolled-egg | [キッコーマン：基本の卵焼き](https://www.kikkoman.co.jp/homecook/search/recipe/00004002/) | 発行年は未確認。スライド上の ` [キッコーマン閲覧 '26]` は閲覧年を示す |

目玉焼きの蒸し焼き・両面焼きによる食感の違いと、砂糖・しょうゆを使い卵液を分けて巻く卵焼きの基本を参照した。
ご飯・トーストとの組合せ、気分から料理を選ぶ表、説明の順序は今回のデモ向けの提案。
人気順位・栄養値・調理効果の実験結果を示すものではない。
参考ページの写真は使用していない。

`examples/eggs.slidespec.json` の文章を編集し、次で再生成できる。

このPiで作成済みのDockerイメージを使う場合は、リポジトリ直下で次を実行する。ホストのPython・uvは不要。

```bash
bash scripts/try_eggs.sh
```

別環境では先に `docker build -t research-slide-agent:local .` を実行する。コードやマスターを変更した後も再ビルドする。
Python 3.12以上・uv・LibreOffice・Popplerがある開発環境では、Dockerを使わず次でも実行できる。

```bash
uv run python scripts/render_spec.py examples/eggs.slidespec.json --output artifacts/canonical-eggs --render
```

`artifacts/canonical-eggs/index.html` をブラウザで開くと各ページを切り替えられる。
`presentation.pptx` は編集用、`preview/presentation.pdf` は閲覧用。
このPDFはLibreOfficeの参考表示で、PowerPointとの一致は保証しない。最終PDFはPowerPointから書き出す。
これはローカルで直接生成エンジンを試す手順であり、MCPサーバーの承認状態は操作しない。
