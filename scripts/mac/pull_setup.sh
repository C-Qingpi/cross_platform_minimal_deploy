#!/usr/bin/env bash
# Git pull (arion_agent + cross_platform_minimal_deploy) then refresh deps.
# Preserves runtime (.env, agents.json, workspaces, .venv, etc.) via git_setup.sh.
#
# Run from deploy root:
#   ./scripts/mac/pull_setup.sh
#
# Or double-click pull_setup.command in Finder.
#
# Optional env:
#   GIT_BRANCH=dev|main   override branch (auto: Dev checkout -> dev, Prod -> main)
#   SKIP_SSH=1            default; set SKIP_SSH=0 to re-check GitHub SSH
#   SKIP_DEPS=1           pull only, skip setup.sh

set -euo pipefail

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:$PATH"
export UV_INDEX_URL="${UV_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
export npm_config_registry="${npm_config_registry:-https://registry.npmmirror.com}"

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STACK_ROOT="$(cd "$DEPLOY_DIR/.." && pwd)"
GIT_SETUP="$DEPLOY_DIR/scripts/mac/git_setup.sh"
LOG="${MAC_PULL_SETUP_LOG:-$HOME/Desktop/mac_pull_setup.log}"

exec > >(tee -a "$LOG") 2>&1
echo "=== mac_pull_setup $(date -Iseconds) ==="
echo "deploy=$DEPLOY_DIR"
echo "stack=$STACK_ROOT"
echo "Log: $LOG"

if [[ ! -x "$GIT_SETUP" ]]; then
  echo "ERROR: missing $GIT_SETUP"
  exit 1
fi

if [[ -n "${GIT_BRANCH:-}" ]]; then
  BRANCH="$GIT_BRANCH"
elif [[ "$DEPLOY_DIR" == *ArionAgentDev* ]]; then
  BRANCH=dev
elif [[ "$DEPLOY_DIR" == *ArionAgentProd* ]]; then
  BRANCH=main
elif [[ -f "$DEPLOY_DIR/deploy.config" ]] && grep -qE '^mode=dev\b' "$DEPLOY_DIR/deploy.config"; then
  BRANCH=dev
else
  BRANCH=main
fi

export AGENTLEARNING_ROOT="$STACK_ROOT"
export GIT_BRANCH="$BRANCH"
export SKIP_SSH="${SKIP_SSH:-1}"

echo "AGENTLEARNING_ROOT=$AGENTLEARNING_ROOT"
echo "GIT_BRANCH=$GIT_BRANCH"
echo "SKIP_SSH=$SKIP_SSH"

bash "$GIT_SETUP"

echo ""
echo "Pull + setup complete."
echo "  arion_agent:     $(git -C "$STACK_ROOT/arion_agent" log -1 --oneline 2>/dev/null || echo '?')"
echo "  deploy:          $(git -C "$DEPLOY_DIR" log -1 --oneline 2>/dev/null || echo '?')"
echo ""
echo "Restart this checkout to load new code:"
echo "  cd $DEPLOY_DIR && ./stop.sh && ./start.sh"
