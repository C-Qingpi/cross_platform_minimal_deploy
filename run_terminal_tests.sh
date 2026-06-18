#!/usr/bin/env bash
# Run terminal behavior tests on macOS/Linux (real agent workspace).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== macOS/Linux terminal test runner ==="
echo "platform: $(uname -s) $(uname -m)"

pip install -e ../arion_agent -q
pip install -r requirements.txt -q

cd agent
python test_jobs_behaviors.py "$@"
