#!/usr/bin/env bash
# One-time Mac setup: git + GitHub SSH for sync_from_git.sh
set -euo pipefail

export PATH="$HOME/.local/bin:/usr/bin:/bin"
ROOT="${AGENT_LEARNING_ROOT:-$HOME/Desktop/AgentLearning}"
KEY="$HOME/.ssh/github_arionagent"
REMOTE_SSH="git@github.com:C-Qingpi/ArionAgent.git"

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

if [[ ! -f "$KEY" ]]; then
  echo "Generating GitHub SSH key: $KEY"
  ssh-keygen -t ed25519 -f "$KEY" -N "" -C "yongbo_mac@AgentLearning"
fi

if ! grep -q "Host github.com" "$HOME/.ssh/config" 2>/dev/null; then
  cat >> "$HOME/.ssh/config" <<EOF

Host github.com
  HostName github.com
  User git
  IdentityFile $KEY
  IdentitiesOnly yes
EOF
  chmod 600 "$HOME/.ssh/config"
fi

ssh-keyscan -t ed25519 github.com >> "$HOME/.ssh/known_hosts" 2>/dev/null || true

cd "$ROOT"
if [[ ! -d .git ]]; then
  git init
fi
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_SSH"

echo ""
echo "Add this public key to GitHub (Settings -> SSH keys):"
echo "https://github.com/settings/keys"
echo ""
cat "${KEY}.pub"
echo ""
echo "Then run:  cd $ROOT && ./cross_platform_minimal_deploy/sync_from_git.sh"
