# PowerPointの互換性とPDFの基準

以下は2026-10-16の旧抽出経路の調査履歴。現在は修正版の見本ページを複製する。旧抽出コードと一時ログは整理済み。
現行の方式は [書式の正本と生成](TEMPLATE_AND_CONTENT_RULES.md) を参照。

2026-10-16。Macで卵デモを開くと修復が要求されたこと、Piで変換した手本PDFのフォント・表・配置が崩れていることを受けた調査と修正。

## PPTXの修復警告

Microsoft公式 `DocumentFormat.OpenXml` 3.5.1の `OpenXmlValidator` で比較した。

| ファイル | 修正前のXMLエラー | 修正後 |
|---|---:|---:|
| 先生の原本PPTX | 0 | 原本は変更しない |
| 抽出テンプレート | 118 | 0 |
| 卵デモPPTX | 95 | 0 |

抽出処理で、継承元と直接書式を結合するときに和文・欧文・複雑な文字体系のフォント要素の順序が崩れた。
DrawingMLの `a:latin`、`a:ea`、`a:cs` は順序が決まっているが、一部が `a:cs` の後へ追加されていた。
また、表紙の箇条書き色 `a:buClrTx` を重複追加していた。
属性値だけでなくXMLの子要素順序・個数が重要であり、python-pptxで開けることやLibreOfficeで描画できることはPowerPoint互換性の証明にならなかった。

`scripts/prepare_lab_template.py` を修正して再抽出し、原本のマスター・テーマはバイト単位で維持した。
CIでテンプレートと生成デモをMicrosoft SDKで検証し、1件でもエラーがあれば失敗させる。
追加検査で、python-pptx 1.0.2がグラフの軸IDに負数を使い、UInt32に反する6件のエラーも確認した。
生成時に軸の定義と全参照を小さな正整数へ揃え、UInt32とOfficeのInt32上限の両方を満たす。棒・折れ線・散布図で参照の整合性を試験する。
当時の一時ログは整理時に削除した。上表はその検証結果の記録。
これは修復を引き起こしうる不正XMLを取り除いた確認であり、Mac/Windowsの実PowerPointによる無警告の確認は別に必要。

## 手本PDF

現在の正本は、ユーザーが差し替えた `reference_materials/content-pdfs/slide_sample.pdf`。
28ページで、PPTXの表示スライド1–28に対応する。CreatorがPowerPoint、ProducerがmacOS Quartzであること、游ゴシック・Arial等のサブセットが埋め込まれていることを確認した。
本文抽出と全28ページの画像確認を実施し、構成ルール12項目を再照合した。
PDFのSHA-256と根拠は配布ルールMarkdownで管理する。既存の手本PDFをLibreOfficeで上書きしない。

## 見た目を保つ運用

1. Piで、指定PPTXのテーマ・マスター・レイアウトを使って編集可能なPPTXを生成する。
2. 正しいフォントが使えるMac/WindowsのPowerPointで開き、修復警告、文字、表、改行を確認する。
3. そのPowerPointの「ファイル → エクスポート」または「名前を付けて保存」からPDFを書き出す。
4. そのPDFを最終配布用とする。サーバーでのプレビュー生成は行わない。

PDFを差し替えても、Piにフォントがインストールされたり、生成物のPDF変換エンジンがPowerPointへ変わったりはしない。
Piで `fc-match 'Yu Gothic'` はNoto Sans、`fc-match Arial` はLiberation Sansを返した。
フォントが揃っても、別の変換エンジンによる表・行間・図形の差まで解消する保証はない。
原本の見た目の完全再現を、現在のPi/LibreOffice構成の機能として保証しない。
構造検査結果では `powerpoint_verified: false` とし、PowerPoint実機の表示確認済みとは扱わない。

フォント埋め込みはPowerPointで可能な範囲で使う。別の文章へ編集するテンプレートでは全字の埋め込みが適しているが、フォントごとの埋め込み可否を確認する。
今回のPDFに埋め込まれたサブセットを取り出し、汎用フォントとして流用する運用にはしない。

PowerPointでの最終PDF出力まで自動化するには、PowerPointを実行する別環境またはMicrosoft側の変換サービスが必要になる。
Microsoft GraphにもPPTX→PDF変換があるが、認証・OneDrive/SharePoint・サービス制約と書式を検証する必要があり、ローカルPowerPointとの完全一致を保証するものではない。今回その接続は実装していない。
現時点ではMacでのPDF出力を最終工程とする。

## 公式資料

- [Microsoft：OpenXmlValidator](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.validation.openxmlvalidator)
- [LibreOffice：Microsoft Office形式の変換制約](https://help.libreoffice.org/latest/en-US/text/shared/guide/ms_import_export_limitations.html)
- [Microsoft：PDFとして保存する](https://support.microsoft.com/en-us/powerpoint/training/save-powerpoint-presentations-as-pdf-files)
- [Microsoft：カスタムフォントの埋め込み](https://support.microsoft.com/ja-jp/office/fonts/benefits-of-embedding-custom-fonts)
- [Microsoft Graph：ファイル形式の変換](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format?view=graph-rest-1.0)
