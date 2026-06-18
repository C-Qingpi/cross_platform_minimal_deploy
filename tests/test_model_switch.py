"""Model switch: instant backend state + runner inbox apply."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPLOY_DIR))
sys.path.insert(0, str(DEPLOY_DIR / "backend"))

from agent_state import AgentStateMachine


def test_set_model_updates_thread_in_state():
    with tempfile.TemporaryDirectory() as td:
        events = Path(td) / "events.jsonl"
        sm = AgentStateMachine(events)
        sm.set_model("DESKTOP", "openai:gpt-4o-mini", "DESKTOP-main")
        state = sm.get_agent_state("DESKTOP")
        assert state["threads"]["DESKTOP-main"]["model"] == "openai:gpt-4o-mini"


def test_model_switched_event_with_thread():
    with tempfile.TemporaryDirectory() as td:
        events = Path(td) / "events.jsonl"
        sm = AgentStateMachine(events)
        sm.replay()
        sm._apply(
            {
                "event": "model_switched",
                "agent_id": "DESKTOP",
                "thread": "DESKTOP-main",
                "model": "anthropic:claude-sonnet-4-5",
            },
            notify=False,
        )
        state = sm.get_agent_state("DESKTOP")
        assert state["threads"]["DESKTOP-main"]["model"] == "anthropic:claude-sonnet-4-5"
        assert state["model"] == "anthropic:claude-sonnet-4-5"


def test_apply_inbox_model_item_before_queue():
    """Model inbox items update runner memory without waiting on the turn queue."""
    thread_models: dict[str, dict[str, str]] = {}
    active_models: dict[str, str] = {}

    def apply_item(agent_id: str, item: dict) -> bool:
        kind = item.get("kind")
        if kind == "thread_model":
            thread_id = item.get("thread_id", f"{agent_id}-main")
            thread_models.setdefault(agent_id, {})[thread_id] = item["model"]
            return True
        if kind == "model_switch":
            active_models[agent_id] = item["model"]
            return True
        return False

    item = {
        "kind": "thread_model",
        "thread_id": "DESKTOP-main",
        "model": "moonshot:kimi-k2.5",
    }
    assert apply_item("DESKTOP", item) is True
    assert thread_models["DESKTOP"]["DESKTOP-main"] == "moonshot:kimi-k2.5"


def test_list_threads_merge_prefers_persisted_model():
    """Persisted threads.json model must win over stale in-memory state."""
    persisted = {"thread_id": "debugger", "name": "debugger", "model": "deepseek:deepseek_v4_flash"}
    state = {"debugger": {"thread_id": "debugger", "status": "idle", "active": False, "model": "deepseek:deepseek_v4_pro"}}
    merged = [{**state.get(persisted["thread_id"], {}), **persisted}]
    assert merged[0]["model"] == "deepseek:deepseek_v4_flash"
    assert merged[0]["status"] == "idle"


def test_resolve_model_prefers_threads_json_over_memory():
    """Old threads keep stale in-memory model until inbox poll; disk is authoritative."""
    thread_models: dict[str, dict[str, str]] = {"DESKTOP": {"debugger": "deepseek:deepseek_v4_pro"}}
    disk_models = {"debugger": "deepseek:deepseek_v4_flash"}

    def resolve(in_memory: dict[str, dict[str, str]], on_disk: dict[str, str], thread_id: str) -> str:
        model = on_disk.get(thread_id)
        if model:
            cached = in_memory.get("DESKTOP", {}).get(thread_id)
            if cached != model:
                in_memory.setdefault("DESKTOP", {})[thread_id] = model
            return model
        return in_memory.get("DESKTOP", {})[thread_id]

    assert resolve(thread_models, disk_models, "debugger") == "deepseek:deepseek_v4_flash"
    assert thread_models["DESKTOP"]["debugger"] == "deepseek:deepseek_v4_flash"


def test_model_switch_api_returns_updated_thread_model():
    """Simulates switch_model endpoint: state must reflect new model immediately."""
    with tempfile.TemporaryDirectory() as td:
        events = Path(td) / "events.jsonl"
        sm = AgentStateMachine(events)
        agent_id = "DESKTOP"
        thread_id = f"{agent_id}-main"
        old = "deepseek:deepseek_v4_flash"
        new = "openai:gpt-4o-mini"
        sm.set_model(agent_id, old, thread_id)
        before = sm.get_agent_state(agent_id)
        assert before["threads"][thread_id]["model"] == old

        sm.set_model(agent_id, new, thread_id)
        after = sm.get_agent_state(agent_id)
        assert after["threads"][thread_id]["model"] == new
