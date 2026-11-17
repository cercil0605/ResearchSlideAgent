# 06 内容

スライドの「中身」をどう作り、どう確かめているかです。

## 役割分担

```mermaid
flowchart LR
    subgraph AI[AIエージェントの仕事]
        R[論文を読む] --> D[説明の順番と粒度を決める]
        D --> V[ページごとに図の役割を決める]
        V --> W[見出しと短い文を書く]
        W --> SC[保存前に自己点検]
        SC --> L[完成画像を見て直す]
    end
    subgraph SV[サーバーの仕事]
        RU[ルールを渡す]
        IN[資料を検査して渡す]
        CK[形を検査して指摘する]
    end
    RU -.-> R
    IN -.-> R
    SC -.-> CK
```

**内容の良し悪しを判断するのは AI だけです。** サーバーの指摘は「形」の指摘で、`content_review: not_performed`（内容は見ていない）と明記して返します。

## AI に渡すルール

`get_authoring_context` が、次の4文書を全文で渡します。原本は `plugins/research-slide-agent/skills/research-slides/references/` です。

| 文書 | 中身 |
|---|---|
| `authoring-workflow.md` | 作り方の手順 F01〜F07 |
| `professor-guidelines.md` | 教授の明示ルール G01〜（構成、図、引用、表など） |
| `presentation-guidelines.md` | 過去の発表資料から読み取った説明のしかた |
| `canonical-skeleton.md` | 設計書（SlideSpec）の書き方 |

作り方の手順（F01〜F07）：

```mermaid
flowchart LR
    F1[F01<br/>論文から<br/>説明の骨格] --> F2[F02<br/>粒度と順序]
    F2 --> F3[F03<br/>図の役割]
    F3 --> F4[F04<br/>見出しと文]
    F4 --> F5[F05<br/>実験と結果を<br/>対応させる]
    F5 --> F6[F06<br/>保存前の<br/>自己点検]
    F6 --> F7[F07<br/>完成画像で<br/>仕上げ]
```

基本の構成は「表紙 → 概要 → 背景 → 関連研究 → 目的 → 手法 → 実験 → 結果 → 考察 → まとめ」です。

## 論文から設計書まで

```mermaid
flowchart TD
    P[論文PDF] -->|検査して登録| S1[source_id]
    S1 -->|read_source| T[本文<br/>1回24,000字まで]
    S1 -->|render_pdf_page| I[ページ画像]
    I -->|crop_pdf_region| F[切り抜いた図<br/>新しいsource_id]
    T --> SP[設計書]
    F --> SP
    S1 -->|著者・年| C[引用]
    C --> SP
```

- 切り抜いた図は、元の PDF の著者・年を**自動で引き継ぎます**。図ごとに入力は不要です。
- 設計書の引用は、登録した資料の著者・年と**一致しないと保存できません**（`SOURCE_METADATA_MISMATCH`）。
- 本文が長いときは途中で切られ、`truncated: true` が返ります。

## 受け付ける資料

| 項目 | 上限・条件 |
|---|---|
| 種類 | PDF、PPTX、PNG、JPEG、CSV（UTF-8）、XLSX |
| 1ファイル | 20 MiB |
| 1つの作業場所 | 登録資料10件、切り抜き図80件、合計100 MiB |
| PDF | 暗号化なし、500ページまで |
| Office | マクロ、外部リンク、埋め込みバイナリは拒否 |

（`files.py`、`store.py` の `register()`）

## 設計書を保存したときの検査

```mermaid
flowchart TD
    S[save_slide_spec] --> A{型は正しい?<br/>40枚まで・順番が連続など}
    A -->|いいえ| E1[拒否]
    A -->|はい| B{版番号は最新?}
    B -->|いいえ| E2[SPEC_VERSION_CONFLICT]
    B -->|はい| C{引用・画像は<br/>登録済みの資料?}
    C -->|いいえ| E3[拒否]
    C -->|はい| D[保存して指摘を返す]
```

返す指摘の例：

| コード | 意味 |
|---|---|
| `MISSING_EXPLANATORY_VISUAL` | 表紙以外に図がない |
| `VISUAL_LAYOUT_UNSUPPORTED` | 選んだ見本に図や表の枠がない |
| `SHARED_CONTENT_TARGET_REVIEW` | 複数の役割（入力・処理など）が同じ本文枠を指している |
| `METHOD_FIGURE_LAYOUT_REVIEW` | 手法のページが図の説明だけになっていないか |
| `ADJACENT_TABLE_MERGE_REVIEW` | 隣のページの表とまとめられそう |

ほかに、見出し枠に見本の文字が残っているページ（`inherited_headings`）と、研究発表で各ページに必要な役割のうち足りないもの（`missing_page_roles`）も返します。

## なぜこうしたか

- ルールをサーバーから配ると、どの AI エージェントにも同じ版のルールが届きます。文書ごとのハッシュも返すので、どの版を使ったか追えます。
- サーバーは内容を判断しないので、指摘は「確認のきっかけ」です。合否ではありません。
