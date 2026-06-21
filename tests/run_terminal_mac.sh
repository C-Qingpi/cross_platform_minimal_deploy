#!/usr/bin/env bash
# Run terminal tests on Mac after sync_from_git.sh
set -euo pipefail

export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
ROOT="${AGENT_LEARNING_ROOT:-$HOME/Desktop/AgentLearning}"
export DEPLOY_ROOT="${DEPLOY_ROOT:-$ROOT/cross_platform_minimal_deploy}"
VENV="$ROOT/cross_platform_minimal_deploy/.venv"
PY="$VENV/bin/python"
UV="$HOME/.local/bin/uv"

echo "=== Mac terminal tests ==="
echo "platform: $(uname -s) $(uname -m)"
echo "python: $($PY --version)"

cd "$ROOT/arion_agent"
"$UV" pip install -e ".[deepseek]" --python "$PY" -q

cd "$ROOT/cross_platform_minimal_deploy"
"$UV" pip install -r requirements.txt --python "$PY" -q

"$PY" tests/integration/test_jobs_behaviors.py --direct-only
"$PY" tests/integration/test_jobs_behaviors.py --agent-only

echo "=== Mac all job tests PASS ==="
