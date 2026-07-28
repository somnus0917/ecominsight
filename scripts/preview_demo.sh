#!/usr/bin/env bash
# Build the public synthetic demo and run the local API and frontend together.
set -Eeuo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

api_pid=""
web_pid=""

cleanup() {
  if [[ -n "$web_pid" ]] && kill -0 "$web_pid" 2>/dev/null; then
    kill "$web_pid" 2>/dev/null || true
  fi
  if [[ -n "$api_pid" ]] && kill -0 "$api_pid" 2>/dev/null; then
    kill "$api_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

command -v uv >/dev/null || {
  echo "未找到 uv，请先安装：https://docs.astral.sh/uv/" >&2
  exit 1
}
command -v npm >/dev/null || {
  echo "未找到 npm，请先安装 Node.js 22 或更高版本。" >&2
  exit 1
}

uv sync --all-groups
npm --prefix frontend ci
uv run ecom-demo

export ECOM_API_DATABASE_PATH="data/demo/processed/ecom_insight_demo.duckdb"
export ECOM_API_FEEDBACK_DATABASE_PATH="data/demo/processed/feedback_demo.sqlite"
export ECOM_API_DATA_MODE="demo"

uv run ecom-api &
api_pid="$!"

for _attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null; then
    break
  fi
  sleep 1
done

if ! curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null; then
  echo "后端未能在 30 秒内启动，请检查上方日志。" >&2
  exit 1
fi

echo "演示数据已生成。前端：http://127.0.0.1:5173"
echo "接口文档：http://127.0.0.1:8000/docs"
echo "按 Ctrl+C 同时关闭前端和后端。"

npm --prefix frontend run dev -- --host 127.0.0.1 &
web_pid="$!"
wait "$web_pid"
