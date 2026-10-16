# 書式テンプレートと発表内容ルール

2026-10-16。Microsoft、python-pptx、OpenAI、Cloudflareの公式資料と現実装を照合した整理。
提供された `slide_sample.pptx` から書式テンプレートを作成し、本文・箇条書き用の固定枠で生成する経路を追加した。
手本PDFはユーザー提供のPowerPoint出力28ページへ差し替え済み。生成PPTXのXML修正と表示上の制約は [互換性の調査と運用](POWERPOINT_COMPATIBILITY.md) を参照。
公開設定やMicrosoft PowerPoint上の実機確認はまだ行っていない。

## 書式の定義

このプロジェクトでいう「スライドマスター」は、実用上は指定PPTXに含まれる
**テーマ・スライドマスター・スライドレイアウトを合わせた書式テンプレート**を意味する。

| PowerPointの要素 | 定義するもの |
|---|---|
| テーマ | テーマのフォント・配色・効果。位置や箇条書きの全設定はテーマだけでは決まらない |
| スライドマスター | 共通背景・ロゴ・装飾、タイトル/本文などの基本文字スタイル |
| スライドレイアウト | 表紙・本文・二段組などの種類ごとのプレースホルダー位置・寸法と書式 |
| プレースホルダー内の段落スタイル | 階層ごとの文字サイズ・色・箇条書き記号・インデント・行間・段落間隔 |
| 個別スライドの直接書式 | そのページだけの上書き。新規スライドへの共通継承は前提にできない |

新規スライドはレイアウトに紐付き、レイアウトはマスターに紐付く。
普通のテキストボックスを完成ページに置いただけでは、その位置や直接書式が新規スライドの規則になるとは限らない。
プレースホルダーは「クリックしてタイトルを入力」などと表示される内容用の枠で、通常のテキストボックスと区別する。
箇条書き記号を文字として手入力するだけでは、段落レベル・インデントの定義にならない。

