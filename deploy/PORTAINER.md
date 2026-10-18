# Portainer Stack deployment

## 準備

- Docker Standalone / Compose対応のPortainer。SwarmはこのSQLite共有volume構成の対象外。
- 64-bit Linux ARM64またはAMD64。API/workerは同じホストの同じvolume。
- 1人利用はCloudflare Tunnel + Access + Managed OAuth。別の認可サーバーは不要。[AUTH.md](AUTH.md)参照。
- 抽出済み実マスターはGit管理された `templates/lab-template.pptx` をイメージに同梱。ホストへの別配置は不要。
- `RSA_SESSION_KEY` は `python3 -c 'import secrets;print(secrets.token_urlsafe(48))'` 等で生成し、Portainerの環境変数として管理。repoへ保存しない。

## 初回

1. ローカルビルドならリポジトリ直下で `docker build -t research-slide-agent:local .`。GHCRなら事前にprivate registry認証をPortainerへ登録。
2. `.env.example` の公開URL、Cloudflareチームドメイン、AccessアプリAUD、自分の許可メール、セッション鍵を設定。
   既存の独自OAuthを使う場合だけ `.env.oauth.example` を使う。
3. Portainer → Stacks → Add stack → Web editor に `deploy/portainer-stack.yml` を貼り付ける。Web editorはbuild contextを持たないためこのファイルにbuild命令はない。
4. Environment variablesに全ての値を設定。`RSA_IMAGE` は実在するコミットSHAタグを推奨。CIが作るタグは `latest` と完全commit SHAであり、`0.1.0`タグは手動で付与しない限り存在しない。
5. Deploy。APIとworkerの状態を確認。
6. ホストプロキシまたはホスト上のCloudflare Tunnelは `127.0.0.1:8010` に転送し、元のHostを保持。ホストの8000番はPortainerが使用するため避ける。別コンテナのproxyならAPIをそのnetworkに接続して`api:8000`を使う。APIのHost allowlistはRSA_BASE_URLのみ。
7. Accessの本人だけを許可するポリシーとManaged OAuthを設定し、外部のdiscoveryとInspectorでOAuth接続→ChatGPTで受入試験。[AUTH.md](AUTH.md)参照。
   Docker healthcheckはoriginの `/health` を使い、Accessへのログインは不要。

初回volumeはイメージ内の`/data`の所有者10001を引き継ぐ。既存volumeの権限が違う場合は管理者がこのvolumeだけ10001:10001へ合わせる。SQLiteをNFSや複数Piへmountしない。

workerは`network_mode:none`。元資料からの外部リンクは入力検証でも拒否。画像・フォント・入力はvolumeとイメージから取得し、生成時のネットワークは不要。

テンプレート更新は `templates/lab-template.pptx` と `.profile.json` を更新してイメージを再ビルドする。同じイメージタグをAPIとworkerに指定すると、両者が同じ書式を使う。研究本文を含む原本PPTX、手本PDF、プレビュー、開発用キャッシュは同梱しない。PDF由来の内容ルールMarkdownは配布用Pluginに含める。資料・DB・生成結果は `research_data` volumeへ保存する。

完成PPTXのプレビューはget_slide_previewの要求を既存キューへ入れ、network_mode:noneのworkerで描画する。
既存イメージのLibreOffice・Poppler・日本語フォントとuser/workerの同時ジョブ上限を使う。一覧は最大6頁。
APIは変換を実行しない。描画失敗でもPPTXは取得でき、retry_job(preview_job_id)で再試行可能。
Piでの処理時間・メモリとPowerPointとの差は本番受入で確認する。

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

proxy・WAF等にもAuthorization、Cf-Access-Jwt-Assertion、Cookie、query/cap、本文を記録させない。TLS終端からAPIまでは同一ホストまたは管理対象ネットワークに限定。公開APIのrate limitは既存proxyで設定する。

## ログと削除

workerのJSONログは `/data/logs/worker.log`。Python標準のTimedRotatingFileHandlerでUTC日次、過去6ファイルを保持。毎時maintenanceを書き込みrotationを進める。現在分と合わせ最大7日相当。ComposeのDocker log driverはnoneにして、コンテナログに二重保管しない。PortainerのConsoleやホストから対象volumeのログを確認する。

workerは起動時/毎時、作成7日後のプロジェクトを削除。`rsa cleanup` は手動実行も可能。ワーカー停止中もAPIの期限判定で取得を拒否する。共有テンプレートはイメージ内の `/templates` にあるため削除しない。バックアップやSSDスナップショットも保持期限を管理する。削除失敗は`WORKER_CYCLE_FAILED`のerror_codeとして残る。

## 更新・ロールバック

### ラズパイから直接更新する構成（Portainer APIキー不要）

