#!/usr/bin/env bash
# Run the local-mode MCP server (stdio) entirely inside the Docker image.
# Register this script as the MCP server command in Claude Code, Codex CLI, Claude Desktop, etc.
#
#   RSA_LOCAL_DIR  folder for papers and outputs (default: ~/ResearchSlides)
#   RSA_IMAGE      image to run (default: research-slide-agent:local; build with `docker build -t research-slide-agent:local .`)
#
# The folder is mounted at the same absolute path, so paths the LLM sends and the
# local_path values it receives are the host paths. State lives in $RSA_LOCAL_DIR/.rsa-data.
set -euo pipefail

work="${RSA_LOCAL_DIR:-$HOME/ResearchSlides}"
image="${RSA_IMAGE:-research-slide-agent:local}"
mkdir -p "$work/outputs" "$work/.rsa-data"
work="$(cd "$work" && pwd -P)"

# Run as the calling user so files in the shared folder stay theirs; LibreOffice needs a writable HOME.
exec docker run -i --rm --init --network none \
  --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$work:$work" \
  "$image" \
  rsa local --input-dir "$work" --output-dir "$work/outputs" --data-dir "$work/.rsa-data"
