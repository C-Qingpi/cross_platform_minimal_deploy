#!/usr/bin/env bash
# Windows/Linux: create git bundle and copy to Mac (LAN sync, no GitHub auth on Mac).
set -euo pipefail

MAC_HOST="${MAC_HOST:-yongbo_mac@10.100.33.146}"
MAC_PASS="${MAC_PASS:-19991112}"
MAC_ROOT="${MAC_ROOT:-Desktop/AgentLearning}"
REPO="${REPO:-/mnt/e/git_repo}"
BRANCH="${BRANCH:-main}"
BUNDLE="/tmp/arion-terminal-sync.bundle"

TERMINAL_PATHS=(
  arion_agent/arion_agent/environments/shell
  arion_agent/pyproject.toml
  arion_agent/tests/test_jobs.py
  arion_agent/tests/test_wait_tool.py
  cross_platform_minimal_deploy/tests/integration/test_jobs_behaviors.py
  cross_platform_minimal_deploy/tests/run_terminal.sh
  cross_platform_minimal_deploy/tests/run_terminal.ps1
  cross_platform_minimal_deploy/scripts/legacy/sync_from_git.sh
  cross_platform_minimal_deploy/scripts/legacy/setup_mac_git.sh
  cross_platform_minimal_deploy/scripts/legacy/push_terminal_bundle.sh
)

cd "$REPO"
git bundle create "$BUNDLE" "$BRANCH"
sshpass -p "$MAC_PASS" scp -o StrictHostKeyChecking=accept-new "$BUNDLE" "${MAC_HOST}:~/Desktop/arion-terminal-sync.bundle"

sshpass -p "$MAC_PASS" ssh -o StrictHostKeyChecking=accept-new "$MAC_HOST" "bash -s" <<REMOTE
set -euo pipefail
ROOT="\$HOME/${MAC_ROOT}"
BUNDLE="\$HOME/Desktop/arion-terminal-sync.bundle"
mkdir -p "\$ROOT"
cd "\$ROOT"
if [[ ! -d .git ]]; then git init; fi
git remote remove origin 2>/dev/null || true
git remote remove bundle 2>/dev/null || true
git remote add bundle "\$BUNDLE"
git fetch bundle "$BRANCH"
for path in ${TERMINAL_PATHS[*]}; do
  git checkout "FETCH_HEAD" -- "\$path"
done
git remote remove bundle
echo "Mac updated selected paths from bundle at \$ROOT"
REMOTE

echo "Bundle pushed and selected paths updated on Mac."