`scripts/deploy_poll.py`は既存の`gh`ログインとDockerのGHCR認証を使い、
CIが公開した`deploy/production`の`compose.yaml`を取得する。
`.env.cloudflare`に認証設定が揃った場合だけ、イメージをpullし、APIとworkerを停止して
同じコミットSHAのイメージで起動する。取得に失敗した場合は既存コンテナを停止しない。
起動後はGitHub Deployments APIへ`production`環境の成功状態をすぐ登録するため、
GitHubリポジトリのDeployments画面でPiが稼働させたコミットSHAを確認できる。
報告に失敗した場合は`var/deploy/github-pending.json`へ保持し、次回の実行で再送する。
GitHub API認証にはPi上の`.env.deploy`にある`RSA_DEPLOY_GITHUB_TOKEN`を使う。
このtokenには対象repoのContents読み取りとDeployments書き込み権限が必要。tokenはコンテナへ渡さず、
Pi上の更新スクリプトだけが読み取る。既に稼働中の版も初回実行時に報告する。
設定が未完了の場合は不足する変数名だけを表示して終了する。

このPi用の`research-slide-agent-update.service`と`.timer`を`/etc/systemd/system/`へ配置して
`sudo systemctl enable --now research-slide-agent-update.timer`で有効にすると、
起動1分後と、前回処理の終了から1分ごとに確認する。
serviceは`User=kei`、repoの場所と認証ファイルの場所もこのPiに合わせている。
別ホストではこれらを変更する。Dockerへのアクセス権が必要。

手動確認は`sudo systemctl start research-slide-agent-update.service`、
結果は`journalctl -u research-slide-agent-update.service`で確認する。
停止する場合は`sudo systemctl disable --now research-slide-agent-update.timer`。
この方式ではPortainerがStackの作成元ではないため、コンテナの状態はPortainerで確認できるが、
Composeと環境変数の変更はこのrepoと`.env.cloudflare`で管理する。
`var/deploy/`に適用したComposeと状態を保存する。認証情報はGitHubへ送らない。

### Portainer GitOpsの定期確認

`main`のCIはテストとARM64/AMD64イメージの公開に成功すると、`deploy/production`ブランチの
`compose.yaml`を更新する。このファイルは両サービスのイメージを同じコミットSHAに固定する。
古いmainのCIが後から終わっても、現在のmainと違うSHAは公開しない。
GitHub Actionsの`deployment`ジョブだけが`contents: write`を使い、Pi上のrunnerは使わない。

Portainerでこの連携を使う場合は、StackをGit repositoryから作り、次を設定する。

- Repository: `https://github.com/cercil0605/ResearchSlideAgent`
- Reference: `refs/heads/deploy/production`
- Compose path: `compose.yaml`
- GitOps updates: 有効、MechanismはPolling、Fetch intervalは1分
- Re-pull image: 有効
- Force redeployment: 無効（新しいデプロイが公開されたときだけ更新）

非公開repoのGit認証とGHCRのpull認証は別々に登録する。環境変数は`.env.example`に従う。
公開済みComposeではイメージが固定されるため、`RSA_IMAGE`の環境変数による上書きはしない。
PortainerのGitOps Pollingが利用できるバージョン・エディションを使う。
GitHubからPortainerへ接続する必要はなく、Portainerの公開設定を追加する必要もない。

このPortainer GitOps方式を使う場合は、Pi上の `research-slide-agent-update.timer` は有効にしない。Piから直接Composeを更新する方式とPortainer GitOpsを同時に動かすと、同じコンテナを二重に管理して更新が競合する。

ロールバックはPortainerで一時的にGitOps更新を止め、`deploy/production`の直前のコミットを
Referenceに指定して再配置する。運用再開時はReferenceを上記ブランチに戻す。

### 手動更新

CIでtest/build後、PortainerのRSA_IMAGEをcommit SHAタグへ変更し再Deploy。実行中のworkerにはstop_grace_period 10分を設定。最終確認前に旧イメージとvolumeを破棄しない。ロールバックは旧タグへ戻す。SQLite schema変更を伴う更新は両方のプロセスを止め、整合したDBバックアップを取得してから行う。

イメージ監視による自動更新を使う場合は `RSA_IMAGE=ghcr.io/cercil0605/researchslideagent:latest` とし、
更新対象をこのStackのapi・workerだけに限定する。CIはテスト成功後にARM64/AMD64イメージをGHCRへ公開するため、Pi上のself-hosted runnerは不要。
監視ツールにはGHCRが非公開ならpull用資格情報を別途設定する。Portainerに登録した認証情報が自動的に監視ツールへ渡るわけではない。
両サービスを同じ更新サイクルで停止・再作成し、workerを待つ停止時間は10分に合わせる。
本家 `containrrr/watchtower` は2025-12-17にアーカイブ済みのため、新規導入する監視実装は別途選定する。
この変更では監視コンテナのインストールやホスト設定は行わない。
イメージ監視はenvやComposeの変更を反映しないので、それらを変えた場合はPortainerからStackを再配置する。

APIは生成しないため通常512 MiB、workerは上限2 GiB/2 CPU。Piに応じて調整する。メモリ不足のkillはlease回収後に最大3試行。40枚の実測を見て設定する。

2026-10-16の実機では `docker info` の `MemoryLimit=false` と `SwapLimit=false` を確認した。このPiではStackに `mem_limit` を書いても適用されない。メモリ隔離を前提に運用する場合は、ホストのmemory cgroupを有効にしてから `docker info` で対応を確認する。

[Portainer公式Stack作成手順](https://docs.portainer.io/user/docker/stacks/add)。
