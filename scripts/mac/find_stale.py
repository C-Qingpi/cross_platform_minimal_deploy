#!/usr/bin/env python3
"""Find all stale start/stop scripts on Mac deploy folders."""

from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")

REMOTE = r"""#!/bin/bash
set -uo pipefail
echo "=== find stale start/stop scripts under Desktop ==="
find "$HOME/Desktop" \( -path "*/node_modules/*" -o -path "*/.venv/*" -o -path "*/.git/*" \) -prune -o \
  \( -iname "start_dev*" -o -iname "stop_dev*" -o -iname "start_prod*" -o -iname "stop_prod*" \) -print 2>/dev/null | sort

echo
echo "=== all start/stop* at deploy roots ==="
for root in \
  "$HOME/Desktop/ArionAgentProd/cross_platform_minimal_deploy" \
  "$HOME/Desktop/ArionAgentDev/cross_platform_minimal_deploy" \
  "$HOME/Desktop/AgentLearning/cross_platform_minimal_deploy"; do
  [[ -d "$root" ]] || continue
  echo "-- $root --"
  ls -la "$root"/start* "$root"/stop* 2>/dev/null || true
done
"""


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    _, o, e = c.exec_command(REMOTE, timeout=60)
    print(o.read().decode())
    err = e.read().decode()
    if err.strip():
        print("STDERR:", err, file=sys.stderr)
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
