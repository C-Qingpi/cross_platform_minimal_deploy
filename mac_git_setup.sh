#!/usr/bin/env bash
# One-time / repeat: GitHub SSH + git pull for arion_agent + cross_platform_minimal_deploy.
# Preserves deploy runtime files (.env, agents.json, workspaces, .arion, .venv, etc.)
#
# Run on Mac:
#   cd ~/Desktop/AgentLearning/cross_platform_minimal_deploy
#   chmod +x mac_git_setup.sh
#   ./mac_git_setup.sh
#
# Optional env:
#   AGENTLEARNING_ROOT=~/Desktop/AgentLearning
#   GITHUB_USER=C-Qingpi
#   GIT_BRANCH=main
#   SKIP_SSH=1          # skip SSH key generation / github.com test
#   SKIP_DEPS=1         # skip mac_setup.sh after pull
#   FRESH_RESET=1       # git reset --hard + clean -fdx before restore (drops stale local scripts)

set -euo pipefail

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

ROOT="${AGENTLEARNING_ROOT:-$HOME/Desktop/AgentLearning}"
GITHUB_USER="${GITHUB_USER:-C-Qingpi}"
GIT_BRANCH="${GIT_BRANCH:-main}"
ARION_DIR="$ROOT/arion_agent"
DEPLOY_DIR="$ROOT/cross_platform_minimal_deploy"
ARION_REPO="git@github.com:${GITHUB_USER}/arion_agent.git"
DEPLOY_REPO="git@github.com:${GITHUB_USER}/cross_platform_minimal_deploy.git"
BACKUP_ROOT="$ROOT/.runtime_backup_$(date +%Y%m%d_%H%M%S)"
LOG="${MAC_GIT_SETUP_LOG:-$HOME/Desktop/mac_git_setup.log}"

exec > >(tee -a "$LOG") 2>&1
echo "=== mac_git_setup $(date -Iseconds) ==="
echo "ROOT=$ROOT"
echo "Log: $LOG"

ensure_github_ssh() {
  if [[ "${SKIP_SSH:-0}" == "1" ]]; then
    echo "[ssh] SKIP_SSH=1 — skipping SSH setup"
    return 0
  fi

  mkdir -p "$HOME/.ssh"
  chmod 700 "$HOME/.ssh"

  if [[ ! -f "$HOME/.ssh/id_ed25519" && ! -f "$HOME/.ssh/id_rsa" ]]; then
    echo "[ssh] Generating ed25519 key for GitHub ..."
    ssh-keygen -t ed25519 -C "$(whoami)@$(hostname -s)" -f "$HOME/.ssh/id_ed25519" -N ""
  fi

  KEY_FILE="$HOME/.ssh/id_ed25519"
  [[ -f "$KEY_FILE" ]] || KEY_FILE="$HOME/.ssh/id_rsa"

  # Always pin github.com to the key we manage (do not append duplicate Host blocks).
  python3 - "$HOME/.ssh/config" "$KEY_FILE" <<'PY'
import sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
key_file = sys.argv[2]
block = f"""
Host github.com
  HostName github.com
  User git
  IdentityFile {key_file}
  IdentitiesOnly yes
""".strip() + "\n"

text = cfg_path.read_text() if cfg_path.exists() else ""
lines = text.splitlines()
out: list[str] = []
i = 0
while i < len(lines):
    line = lines[i]
    if line.strip().lower() == "host github.com":
        i += 1
        while i < len(lines) and not (
            lines[i].strip().lower().startswith("host ")
            and lines[i].strip().lower() != "host github.com"
        ):
            i += 1
        continue
    out.append(line)
    i += 1

while out and not out[-1].strip():
    out.pop()

if out:
    merged = "\n".join(out).rstrip() + "\n\n" + block
else:
    merged = block
cfg_path.parent.mkdir(mode=0o700, exist_ok=True)
cfg_path.write_text(merged)
PY
  chmod 600 "$HOME/.ssh/config"
  echo "[ssh] github.com -> $KEY_FILE"

  eval "$(ssh-agent -s)" >/dev/null
  ssh-add "$KEY_FILE"

  ssh_out="$(ssh -o StrictHostKeyChecking=accept-new -T git@github.com 2>&1 || true)"
  if echo "$ssh_out" | grep -qi 'successfully authenticated'; then
    echo "[ssh] GitHub SSH OK"
    echo "$ssh_out" | tail -1
    return 0
  fi

  echo "$ssh_out"

  echo "[ssh] GitHub SSH not authenticated yet."
  echo "[ssh] Public key (add at https://github.com/settings/keys if not already):"
  echo "-----"
  cat "${KEY_FILE}.pub"
  echo "-----"
  echo "  1. Copy the public key above"
  echo "  2. GitHub → Settings → SSH and GPG keys → New SSH key"
  echo "  3. Re-run: ./mac_git_setup.sh"
  exit 2
}

