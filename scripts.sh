#!/usr/bin/env bash
# TeamDesk 启动脚本（零依赖，make 的等价物；两者可互换）
# 用法: ./scripts.sh {up|down|dev|sample|kill}
set -euo pipefail
cd "$(dirname "$0")"

LOG_DIR="${LOG_DIR:-/tmp/teamdesk-logs}"

case "${1:-help}" in
  up)
    [ -f .env ] || cp .env.example .env
    docker compose up --build -d
    echo "backend  http://localhost:8320  |  frontend  http://localhost:8321"
    ;;
  down)
    docker compose down
    ;;
  sample)
    (cd backend && uv run python ../data/make_samples.py)
    ;;
  dev)
    ./scripts.sh kill || true
    mkdir -p "$LOG_DIR"
    echo "[dev] starting backend :8320 ..."
    (cd backend && nohup uv run uvicorn app.main:app --port 8320 >> "$LOG_DIR/backend.log" 2>&1 & echo $! > "$LOG_DIR/backend.pid")
    if [ -f frontend/package.json ]; then
      echo "[dev] starting frontend :8321 ..."
      (cd frontend && nohup npm run dev -- --port 8321 --strictPort >> "$LOG_DIR/frontend.log" 2>&1 & echo $! > "$LOG_DIR/frontend.pid")
    else
      echo "[dev] frontend/ 尚未就绪，先只起 backend"
    fi
    sleep 4
    if curl -sf http://localhost:8320/api/health > /dev/null; then
      echo "[dev] backend healthy"
    else
      echo "[dev] backend 启动失败，见 $LOG_DIR/backend.log" >&2
      exit 1
    fi
    ;;
  kill)
    [ -f "$LOG_DIR/backend.pid" ] && kill "$(cat "$LOG_DIR/backend.pid")" 2>/dev/null || true
    [ -f "$LOG_DIR/frontend.pid" ] && kill "$(cat "$LOG_DIR/frontend.pid")" 2>/dev/null || true
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    echo "[kill] done"
    ;;
  help|*)
    grep -E '^  (up|down|dev|sample|kill)\)' "$0" | sed 's/^  //'
    echo "用法: ./scripts.sh {up|down|dev|sample|kill}   （等效: make {up,down,dev,sample,kill}）"
    ;;
esac
