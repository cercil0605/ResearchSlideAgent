# Raspberry Pi / Portainer 運用判断

## 選択肢

| 方式 | 適性 | 判断 |
|---|---|---|
| PortainerでAPI+workerを常駐 | 対話からの随時生成、再試行、履歴、認証 | 今回採用。既存管理方法を使える |
| GitHub-hosted Actionsでテスト・multiarch build、Portainerで更新 | Pi上のビルド負荷を下げる | 推奨。CIは研究資料を処理しない |
| Piのself-hosted Actions runner | private repoでのビルド/デプロイ | 実現可能。ただし初期構成では不要 |
| Actions workflow_dispatchを生成キューにする | API受付・個人資料・2段階承認 | 採用しない。ジョブ状態/資料保持/認証が二重になる |
| GCP Cloud Run/Tasks | 複数台・可用性・負荷増加 | Pi運用の実測後に判断。現実装はGCP非対応 |

[GitHub公式runner仕様](https://docs.github.com/en/actions/reference/runners/self-hosted-runners) はLinux ARM64を記載しています。対応ステータスは変更されるので登録画面で確認。登録するなら **Settings → Actions → Runners → New self-hosted runner → Linux / ARM64** で表示される公式コマンドを使用し、systemd serviceで常駐します。Portainerで第三者runner imageを常駐させる必要はありません。

runnerを使う場合、private repo、信頼できるmain/手動デプロイに限定し、外部PRを走らせないでください。Docker socketへのアクセスは実質ホスト管理権限です。アプリのAPI/workerコンテナにrunnerやDocker socketを追加しません。[公式runner追加ガイド](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners)。

## Piの最初の試験

64-bit OS (`uname -m` が `aarch64`)、Pi 5/RAM 8 GB/SSD/冷却を設計上の開始目安とします。Pi 4/4 GBもワーカー1件で試せますが、実測前に可用性・性能を保証しません。32-bit OS向けイメージは用意していません。

1. ARM64イメージで5枚のsampleをrender。
2. 実マスター、必要な日本語フォントで5枚を確認。
3. 40枚で処理時間・最大RSS・温度・swapを記録。
4. worker再起動、Pi再起動、ディスク枯渇で再試行/失敗表示を確認。
5. 7日期限、ログ削除、HTTPS/OAuthを確認。

PiにGPUやローカルLLMは不要です。意味の設計はChatGPT側、PiはPPTX構造化とLibreOffice変換を担当します。

## 外部公開

ChatGPT側から届くpublic HTTPS endpointが必要です。LAN限定URL・localhostだけではリモート接続できません。既存のHTTPSリバースプロキシ、到達可能な回線/ドメインを利用します。Portainer UIやDocker socketを公開する必要はありません。CGNAT等で受信不能なら公開経路の追加が必要で、この作業ではルータやDNSを変更していません。
