#!/usr/bin/env python3
from __future__ import annotations
import os, paramiko
HOST=os.environ.get("MAC_HOST","10.100.33.146")
USER=os.environ.get("MAC_USER","yongbo_mac")
PASSWORD=os.environ.get("MAC_PASS","19991112")
REMOTE=r"""#!/bin/bash
P="$HOME/Desktop/ArionAgentProd/cross_platform_minimal_deploy"
D="$HOME/Desktop/ArionAgentDev/cross_platform_minimal_deploy"
echo "=== prod turn 23:22 context ==="
grep -n "2026-06-19 23:22" "$P/.run/logs/agent.log" | head -20
echo "=== prod tool calls around search_test ==="
grep -iE "tool_call|semantic|read_file|grep|Glob" "$P/.run/logs/agent.log" | grep -i search_test | tail -15 || true
echo "=== prod agents with search in name ==="
python3 -c "import json; d=json.load(open('$P/agents.json')); print(list(d.get('agents',{}).keys()))"
echo "=== dev agents ==="
python3 -c "import json; d=json.load(open('$D/agents.json')); print(list(d.get('agents',{}).keys()))"
"""
c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=30)
_,o,e=c.exec_command(REMOTE, timeout=60)
print(o.read().decode())
c.close()
