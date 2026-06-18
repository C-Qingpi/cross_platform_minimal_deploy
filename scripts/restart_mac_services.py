#!/usr/bin/env python3
"""Restart Mac deploy agent runner and backend (port-specific, deploy dir only)."""

from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")
MAC_ROOT = os.environ.get("MAC_ROOT", "Desktop/AgentLearning")

REMOTE = f"""#!/bin/bash
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
ROOT="$HOME/{MAC_ROOT}/cross_platform_minimal_deploy"
PYTHON="$ROOT/.venv/bin/python"
LOG_DIR="$ROOT/.run/logs"
cd "$ROOT"
mkdir -p .run "$LOG_DIR"

stop_port() {{
  PORT="$1"
  PIDS=$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)
  for pid in $PIDS; do
    cmd=$(ps -p "$pid" -o command= 2>/dev/null || true)
    [[ "$cmd" == *"$ROOT"* ]] || continue
    echo "Stopping port $PORT pid=$pid"
    kill "$pid" 2>/dev/null || true
    for i in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
    kill -9 "$pid" 2>/dev/null || true
  done
}}

if [[ -f .run/agent.pid ]]; then
  APID=$(tr -d '[:space:]' < .run/agent.pid)
  if [[ "$APID" =~ ^[0-9]+$ ]] && kill -0 "$APID" 2>/dev/null; then
    cmd=$(ps -p "$APID" -o command= 2>/dev/null || true)
    if [[ "$cmd" == *"$ROOT"* ]]; then
      echo "Stopping agent runner pid=$APID"
      kill "$APID" 2>/dev/null || true
      for i in $(seq 1 20); do kill -0 "$APID" 2>/dev/null || break; sleep 0.25; done
      kill -9 "$APID" 2>/dev/null || true
    fi
  fi
  rm -f .run/agent.pid
fi

for pid in $(pgrep -f agent_runner.py 2>/dev/null || true); do
  cmd=$(ps -p "$pid" -o command= 2>/dev/null || true)
  [[ "$cmd" == *"$ROOT"* ]] || continue
  echo "Stopping stray agent runner pid=$pid"
  kill "$pid" 2>/dev/null || true
  for i in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
  kill -9 "$pid" 2>/dev/null || true
done

stop_port 8920
stop_port 5174

nohup caffeinate -dims "$PYTHON" agent/agent_runner.py >>"$LOG_DIR/agent.stdout.log" 2>&1 &
echo $! > "$ROOT/.run/agent.pid"
sleep 2
APID=$(tr -d '[:space:]' < "$ROOT/.run/agent.pid")
if kill -0 "$APID" 2>/dev/null; then
  echo "Agent runner pid=$APID"
else
  echo "Agent runner FAILED"
  tail -15 "$LOG_DIR/agent.log" 2>/dev/null || tail -15 "$LOG_DIR/agent.stdout.log"
  exit 1
fi

nohup caffeinate -dims "$PYTHON" -m uvicorn main:app --host 0.0.0.0 --port 8920 --app-dir "$ROOT/backend" >>"$LOG_DIR/backend.stdout.log" 2>&1 &
echo $! > "$ROOT/.run/backend.pid"
sleep 2
BPID=$(tr -d '[:space:]' < "$ROOT/.run/backend.pid")
if kill -0 "$BPID" 2>/dev/null; then
  echo "Backend pid=$BPID"
else
  echo "Backend FAILED"
  tail -15 "$LOG_DIR/backend.log" 2>/dev/null || tail -15 "$LOG_DIR/backend.stdout.log"
  exit 1
fi

cd "$ROOT/frontend"
nohup npm run dev -- --host 0.0.0.0 --port 5174 >>"$LOG_DIR/frontend.stdout.log" 2>&1 &
echo $! > "$ROOT/.run/frontend.pid"
cd "$ROOT"
sleep 3
FPID=$(tr -d '[:space:]' < "$ROOT/.run/frontend.pid")
if kill -0 "$FPID" 2>/dev/null; then
  echo "Frontend pid=$FPID"
else
  echo "Frontend FAILED"
  tail -15 "$LOG_DIR/frontend.stdout.log"
  exit 1
fi

echo RESTART DONE
"""


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"connecting to {USER}@{HOST} ...")
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    stdin, stdout, stderr = client.exec_command("bash -s", timeout=120)
    stdin.write(REMOTE)
    stdin.channel.shutdown_write()
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out)
    if err.strip():
        print(err, file=sys.stderr)
    client.close()
    print(f"exit {code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
