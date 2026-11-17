#!/usr/bin/env bash
# Register / unregister the local MCP server with an agent CLI (claude, codex or agy).
#   mcp-agent.sh pick   [agent]   choose the agent (asks if omitted); aborts if its CLI is missing; prints the name
#   mcp-agent.sh add    [agent]   register scripts/rsa-local-docker.sh
#   mcp-agent.sh remove [agent]   unregister
set -euo pipefail

cmd="${1:-}"; agent="${2:-}"
name="${RSA_MCP_NAME:-research-slides}"
server="$(cd "$(dirname "$0")" && pwd)/rsa-local-docker.sh"

die() { echo "中止: $*" >&2; exit 1; }

choose() {
  if [ -z "$agent" ]; then
    [ -t 0 ] || die "対話できません。AGENT=claude|codex|agy を指定してください"
    PS3="番号を入力: "
    echo "登録するエージェントを選んでください:" >&2
    select agent in claude codex agy; do break; done
  fi
  case "$agent" in
    claude|codex|agy) ;;
    *) die "エージェントは claude / codex / agy のどれかを指定してください（指定値: '${agent}'）" ;;
  esac
  command -v "$agent" >/dev/null 2>&1 || die "$agent コマンドが見つかりません。インストール後にやり直してください"
}

case "$cmd" in
  pick)   choose; echo "$agent" ;;
  add)
    choose
    "$agent" mcp remove "$name" >/dev/null 2>&1 || true   # 再実行しても重複しない
    if [ "$agent" = claude ]; then
      claude mcp add --scope user "$name" -- "$server"      # どのフォルダからでも使えるようuserスコープ
    elif [ "$agent" = agy ]; then
      agy mcp add "$name" "$server"
    else
      codex mcp add "$name" -- "$server"
    fi
    echo "OK  $agent に $name を登録しました。$agent を再起動してください" ;;
  remove) choose; "$agent" mcp remove "$name" ;;
  *) die "使い方: $0 pick|add|remove [claude|codex]" ;;
esac
