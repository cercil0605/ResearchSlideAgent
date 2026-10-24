# 手本PDFの管理

教授の文章による指示は `guidelines/professor-slide-guidelines-2025-12-02.txt` に原文のまま保存する。
更新日2025-12-02、SHA-256 `65a51981aa99ffd2867f665858d9c33986c7b1c784950a33d33fd0b21482451e`。
原文テキストは約19 KBなのでGit管理し、配布用の要約は `professor-guidelines.md` としてPluginに含める。
ユーザー指示・教授の明示事項・PDFからの推奨を区別して管理する。

`content-pdfs/slide_sample.pdf` は2026-10-16にユーザーが差し替えた、PowerPoint出力の28ページを正本とする。
SHA-256: `b9547268fc0a86d077de6514bdcee3dd3701491be6a12f03851b72dcff179d16`。
PDF本体はGit対象外。ルールと根拠の追跡情報をGit管理する。

既存PDFをLibreOffice変換で上書きしない。Piで作る変換テストやプレビューは `artifacts/` に保存する。
PowerPointで正しく表示されるMacまたはWindowsから、スライドをPDFとして書き出し、この場所へ配置する。
その後、`$update-presentation-rules` でページ・ハッシュ・既存ルールとの対応を再確認する。
今回のPDFは原本PPTXの表示スライド1–28を含み、非表示29–42は含まない。

PPTXの書式テンプレートは `templates/lab-template.pptx`。PDFからテーマ・マスターを再構築しない。
新規に生成したPPTXの最終PDFも、PowerPointで確認してから書き出す。手本PDFを差し替えるだけでは生成物の描画方式は変わらない。

## 追加の構成見本（2026-10-24）

`content-pdfs/実演による建設機械操作_改善版.pdf`は今回追加された24ページのPowerPoint出力。
SHA-256 `f78f8bd5a108e1a3f8d5f55aea28101d7ae4d2436059c72410780057f47f3679`。
本文全頁と全頁の一覧画像を確認し、構成名＋具体的な題材というタイトルの付け方をR13へ反映した。
関連研究の区別、ページごとの説明充足、本文と図表の組合せは、今回のユーザー指示と照合してR14–R15へ反映した。
完成画像の点検手順R16はユーザー指示に基づくもので、このPDFの制作過程を推定した規則ではない。
元の`slide_sample.pdf`を置き換えず、PPTXの書式原本も変更しない。研究事実の引用元には使わない。

## ローカルの提供原本

`local-inputs/` はGit・Docker対象外の保管場所。生成処理からは読み込まない。

- `学会発表スケルトン.pptx`: ユーザーの提供原本。`templates/lab-template.pptx`と同一内容。
- `eggs-original.pptx`: 比較に使った旧卵例。旧`artifacts/eggs/presentation.pptx`から内容を変えず移動。

実行に必要なのは `templates/lab-template.pptx` と `.profile.json`。
原本を残すのは受領時の資料の保管のためであり、サーバーの必須ファイルではない。
