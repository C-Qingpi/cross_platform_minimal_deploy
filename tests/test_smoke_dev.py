"""Dev deploy smoke: SearchEnvironment + interrupt/resume resilience."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

DEPLOY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPLOY_DIR))
sys.path.insert(0, str(DEPLOY_DIR / "agent"))

SMOKE_WS = DEPLOY_DIR / "tests" / "_smoke_workspace"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ARION_DEPLOY_MODE", raising=False)
    cfg = DEPLOY_DIR / "deploy.config"
    if not cfg.is_file():
        shutil.copy(DEPLOY_DIR / "deploy.config.example", cfg)
    if SMOKE_WS.exists():
        shutil.rmtree(SMOKE_WS, ignore_errors=True)
    SMOKE_WS.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DEPLOY_ROOT", str(SMOKE_WS))
    yield
    shutil.rmtree(SMOKE_WS, ignore_errors=True)


def _import_agent_runner():
    import agent_events as events
    import agent_runner as ar

    events_path = SMOKE_WS / ".arion" / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events.init(events_path)
    ar.registry = ar.AgentRegistry(SMOKE_WS)
    ar._agent_cache.clear()
    ar._runtimes.clear()
    return ar


def _setup_registry(agent_id: str = "smoke") -> Path:
    import agent_registry

    reg = agent_registry.AgentRegistry(SMOKE_WS)
    reg.create_agent(agent_id, workspace=str(SMOKE_WS / "ws"), model="deepseek:deepseek_v4_flash")
    return SMOKE_WS / "ws"


class TestDevSearchMiddleware:
    def test_dev_enables_semantic_search_tool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pytest.importorskip("fastembed")
        monkeypatch.setenv("ARION_DEPLOY_MODE", "dev")
        ws = _setup_registry()
        ar = _import_agent_runner()

        middleware = ar._optional_middleware(ws)
        assert len(middleware) == 1
        assert middleware[0].tools[0].name == "semantic_search"

    def test_prod_enables_semantic_search_tool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pytest.importorskip("fastembed")
        monkeypatch.setenv("ARION_DEPLOY_MODE", "dev")
        ws = _setup_registry()
        ar = _import_agent_runner()

        middleware = ar._optional_middleware(ws)
        assert len(middleware) == 1
        assert middleware[0].tools[0].name == "semantic_search"


class TestInterruptResume:
    def test_cancel_mid_turn_then_resume_invoke(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARION_DEPLOY_MODE", "dev")
        _setup_registry()
        ar = _import_agent_runner()

        async def _run() -> None:
            aid = "smoke"
            tid = ar.default_thread_id(aid)
            model = "deepseek:deepseek_v4_flash"
            runtime = ar._thread_runtime(aid, tid)

            class _SlowAgent:
                def __init__(self) -> None:
                    self.calls: list[object | None] = []

                async def ainvoke(self, payload, config=None):
                    self.calls.append(payload)
                    if payload is None:
                        return {"messages": []}
                    await asyncio.sleep(30)
                    return {"messages": []}

            slow = _SlowAgent()
            turn = asyncio.create_task(
                ar._run_turn(
                    aid, slow, {"messages": [("user", "hold")]}, "msg-1",
                    thread_id=tid, model=model, runtime=runtime,
                )
            )
            await asyncio.sleep(0.3)
            runtime.cancel_event.set()
            await turn
            assert slow.calls[0] is not None

            await ar._run_turn(
                aid, slow, None, "msg-resume",
                thread_id=tid, model=model, runtime=runtime,
            )
            assert None in slow.calls

        asyncio.run(_run())

    def test_process_restart_checkpoint_continuity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        if not os.environ.get("DEEPSEEK_API_KEY", "").startswith("sk-"):
            from dotenv import load_dotenv
            load_dotenv(DEPLOY_DIR / ".env")
        if not os.environ.get("DEEPSEEK_API_KEY", "").startswith("sk-"):
            pytest.skip("DEEPSEEK_API_KEY required for live checkpoint smoke")

        monkeypatch.setenv("ARION_DEPLOY_MODE", "dev")
        ws = _setup_registry()
        ar = _import_agent_runner()
        from config import apply_provider_env, load_config, register_proxies
        from prompts import wrap_user_message

        apply_provider_env(load_config())
        register_proxies()

        async def _run() -> None:
            aid = "smoke"
            tid = ar.default_thread_id(aid)
            model = "deepseek:deepseek_v4_flash"
            cfg = {"configurable": {"thread_id": tid}}

            agent1 = ar.create_agent_instance(aid, model)
            await agent1.ainvoke(
                {"messages": [("user", wrap_user_message("Remember codeword NEBULA. Reply OK only."))]},
                config=cfg,
            )

            ckpt = ws / ".arion" / "agents" / aid / "checkpoints.sqlite"
            assert ckpt.is_file()

            ar._agent_cache.clear()
            agent2 = ar.create_agent_instance(aid, model)
            result = await agent2.ainvoke(
                {"messages": [("user", wrap_user_message("What codeword did I ask you to remember? One word only."))]},
                config=cfg,
            )
            ai = [m for m in result["messages"] if getattr(m, "type", "") == "ai"]
            assert ai
            assert "NEBULA" in ai[-1].content.upper()

        asyncio.run(_run())


class TestSemanticSearchLive:
    def test_semantic_search_finds_workspace_doc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pytest.importorskip("fastembed")
        monkeypatch.setenv("ARION_DEPLOY_MODE", "dev")
        ws = _setup_registry()
        doc = ws / "project_notes.md"
        doc.write_text(
            "The internal codename for the lunar relay project is Nebula Relay.\n",
            encoding="utf-8",
        )

        async def _run() -> None:
            ar = _import_agent_runner()
            middleware = ar._optional_middleware(ws)
            search_mw = middleware[0]
            search_mw.before_agent({})
            deadline = time.time() + 120
            while time.time() < deadline:
                st = search_mw.service.status()
                if st.initial_sync_done and st.indexed_files > 0:
                    break
                await asyncio.sleep(1)

            tool = search_mw.tools[0]
            out = tool.invoke({"query": "lunar relay codename Nebula"})
            search_mw.after_agent({})
            assert "project_notes.md" in out or "Nebula" in out

        asyncio.run(_run())
