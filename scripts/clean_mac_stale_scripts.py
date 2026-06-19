#!/usr/bin/env python3
"""Move stale start_dev/start_prod scripts off Mac deploy dirs; keep agents.json etc."""

from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")

REMOTE = r"""#!/bin/bash
set -uo pipefail
shopt -s nullglob 2>/dev/null || setopt NULL_GLOB 2>/dev/null || true

STALE_GLOBS=(
  start_dev.sh start_dev.ps1 start_dev.bat start_dev.command
  stop_dev.sh stop_dev.ps1 stop_dev.bat stop_dev.command
  start_prod.sh start_prod.ps1 start_prod.bat start_prod.command
  stop_prod.sh stop_prod.ps1 stop_prod.bat stop_prod.command
)

TRASH="$HOME/Desktop/to_be_deleted/arion_stale_scripts_20260619"
mkdir -p "$TRASH"

move_stale() {
  local src="$1"
  local bucket="$2"
  [[ -e "$src" ]] || return 0
  local dest="$TRASH/$bucket/$(basename "$src")"
  mkdir -p "$TRASH/$bucket"
  mv "$src" "$dest"
  echo "  moved $(basename "$src") -> to_be_deleted/$bucket/"
}

clean_deploy() {
  local label="$1"
  local rel="$2"
  local d="$HOME/$rel/cross_platform_minimal_deploy"
  echo "===== ${label} ====="
  if [[ ! -d "$d" ]]; then
    echo "  missing $d"
    return 0
  fi

  local bucket
  bucket="$(basename "$rel")"
  local n=0

  for name in "${STALE_GLOBS[@]}"; do
    if [[ -e "$d/$name" ]]; then
      move_stale "$d/$name" "$bucket"
      n=$((n + 1))
    fi
  done

  if [[ -d "$d/to_be_deleted" ]]; then
    for name in "${STALE_GLOBS[@]}"; do
      if [[ -e "$d/to_be_deleted/$name" ]]; then
        move_stale "$d/to_be_deleted/$name" "$bucket/from_repo_to_be_deleted"
        n=$((n + 1))
      fi
    done
    rmdir "$d/to_be_deleted" 2>/dev/null && echo "  removed empty to_be_deleted/" || true
  fi

  find "$HOME/$rel" -maxdepth 1 -type d -name '.runtime_backup_*' -exec rm -rf {} + 2>/dev/null || true

  echo "  kept: start.sh stop.sh start.command stop.command deploy.config .env agents.json workspaces/ .arion/ .venv/"
  ls "$d"/start.sh "$d"/stop.sh "$d"/start.command "$d"/stop.command 2>/dev/null | sed 's|^|    |' || echo "    (only unified start.sh / stop.sh remain)"
  echo "  moved $n stale script(s)"
  echo
}

clean_deploy Prod Desktop/ArionAgentProd
clean_deploy Dev Desktop/ArionAgentDev

LEG="$HOME/Desktop/AgentLearning/cross_platform_minimal_deploy"
if [[ -d "$LEG" ]]; then
  echo "===== legacy AgentLearning ====="
  bucket="AgentLearning"
  n=0
  for name in "${STALE_GLOBS[@]}"; do
    if [[ -e "$LEG/$name" ]]; then
      move_stale "$LEG/$name" "$bucket"
      n=$((n + 1))
    fi
  done
  echo "  moved $n stale script(s); runtime data untouched at $LEG"
  echo
fi

JOBS="$HOME/Desktop/.arion/jobs"
if [[ -d "$JOBS" ]]; then
  echo "===== stale Desktop/.arion/jobs (old Start_dev/Start_prod helpers) ====="
  jn=0
  for f in "$JOBS"/Start_dev* "$JOBS"/Stop_dev* "$JOBS"/Start_prod* "$JOBS"/Stop_prod* "$JOBS"/Start_production*; do
    [[ -e "$f" ]] || continue
    mkdir -p "$TRASH/desktop_arion_jobs"
    mv "$f" "$TRASH/desktop_arion_jobs/"
    jn=$((jn + 1))
  done
  echo "  moved $jn job artifact(s) to to_be_deleted/desktop_arion_jobs/"
fi

echo "TRASH=$TRASH"
echo "DONE"
"""


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"connecting to {USER}@{HOST} ...")
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    _, stdout, stderr = client.exec_command(REMOTE, timeout=120)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out)
    if err.strip():
        print("STDERR:", err, file=sys.stderr)
    client.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
