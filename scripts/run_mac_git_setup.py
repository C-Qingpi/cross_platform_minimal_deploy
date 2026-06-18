#!/usr/bin/env python3
"""Upload mac_git_setup.sh to Mac and run it (password SSH from env)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

DEPLOY = Path(__file__).resolve().parents[1]
SCRIPT = DEPLOY / "mac_git_setup.sh"

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")
MAC_ROOT = os.environ.get("MAC_ROOT", "Desktop/AgentLearning")
SKIP_SSH = os.environ.get("SKIP_SSH", "0")
SKIP_DEPS = os.environ.get("SKIP_DEPS", "0")


def main() -> int:
    if not SCRIPT.is_file():
        print(f"missing {SCRIPT}", file=sys.stderr)
        return 1

    remote_deploy = f"/Users/{USER}/{MAC_ROOT}/cross_platform_minimal_deploy"
    remote_script = f"{remote_deploy}/mac_git_setup.sh"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"connecting to {USER}@{HOST} ...")
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    sftp = client.open_sftp()
    try:
        sftp.stat(remote_deploy)
    except OSError:
        client.exec_command(f"mkdir -p {remote_deploy}")[1].read()

    print(f"uploading {SCRIPT.name} -> {remote_script}")
    sftp.put(str(SCRIPT), remote_script)
    sftp.close()

    cmd = (
        f"chmod +x {remote_script} && "
        f"AGENTLEARNING_ROOT=$HOME/{MAC_ROOT} SKIP_SSH={SKIP_SSH} SKIP_DEPS={SKIP_DEPS} "
        f"bash {remote_script}"
    )
    _, stdout, stderr = client.exec_command(cmd, timeout=1800)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out)
    if err.strip():
        print("STDERR:", err, file=sys.stderr)
    client.close()
    print(f"exit {code}")
    if code == 2:
        print(
            "\nGitHub SSH key was generated but not registered yet.\n"
            "Add the public key shown above at https://github.com/settings/keys\n"
            "Then re-run: python scripts/run_mac_git_setup.py"
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
