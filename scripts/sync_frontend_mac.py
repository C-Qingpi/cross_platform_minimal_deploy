#!/usr/bin/env python3
"""Sync frontend/ to Mac (no node_modules)."""

from __future__ import annotations

import os
import sys
import tarfile
import tempfile
from pathlib import Path

import paramiko

REPO = Path(__file__).resolve().parents[1] / "frontend"
HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")
MAC_FRONT = os.environ.get(
    "MAC_FRONT",
    "Desktop/AgentLearning/cross_platform_minimal_deploy/frontend",
)
SKIP = {"node_modules", "dist", ".vite"}


def main() -> int:
    tmp = Path(tempfile.gettempdir()) / "frontend-sync.tgz"
    with tarfile.open(tmp, "w:gz") as tar:
        for path in REPO.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(REPO)
            if SKIP & set(rel.parts):
                continue
            tar.add(path, arcname=rel.as_posix())
    print(f"built {tmp} ({tmp.stat().st_size} bytes)")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"connecting to {USER}@{HOST} ...")
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    sftp = client.open_sftp()
    remote_tar = f"/Users/{USER}/Desktop/frontend-sync.tgz"
    sftp.put(str(tmp), remote_tar)
    sftp.close()
    print("upload done")

    script = f"""set -e
FRONT="$HOME/{MAC_FRONT}"
mkdir -p "$FRONT"
tar -xzf "$HOME/Desktop/frontend-sync.tgz" -C "$FRONT"
rm -f "$HOME/Desktop/frontend-sync.tgz"
grep -q "Jump to latest" "$FRONT/src/components/PaginatedConversationLog.tsx" && echo jump-button: OK
grep -q "overflow-wrap" "$FRONT/src/index.css" && echo overflow-fix: OK
echo FRONTEND SYNC DONE
"""
    _, stdout, stderr = client.exec_command(script, timeout=120)
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
