#!/usr/bin/env python3
"""Pull latest git on Mac for Prod (main) and Dev (dev) sibling checkouts.

Prod: ~/Desktop/ArionAgentProd/{arion_agent,cross_platform_minimal_deploy}
Dev:  ~/Desktop/ArionAgentDev/{arion_agent,cross_platform_minimal_deploy}

Preserves runtime files (.env, agents.json, workspaces, .arion, .venv, etc.)
via scripts/mac/git_setup.sh backup/restore.

From Windows:
  python scripts/mac/pull_prod_dev.py
  python scripts/mac/pull_prod_dev.py --prod-only
  python scripts/mac/pull_prod_dev.py --dev-only
  python scripts/mac/pull_prod_dev.py --restart-prod
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import paramiko

DEPLOY = Path(__file__).resolve().parents[2]
SETUP_SCRIPT = DEPLOY / "scripts/mac/git_setup.sh"
MAC_SETUP_SCRIPT = DEPLOY / "scripts/mac/setup.sh"

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")

PROD_ROOT = os.environ.get("MAC_PROD_ROOT", "Desktop/ArionAgentProd")
DEV_ROOT = os.environ.get("MAC_DEV_ROOT", "Desktop/ArionAgentDev")


def _remote_git_pull(*, root: str, branch: str) -> str:
    home = f"/Users/{USER}"
    remote_setup = f"{home}/{root}/cross_platform_minimal_deploy/scripts/mac/git_setup.sh"
    return f"""
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
mkdir -p "{home}/{root}/cross_platform_minimal_deploy"
chmod +x "{remote_setup}"
AGENTLEARNING_ROOT="{home}/{root}" GIT_BRANCH="{branch}" SKIP_SSH=1 SKIP_DEPS=1 bash "{remote_setup}"
git -C "{home}/{root}/arion_agent" log -1 --oneline
git -C "{home}/{root}/cross_platform_minimal_deploy" log -1 --oneline
"""


def _remote_mac_setup(*, root: str) -> str:
    home = f"/Users/{USER}"
    remote_mac_setup = f"{home}/{root}/cross_platform_minimal_deploy/scripts/mac/setup.sh"
    return f"""
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
chmod +x "{remote_mac_setup}"
bash "{remote_mac_setup}"
"""


RESTART_PROD = f"""
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
ROOT="/Users/{USER}/{PROD_ROOT}/cross_platform_minimal_deploy"
PYTHON="$ROOT/.venv/bin/python"
LOG_DIR="$ROOT/.run/logs"
cd "$ROOT"
mkdir -p .run "$LOG_DIR"
source "$ROOT/deploy_env.sh"
deploy_env_load "$ROOT"

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
      kill "$APID" 2>/dev/null || true
    fi
  fi
  rm -f .run/agent.pid
fi

for pid in $(pgrep -f agent_runner.py 2>/dev/null || true); do
  cmd=$(ps -p "$pid" -o command= 2>/dev/null || true)
  [[ "$cmd" == *"$ROOT"* ]] || continue
  kill "$pid" 2>/dev/null || true
done

stop_port "$BACKEND_PORT"
stop_port "$FRONTEND_PORT"

