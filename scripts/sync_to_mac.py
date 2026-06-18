#!/usr/bin/env python3
"""Sync arion_agent + cross_platform_minimal_deploy tarball to Mac."""

from __future__ import annotations

import os
import sys
import tarfile
import tempfile
from pathlib import Path

import paramiko

DEPLOY = Path(__file__).resolve().parents[1]
ARION = Path(os.environ.get("ARION_AGENT_ROOT", DEPLOY.parent / "arion_agent"))

HOST = os.environ.get("MAC_HOST", "10.100.33.146")
USER = os.environ.get("MAC_USER", "yongbo_mac")
PASSWORD = os.environ.get("MAC_PASS", "19991112")
MAC_ROOT = os.environ.get("MAC_ROOT", "Desktop/AgentLearning")

SKIP_DIRS = {
    "node_modules", ".venv", "workspaces", ".arion", ".run", "dist",
    "__pycache__", ".pytest_cache", ".git", "to_be_deleted", "frontend/dist",
}
SKIP_FILES = {"agents.json", "agent_config.toml"}
SKIP_SUFFIX = {".egg-info"}


def should_skip(path: Path) -> bool:
    if path.name in SKIP_FILES:
        return True
    parts = set(path.parts)
    if parts & SKIP_DIRS:
        return True
    return any(part.endswith(".egg-info") for part in path.parts)


def build_tarball() -> Path:
    tmp = Path(tempfile.gettempdir()) / "agentlearning-sync.tgz"
    with tarfile.open(tmp, "w:gz") as tar:
        for root_name, root in (("cross_platform_minimal_deploy", DEPLOY), ("arion_agent", ARION)):
            for path in root.rglob("*"):
                if path.is_dir():
                    continue
                rel = path.relative_to(root)
                if should_skip(rel):
                    continue
                tar.add(path, arcname=f"{root_name}/{rel.as_posix()}")
    return tmp


REMOTE_SCRIPT = f"""set -e
ROOT="$HOME/{MAC_ROOT}"
ENV_BAK="/tmp/minimal_deploy.env"
AGENTS_BAK="/tmp/minimal_deploy.agents.json"
[[ -f "$ROOT/cross_platform_minimal_deploy/.env" ]] && cp "$ROOT/cross_platform_minimal_deploy/.env" "$ENV_BAK"
[[ -f "$ROOT/cross_platform_minimal_deploy/agents.json" ]] && cp "$ROOT/cross_platform_minimal_deploy/agents.json" "$AGENTS_BAK"
mkdir -p "$ROOT"
tar -xzf "$HOME/Desktop/agentlearning-sync.tgz" -C "$ROOT"
[[ -f "$ENV_BAK" ]] && cp "$ENV_BAK" "$ROOT/cross_platform_minimal_deploy/.env"
[[ -f "$AGENTS_BAK" ]] && cp "$AGENTS_BAK" "$ROOT/cross_platform_minimal_deploy/agents.json"
cd "$ROOT/cross_platform_minimal_deploy"
chmod +x start.sh stop.sh mac_setup.sh *.command 2>/dev/null || true
for f in start.sh stop.sh start.command stop.command setup.command mac_setup.sh; do
  sed -i '' 's/\\r$//' "$f" 2>/dev/null || true
done
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
if [[ -x .venv/bin/python && -x "$HOME/.local/bin/uv" ]]; then
  cd "$ROOT/arion_agent"
  "$HOME/.local/bin/uv" pip install -e ".[deepseek]" --python "$ROOT/cross_platform_minimal_deploy/.venv/bin/python" -q
  cd "$ROOT/cross_platform_minimal_deploy"
  "$HOME/.local/bin/uv" pip install -r requirements.txt --python .venv/bin/python -q
fi
cd "$ROOT/cross_platform_minimal_deploy/frontend" && npm install --silent
cd "$ROOT/cross_platform_minimal_deploy"
grep -q Summarizing frontend/src/App.tsx && echo "toast: OK" || echo "toast: MISSING"
grep -q on_llm_stream agent/agent_runner.py && echo "stream-runner: OK" || echo "stream-runner: MISSING"
grep -q stream_draft backend/adapters/arion_reader.py && echo "stream-api: OK" || echo "stream-api: MISSING"
grep -q streamDraft frontend/src/hooks/useChatLog.ts && echo "stream-ui: OK" || echo "stream-ui: MISSING"
test -f "$ROOT/arion_agent/arion_agent/util/streaming.py" && echo "stream-core: OK" || echo "stream-core: MISSING"
grep -q make_prefetch_node "$ROOT/arion_agent/arion_agent/assembly.py" && echo "prefetch-core: OK" || echo "prefetch-core: MISSING"
grep -q '"prefetch"' "$ROOT/arion_agent/arion_agent/graph.py" && echo "prefetch-graph: OK" || echo "prefetch-graph: MISSING"
grep -q prefetched agent/agent_events.py && echo "prefetch-deploy: OK" || echo "prefetch-deploy: MISSING"
grep -q "Jump to latest" frontend/src/components/PaginatedConversationLog.tsx && echo "jump-button: OK" || echo "jump-button: MISSING"
if grep -q 'E:\\\\' agents.json 2>/dev/null || grep -q 'E:/' agents.json 2>/dev/null; then
  echo "agents.json: WARN Windows paths detected"
else
  echo "agents.json: OK"
fi
test -f .env && echo "env: OK" || echo "env: MISSING"
rm -f "$HOME/Desktop/agentlearning-sync.tgz"
echo SYNC DONE
"""


def main() -> int:
    tarball = build_tarball()
    print(f"built {tarball} ({tarball.stat().st_size} bytes)")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"connecting to {USER}@{HOST} ...")
    client.connect(
        HOST, username=USER, password=PASSWORD,
        timeout=30, banner_timeout=30, auth_timeout=30,
    )
    print("connected")

    sftp = client.open_sftp()
    remote_tar = f"/Users/{USER}/Desktop/agentlearning-sync.tgz"
    print(f"uploading to {remote_tar} ...")
    sftp.put(str(tarball), remote_tar)
    sftp.close()
    print("upload done")

    _, stdout, stderr = client.exec_command(REMOTE_SCRIPT, timeout=900)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out)
    if err.strip():
        print("STDERR:", err, file=sys.stderr)
    client.close()
    print(f"exit {code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