backup_deploy_runtime() {
  mkdir -p "$BACKUP_ROOT"
  echo "[backup] Saving runtime files to $BACKUP_ROOT"

  backup_path() {
    local rel="$1"
    local src="$DEPLOY_DIR/$rel"
    if [[ -e "$src" ]]; then
      mkdir -p "$(dirname "$BACKUP_ROOT/deploy/$rel")"
      cp -a "$src" "$BACKUP_ROOT/deploy/$rel"
      echo "  saved deploy/$rel"
    fi
  }

  backup_path ".env"
  backup_path "deploy.config"
  backup_path "agents.json"
  backup_path "agent_config.toml"
  backup_path "workspaces"
  backup_path ".arion"
  if [[ "${FRESH_RESET:-0}" != "1" ]]; then
    backup_path ".run"
  fi
  backup_path ".venv"
  backup_path "frontend/node_modules"
}

ensure_deploy_config() {
  local cfg="$DEPLOY_DIR/deploy.config"
  if [[ -f "$cfg" ]]; then
    return 0
  fi
  cp "$DEPLOY_DIR/deploy.config.example" "$cfg"
  if [[ "$ROOT" == *ArionAgentProd* ]]; then
    sed -i '' 's/^mode=dev/mode=prod/' "$cfg"
  fi
  echo "[fresh] Created deploy.config from example ($(grep '^mode=' "$cfg" || true))"
}

purge_stale_deploy_entries() {
  local trash="$HOME/Desktop/to_be_deleted/$(basename "$ROOT")_deploy_cruft"
  mkdir -p "$trash"
  local removed=0
  local name
  for name in \
    start_dev.sh start_dev.ps1 start_dev.bat start_dev.command \
    stop_dev.sh stop_dev.ps1 stop_dev.bat stop_dev.command \
    start_prod.sh start_prod.ps1 start_prod.bat start_prod.command \
    stop_prod.sh stop_prod.ps1 stop_prod.bat stop_prod.command; do
    if [[ -e "$DEPLOY_DIR/$name" ]]; then
      mv "$DEPLOY_DIR/$name" "$trash/"
      removed=$((removed + 1))
    fi
  done
  if [[ -d "$DEPLOY_DIR/to_be_deleted" ]]; then
    mv "$DEPLOY_DIR/to_be_deleted" "$trash/repo_to_be_deleted"
    removed=$((removed + 1))
  fi
  find "$ROOT" -maxdepth 1 -type d -name '.runtime_backup_*' -exec rm -rf {} + 2>/dev/null || true
  if [[ "$removed" -gt 0 ]]; then
    echo "[fresh] Archived $removed stale deploy path(s) -> $trash"
  fi
}

restore_deploy_runtime() {
  if [[ ! -d "$BACKUP_ROOT/deploy" ]]; then
    echo "[restore] No deploy backup at $BACKUP_ROOT — nothing to restore"
    return 0
  fi

  echo "[restore] Restoring runtime files from $BACKUP_ROOT"

  restore_item() {
    local rel="$1"
    local src="$BACKUP_ROOT/deploy/$rel"
    local dest="$DEPLOY_DIR/$rel"
    if [[ ! -e "$src" ]]; then
      return 0
    fi
    mkdir -p "$(dirname "$dest")"
    rm -rf "$dest"
    cp -a "$src" "$dest"
    echo "  restored $rel"
  }

  restore_item ".env"
  restore_item "deploy.config"
  restore_item "agents.json"
  restore_item "agent_config.toml"
  restore_item "workspaces"
  restore_item ".arion"
  if [[ "${FRESH_RESET:-0}" != "1" ]]; then
    restore_item ".run"
  fi
  restore_item ".venv"
  restore_item "frontend/node_modules"
  ensure_deploy_config
}

