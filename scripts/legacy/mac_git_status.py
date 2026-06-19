#!/usr/bin/env python3
import os, paramiko
HOST=os.environ.get("MAC_HOST","10.100.33.146")
USER=os.environ.get("MAC_USER","yongbo_mac")
PASSWORD=os.environ.get("MAC_PASS","19991112")
REMOTE=r"""#!/bin/bash
set -uo pipefail
for root in ArionAgentProd ArionAgentDev; do
  D="$HOME/Desktop/$root/cross_platform_minimal_deploy"
  echo "=== $root ==="
  git -C "$D" checkout -- deploy_env.sh scripts/mac/git_setup.sh scripts/mac/setup.sh setup.command 2>/dev/null || true
  git -C "$D" status --short
  ls "$D"/start*.sh "$D"/stop*.sh 2>/dev/null | sed 's|^|  |'
done
"""
c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=30)
_,o,_=c.exec_command(REMOTE, timeout=60)
print(o.read().decode())
c.close()
