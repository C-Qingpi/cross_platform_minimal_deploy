#!/bin/bash
# Stop only this deploy's backend, agent runner, and frontend (by saved PIDs).
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=deploy_env.sh
source "$ROOT/deploy_env.sh"
deploy_env_load "$ROOT"

RUN_DIR="$ROOT/.run"

stop_pid() {
  local name="$1"
  local pidfile="$2"
  [[ -f "$pidfile" ]] || return 0
  local pid
  pid="$(tr -d '[:space:]' < "$pidfile")"
  [[ "$pid" =~ ^[0-9]+$ ]] || { rm -f "$pidfile"; return 0; }
  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping $name (pid $pid) ..."
    kill "$pid" 2>/dev/null || true
    local i=0
    while kill -0 "$pid" 2>/dev/null && [[ $i -lt 20 ]]; do
      sleep 0.25
      i=$((i + 1))
    done
    if kill -0 "$pid" 2>/dev/null; then
      echo "  $name still running - sending SIGKILL"
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "  stopped $name"
  else
    echo "$name not running (stale pid $pid)"
  fi
  rm -f "$pidfile"
}

stop_cmd_if_ours() {
  local label="$1"
  local needle="$2"
  local pid cmd
  for pid in $(pgrep -f "$needle" 2>/dev/null || true); do
    [[ -n "$pid" ]] || continue
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    [[ "$cmd" == *"$ROOT"* ]] || continue
    [[ "$cmd" == *"$needle"* ]] || continue
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping $label (pid $pid) ..."
      kill "$pid" 2>/dev/null || true
      local i=0
      while kill -0 "$pid" 2>/dev/null && [[ $i -lt 20 ]]; do
        sleep 0.25
        i=$((i + 1))
      done
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
      echo "  stopped $label"
    fi
  done
}

stop_port_if_ours() {
  local port="$1"
  local label="$2"
  local pids pid cwd cmd
  pids="$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  [[ -n "$pids" ]] || return 0
  for pid in $pids; do
    [[ -n "$pid" ]] || continue
    cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1 || true)"
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$cwd" == "$ROOT"* ]] || [[ "$cmd" == *"$ROOT"* ]]; then
      echo "Stopping $label on port $port (pid $pid) ..."
      kill "$pid" 2>/dev/null || true
    fi
  done
}

echo "Stopping ${DEPLOY_MODE} deploy (ports $BACKEND_PORT / $FRONTEND_PORT) ..."
mkdir -p "$RUN_DIR"
stop_pid "backend" "$RUN_DIR/backend.pid"
stop_pid "agent runner" "$RUN_DIR/agent.pid"
stop_pid "frontend" "$RUN_DIR/frontend.pid"

stop_cmd_if_ours "backend" "uvicorn main:app"
stop_cmd_if_ours "agent runner" "agent_runner.py"
stop_port_if_ours "$BACKEND_PORT" "backend"
stop_port_if_ours "$FRONTEND_PORT" "frontend"

echo "Done."

if [[ -t 0 ]] && [[ "${MINIMAL_DEPLOY_QUIET:-}" != 1 ]]; then
  echo ""
  read -r -p "Press Enter to close..." _ || true
fi
