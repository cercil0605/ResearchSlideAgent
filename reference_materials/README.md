# 手本PDFの管理

`content-pdfs/slide_sample.pdf` は2026-10-16にユーザーが差し替えた、PowerPoint出力の28ページを正本とする。
SHA-256: `b9547268fc0a86d077de6514bdcee3dd3701491be6a12f03851b72dcff179d16`。
PDF本体はGit対象外。ルールと根拠の追跡情報をGit管理する。

既存PDFをLibreOffice変換で上書きしない。Piで作る変換テストやプレビューは `artifacts/` に保存する。
PowerPointで正しく表示されるMacまたはWindowsから、スライドをPDFとして書き出し、この場所へ配置する。
その後、`$update-presentation-rules` でページ・ハッシュ・既存ルールとの対応を再確認する。
今回のPDFは原本PPTXの表示スライド1–28を含み、非表示29–42は含まない。

PPTXの書式テンプレートは `templates/lab-template.pptx`。PDFからテーマ・マスターを再構築しない。
新規に生成したPPTXの最終PDFも、PowerPointで確認してから書き出す。手本PDFを差し替えるだけでは生成物の描画方式は変わらない。
