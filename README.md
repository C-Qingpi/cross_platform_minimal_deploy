# Cross-platform minimal agent deploy

Local web UI for ArionAgent. Backend reads checkpoint logs from disk; the agent process runs independently.

Works on **Windows** and **macOS**.

## Architecture

```
Browser (React log viewer)
    │ poll /api/messages
    ▼
Backend (FastAPI, no arion_agent import)
    │ inbox JSONL + events.jsonl
    ▼
Agent runner (Python, arion_agent)
    └── workspace/.arion/agents/{id}/checkpoints.sqlite
```

The UI is a pure **agent log viewer**: thinking, tool calls, tool results, final assistant messages. The backend keeps an append-only **display log** per thread (`.arion/agents/{id}/display_log/`) so summarization compacts the agent checkpoint without erasing chat history in the UI. On first read, the display log is bootstrapped from checkpoint history to recover messages already evicted. The **compaction summary** banner shows what the agent retained in working memory.

The UI loads the **last 500 messages** by default. Scroll up to fetch older pages of 500. The header shows total message count.

## Features

- Multiple agents, each with workspace root + optional directory mounts
- Chat threads per agent (shared workspace)
- Send / stop, create / delete agents and threads
- Hot-switch models (`provider:model`, default `deepseek:deepseek_v4_flash`)
- Default: arion identity prompts (STANDARD_SOUL), summarization compaction, file + shell tools, subagenting off

## Repositories

This deploy expects the **arion_agent** library as a sibling checkout:

```
e:/git_repo/
  arion_agent/                  ← pip install -e .
  cross_platform_minimal_deploy/  ← this repo
```

Mac layout is the same idea under `~/Desktop/AgentLearning/`.

### Mac: GitHub SSH + git pull (preserve runtime)

If the Mac was previously synced via tarball, switch to git without losing agents/workspaces:

```bash
cd ~/Desktop/AgentLearning/cross_platform_minimal_deploy
chmod +x mac_git_setup.sh
./mac_git_setup.sh
```

This script:

1. Creates `~/.ssh/id_ed25519` if needed and prints the public key for [GitHub SSH keys](https://github.com/settings/keys)
2. `git pull` (or clone) `C-Qingpi/arion_agent` and `C-Qingpi/cross_platform_minimal_deploy` side by side
3. Restores runtime files: `.env`, `agents.json`, `agent_config.toml`, `workspaces/`, `.arion/`, `.venv/`, `frontend/node_modules/`
4. Runs `mac_setup.sh` to refresh pip/npm deps

From Windows (pushes script and runs over SSH):

```powershell
cd cross_platform_minimal_deploy
python scripts/run_mac_git_setup.py
```

If exit code 2: add the printed SSH public key to GitHub, then re-run.


```bash
# Clone both repos side by side, then:
cd ../arion_agent && pip install -e ".[deepseek,openai,anthropic,moonshot]"

cd ../cross_platform_minimal_deploy
cp .env.example .env
# Set DEEPSEEK_API_KEY in .env

pip install -r requirements.txt
cd frontend && npm install && cd ..
```

## Run

**Windows (PowerShell):**

```powershell
.\start.ps1
```

**macOS / Linux:**

```bash
chmod +x start.sh stop.sh
./start.sh
```

On macOS you can also double-click **`start.command`** / **`stop.command`** in Finder (runs in Terminal). First-time setup: double-click **`setup.command`**.

Open http://localhost:5174

**Dev-only:** `start_dev.*` sets `ARION_DEPLOY_MODE=dev`, which enables optional `semantic_search` middleware (background index at `{workspace}/.arion/index/`). Install with editable arion_agent including search extras: `pip install -e ../arion_agent[deepseek,search]`.

Smoke tests:

```bash
python -m pytest tests/test_smoke_dev.py -v
python agent/agent_runner.py --test-resume
```

Processes:

| Service | Port (default) |
|---------|----------------|
| Backend | 8920 |
| Frontend | 5174 |

## Configuration

- `.env` — `DEEPSEEK_API_KEY`, `DEPLOY_ROOT`, ports
- `agent_config.toml` — model default and provider keys (auto-seeded from `.env`)

Model string format: `provider:model_id`

Examples:

- `deepseek:deepseek_v4_flash` (default)
- `deepseek:deepseek_v4_pro`
- `openai:gpt-4o-mini`

Underscores in model ids are normalized to hyphens for DeepSeek.

## Create an agent with mounts

Use the UI **+ New** button, or POST `/api/agents`:

```json
{
  "agent_id": "researcher",
  "mounts": [{ "name": "refs", "path": "/path/to/extra/dir" }]
}
```

Mounts appear under `workspace/imported_directories/{name}/`.

## Agent defaults (runner)

| Setting | Value |
|---------|-------|
| Soul / memory | `STANDARD_SOUL`, `STANDARD_DEEPMEMORY` |
| System prompt | arion `BASE_ARION_PROMPT` + `STANDARD_SOUL` / `STANDARD_DEEPMEMORY` |
| User messages | pass-through (no deploy wrapper) |
| Summarization | proactive prefetch apply in headroom zone + hard compress fallback (STANDARD_POLICY) |
| Subagents | disabled |
| File + shell | enabled |
| Planning | disabled |

## Test agent without UI

```bash
python agent/agent_runner.py --test
```
