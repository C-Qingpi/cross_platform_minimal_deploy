#!/usr/bin/env python3
"""Repair Mac frontend after a bad runtime restore overwrote package.json."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

DEPLOY = Path(__file__).resolve().parents[2]
SCRIPT = DEPLOY / "scripts/mac/git_setup.sh"

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")
MAC_ROOT = os.environ.get("MAC_ROOT", "Desktop/AgentLearning")

REMOTE = f"""#!/bin/bash
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
ROOT="$HOME/{MAC_ROOT}"
DEPLOY="$ROOT/cross_platform_minimal_deploy"
cd "$DEPLOY"
git checkout -- frontend
cd frontend
npm install --silent
cd "$DEPLOY"
test -f frontend/package.json && echo "frontend/package.json: OK"
AGENTLEARNING_ROOT="$ROOT" SKIP_SSH=1 bash scripts/mac/git_setup.sh
"""


def main() -> int:
    remote_deploy = f"/Users/{USER}/{MAC_ROOT}/cross_platform_minimal_deploy"
    remote_script = f"{remote_deploy}/scripts/mac/git_setup.sh"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    sftp = client.open_sftp()
    sftp.put(str(SCRIPT), remote_script)
    sftp.close()

    _, stdout, stderr = client.exec_command(REMOTE, timeout=1800)
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
