"""Tests for turn_models from events.jsonl task_started records."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPLOY_DIR / "backend"))

from turn_models import active_turn_model, load_task_models, slice_turn_models_for_window


def test_load_task_models_from_events():
    with tempfile.TemporaryDirectory() as td:
        events = Path(td) / "events.jsonl"
        rows = [
            {"event": "task_started", "agent_id": "DESKTOP", "thread": "main", "model": "deepseek:deepseek_v4_flash", "msg_id": "msg-1"},
            {"event": "task_completed", "agent_id": "DESKTOP", "thread": "main", "model": "deepseek:deepseek_v4_flash", "msg_id": "msg-1"},
            {"event": "task_started", "agent_id": "DESKTOP", "thread": "main", "model": "deepseek:deepseek_v4_pro", "msg_id": "msg-2"},
        ]
        events.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

        turn_models, task_models = load_task_models(events, "DESKTOP", "main")
        assert turn_models == ["deepseek:deepseek_v4_flash"]
        assert task_models == {"msg-1": "deepseek:deepseek_v4_flash", "msg-2": "deepseek:deepseek_v4_pro"}
        assert active_turn_model(task_models, "msg-2") == "deepseek:deepseek_v4_pro"
        assert active_turn_model(task_models, "msg-missing") is None


def test_cancelled_task_started_excluded_from_turn_models():
    with tempfile.TemporaryDirectory() as td:
        events = Path(td) / "events.jsonl"
        rows = [
            {"event": "task_started", "agent_id": "DESKTOP", "thread": "t1", "model": "deepseek:deepseek_v4_pro", "msg_id": "msg-1"},
            {"event": "task_cancelled", "agent_id": "DESKTOP", "thread": "t1", "model": "deepseek:deepseek_v4_pro", "msg_id": "msg-1"},
            {"event": "task_started", "agent_id": "DESKTOP", "thread": "t1", "model": "deepseek:deepseek_v4_pro", "msg_id": "msg-2"},
            {"event": "task_completed", "agent_id": "DESKTOP", "thread": "t1", "model": "deepseek:deepseek_v4_pro", "msg_id": "msg-2"},
            {"event": "task_started", "agent_id": "DESKTOP", "thread": "t1", "model": "deepseek:deepseek_v4_flash", "msg_id": "msg-3"},
            {"event": "task_completed", "agent_id": "DESKTOP", "thread": "t1", "model": "deepseek:deepseek_v4_flash", "msg_id": "msg-3"},
        ]
        events.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

        turn_models, task_models = load_task_models(events, "DESKTOP", "t1")
        assert turn_models == ["deepseek:deepseek_v4_pro", "deepseek:deepseek_v4_flash"]
        assert task_models["msg-1"] == "deepseek:deepseek_v4_pro"
        assert task_models["msg-3"] == "deepseek:deepseek_v4_flash"


def test_slice_turn_models_for_paginated_window():
    """Global turn_models must align to the visible message page, not whole thread."""
    messages = []
    turn_models = []
    for i in range(30):
        messages.append({"type": "human", "content": f"h{i}"})
        messages.append({"type": "ai", "content": f"a{i}"})
        turn_models.append("deepseek:deepseek_v4_flash")
    messages.extend([{"type": "human", "content": "latest"}, {"type": "ai", "content": "done"}])
    turn_models.append("deepseek:deepseek_v4_pro")

    total = len(messages)
    start = total - 500 if total > 500 else 0
    start = max(0, total - 2)
    sliced = slice_turn_models_for_window(messages, start, total, turn_models)
    assert sliced == ["deepseek:deepseek_v4_pro"]