根拠: [Microsoft: レイアウト](https://support.microsoft.com/en-us/powerpoint/what-is-a-slide-layout)、
[Microsoft: プレースホルダー](https://support.microsoft.com/en-us/powerpoint/add-edit-or-remove-a-placeholder-on-a-slide-layout)、
[Microsoft: 箇条書き](https://support.microsoft.com/en-us/powerpoint/add-bullets-or-numbers-to-text)、
[python-pptx: 継承とスライド追加](https://python-pptx.readthedocs.io/en/latest/user/slides.html)。

## 用意する簡潔なPPTX

既存の教授のPPTXを複製し、書式を維持したまま内容をダミー文に置き換える。
新しい無地のファイルへ見た目だけを作り直す必要はない。

1. デスクトップ版PowerPointの「表示 → スライドマスター」を開く。
   最上段のマスターと、その下の使用するレイアウトを確認する。
2. 共通の背景・装飾はマスターまたはレイアウトへ置く。
   表紙、本文、二段組、図中心など、実際に使う種類の枠は各レイアウトで定義する。
   使用するマスターは可能なら1つに整理する。元資料に複数ある場合は、勝手に消さず使用対象を示す。
3. タイトル、本文、必要なら引用・キャプション用の枠を定義する。
   位置と幅・高さだけでなく、枠内余白、縦位置、折返し、段落間隔も整える。
   役割が分かるレイアウト名を付けると対応付けやすい。固定の名称や番号にする必要はない。
4. 本文は使う階層ごとに、和文・欧文のフォント、文字サイズ・色、箇条書き記号とサイズ、
   記号の位置、本文開始位置、折返し行の開始位置、行間・段落前後の間隔を設定する。
   例えば第1～第3階層を使うなら、各階層を設定して見本を残す。
5. 通常表示でレイアウトごとに見本を1枚ずつ残す。長い行の折返し、日本語と英数字、箇条書きの階層を確認できるダミー文を入れる。
   引用や図のキャプションにも見本を入れる。マスターに載せにくい特殊な書式は見本ページに残して別途伝える。
6. 同じレイアウトを使った新規スライドで、枠や箇条書きを手調整せず同じ書式になるか確認する。
   複製ページは直接書式も引き継ぐため、この確認の代わりにはならない。
7. `.pptx` として `templates/lab-template.pptx` に保存する。
   PowerPointの再利用用テンプレート形式は `.potx` だが、現在のアプリに渡すファイルは `.pptx` とする。
   マスターやレイアウトはPPTXにも含まれる。`.potx` の拡張子を変更するだけでは変換にならない。

例として表紙・本文・本文＋図・二段組・まとめの3～5種類程度から始められる。
枚数・種類・文字サイズの数値はユーザーのPPTXに従い、この文書で新たに指定しない。
表・グラフ・図中ラベルの独自スタイルまで厳密に揃える場合は、その見本も含める。
これらの全てが本文プレースホルダーから自動継承されると仮定しない。

根拠: [Microsoft: マスターとレイアウトによるテンプレート作成](https://support.microsoft.com/en-us/powerpoint/create-and-save-a-powerpoint-template)。

Mac・Windows・Piのプレビューで必要なフォントが利用できるかも確認する。
PiのLibreOfficeプレビューは参考表示とし、最終PDFは正しく表示されるPowerPointから出力する。
フォント名の指定だけでは別端末にフォントは追加されない。埋込み可能性はフォントによって異なり、
PowerPointの埋込みがPiのLibreOfficeでそのまま使えるとは、この実装では確認していない。
勝手に代替フォントへ変えず、利用できないものを報告する。
根拠: [Microsoft: カスタムフォント](https://support.microsoft.com/en-us/office/fonts/download-and-install-custom-fonts-to-use-with-office)、
[Microsoft: フォント埋込み](https://support.microsoft.com/en-gb/office/fonts/benefits-of-embedding-custom-fonts)。

## 提供された見本からの抽出結果

`scripts/prepare_lab_template.py` が `templates/lab-template.pptx` と `.profile.json` を作成する。
原本のSHA-256を照合する、今回の見本専用の抽出レシピである。別資料へ無検証で流用しない。

| layout_id | 用途 | 本文用の枠 |
|---|---|---|
| 5 | RSA 表紙 | title、key_message（発表者・所属等） |
| 7 | RSA 本文 | key_message、body、citations |
| 8 | RSA 本文と図 | key_message、body、visual、citations |
| 9 | RSA 二段組 | key_message、body、body_right、citations |
| 10 | RSA 図表 | key_message、visual、citations |

原本はマスター2種類・レイアウト18種類を含む。全42ページが2つ目のマスターを使用していた。
両マスターとテーマは元のXML・関係ファイルをバイト単位で保持する。
表紙のレイアウトと、使用されていなかった4つのレイアウトを整理し、それ以外のレイアウトも保持する。
このためマスターの見た目を描き直すことも、研究本文42ページを残すこともせず、約160 KBの5枚の見本にまとめられる。

表紙はp.1のタイトル・所属欄・ブランド画像と元レイアウトの区切り線を利用する。
本文の外側の範囲はp.3、本文・箇条書きはp.8、下位項目はp.28、引用はp.7から抽出する。
表紙タイトル28 pt、通常タイトル24 pt、本文・第1階層18 pt、下位項目16 ptを利用する。
引用欄は原本から取得した12 pt・行間130%と枠内余白に合わせ、一行を収められる高さを確保する。
出典追跡は `.profile.json` に記録する。局所的な強調色や全ページの配置を一つの標準に潰したものではない。

内容の違う発表に再利用するため、本文範囲内を要点・本文/図表・引用の固定枠に分けた。
二段組の分割や要点/引用用の行の予約は生成用に正規化した部分で、原本の全ページが同じ配置だったという意味ではない。

固定枠では位置・寸法・段落書式をPPTXから取得し、図表もvisual枠内へ配置する。
Blockの `level`、`bullet`、`slot` で段落階層と左右の列を指定する。座標・フォントサイズは受け付けない。
文字が収まらない場合は枠拡張や縮小を行わず停止する。従来の合成テンプレート用生成経路は別に維持する。
本文・表紙の欧文/和文フォント、文字色、箇条書きと行間を固定枠に保持する。
普通のテキストボックスを本文用プレースホルダーへ移す際は、元の文字色等も明示し、別のマスター既定値が混ざらないようにする。

生成後はmaster/layout/themeの意味的変更を検知した上で元のXMLバイト列を維持する。
図表のネイティブ構造・承認済み文字列・位置・重なりを検査するが、フォント代替やOffice間の描画差は実機確認が残る。
ネイティブ図表の全ての装飾が見本中の全図表と完全一致するという保証ではない。

```bash
uv run python scripts/prepare_lab_template.py
uv run python scripts/template_smoke.py
```

後者は研究事実を含まない6枚の合成スライドを生成してPDF・PNGへ変換する。
本物の研究発表の構成・内容承認を省略してよいという意味ではない。

## PDF由来の内容・構成ルール

- 原本: `reference_materials/content-pdfs/`。
- 開発用Skill: `.agents/skills/update-presentation-rules/SKILL.md`。
- 配布用ルール: `plugins/research-slide-agent/skills/research-slides/references/presentation-guidelines.md`。

抽出済み `templates/lab-template.pptx` と `.profile.json`、ルールMarkdown、SkillはGit管理する。
原本 `slide_sample.pptx`、手本PDF、生成プレビュー、テスト出力はGit管理しない。
Dockerイメージには抽出済みPPTXと出典情報を同梱し、参考PDFや原本なしで生成できる。
PDFからルールを更新する開発者は、別途原本PDFをこのフォルダへ配置する。
PDFは手本としての説明順序、主張と根拠の対応、図表の説明方法などを学ぶ資料であり、
新しい発表の実験結果を裏付ける資料として自動で引用しない。

開発時に `$update-presentation-rules` を呼ぶと、PDFの追加・変更を調べてルールを更新する。
明示された必須指示と、手本から読み取った推奨を区別し、ファイル名・PDFページ・SHA-256で根拠を追跡する。
単にルールを増やすのではなく、矛盾・重複・根拠の消失も見直す。
Skillは更新手順であり、カレンダーやcronの定期実行は設定していない。
根拠: [OpenAI: リポジトリ内のSkillと呼出方法](https://learn.chatgpt.com/docs/build-skills)。

配布用ルールは既存の `research-slides` Skillから参照する。MCPサーバー単独ではMarkdownを自動で読み込まない。
ルール変更を利用中のChatGPTへ反映する際には、配布パッケージの更新・再読込を確認する。
既存プロジェクトや承認済み仕様を、ルール更新だけで自動的に書き換えない。

## 公開ホスト名

Cloudflare Tunnelで、Pi上のサービスへ割り当てる外向きのドメイン名。
例えば所有ドメインが `example.com` なら `slides.example.com` というサブドメインを割り当てる。
これは例示であり実際のドメインは未設定。

| 項目 | 設定例 |
|---|---|
| TunnelのPublic hostname / 公開アプリのホスト名 | `slides.example.com` |
| Tunnelの転送先Service | `http://localhost:8010` |
| Dockerのホスト側公開ポート | `127.0.0.1:8010:8000` |
| アプリのRSA_BASE_URL | `https://slides.example.com` |
| ChatGPTへ登録するMCP接続URL | `https://slides.example.com/mcp` |

前提は `cloudflared` がPiホストのサービスとして動く場合。
`localhost:8010` はPiの内側の宛先、`slides.example.com` は外部からアクセスする名前。
Tunnelの管理名・UUIDやPortainerのコンテナ名とは別。
前回の実機確認ではPortainerがホストの8000番を使用しており、既存Stack例の8000番をそのまま使うと競合する。
Compose/PortainerのStack定義は8010番へ変更済み。実際のStack配備とTunnelのルート追加はまだ行っていない。

Cloudflareの管理画面で「Networking → Tunnels → 対象Tunnel → Routes」を開く。
追加する場合は「Add route → Published application」でHostnameとService URLを設定する。
既存の画面によりPublic Hostnames等の表記もある。ホスト名と転送先Serviceの組を確認する。
根拠: [Cloudflare: ホスト名とサービスの対応](https://developers.cloudflare.com/tunnel/concepts/routing/)、
[Cloudflare: 公開アプリのルート設定](https://developers.cloudflare.com/tunnel/get-started/#publish-an-application)。