nohup caffeinate -dims "$PYTHON" agent/agent_runner.py >>"$LOG_DIR/agent.stdout.log" 2>&1 &
echo $! > "$ROOT/.run/agent.pid"
sleep 2
nohup caffeinate -dims "$PYTHON" -m uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" --app-dir "$ROOT/backend" >>"$LOG_DIR/backend.stdout.log" 2>&1 &
echo $! > "$ROOT/.run/backend.pid"
sleep 2
cd "$ROOT/frontend"
nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" >>"$LOG_DIR/frontend.stdout.log" 2>&1 &
echo $! > "$ROOT/.run/frontend.pid"
echo "PROD RESTART DONE (mode=$DEPLOY_MODE ports=$BACKEND_PORT/$FRONTEND_PORT)"
"""


def _upload_setup(sftp: paramiko.SFTPClient, root: str) -> None:
    remote_dir = f"/Users/{USER}/{root}/cross_platform_minimal_deploy"
    remote_git_setup = f"{remote_dir}/scripts/mac/git_setup.sh"
    remote_mac_setup = f"{remote_dir}/scripts/mac/setup.sh"
    try:
        sftp.stat(remote_dir)
    except OSError:
        sftp.mkdir(f"/Users/{USER}/{root}")
        sftp.mkdir(remote_dir)
    for sub in ("scripts", "scripts/mac"):
        try:
            sftp.stat(f"{remote_dir}/{sub}")
        except OSError:
            sftp.mkdir(f"{remote_dir}/{sub}")
    print(f"upload git_setup.sh -> {remote_git_setup}")
    sftp.put(str(SETUP_SCRIPT), remote_git_setup)
    if MAC_SETUP_SCRIPT.is_file():
        print(f"upload setup.sh -> {remote_mac_setup}")
        sftp.put(str(MAC_SETUP_SCRIPT), remote_mac_setup)


def _run(client: paramiko.SSHClient, script: str, *, timeout: int = 1800) -> tuple[int, str, str]:
    _, stdout, stderr = client.exec_command(f"bash -s <<'REMOTE_EOF'\n{script}\nREMOTE_EOF", timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    return code, out, err


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull main→Prod and dev→Dev on Mac")
    parser.add_argument("--prod-only", action="store_true")
    parser.add_argument("--dev-only", action="store_true")
    parser.add_argument("--skip-deps", action="store_true", help="skip mac_setup.sh (faster)")
    parser.add_argument("--restart-prod", action="store_true", help="restart Prod services after pull")
    args = parser.parse_args()

    if not SETUP_SCRIPT.is_file():
        print(f"missing {SETUP_SCRIPT}", file=sys.stderr)
        return 1

    do_prod = not args.dev_only
    do_dev = not args.prod_only

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"connecting to {USER}@{HOST} ...")
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    sftp = client.open_sftp()
    if do_prod:
        _upload_setup(sftp, PROD_ROOT)
    if do_dev:
        _upload_setup(sftp, DEV_ROOT)
    sftp.close()

    def _pull_env(root: str, branch: str, label: str) -> int:
        print(f"\n--- {label}: {root} @ {branch} ---")
        sftp2 = client.open_sftp()
        _upload_setup(sftp2, root)
        sftp2.close()

        code, out, err = _run(client, _remote_git_pull(root=root, branch=branch))
        if out.strip():
            print(out)
        if err.strip():
            print("STDERR:", err, file=sys.stderr)
        if code != 0:
            print(f"{label.lower()} git exit {code}")
            return code

        if not args.skip_deps:
            sftp3 = client.open_sftp()
            _upload_setup(sftp3, root)
            sftp3.close()
            code, out, err = _run(client, _remote_mac_setup(root=root), timeout=1800)
            if out.strip():
                print(out)
            if err.strip():
                print("STDERR:", err, file=sys.stderr)
            if code != 0:
                print(f"{label.lower()} deps exit {code}")
                return code

        print(f"=== {label} OK ===")
        return 0

    exit_code = 0
    if do_prod:
        code = _pull_env(PROD_ROOT, "main", "Prod")
        if code != 0:
            exit_code = code
    if do_dev:
        code = _pull_env(DEV_ROOT, "dev", "Dev")
        if code != 0:
            exit_code = code

    if args.restart_prod and do_prod and exit_code == 0:
        print(f"\n--- Restart Prod services ---")
        code, out, err = _run(client, RESTART_PROD, timeout=120)
        if out.strip():
            print(out)
        if err.strip():
            print("STDERR:", err, file=sys.stderr)
        print(f"restart exit {code}")
        if code != 0:
            exit_code = code

    client.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
