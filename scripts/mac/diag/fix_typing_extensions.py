#!/usr/bin/env python3
"""Install missing typing-extensions in Mac Prod/Dev venvs and verify langchain_core."""
from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")

REMOTE = r"""
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
UV="$HOME/.local/bin/uv"

fix_root() {
  local label="$1" root="$2"
  local dep="$root/cross_platform_minimal_deploy"
  local vpy="$dep/.venv/bin/python"
  echo "========== $label =========="
  if [[ ! -x "$vpy" ]]; then
    echo "skip: no venv at $dep"
    return 0
  fi
  "$UV" pip install --reinstall "typing-extensions>=4.5.0" "langchain-core>=1.2.13" --python "$vpy"
  "$vpy" -m pip show typing-extensions langchain-core | sed -n '1,12p'
  "$vpy" -c "import typing_extensions; from langchain_core._api.deprecation import deprecated; print('typing_extensions ok')"
  "$vpy" -c "from arion_agent.environments.search import is_search_available; print('search_available', is_search_available())"
}

fix_root PROD "$HOME/Desktop/ArionAgentProd"
fix_root DEV "$HOME/Desktop/ArionAgentDev"
echo DONE
"""


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    _, stdout, stderr = client.exec_command(REMOTE, timeout=180)
    out = stdout.read().decode()
    err = stderr.read().decode()
    client.close()
    sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    return 0 if "DONE" in out and "search_available True" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
