# Google Cloudへの移行（未実装）

今回の追加指示に従い、実動する実装はRaspberry Pi + Portainerに切り替えています。GCPの課金リソースは作成していません。GCPアダプターやデプロイ可能なCloud Run manifestは作っていません。SQLite版をCloud Runへそのままdeployすると一時ディスクにデータを失い、インスタンス間で排他も成立しないためです。

移行を選ぶ場合は次の実装を完了してからdeployします。

| Piの実装 | 東京asia-northeast1の移行先・要件 |
|---|---|
| StoreのSQLite transaction | Firestore transaction。承認version/hash、owner上限、全体上限、lease/fencingを保持 |
| Docker volume inputs/artifacts | Cloud Storage。owner/project namespace、7日lifecycle、期限付きURL、期限後API拒否 |
| queued polling worker | Cloud Tasks。payloadはjob_idのみ、最大3試行、重複配信をdigestとleaseで排他 |
| APIコンテナ | Cloud Run public HTTPS + OAuth resource server |
| workerコンテナ | private Cloud Run worker HTTP、TasksサービスアカウントのOIDC audience検証、invoker最小権限 |
| 毎時cleanup | Cloud Scheduler認証付きendpoint + Firestore TTL/明示削除。削除遅延中も拒否 |
| daily file logs | 専用Cloud Logging bucket retention_days=7。Default bucketの既定値を流用しない |

Storageはsoft deleteの実設定を確認し、7日後の完全削除方針ならsoft-delete保持との合計日数を調整します。共有マスターは別bucket/プレフィックス、個人入力と別のIAM/retention。Cloud Tasks作成者とworker invokerを分離し、ジョブID以外の大きなpayloadを渡さない。

現状のユーザー向け機能をGCPで使えると主張するためのファイルではなく、Piから移行する時の作業境界です。

公式: [Cloud Run + Tasks](https://docs.cloud.google.com/run/docs/triggering/using-tasks)、[Storage soft delete](https://docs.cloud.google.com/storage/docs/soft-delete)。
