# 07 データと状態

何が保存され、どう変わり、いつ消えるかです（`store.py`）。

## 保存しているもの

```mermaid
erDiagram
    PROJECT ||--o{ SPEC : "版ごとに保存"
    PROJECT ||--o{ FILE : "資料・切り抜き図"
    PROJECT ||--o{ JOB : "生成・画像化・部分修正"
    PROJECT ||--o{ PATCH : "手直しPPTXの変更案"
    FILE ||--o{ FILE : "切り抜き図の元PDF"
    PROJECT {
        string id
        string owner "持ち主"
        time expires "作成から7日"
        int version "最新の版番号"
    }
    SPEC {
        int version
        string digest "内容のハッシュ"
        string template_sha "保存時の正本"
    }
    FILE {
        string id "source_id"
        string kind "pdf/png/pptx..."
        string author
        int year
    }
    JOB {
        string id
        string state
        int attempts "最大3"
        string error
    }
```

- データベースは SQLite 1つ（`<データ置き場>/state.sqlite3`）。ファイルは `<データ置き場>/<作業場所ID>/` の下に置きます。
- データ置き場は、local（Docker）なら `~/ResearchSlides/.rsa-data`、remote なら Docker のボリューム `/data` です。

## 版番号

```mermaid
flowchart LR
    V0[版0<br/>作成直後] -->|save_slide_spec<br/>expected_version=0| V1[版1]
    V1 -->|expected_version=1| V2[版2]
    V1 -.->|expected_version=0| X[SPEC_VERSION_CONFLICT]
```

保存のたびに版が1つ上がります。古い版を前提に保存しようとすると拒否されます（同時に2か所から書き換えて上書きするのを防ぐため）。

## ジョブの一生

```mermaid
stateDiagram-v2
    [*] --> queued: enqueue_generation
    queued --> running: workerが受け取る（試行回数+1）
    running --> validating: PPTXができた
    validating --> completed: 検査に合格
    running --> failed: 中身の問題<br/>（はみ出しなど）
    running --> queued: 一時的な失敗<br/>（3回未満なら自動で待って再挑戦）
    running --> queued: 30分応答なし
    failed --> queued: retry_job（3回まで）
    completed --> [*]
```

| 決まり | 内容 |
|---|---|
| 同じ設計書 | 同じ内容のジョブがあれば、新しく作らずそれを返す |
| 1人1ジョブ | 自分のジョブが動いている間は、次を入れられない（`USER_JOB_LIMIT`） |
| 全体の同時実行 | 1〜2件（`RSA_WORKER_LIMIT`） |
| 一時的な失敗 | ファイル読み書きの失敗などは、3回目まで自動で再挑戦（待ち時間は2秒、4秒と増える） |
| 中身の失敗 | はみ出しなどは自動では再挑戦しない。設計書を直して保存し直す |
| 応答なし | 30分たっても終わらないジョブは、やり直しに戻す |

## いつ消えるか

```mermaid
timeline
    title 作業場所の寿命
    作成 : create_project
    〜7日 : 使える
    7日後 : 使えなくなる（取得を拒否）
    次の掃除 : 資料・PPTX・記録を削除（workerが1時間ごと）
```

| もの | 期限 |
|---|---|
| 作業場所と中身すべて | 作成から7日（延長なし） |
| ダウンロード URL（remote） | 10分 |
| ブラウザのログイン（remote） | 30分 |
| local の出力フォルダにコピーした PPTX | **消えない**（あなたのファイル） |
| worker のログ（`<データ置き場>/logs/`） | 約7日（1日ごとに切り替え、6日分を保持） |

## なぜこうしたか

- 研究資料を長く持たないため、期限は作成から7日で固定しています。
- データベースを SQLite 1つにしたのは、Raspberry Pi 1台で動かすためです。
