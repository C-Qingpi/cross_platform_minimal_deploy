"""Background-job behavior tests through the minimal deploy workspace.

Runs direct JobRegistry checks and an agent turn that uses the shell job tools.
Usage:
  python tests/integration/test_jobs_behaviors.py
  python tests/integration/test_jobs_behaviors.py --direct-only
  python tests/integration/test_jobs_behaviors.py --agent-only
"""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
DEPLOY_DIR = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(DEPLOY_DIR))
sys.path.insert(0, str(DEPLOY_DIR / "agent"))

load_dotenv(DEPLOY_DIR / ".env")
if not os.environ.get("DEPLOY_ROOT", "").strip():
    os.environ["DEPLOY_ROOT"] = str(DEPLOY_DIR)

from agent_registry import AgentRegistry, default_thread_id
from config import apply_provider_env, get_model, load_config, register_proxies
from prompts import wrap_user_message


def _platform_label() -> str:
    return f"{sys.platform} ({platform.machine()})"


def _resolve_test_agent(registry: AgentRegistry) -> tuple[str, Path]:
    agents = registry.list_agents()
    if not agents:
        registry.create_agent("default", model=get_model())
        agents = registry.list_agents()
    ids = {a["agent_id"] for a in agents}
    agent_id = "default" if "default" in ids else agents[0]["agent_id"]
    info = registry.get_agent(agent_id)
    assert info is not None
    return agent_id, Path(info["workspace"])


def _workspace() -> Path:
    _agent_id, ws = _resolve_test_agent(AgentRegistry(DEPLOY_DIR))
    return ws


async def run_direct_tests(ws: Path) -> list[str]:
    from arion_agent.environments.shell.jobs import JobRegistry

    results: list[str] = []
    results.append(f"platform: {_platform_label()}")
    reg = JobRegistry(ws)
    label = f"behav{int(time.time()) % 100000}"

    started = await reg.run("echo ARION_JOB_OK", description=label)
    results.append(f"run: {started}")
    assert "Started job" in started, started

    async def _await_exit(job_id: str, timeout: float = 10.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = reg.job_state(job_id)
            if st is not None and st.state != "running":
                return
            await asyncio.sleep(0.1)
        raise AssertionError(f"job {job_id} did not finish")

    await _await_exit(label)
    st = reg.job_state(label)
    results.append(f"state: {st.state} exit={st.exit_code}")
    assert st.state == "exited" and st.exit_code == 0, st
    log = reg.read_log(label)
    results.append(f"log:\n{log}")
    assert "ARION_JOB_OK" in log, log

    # Recoverability: a fresh registry sees the finished job.
    fresh = JobRegistry(ws)
    assert fresh.job_state(label).exit_code == 0, "not recoverable across instances"
    results.append("recoverable: OK")

    # Stop a running job.
    sleeper = f"{label}-sleep"
    await reg.run("sleep 30", description=sleeper)
    assert reg.job_state(sleeper).state == "running"
    stopped = await reg.stop(sleeper)
    results.append(f"stop: {stopped}")
    await _await_exit(sleeper)
    assert reg.job_state(sleeper).state == "stopped"

    listing = reg.list_jobs()
    results.append(f"list:\n{listing}")
    assert label in listing, listing

    return results


async def run_agent_test(ws: Path) -> str:
    from agent_runner import create_agent_instance, registry

    agent_id, _ws = _resolve_test_agent(registry)
    agent = create_agent_instance(agent_id, get_model())
    tid = default_thread_id(agent_id)

    prompt = wrap_user_message(
        "Background job check. Do exactly this sequence with no extra steps:\n"
        "1) shell_run command='echo AGENT_JOB_OK' description=agentcheck\n"
        "2) wait job_id=agentcheck\n"
        "3) shell_log job_id=agentcheck\n"
        "Reply with the exact shell_log output only."
    )

    result = await agent.ainvoke(
        {"messages": [("user", prompt)]},
        config={"configurable": {"thread_id": tid}},
    )
    messages = result.get("messages", [])
    ai = [m for m in messages if getattr(m, "type", "") == "ai"]
    return ai[-1].content if ai else "no ai response"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-only", action="store_true")
    parser.add_argument("--direct-only", action="store_true")
    args = parser.parse_args()

    config = load_config()
    apply_provider_env(config)
    register_proxies()
    ws = _workspace()
    print(f"workspace: {ws}")
    print(f"platform: {_platform_label()}")

    if not args.agent_only:
        print("\n=== Direct JobRegistry tests ===")
        for line in await run_direct_tests(ws):
            print(line)
        print("\nDirect tests: PASS")

    if not args.direct_only:
        print("\n=== Agent shell-job tool test ===")
        from agent_runner import registry as runner_registry
        agent_id, _ = _resolve_test_agent(runner_registry)
        print(f"agent: {agent_id}")
        reply = await run_agent_test(ws)
        print(reply)
        assert "AGENT_JOB_OK" in reply, reply
        print("\nAgent test: PASS")


if __name__ == "__main__":
    asyncio.run(main())
