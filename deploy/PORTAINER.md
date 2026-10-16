# Portainer Stack deployment

## 準備

- Docker Standalone / Compose対応のPortainer。SwarmはこのSQLite共有volume構成の対象外。
- 64-bit Linux ARM64またはAMD64。API/workerは同じホストの同じvolume。
- 公開HTTPSリバースプロキシと認可サーバー。AUTH.md参照。
- 抽出済み実マスターはGit管理された `templates/lab-template.pptx` をイメージに同梱。ホストへの別配置は不要。
- `RSA_SESSION_KEY` は `python3 -c 'import secrets;print(secrets.token_urlsafe(48))'` 等で生成し、Portainerの環境変数として管理。repoへ保存しない。

## 初回

1. ローカルビルドならリポジトリ直下で `docker build -t research-slide-agent:local .`。GHCRなら事前にprivate registry認証をPortainerへ登録。
2. `.env.example` をもとに実環境の値を決定。`RSA_ALLOWED_SUBS` はGoogle emailではなくbrokerのユーザーsub。
3. Portainer → Stacks → Add stack → Web editor に `deploy/portainer-stack.yml` を貼り付ける。Web editorはbuild contextを持たないためこのファイルにbuild命令はない。
4. Environment variablesに全ての値を設定。`RSA_IMAGE` は実在するコミットSHAタグを推奨。CIが作るタグは `latest` と完全commit SHAであり、`0.1.0`タグは手動で付与しない限り存在しない。
5. Deploy。APIとworkerの状態を確認。
6. ホストプロキシまたはホスト上のCloudflare Tunnelは `127.0.0.1:8010` に転送し、元のHostを保持。ホストの8000番はPortainerが使用するため避ける。別コンテナのproxyならAPIをそのnetworkに接続して`api:8000`を使う。APIのHost allowlistはRSA_BASE_URLのみ。
7. 外部の `https://.../health` と `/.well-known/oauth-protected-resource` を確認し、InspectorでOAuth接続→ChatGPTで受入試験。

初回volumeはイメージ内の`/data`の所有者10001を引き継ぐ。既存volumeの権限が違う場合は管理者がこのvolumeだけ10001:10001へ合わせる。SQLiteをNFSや複数Piへmountしない。

workerは`network_mode:none`。元資料からの外部リンクは入力検証でも拒否。画像・フォント・入力はvolumeとイメージから取得し、生成時のネットワークは不要。

テンプレート更新は `templates/lab-template.pptx` と `.profile.json` を更新してイメージを再ビルドする。同じイメージタグをAPIとworkerに指定すると、両者が同じ書式を使う。研究本文を含む原本PPTX、手本PDF、プレビュー、開発用キャッシュは同梱しない。PDF由来の内容ルールMarkdownは配布用Pluginに含める。資料・DB・生成結果は `research_data` volumeへ保存する。

ホストのテンプレートに差し替える場合だけ、Stackの `x-runtime.volumes` に `/srv/research-slide-agent/lab-template.pptx:/templates/lab-template.pptx:ro` を追加する。この場合は両コンテナを停止してファイルを更新し、同時に再起動する。

## HTTPSプロキシの例

既存のNginxの適切なserverブロックに合わせる例です。TLS証明書の用意と適用は管理者が行います。

```nginx
location / {
    proxy_pass http://127.0.0.1:8010;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_read_timeout 300s;
    client_max_body_size 20m;
    access_log off;
}
```

proxy・WAF等にもAuthorization、Cookie、query/cap、本文を記録させない。TLS終端からAPIまでは同一ホストまたは管理対象ネットワークに限定。公開APIのrate limitは既存proxyで設定する。

## ログと削除

workerのJSONログは `/data/logs/worker.log`。Python標準のTimedRotatingFileHandlerでUTC日次、過去6ファイルを保持。毎時maintenanceを書き込みrotationを進める。現在分と合わせ最大7日相当。ComposeのDocker log driverはnoneにして、コンテナログに二重保管しない。PortainerのConsoleやホストから対象volumeのログを確認する。

workerは起動時/毎時、作成7日後のプロジェクトを削除。`rsa cleanup` は手動実行も可能。ワーカー停止中もAPIの期限判定で取得を拒否する。共有テンプレートはイメージ内の `/templates` にあるため削除しない。バックアップやSSDスナップショットも保持期限を管理する。削除失敗は`WORKER_CYCLE_FAILED`のerror_codeとして残る。

## 更新・ロールバック

CIでtest/build後、PortainerのRSA_IMAGEをcommit SHAタグへ変更し再Deploy。実行中のworkerにはstop_grace_period 10分を設定。最終確認前に旧イメージとvolumeを破棄しない。ロールバックは旧タグへ戻す。SQLite schema変更を伴う更新は両方のプロセスを止め、整合したDBバックアップを取得してから行う。

APIは生成しないため通常512 MiB、workerは上限2 GiB/2 CPU。Piに応じて調整する。メモリ不足のkillはlease回収後に最大3試行。40枚の実測を見て設定する。

2026-10-16の実機では `docker info` の `MemoryLimit=false` と `SwapLimit=false` を確認した。このPiではStackに `mem_limit` を書いても適用されない。メモリ隔離を前提に運用する場合は、ホストのmemory cgroupを有効にしてから `docker info` で対応を確認する。

[Portainer公式Stack作成手順](https://docs.portainer.io/user/docker/stacks/add)。
