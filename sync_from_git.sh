#!/usr/bin/env bash
# Pull selected terminal-related paths from origin without touching workspace data.
#
# One-time: makes ~/Desktop/AgentLearning git-managed (git init + remote).
# Ongoing:  git fetch && checkout selected paths from origin/main.
#
# Usage (Mac):
#   cd ~/Desktop/AgentLearning
#   ./cross_platform_minimal_deploy/sync_from_git.sh
#
# Env overrides:
#   AGENT_LEARNING_ROOT  default: ~/Desktop/AgentLearning
#   AGENT_GIT_REMOTE     default: git@github.com:C-Qingpi/ArionAgent.git
#   AGENT_GIT_BRANCH     default: main
#
# First-time Mac setup (GitHub SSH key):
#   ./cross_platform_minimal_deploy/setup_mac_git.sh
#   add printed key at https://github.com/settings/keys
#   ./cross_platform_minimal_deploy/sync_from_git.sh
#
# LAN fallback (no GitHub auth on Mac): run from Windows/WSL
#   ./cross_platform_minimal_deploy/push_terminal_bundle.sh

set -euo pipefail

ROOT="${AGENT_LEARNING_ROOT:-$HOME/Desktop/AgentLearning}"
REMOTE="${AGENT_GIT_REMOTE:-git@github.com:C-Qingpi/ArionAgent.git}"
BRANCH="${AGENT_GIT_BRANCH:-main}"

TERMINAL_PATHS=(
  arion_agent/arion_agent/environments/shell
  arion_agent/pyproject.toml
  arion_agent/tests/test_jobs.py
  arion_agent/tests/test_wait_tool.py
  cross_platform_minimal_deploy/agent/test_jobs_behaviors.py
  cross_platform_minimal_deploy/run_terminal_tests.sh
  cross_platform_minimal_deploy/run_terminal_tests.ps1
  cross_platform_minimal_deploy/sync_from_git.sh
  cross_platform_minimal_deploy/setup_mac_git.sh
  cross_platform_minimal_deploy/push_terminal_bundle.sh
)

cd "$ROOT"

if [[ ! -d .git ]]; then
  echo "Initializing git at $ROOT"
  git init
  git remote add origin "$REMOTE"
fi

echo "Fetching origin/$BRANCH ..."
git fetch origin "$BRANCH"

echo "Checking out selected paths from origin/$BRANCH:"
for path in "${TERMINAL_PATHS[@]}"; do
  echo "  $path"
  git checkout "origin/$BRANCH" -- "$path"
done

echo "Done. Selected terminal files now match origin/$BRANCH."
