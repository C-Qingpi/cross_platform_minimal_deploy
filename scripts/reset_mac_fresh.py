#!/usr/bin/env python3
"""Fresh-reset Mac Prod (main) and Dev (dev) checkouts; preserve agent runtime data only.

Uses mac_git_setup.sh with FRESH_RESET=1:
  backup .env deploy.config agents.json workspaces .arion .venv node_modules
  git reset --hard + clean -fdx on arion_agent + cross_platform_minimal_deploy
  restore agent data, purge stale start_dev/start_prod scripts
  run mac_setup.sh

From Windows:
  python scripts/reset_mac_fresh.py
  python scripts/reset_mac_fresh.py --prod-only
  python scripts/reset_mac_fresh.py --dev-only
  python scripts/reset_mac_fresh.py --skip-deps
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import paramiko

DEPLOY = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = DEPLOY / "mac_git_setup.sh"
MAC_SETUP_SCRIPT = DEPLOY / "mac_setup.sh"

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")

PROD_ROOT = os.environ.get("MAC_PROD_ROOT", "Desktop/ArionAgentProd")
DEV_ROOT = os.environ.get("MAC_DEV_ROOT", "Desktop/ArionAgentDev")


def _remote_fresh(*, root: str, branch: str, skip_deps: bool) -> str:
    home = f"/Users/{USER}"
    remote_setup = f"{home}/{root}/cross_platform_minimal_deploy/mac_git_setup.sh"
    skip_deps_flag = "1" if skip_deps else "0"
    return f"""
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
mkdir -p "{home}/{root}/cross_platform_minimal_deploy"
chmod +x "{remote_setup}"
AGENTLEARNING_ROOT="{home}/{root}" GIT_BRANCH="{branch}" SKIP_SSH=1 SKIP_DEPS={skip_deps_flag} FRESH_RESET=1 bash "{remote_setup}"
echo "=== verify {root} ==="
D="{home}/{root}/cross_platform_minimal_deploy"
git -C "$D" status --short
git -C "$D" log -1 --oneline
ls "$D"/start.sh "$D"/stop.sh "$D"/start.command "$D"/stop.command 2>/dev/null
test -f "$D/agents.json" && echo "agents.json OK" || echo "agents.json missing"
test -f "$D/deploy.config" && grep '^mode=' "$D/deploy.config" || echo "deploy.config missing"
"""


def _upload_setup(sftp: paramiko.SFTPClient, root: str) -> None:
    remote_dir = f"/Users/{USER}/{root}/cross_platform_minimal_deploy"
    try:
        sftp.stat(remote_dir)
    except OSError:
        sftp.mkdir(f"/Users/{USER}/{root}")
        sftp.mkdir(remote_dir)
    sftp.put(str(SETUP_SCRIPT), f"{remote_dir}/mac_git_setup.sh")
    if MAC_SETUP_SCRIPT.is_file():
        sftp.put(str(MAC_SETUP_SCRIPT), f"{remote_dir}/mac_setup.sh")


def _run(client: paramiko.SSHClient, script: str, *, timeout: int = 1800) -> tuple[int, str, str]:
    _, stdout, stderr = client.exec_command(f"bash -s <<'REMOTE_EOF'\n{script}\nREMOTE_EOF", timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    return code, out, err


def main() -> int:
    parser = argparse.ArgumentParser(description="Fresh reset Mac Prod/Dev checkouts")
    parser.add_argument("--prod-only", action="store_true")
    parser.add_argument("--dev-only", action="store_true")
    parser.add_argument("--skip-deps", action="store_true", help="skip mac_setup.sh")
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

    exit_code = 0

    def _fresh(label: str, root: str, branch: str) -> None:
        nonlocal exit_code
        print(f"\n--- {label}: {root} @ {branch} (FRESH_RESET) ---")
        sftp = client.open_sftp()
        _upload_setup(sftp, root)
        sftp.close()
        code, out, err = _run(
            client,
            _remote_fresh(root=root, branch=branch, skip_deps=args.skip_deps),
            timeout=1800,
        )
        if out.strip():
            print(out)
        if err.strip():
            print("STDERR:", err, file=sys.stderr)
        if code != 0:
            print(f"{label} exit {code}")
            exit_code = code
        else:
            print(f"=== {label} OK ===")

    if do_prod:
        _fresh("Prod", PROD_ROOT, "main")
    if do_dev:
        _fresh("Dev", DEV_ROOT, "dev")

    client.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
