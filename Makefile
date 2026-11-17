# ローカルモード（ChatGPTデスクトップ / Codex / Claude Code）の操作をまとめたMakefile。
# `make` だけで一覧を表示します。
SHELL := /bin/bash
IMAGE ?= research-slide-agent:local
SCRIPT := $(CURDIR)/scripts/rsa-local-docker.sh
AGENT ?=
AGENTCTL := $(CURDIR)/scripts/mcp-agent.sh

.DEFAULT_GOAL := help
.PHONY: help setup build update register unregister doctor smoke

help: ## この一覧を表示
	@echo "初回:        make setup     (エージェントを選択 → イメージ作成 → 登録 → 状態確認)"
	@echo "コード更新後: make update    (git pull + イメージ再作成。登録し直しは不要)"
	@echo ""
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-18s %s\n", $$1, $$2}'

setup: ## 初回セットアップ。claude/codexを選び、なければ中止（AGENT=claude|codex で指定可）
	@agent=$$("$(AGENTCTL)" pick "$(AGENT)") || exit 1; \
	$(MAKE) build && "$(AGENTCTL)" add "$$agent" && $(MAKE) doctor

build: ## Dockerイメージを作る（初回・Dockerfile変更後）
	docker build --build-arg RSA_CODE_COMMIT=$$(git rev-parse --short HEAD 2>/dev/null || echo unknown) -t $(IMAGE) .

update: ## 最新コードを取り込んで再ビルド。クライアントの再登録は不要
	git pull --ff-only
	$(MAKE) build
	@echo "完了: ChatGPT/Codex/Claudeを再起動（または新しいチャット）で新版が使われます"

register: ## claude/codexへ登録のみ行う（AGENT=claude|codex。省略時は選択）
	@"$(AGENTCTL)" add "$(AGENT)"

unregister: ## 登録を外す（AGENT=claude|codex。省略時は選択）
	@"$(AGENTCTL)" remove "$(AGENT)"

doctor: ## Docker起動・イメージ・スクリプトの状態を確認
	@docker info >/dev/null 2>&1 && echo "OK  Dockerが起動しています" || { echo "NG  Docker Desktopを起動してください"; exit 1; }
	@docker image inspect $(IMAGE) >/dev/null 2>&1 && echo "OK  イメージ $(IMAGE)" || { echo "NG  イメージなし: make build"; exit 1; }
	@test -x "$(SCRIPT)" && echo "OK  $(SCRIPT)" || { echo "NG  実行権限なし: chmod +x $(SCRIPT)"; exit 1; }

smoke: ## MCPのinitializeを1回送って応答を確認（登録前の動作確認）
	@echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
	  | RSA_IMAGE=$(IMAGE) "$(SCRIPT)" | head -c 600; echo
