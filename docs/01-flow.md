# 01 処理の流れ

AI エージェントがどう呼び、サーバーの中で何が起きるかです。

## 登場するもの

```mermaid
flowchart LR
    L[AIエージェント<br/>考える担当] <-->|MCP| M[入口<br/>server.py]
    M <--> D[(保存場所<br/>SQLite + ファイル)]
    D -->|順番待ちの仕事| W[worker<br/>PPTXを作る担当]
    W --> D
```

- **入口**は、すぐ終わる仕事（保存、読み出し、ページの画像化）をその場で返します。
- **時間がかかる仕事**（PPTX 生成、完成画像の作成）は「ジョブ」として順番待ちに入れ、**worker** が後で処理します。

## 新しく作るとき

```mermaid
sequenceDiagram
    autonumber
    actor U as あなた
    participant L as AIエージェント
    participant M as 入口
    participant W as worker

    U->>L: 論文を渡して依頼
    L->>M: ルールとテンプレート情報をもらう
    L->>M: 作業場所を作る（create_project）
    L->>M: 論文を登録する
    L->>M: 本文を読む・ページを画像で見る・図を切り抜く
    Note over L: 構成と文章を考え、<br/>スライド設計書（SlideSpec）を書く
    L->>M: 設計書を保存（save_slide_spec）
    M-->>L: 改善の指摘（authoring_feedback）
    L->>M: 生成を頼む（enqueue_generation）
    M->>W: ジョブを渡す
    W->>W: PPTXを作って検査
    L->>M: 状態を聞く（get_job）
    L->>M: 完成画像を見る（get_slide_preview）
    M->>W: 画像化ジョブ（初回だけ）
    alt 直したい
        L->>M: 設計書を直して保存 → もう一度生成
    end
    M-->>L: PPTXの場所
    L-->>U: 完成
```

ポイントは2つです。

- 設計書を保存すると、サーバーは**内容ではなく形**の指摘（見出しが残っている、図がない、など）を返します。
- 完成画像は、**AI が自分の目で確かめる**ためのものです。サーバーは見た目の良し悪しを判断しません。

## 人が手で直した PPTX を少し変えるとき

```mermaid
sequenceDiagram
    participant L as AIエージェント
    participant M as 入口
    participant W as worker
    L->>M: 手直し済みPPTXを登録
    L->>M: 中身の一覧をもらう（inspect_uploaded_pptx）
    L->>M: 変える文字を提案（propose_pptx_patch）
    M-->>L: patch_id
    L->>M: patch_id で生成を頼む
    W->>W: 指定した文字だけ置き換え
```

- 変えられるのは**単純な文字の枠だけ**です。書式が混ざった文字や表は変えません。
- 置き換えない部分は、元ファイルと**1バイトも変わりません**。

## なぜこうしたか

- 生成と画像化は時間とメモリを使う（LibreOffice を動かす）ので、入口と分けて順番に処理します。
- サーバーが内容を考えないのは、追加の AI 料金をかけず、どの AI エージェントでも同じ動きにするためです。
