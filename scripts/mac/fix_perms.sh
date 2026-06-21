#!/usr/bin/env bash
# Fix permissions: make all .sh and .command files executable.
# Run from deploy root or via: bash scripts/mac/fix_perms.sh
#
# Usage:
#   ./scripts/mac/fix_perms.sh          # fix this checkout
#   bash scripts/mac/fix_perms.sh /path  # fix a specific checkout

set -euo pipefail

if [[ -n "${1:-}" ]]; then
  DEPLOY_DIR="$1"
else
  DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fi

echo "Fixing permissions in: $DEPLOY_DIR"
echo ""

count=0
while IFS= read -r -d '' f; do
  if [[ ! -x "$f" ]]; then
    chmod +x "$f"
    echo "  +x  ${f#"$DEPLOY_DIR/"}"
    count=$((count + 1))
  fi
done < <(find "$DEPLOY_DIR" -type f \( -name '*.sh' -o -name '*.command' \) \
  ! -path '*/.venv/*' ! -path '*/node_modules/*' ! -path '*/.git/*' \
  ! -path '*/__pycache__/*' ! -path '*.egg-info/*' -print0)

echo ""
if [[ "$count" -eq 0 ]]; then
  echo "All scripts are already executable."
else
  echo "Fixed $count script(s)."
fi
