#!/usr/bin/env python3
"""Diagnose semantic_search availability on Mac Prod/Dev deploy folders."""

from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")

REMOTE = r"""#!/bin/bash
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

check_deploy() {
  local label="$1"
  local root="$2"
  local d="$root/cross_platform_minimal_deploy"
  echo "========== ${label}: ${d} =========="
  if [[ ! -d "$d" ]]; then
    echo "MISSING"
    echo
    return
  fi
  git -C "$d" log -1 --oneline 2>/dev/null || true
  git -C "$root/arion_agent" log -1 --oneline 2>/dev/null || true

  echo "--- listeners ---"
  for p in 8920 8921 5174 5175; do
    lsof -i :"$p" -sTCP:LISTEN 2>/dev/null | head -2 || true
  done

  echo "--- agent processes ---"
  found=0
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    cmd=$(ps -p "$pid" -o command= 2>/dev/null || true)
    [[ "$cmd" == *"$d"* ]] || continue
    found=1
    echo "pid=$pid"
    echo "cmd=$cmd"
    ps eww -p "$pid" 2>/dev/null | tr ' ' '\n' | grep -E '^(ARION_DEPLOY_MODE|BACKEND_PORT|DEPLOY_ROOT)=' || true
  done < <(pgrep -f agent_runner.py 2>/dev/null || true)
  [[ "$found" -eq 0 ]] && echo "(none for this deploy)"

  local vpy="$d/.venv/bin/python"
  if [[ ! -x "$vpy" ]]; then
    echo "no venv at $vpy"
    echo
    return
  fi

  echo "--- search deps ---"
  "$vpy" -c "import fastembed; print('fastembed OK', fastembed.__version__)" 2>&1 || echo "fastembed MISSING"
  "$vpy" -c "from arion_agent.environments.search import is_search_available; print('is_search_available', is_search_available())" 2>&1 || echo "search import failed"

  echo "--- middleware probe (ARION_DEPLOY_MODE=dev) ---"
  ARION_DEPLOY_MODE=dev "$vpy" -c "
import os, sys
sys.path.insert(0, '${d}/agent')
os.environ['ARION_DEPLOY_MODE'] = 'dev'
from pathlib import Path
import agent_runner as ar
for candidate in ['${d}/workspaces/default', '${d}']:
    ws = Path(candidate)
    if ws.is_dir():
        break
else:
    ws = Path('${d}')
mw = ar._optional_middleware(ws)
print('workspace', ws)
print('middleware_count', len(mw))
if mw:
    print('tool', mw[0].tools[0].name)
" 2>&1

  echo "--- middleware probe (no ARION_DEPLOY_MODE) ---"
  env -u ARION_DEPLOY_MODE "$vpy" -c "
import sys
sys.path.insert(0, '${d}/agent')
from pathlib import Path
import agent_runner as ar
ws = Path('${d}')
print('middleware_count', len(ar._optional_middleware(ws)))
" 2>&1

  echo "--- agent log tail ---"
  grep -iE 'search|semantic|Dev deploy' "$d/.run/logs/agent.log" 2>/dev/null | tail -8 || true
  grep -iE 'search|semantic|Dev deploy' "$d/.run/logs/agent.stdout.log" 2>/dev/null | tail -8 || true
  echo
}

check_deploy DEV "$HOME/Desktop/ArionAgentDev"
check_deploy PROD "$HOME/Desktop/ArionAgentProd"

D="$HOME/Desktop/ArionAgentDev/cross_platform_minimal_deploy"
P="$HOME/Desktop/ArionAgentProd/cross_platform_minimal_deploy"
echo "========== DEEP: dev config + live agent tools =========="
echo "--- .env DEPLOY_ROOT ---"
grep DEPLOY_ROOT "$D/.env" 2>/dev/null || echo "(not set in dev .env)"
grep DEPLOY_ROOT "$P/.env" 2>/dev/null || echo "(not set in prod .env)"
echo "--- dev agents.json ---"
if [[ -f "$D/agents.json" ]]; then head -c 1200 "$D/agents.json"; echo; else echo "missing"; fi
echo "--- prod agents.json (first agent workspace) ---"
if [[ -f "$P/agents.json" ]]; then head -c 800 "$P/agents.json"; echo; fi
echo "--- dev agent log (semantic/middleware) ---"
grep -iE 'semantic|search|middleware|Dev deploy' "$D/.run/logs/agent.log" 2>/dev/null | tail -15 || true
echo "--- live create_agent_instance tool probe (running env: DEPLOY_ROOT=prod) ---"
export AGENT_CODE="$D/agent"
export DEPLOY_ROOT="$P"
export ARION_DEPLOY_MODE=dev
"$VPY" <<PY
import os, sys
sys.path.insert(0, os.environ["AGENT_CODE"])
import agent_runner as ar

agents = ar.registry.list_agents()
print("DEPLOY_ROOT", ar.DEPLOY_ROOT)
print("registry agents", len(agents))
for a in agents[:5]:
    aid = a["agent_id"]
    model = a.get("model") or "deepseek:deepseek_v4_flash"
    agent = ar.create_agent_instance(aid, model)
    g = agent.get_graph() if hasattr(agent, "get_graph") else None
    names = []
    if g is not None:
        for node in g.nodes.values():
            data = getattr(node, "data", None) or node
            if hasattr(data, "bound") and hasattr(data.bound, "tools_by_name"):
                names.extend(data.bound.tools_by_name.keys())
    names = sorted(set(names))
    print(f"agent={aid} graph_tool_count={len(names)} has_semantic={'semantic_search' in names}")
    if names:
        print("  tools", names)
PY
"""


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"connecting to {USER}@{HOST} ...")
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    _, stdout, stderr = client.exec_command(REMOTE, timeout=120)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out)
    if err.strip():
        print("STDERR:", err, file=sys.stderr)
    client.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
