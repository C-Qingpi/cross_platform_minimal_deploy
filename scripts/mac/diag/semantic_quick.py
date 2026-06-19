#!/usr/bin/env python3
from __future__ import annotations
import os, sys
import paramiko

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")

REMOTE = r"""#!/bin/bash
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
D="$HOME/Desktop/ArionAgentDev/cross_platform_minimal_deploy"
P="$HOME/Desktop/ArionAgentProd/cross_platform_minimal_deploy"

echo "=== dev .env ==="
grep -E '^(DEPLOY_ROOT|ARION)' "$D/.env" 2>/dev/null || true
echo "=== prod .env ==="
grep -E '^(DEPLOY_ROOT|ARION)' "$P/.env" 2>/dev/null || true

echo "=== running dev agent env ==="
for pid in $(pgrep -f agent_runner.py 2>/dev/null || true); do
  cmd=$(ps -p "$pid" -o command= 2>/dev/null || true)
  [[ "$cmd" == *ArionAgentDev* ]] || continue
  ps eww -p "$pid" | tr ' ' '\n' | grep -E '^(ARION_DEPLOY_MODE|DEPLOY_ROOT|BACKEND_PORT)=' || true
done

echo "=== running prod agent env ==="
for pid in $(pgrep -f agent_runner.py 2>/dev/null || true); do
  cmd=$(ps -p "$pid" -o command= 2>/dev/null || true)
  [[ "$cmd" == *ArionAgentProd* ]] || continue
  ps eww -p "$pid" | tr ' ' '\n' | grep -E '^(ARION_DEPLOY_MODE|DEPLOY_ROOT|BACKEND_PORT)=' || true
done

echo "=== code: optional middleware present? ==="
echo -n "dev agent_runner: "; grep -c _optional_middleware "$D/agent/agent_runner.py" 2>/dev/null || echo 0
echo -n "prod agent_runner: "; grep -c _optional_middleware "$P/agent/agent_runner.py" 2>/dev/null || echo 0

echo "=== search_test events dev log ==="
grep search_test "$D/.run/logs/agent.log" 2>/dev/null | tail -10 || echo none
echo "=== search_test events prod log ==="
grep search_test "$P/.run/logs/agent.log" 2>/dev/null | tail -10 || echo none

echo "=== semantic_search mentions dev log ==="
grep semantic_search "$D/.run/logs/agent.log" 2>/dev/null | tail -10 || echo none
echo "=== semantic_search mentions prod log ==="
grep semantic_search "$P/.run/logs/agent.log" 2>/dev/null | tail -10 || echo none

echo "=== dev middleware probe (no full agent) ==="
ARION_DEPLOY_MODE=dev "$D/.venv/bin/python" -c "
import sys; sys.path.insert(0, '$D/agent')
import agent_runner as ar
from pathlib import Path
ws = Path('$P/workspaces/test')
mw = ar._optional_middleware(ws)
print('middleware', len(mw), mw[0].tools[0].name if mw else None)
" 2>&1
"""

def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    _, stdout, stderr = c.exec_command(REMOTE, timeout=90)
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err.strip():
        print("STDERR:", err, file=sys.stderr)
    c.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
