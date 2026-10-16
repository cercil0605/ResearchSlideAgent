#!/usr/bin/env bash
# Use the locally built image; no host Python, plugin, server, or OAuth needed.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if ! docker image inspect research-slide-agent:local >/dev/null 2>&1; then
  echo '先にリポジトリ直下で docker build -t research-slide-agent:local . を実行してください。' >&2
  exit 1
fi
mkdir -p "$repo_dir/artifacts/eggs"
docker run --rm --read-only --network none \
  --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:size=512m,mode=1777 --env HOME=/tmp \
  --mount "type=bind,source=$repo_dir/scripts/render_spec.py,target=/work/render_spec.py,readonly" \
  --mount "type=bind,source=$repo_dir/examples/eggs.slidespec.json,target=/work/eggs.slidespec.json,readonly" \
  --mount "type=bind,source=$repo_dir/artifacts/eggs,target=/output" \
  --workdir /work research-slide-agent:local \
  python render_spec.py eggs.slidespec.json --output /output --render
printf '\nブラウザで開く: %s/artifacts/eggs/index.html\n' "$repo_dir"
