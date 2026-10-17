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
