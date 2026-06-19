#!/usr/bin/env python3
"""Diagnose and repair openai/langchain_openai on Mac Prod."""
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
P="$HOME/Desktop/ArionAgentProd"
DEP="$P/cross_platform_minimal_deploy"
VPY="$DEP/.venv/bin/python"
ARION="$P/arion_agent"

echo "before:"
"$VPY" -c "import openai; print('openai', openai.__version__, openai.__file__); print('DefaultHttpxClient', hasattr(openai,'DefaultHttpxClient'))" || true

"$UV" pip install --reinstall "openai>=2.26.0,<3" "langchain-openai>=1.1.10,<2" --python "$VPY"
cd "$ARION"
"$UV" pip install --reinstall -e ".[deepseek,search]" --python "$VPY"

echo "after:"
"$VPY" -c "import openai; print('openai', openai.__version__); print('DefaultHttpxClient', hasattr(openai,'DefaultHttpxClient'))"
"$VPY" -c "from arion_agent.environments.search import is_search_available; print('search_available', is_search_available())"
echo DONE
"""


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    _, stdout, stderr = client.exec_command(REMOTE, timeout=600)
    out = stdout.read().decode()
    err = stderr.read().decode()
    client.close()
    sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    return 0 if "search_available True" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
