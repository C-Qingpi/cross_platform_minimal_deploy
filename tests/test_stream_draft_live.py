"""Live integration tests for visual LLM streaming in cross_platform_minimal_deploy.

Requires DEEPSEEK_API_KEY in cross_platform_minimal_deploy/.env.
Skipped automatically when the key is missing.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest

DEPLOY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPLOY_DIR))
sys.path.insert(0, str(DEPLOY_DIR / "backend"))
sys.path.insert(0, str(DEPLOY_DIR / "agent"))

from dotenv import load_dotenv

load_dotenv(DEPLOY_DIR / ".env")

from agent_registry import AgentRegistry
from config import apply_provider_env, load_config, register_proxies

HAS_DEEPSEEK = bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())
pytestmark = pytest.mark.skipif(not HAS_DEEPSEEK, reason="DEEPSEEK_API_KEY not set")


def _setup_deploy(tmp_root: Path) -> tuple[AgentRegistry, str, Path]:
    apply_provider_env(load_config())
    register_proxies()
    registry = AgentRegistry(tmp_root)
    agent_id = f"stream-test-{uuid.uuid4().hex[:8]}"
    result = registry.create_agent(agent_id, model="deepseek:deepseek_v4_flash")
    workspace = Path(result["workspace"])
    return registry, agent_id, workspace


def _draft_path(workspace: Path, agent_id: str, thread_id: str) -> Path:
    return workspace / ".arion" / "agents" / agent_id / "stream_draft" / f"{thread_id}.json"


@pytest.fixture
def deploy_ctx():
    with tempfile.TemporaryDirectory() as td:
        tmp_root = Path(td)
        registry, agent_id, workspace = _setup_deploy(tmp_root)
        thread_id = f"{agent_id}-main"
        yield {
            "registry": registry,
            "agent_id": agent_id,
            "workspace": workspace,
            "thread_id": thread_id,
            "deploy_root": tmp_root,
        }


def test_stream_handler_writes_and_clears_draft(deploy_ctx):
    from agent_runner import _make_llm_stream_handler
    from arion_agent.util.streaming import LlmStreamUpdate

    agent_id = deploy_ctx["agent_id"]
    workspace = deploy_ctx["workspace"]
    thread_id = deploy_ctx["thread_id"]
    handler = _make_llm_stream_handler(agent_id, workspace)
    path = _draft_path(workspace, agent_id, thread_id)

    handler(LlmStreamUpdate(thread_id=thread_id, phase="start"))
    handler(
        LlmStreamUpdate(
            thread_id=thread_id,
            phase="delta",
            content="Hello",
            reasoning="thinking step",
        )
    )
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["content"] == "Hello"
    assert data["reasoning"] == "thinking step"

    handler(LlmStreamUpdate(thread_id=thread_id, phase="end"))
    assert not path.exists()


def test_real_deepseek_invoke_emits_stream_draft(deploy_ctx):
    import agent_runner
    from prompts import wrap_user_message

    agent_id = deploy_ctx["agent_id"]
    workspace = deploy_ctx["workspace"]
    thread_id = deploy_ctx["thread_id"]
    draft = _draft_path(workspace, agent_id, thread_id)

    original_registry = agent_runner.registry
    try:
        agent_runner.registry = deploy_ctx["registry"]
        agent = agent_runner.create_agent_instance(agent_id, "deepseek:deepseek_v4_flash")
    finally:
        agent_runner.registry = original_registry
    snapshots: list[dict] = []
    done = asyncio.Event()

    async def poll_draft() -> None:
        while not done.is_set():
            if draft.exists():
                snapshots.append(json.loads(draft.read_text(encoding="utf-8")))
            await asyncio.sleep(0.15)

    async def run_turn() -> dict:
        return await agent.ainvoke(
            {"messages": [("user", wrap_user_message(
                "Reply in 2-3 short sentences about why streaming helps UX. No tools."
            ))]},
            config={"configurable": {"thread_id": thread_id, "model": "deepseek:deepseek_v4_flash"}},
        )

    async def main() -> tuple[dict, list[dict]]:
        poll_task = asyncio.create_task(poll_draft())
        try:
            result = await asyncio.wait_for(run_turn(), timeout=120)
            return result, snapshots
        finally:
            done.set()
            poll_task.cancel()
            with asyncio.suppress(asyncio.CancelledError):
                await poll_task

    result, seen = asyncio.run(main())

    assert not draft.exists(), "stream draft should be cleared after full block completes"

    ai_msgs = [m for m in result["messages"] if getattr(m, "type", "") == "ai"]
    assert ai_msgs, "expected completed AI message in graph result"
    final_content = ai_msgs[-1].content
    assert isinstance(final_content, str) and len(final_content.strip()) > 20

    assert seen, "expected at least one stream_draft snapshot during live call"
    max_content = max(len(s.get("content", "")) for s in seen)
    max_reasoning = max(len(s.get("reasoning", "")) for s in seen)
    assert max_content > 0 or max_reasoning > 0, "draft snapshots were empty"
    assert max(len(s.get("content", "")) for s in seen) <= len(final_content)


def test_backend_exposes_stream_draft_when_thread_active(deploy_ctx):
    from adapters.arion_reader import ArionReader
    from agent_state import AgentStateMachine
    from fastapi.testclient import TestClient

    agent_id = deploy_ctx["agent_id"]
    workspace = deploy_ctx["workspace"]
    thread_id = deploy_ctx["thread_id"]
    draft = _draft_path(workspace, agent_id, thread_id)

    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(
        json.dumps({"content": "live preview", "reasoning": "live thought"}),
        encoding="utf-8",
    )

    events_file = deploy_ctx["deploy_root"] / ".arion" / "events.jsonl"
    events_file.parent.mkdir(parents=True, exist_ok=True)
    events_file.write_text(
        json.dumps(
            {
                "event": "task_started",
                "agent_id": agent_id,
                "thread": thread_id,
                "model": "deepseek:deepseek_v4_flash",
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    reader = ArionReader(str(workspace), agent_id)
    assert reader.get_stream_draft(thread_id) == {
        "content": "live preview",
        "reasoning": "live thought",
    }

    import backend.main as backend_main

    original_registry = backend_main.registry
    original_events = backend_main.events_file
    original_state = backend_main.state_machine
    try:
        backend_main.registry = deploy_ctx["registry"]
        backend_main.events_file = events_file
        backend_main.state_machine = AgentStateMachine(events_file)
        backend_main.state_machine.replay()

        client = TestClient(backend_main.app)
        resp = client.get(
            "/api/messages",
            params={"agent_id": agent_id, "thread_id": thread_id, "limit": 50},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["stream_draft"] == {
            "content": "live preview",
            "reasoning": "live thought",
        }
        assert body["thread_state"]["active"] is True
    finally:
        backend_main.registry = original_registry
        backend_main.events_file = original_events
        backend_main.state_machine = original_state


def test_inbox_runner_turn_produces_stream_draft(deploy_ctx):
    """Full deploy path: _run_turn -> draft file during LLM call."""
    import agent_runner
    from agent_runner import _run_turn, _thread_runtime
    from prompts import wrap_user_message

    agent_id = deploy_ctx["agent_id"]
    workspace = deploy_ctx["workspace"]
    thread_id = deploy_ctx["thread_id"]
    draft = _draft_path(workspace, agent_id, thread_id)

    original_registry = agent_runner.registry
    original_deploy_root = agent_runner.DEPLOY_ROOT
    try:
        agent_runner.registry = deploy_ctx["registry"]
        agent_runner.DEPLOY_ROOT = deploy_ctx["deploy_root"]
        agent_runner._agent_cache.clear()
        agent_runner._runtimes.clear()

        agent = agent_runner.create_agent_instance(agent_id, "deepseek:deepseek_v4_flash")
        runtime = _thread_runtime(agent_id, thread_id)
        snapshots: list[dict] = []
        done = asyncio.Event()

        async def poll_draft() -> None:
            while not done.is_set():
                if draft.exists():
                    snapshots.append(json.loads(draft.read_text(encoding="utf-8")))
                await asyncio.sleep(0.15)

        async def main() -> None:
            poll_task = asyncio.create_task(poll_draft())
            try:
                await asyncio.wait_for(
                    _run_turn(
                        agent_id,
                        agent,
                        {"messages": [("user", wrap_user_message(
                            "Say hello in one friendly sentence. No tools."
                        ))]},
                        f"msg-{uuid.uuid4().hex[:8]}",
                        thread_id=thread_id,
                        model="deepseek:deepseek_v4_flash",
                        runtime=runtime,
                    ),
                    timeout=120,
                )
            finally:
                done.set()
                poll_task.cancel()
                with asyncio.suppress(asyncio.CancelledError):
                    await poll_task

        asyncio.run(main())
    finally:
        agent_runner.registry = original_registry
        agent_runner.DEPLOY_ROOT = original_deploy_root
        agent_runner._agent_cache.clear()
        agent_runner._runtimes.clear()

    assert not draft.exists()
    assert snapshots, "runner turn should produce live stream_draft snapshots"
