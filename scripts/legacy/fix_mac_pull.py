#!/usr/bin/env python3
"""Fix Mac git conflicts after pull and run mac_setup."""

from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")

REMOTE = r"""#!/bin/bash
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

fix_one() {
  local label="$1"
  local root="$2"
  local branch="$3"
  local d="$HOME/$root/cross_platform_minimal_deploy"
  local a="$HOME/$root/arion_agent"
  echo "===== ${label} ====="
  git -C "$a" pull --ff-only origin "$branch"
  git -C "$d" checkout -- scripts/mac/git_setup.sh scripts/mac/setup.sh setup.command start_dev.sh 2>/dev/null || true
  git -C "$d" pull --ff-only origin "$branch"
  git -C "$a" log -1 --oneline
  git -C "$d" log -1 --oneline
  if [[ ! -f "$d/deploy.config" ]]; then
    cp "$d/deploy.config.example" "$d/deploy.config"
    if [[ "$root" == *ArionAgentProd* ]]; then
      sed -i '' 's/^mode=dev/mode=prod/' "$d/deploy.config"
    fi
    echo "created deploy.config: $(grep '^mode=' "$d/deploy.config")"
  fi
  bash "$d/scripts/mac/setup.sh"
}

fix_one Prod Desktop/ArionAgentProd main
fix_one Dev Desktop/ArionAgentDev dev
echo ALL DONE
"""


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"connecting to {USER}@{HOST} ...")
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    _, stdout, stderr = client.exec_command(REMOTE, timeout=1800)
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
