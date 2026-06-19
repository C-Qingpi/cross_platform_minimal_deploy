#!/usr/bin/env python3
"""Restore Mac agents.json after a bad sync overwrote it with Windows paths."""

from __future__ import annotations

import json
import os
from datetime import datetime

import paramiko

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")
MAC_ROOT = os.environ.get("MAC_ROOT", "Desktop/AgentLearning")

AGENTS = {
    "agents": {
        "DESKTOP": {
            "workspace": f"/Users/{USER}/Desktop",
            "mounts": [],
            "model": "deepseek:deepseek_v4_flash",
            "created_at": "2026-06-17T01:45:53.487409",
        },
        "default": {
            "workspace": f"/Users/{USER}/{MAC_ROOT}/cross_platform_minimal_deploy/workspaces/default",
            "mounts": [],
            "model": "deepseek:deepseek_v4_flash",
            "created_at": "2026-06-17T01:40:32.090962",
        },
    }
}


def main() -> int:
    payload = json.dumps(AGENTS, indent=2, ensure_ascii=False)
    remote_path = f"/Users/{USER}/{MAC_ROOT}/cross_platform_minimal_deploy/agents.json"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    sftp = client.open_sftp()
    with sftp.open(remote_path, "w") as f:
        f.write(payload)
    sftp.close()

    _, stdout, _ = client.exec_command(f"cat {remote_path}")
    print(stdout.read().decode())
    client.close()
    print(f"restored {remote_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