pull_or_clone() {
  local name="$1"
  local dir="$2"
  local repo="$3"

  mkdir -p "$ROOT"

  if [[ -d "$dir/.git" ]]; then
    echo "[git] Pull $name"
    git -C "$dir" remote set-url origin "$repo"
    git -C "$dir" fetch origin "$GIT_BRANCH"
    git -C "$dir" checkout "$GIT_BRANCH"
    if [[ "${FRESH_RESET:-0}" == "1" ]]; then
      git -C "$dir" reset --hard "origin/$GIT_BRANCH"
      git -C "$dir" clean -fdx
    else
      git -C "$dir" pull --ff-only origin "$GIT_BRANCH"
    fi
    return 0
  fi

  if [[ -d "$dir" ]]; then
    local stash="$ROOT/.${name}_pre_git_$(date +%Y%m%d_%H%M%S)"
    echo "[git] $dir exists without .git — moving to $stash"
    mv "$dir" "$stash"
  fi

  echo "[git] Clone $name"
  git clone --branch "$GIT_BRANCH" "$repo" "$dir"
}

fix_scripts() {
  cd "$DEPLOY_DIR"
  chmod +x start.sh stop.sh mac_setup.sh mac_git_setup.sh *.command 2>/dev/null || true
  for f in start.sh stop.sh start.command stop.command setup.command mac_setup.sh mac_git_setup.sh; do
    [[ -f "$f" ]] && sed -i '' 's/\r$//' "$f" 2>/dev/null || true
  done
}

verify_runtime() {
  echo "[verify] Runtime checks"
  [[ -f "$DEPLOY_DIR/.env" ]] && echo "  .env: OK" || echo "  .env: MISSING (copy from .env.example)"
  [[ -f "$DEPLOY_DIR/agents.json" ]] && echo "  agents.json: OK" || echo "  agents.json: MISSING (create via UI or restore_mac_agents.py)"
  if [[ -d "$DEPLOY_DIR/workspaces" ]]; then
    echo "  workspaces: OK ($(find "$DEPLOY_DIR/workspaces" -mindepth 1 -maxdepth 2 -type d 2>/dev/null | wc -l | tr -d ' ') dirs)"
  else
    echo "  workspaces: MISSING (will be created when agents run)"
  fi
  if grep -q 'E:\\\\' "$DEPLOY_DIR/agents.json" 2>/dev/null || grep -q 'E:/' "$DEPLOY_DIR/agents.json" 2>/dev/null; then
    echo "  agents.json: WARN Windows paths — run scripts/restore_mac_agents.py"
  fi
  git -C "$ARION_DIR" log -1 --oneline
  git -C "$DEPLOY_DIR" log -1 --oneline
}

main() {
  ensure_github_ssh

  # Backup deploy runtime before any tree replacement
  if [[ -d "$DEPLOY_DIR" ]]; then
    backup_deploy_runtime
  fi

  pull_or_clone "arion_agent" "$ARION_DIR" "$ARION_REPO"
  pull_or_clone "cross_platform_minimal_deploy" "$DEPLOY_DIR" "$DEPLOY_REPO"

  restore_deploy_runtime
  fix_scripts

  if [[ "${FRESH_RESET:-0}" == "1" ]]; then
    purge_stale_deploy_entries
  fi

  if [[ "${SKIP_DEPS:-0}" != "1" && -x "$DEPLOY_DIR/mac_setup.sh" ]]; then
    echo "[deps] Running mac_setup.sh ..."
    bash "$DEPLOY_DIR/mac_setup.sh"
  else
    echo "[deps] Skipped mac_setup.sh (SKIP_DEPS=${SKIP_DEPS:-0})"
  fi

  if [[ "${FRESH_RESET:-0}" == "1" ]]; then
    git -C "$DEPLOY_DIR" checkout -- deploy_env.sh mac_git_setup.sh mac_setup.sh setup.command 2>/dev/null || true
  fi

  verify_runtime
  echo ""
  echo "Done. Start deploy:"
  echo "  cd $DEPLOY_DIR && ./start.sh"
  echo "Backup kept at: $BACKUP_ROOT"
}

main "$@"
