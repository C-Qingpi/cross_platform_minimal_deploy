#!/bin/bash
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
# shellcheck source=deploy_env.sh
source "$ROOT/deploy_env.sh"
deploy_env_load "$ROOT"

RUN_DIR="$ROOT/.run"
mkdir -p "$RUN_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env - set DEEPSEEK_API_KEY"
fi

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$PATH"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON=python3.12
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  PYTHON=python
fi

echo "Starting ${DEPLOY_MODE} deploy (root=$DEPLOY_ROOT) backend :$BACKEND_PORT ..."
(cd backend && exec "$PYTHON" -m uvicorn main:app --host 127.0.0.1 --port "$BACKEND_PORT") &
echo $! > "$RUN_DIR/backend.pid"

sleep 2
echo "Starting agent runner (mode=$DEPLOY_MODE) ..."
(cd agent && exec "$PYTHON" agent_runner.py) &
echo $! > "$RUN_DIR/agent.pid"

sleep 1
echo "Starting frontend http://localhost:$FRONTEND_PORT ..."
(
  cd frontend
  if [[ ! -d node_modules ]]; then npm install; fi
  npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT"
) &
echo $! > "$RUN_DIR/frontend.pid"

echo "PIDs saved under .run/ - logs under .run/logs/"
echo "Open http://localhost:$FRONTEND_PORT"
trap '/bin/bash "$ROOT/stop.sh"' EXIT INT TERM
wait
