#!/usr/bin/env python3
"""Run Mac setup.sh on Prod (and optionally Dev) to repair venv deps."""
from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")
TARGET = os.environ.get("MAC_SETUP_TARGET", "prod")  # prod | dev | both

REMOTE = rf"""
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export UV_INDEX_URL="${{UV_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}}"

run_setup() {{
  local label="$1" dep="$2"
  echo "========== setup $label =========="
  bash "$dep/scripts/mac/setup.sh"
  local vpy="$dep/.venv/bin/python"
  "$vpy" -c "import typing_extensions; from langchain_core._api.deprecation import deprecated; print('langchain ok')"
  "$vpy" -c "from arion_agent.environments.search import is_search_available; print('search_available', is_search_available())"
}}

case "{TARGET}" in
  prod) run_setup PROD "$HOME/Desktop/ArionAgentProd/cross_platform_minimal_deploy" ;;
  dev)  run_setup DEV  "$HOME/Desktop/ArionAgentDev/cross_platform_minimal_deploy" ;;
  both)
    run_setup PROD "$HOME/Desktop/ArionAgentProd/cross_platform_minimal_deploy"
    run_setup DEV  "$HOME/Desktop/ArionAgentDev/cross_platform_minimal_deploy"
    ;;
  *) echo "bad MAC_SETUP_TARGET"; exit 1 ;;
esac
echo DONE
"""


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    _, stdout, stderr = client.exec_command(REMOTE, timeout=900)
    out = stdout.read().decode()
    err = stderr.read().decode()
    client.close()
    sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    return 0 if "DONE" in out and "search_available True" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
