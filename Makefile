SHELL := /bin/bash
LOG_DIR := /tmp/teamdesk-logs

.PHONY: up down dev sample kill

up: ## docker 一键启动（backend:8320 + frontend:8321）
	@test -f .env || cp .env.example .env
	docker compose up --build -d
	@echo "backend  http://localhost:8320  |  frontend  http://localhost:8321"

down: ## 停止并移除 docker 容器
	docker compose down

dev: ## 本地双进程开发（无需 docker；backend uv + frontend vite :8321）
	-$(MAKE) kill
	@mkdir -p $(LOG_DIR)
	@echo "[dev] starting backend :8320 ..."
	@(cd backend && nohup uv run uvicorn app.main:app --port 8320 >> $(LOG_DIR)/backend.log 2>&1 & echo $$! > $(LOG_DIR)/backend.pid)
	@if [ -f frontend/package.json ]; then \
		echo "[dev] starting frontend :8321 ..."; \
		@(cd frontend && nohup npm run dev -- --port 8321 --strictPort >> $(LOG_DIR)/frontend.log 2>&1 & echo $$! > $(LOG_DIR)/frontend.pid); \
	else \
		echo "[dev] frontend/ 尚未就绪，先只起 backend"; \
	fi
	@sleep 4
	@curl -sf http://localhost:8320/api/health >/dev/null && echo "[dev] backend healthy" || { echo "[dev] backend 启动失败，见 $(LOG_DIR)/backend.log"; exit 1; }

sample: ## 生成演示样例数据（确定性 seed，幂等）
	cd backend && uv run python ../data/make_samples.py

kill: ## 停掉本地 dev 进程
	@[ -f $(LOG_DIR)/backend.pid ] && kill $(cat $(LOG_DIR)/backend.pid) 2>/dev/null; true
	@[ -f $(LOG_DIR)/frontend.pid ] && kill $(cat $(LOG_DIR)/frontend.pid) 2>/dev/null; true
	-pkill -f "uvicorn app.main:app" 2>/dev/null; true
	@echo "[kill] done"
