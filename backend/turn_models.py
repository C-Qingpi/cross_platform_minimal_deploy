"""Actual per-turn models from task_started events (independent of UI config)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_task_models(
    events_path: Path,
    agent_id: str,
    thread_id: str,
) -> tuple[list[str], dict[str, str]]:
    """Return completed turn models and msg_id -> model from task_started events."""
    started: dict[str, str] = {}
    completed_order: list[str] = []
    task_models: dict[str, str] = {}
    if not events_path.exists():
        return [], task_models

    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        ev: dict[str, Any] = json.loads(line)
        if ev.get("agent_id") != agent_id:
            continue
        if ev.get("thread") != thread_id:
            continue
        msg_id = ev.get("msg_id")
        if not msg_id:
            continue
        mid = str(msg_id)
        event_type = ev.get("event")
        model = ev.get("model")
        if event_type == "task_started" and model:
            started[mid] = model
            task_models[mid] = model
        elif event_type == "task_completed":
            completed_order.append(mid)

    turn_models = [started[mid] for mid in completed_order if mid in started]
    return turn_models, task_models


def _count_completed_rounds(roles: list[tuple[str, int]], start: int, end: int) -> int:
    """Human turns with an AI reply in [start, end).

    `roles` is a list of (role, msg_index) tuples.
    """
    count = 0
    i = 0
    n = len(roles)
    # Find the first message at or after `start`
    while i < n and roles[i][1] < start:
        i += 1
    while i < n and roles[i][1] < end:
        if roles[i][0] == "human":
            for j in range(i + 1, n):
                if roles[j][1] >= end:
                    break
                if roles[j][0] == "ai":
                    count += 1
                    break
                if roles[j][0] == "human":
                    break
        i += 1
    return count


def slice_turn_models_for_window(
    roles: list[tuple[str, int]],
    start_index: int,
    end_index: int,
    turn_models: list[str],
) -> list[str]:
    """Slice global completed models to match the paginated message window.

    `roles` is a lightweight list of (role, msg_index) tuples — not full messages.
    """
    completed_before = _count_completed_rounds(roles, 0, start_index)
    completed_in_window = _count_completed_rounds(roles, start_index, end_index)
    slice_end = completed_before + completed_in_window
    return turn_models[completed_before:slice_end]


def active_turn_model(
    task_models: dict[str, str],
    active_message_id: str | None,
) -> str | None:
    if not active_message_id:
        return None
    return task_models.get(active_message_id)
