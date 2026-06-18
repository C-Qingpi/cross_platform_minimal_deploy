#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$PATH"
export UV_INDEX_URL="${UV_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
export npm_config_registry="${npm_config_registry:-https://registry.npmmirror.com}"

ROOT="$HOME/Desktop/AgentLearning"
PY="$HOME/.local/bin/python3.12"
UV="$HOME/.local/bin/uv"
VENV="$ROOT/cross_platform_minimal_deploy/.venv"
LOG="$HOME/Desktop/mac_setup.log"
NODE_VERSION="${NODE_VERSION:-20.19.2}"

exec > >(tee -a "$LOG") 2>&1
echo "=== mac_setup $(date -Iseconds) ==="

if [[ ! -x "$PY" ]]; then
  echo "python3.12 not found at $PY - install via: uv python install 3.12"
  exit 1
fi

if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
  echo "Homebrew: $(brew --version | head -1)"
fi

install_node_local() {
  local arch dir tarball
  arch="$(uname -m)"
  case "$arch" in
    arm64) dir="node-v${NODE_VERSION}-darwin-arm64" ;;
    x86_64) dir="node-v${NODE_VERSION}-darwin-x64" ;;
    *) echo "Unsupported arch: $arch"; exit 1 ;;
  esac
  tarball="${dir}.tar.gz"
  echo "Installing Node ${NODE_VERSION} to ~/.local ..."
  curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/${tarball}" -o "/tmp/${tarball}"
  mkdir -p "$HOME/.local"
  tar -xzf "/tmp/${tarball}" -C "$HOME/.local" --strip-components=1
  rm -f "/tmp/${tarball}"
}

if ! command -v node >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Installing node via Homebrew..."
    brew install node
  else
    install_node_local
  fi
fi

export PATH="$HOME/.local/bin:$PATH"
echo "Node: $(node --version)"
echo "Python: $($PY --version)"
echo "PyPI index: $UV_INDEX_URL"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Creating venv at $VENV ..."
  "$UV" venv "$VENV" --python "$PY"
else
  echo "Reusing venv at $VENV"
fi
VPY="$VENV/bin/python"

echo "[1/3] Installing arion_agent (may take several minutes) ..."
cd "$ROOT/arion_agent"
"$UV" pip install -v -e ".[deepseek]" --python "$VPY"

echo "[2/3] Installing deploy backend deps ..."
cd "$ROOT/cross_platform_minimal_deploy"
"$UV" pip install -v -r requirements.txt --python "$VPY"

echo "[3/3] Installing frontend deps ..."
cd frontend
npm install --loglevel info

cd "$ROOT/cross_platform_minimal_deploy"
chmod +x start.sh stop.sh start.command stop.command setup.command mac_setup.sh 2>/dev/null || true
chmod +x start.sh stop.sh

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "WARNING: created .env from example - set DEEPSEEK_API_KEY"
elif ! grep -q '^DEEPSEEK_API_KEY=sk-' .env 2>/dev/null; then
  echo "WARNING: DEEPSEEK_API_KEY may be missing in .env"
fi

echo ""
echo "Setup complete at $(date -Iseconds)"
echo "  cd $ROOT/cross_platform_minimal_deploy"
echo "  ./start.sh"
echo "Log: $LOG"
