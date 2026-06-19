#!/usr/bin/env python3
"""Post-sync verification on Mac (agents.json, streaming files, services)."""

from __future__ import annotations

import json
import os
import sys

import paramiko

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")
MAC_ROOT = os.environ.get("MAC_ROOT", "Desktop/AgentLearning")
ROOT = f"/Users/{USER}/{MAC_ROOT}/cross_platform_minimal_deploy"


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"connecting to {USER}@{HOST} ...")
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

    checks = f"""set -e
ROOT="{ROOT}"
cd "$ROOT"
echo "=== agents.json ==="
cat agents.json
python3 - <<'PY'
import json, pathlib, sys
p = pathlib.Path("{ROOT}/agents.json")
data = json.loads(p.read_text())
bad = []
for aid, info in data.get("agents", {{}}).items():
    ws = info.get("workspace", "")
    if ":\\\\" in ws or ws.startswith("E:") or ws.startswith("C:"):
        bad.append((aid, ws))
if bad:
    print("FAIL: Windows workspace paths:", bad)
    sys.exit(1)
print("agents.json paths: OK")
PY
echo "=== streaming files ==="
test -f ../arion_agent/arion_agent/util/streaming.py
grep -q on_llm_stream agent/agent_runner.py
grep -q stream_draft backend/adapters/arion_reader.py
grep -q streamDraft frontend/src/hooks/useChatLog.ts
grep -q make_prefetch_node ../arion_agent/arion_agent/assembly.py
grep -q '"prefetch"' ../arion_agent/arion_agent/graph.py
grep -q prefetched agent/agent_events.py
echo "streaming files: OK"
echo "=== services ==="
(lsof -i :8920 -sTCP:LISTEN || true) | head -3
(lsof -i :5174 -sTCP:LISTEN || true) | head -3
pgrep -fl agent_runner.py || true
"""

    _, stdout, stderr = client.exec_command(checks, timeout=60)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out)
    if err.strip():
        print(err, file=sys.stderr)
    client.close()
    print(f"verify exit {code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
