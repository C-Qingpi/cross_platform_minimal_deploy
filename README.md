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
chmod +x scripts/mac/git_setup.sh
./scripts/mac/git_setup.sh
```

This script:

1. Creates `~/.ssh/id_ed25519` if needed and prints the public key for [GitHub SSH keys](https://github.com/settings/keys)
2. `git pull` (or clone) `C-Qingpi/arion_agent` and `C-Qingpi/cross_platform_minimal_deploy` side by side
3. Restores runtime files: `.env`, `agents.json`, `agent_config.toml`, `workspaces/`, `.arion/`, `.venv/`, `frontend/node_modules/`
4. Runs `scripts/mac/setup.sh` to refresh pip/npm deps

From Windows (pushes script and runs over SSH):

```powershell
cd cross_platform_minimal_deploy
python scripts/mac/run_git_setup.py
```

Pull or fresh-reset Prod/Dev sibling checkouts on Mac:

```powershell
python scripts/mac/pull_prod_dev.py
python scripts/mac/reset_fresh.py
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

First-time setup per checkout:

```bash
cp deploy.config.example deploy.config
# ArionAgentDev checkout: mode=dev
# ArionAgentProd checkout: mode=prod
```

`setup.command` / `scripts/mac/setup.sh` creates `deploy.config` automatically if missing (Prod path gets `mode=prod`).

**Windows (PowerShell):**

```powershell
.\start.ps1
```

**macOS / Linux:**

```bash
chmod +x start.sh stop.sh deploy_env.sh
./start.sh
```

On macOS you can also double-click **`start.command`** / **`stop.command`** in Finder. First-time setup: double-click **`setup.command`**.

Open the URL printed by start (ports come from `deploy.config`).

**Dev mode** (`mode=dev`) enables optional `semantic_search` middleware (background index at `{workspace}/.arion/index/`). Setup installs `arion-agent[deepseek,search]` for dev checkouts only.

> **After a `git pull` that adds new optional extras** (e.g. `[search]`), re-run `setup.command` (macOS) or `scripts/mac/setup.sh` on dev checkouts to refresh the venv.

Smoke tests:

```bash
python -m pytest tests/test_smoke_dev.py tests/test_deploy_config.py -v
python agent/agent_runner.py --test-resume
```

Processes (defaults from `deploy.config`):

| mode | Backend | Frontend | semantic_search |
|------|---------|----------|-----------------|
| dev  | 8920    | 5174     | yes             |
| prod | 8921    | 5175     | no              |

## Scripts layout

Repo root keeps only deploy entry points (`start.*`, `stop.*`, `deploy.config*`, core Python modules).

| Path | Purpose |
|------|---------|
| `scripts/mac/setup.sh` | Mac deps + venv refresh |
| `scripts/mac/git_setup.sh` | Mac git pull/clone + runtime restore |
| `scripts/mac/run_git_setup.py` | Upload and run git_setup from Windows |
| `scripts/mac/pull_prod_dev.py` | Pull Prod (main) + Dev (dev) on Mac |
| `scripts/mac/reset_fresh.py` | Hard reset Mac checkouts, preserve agent data |
| `scripts/mac/restore_agents.py` | Fix agents.json after bad sync |
| `scripts/mac/diag/` | SSH diagnostics (semantic search, etc.) |
| `scripts/legacy/` | Old tarball/sync helpers (deprecated) |
| `scripts/repro/` | One-off reproduction scripts |
| `tests/integration/test_jobs_behaviors.py` | Terminal job behavior tests |
| `tests/run_terminal.*` | Run integration tests (Windows / Mac / Linux) |

## Configuration

- `deploy.config` — **per checkout**: `mode=dev|prod`, optional port overrides. `DEPLOY_ROOT` is always this folder (never set in `.env`).
- `.env` — secrets only: `DEEPSEEK_API_KEY`, `DEFAULT_MODEL`
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
