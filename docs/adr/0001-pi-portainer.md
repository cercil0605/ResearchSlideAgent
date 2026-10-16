# ADR 0001: Raspberry Pi + Portainer

2026-10-16 / Accepted for initial implementation

元仕様はGCP専用だったがユーザーの追加指示でRaspberry Pi運用を検討。既存Portainerを使い、同一ホストのapi/workerとSQLite WALの永続キューを採用する。研究資料をGitHub Actionsへ送らず、Actionsはテストとmultiarch image buildに限定する。

理由は最小の運用要素で常駐HTTP受付、非同期実行、再起動回復、データ保持を実現できること。single-host前提を受け入れ、NFS/複数Pi/Cloud Runへ直接横展開しない。Pi実機の性能は未計測。ARM64 Dockerで実動検証する。
