#!/usr/bin/env bash
# Run the local-mode MCP server (stdio) entirely inside the Docker image.
# Register this script as the MCP server command in ChatGPT desktop (Codex mode), Claude Code, Codex CLI, etc.
#
#   RSA_LOCAL_DIR   folder for outputs and state (default: ~/ResearchSlides), mounted read-write
#   RSA_INPUT_DIRS  colon-separated folders the LLM may read papers from, mounted read-only
#                   (default: ~/Downloads:~/Documents:~/Desktop, those that exist)
#   RSA_IMAGE       image to run (default: research-slide-agent:local; `make build` creates it)
#
# Folders are mounted at the same absolute path, so paths the LLM sends and the
# local_path values it receives are host paths. State lives in $RSA_LOCAL_DIR/.rsa-data.
set -euo pipefail

work="${RSA_LOCAL_DIR:-$HOME/ResearchSlides}"
image="${RSA_IMAGE:-research-slide-agent:local}"
mkdir -p "$work/outputs" "$work/.rsa-data"
work="$(cd "$work" && pwd -P)"

mounts=(-v "$work:$work")
inputs_args=(--input-dir "$work")
IFS=':' read -r -a input_dirs <<< "${RSA_INPUT_DIRS:-$HOME/Downloads:$HOME/Documents:$HOME/Desktop}"
for dir in "${input_dirs[@]}"; do
  [ -n "$dir" ] && [ -d "$dir" ] || continue
  dir="$(cd "$dir" && pwd -P)"
  [ "$dir" = "$work" ] && continue
  mounts+=(-v "$dir:$dir:ro")
  inputs_args+=(--input-dir "$dir")
done

# Run as the calling user so files in the shared folder stay theirs; LibreOffice needs a writable HOME.
exec docker run -i --rm --init --network none \
  --user "$(id -u):$(id -g)" -e HOME=/tmp \
  "${mounts[@]}" \
  "$image" \
  rsa local "${inputs_args[@]}" --output-dir "$work/outputs" --data-dir "$work/.rsa-data"
