"""Append-only event log for agent lifecycle (multi-agent)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("minimal.events")

EVENTS_FILE: Path = Path()

# toast=True events are surfaced by the frontend toast system via /api/events
TOAST_DURATIONS_MS: dict[str, int] = {
    "summarizing": 6000,
    "summarizing_done": 4000,
    "model_switched": 4000,
    "task_error": 6000,
    "task_recursion_limit": 6000,
    "task_cancelled": 3500,
    "agent_stopped": 4000,
}

EVENT_LOG_LEVELS: dict[str, int] = {
    "task_error": logging.ERROR,
    "task_recursion_limit": logging.ERROR,
    "task_cancelled": logging.WARNING,
    "agent_stopped": logging.WARNING,
}


def init(events_path: Path) -> None:
    global EVENTS_FILE
    EVENTS_FILE = events_path
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _toast_message(event: str, fields: dict[str, Any]) -> str | None:
    agent_id = fields.get("agent_id", "")
    thread = fields.get("thread", "")
    model = fields.get("model", "")
    error = fields.get("error", "")

    if event == "summarizing":
        suffix = f" ({thread})" if thread else ""
        return f"Summarizing conversation history…{suffix}"
    if event == "summarizing_done":
        if fields.get("prefetched"):
            return None
        suffix = f" ({thread})" if thread else ""
        return f"Summarization complete{suffix}"
    if event == "model_switched":
        suffix = f" on {thread}" if thread else ""
        return f"Model switched to {model}{suffix}"
    if event == "task_started":
        return None
    if event == "task_completed":
        return None
    if event == "task_cancelled":
        suffix = f" ({thread})" if thread else ""
        return f"Agent stopped{suffix}"
    if event == "task_error":
        return f"Task error: {error}"
    if event == "task_recursion_limit":
        return "Task hit recursion limit"
    if event == "agent_started":
        return None
    if event == "agent_stopped":
        return f"Agent runner offline ({agent_id})"
    if event == "turn_heartbeat":
        return None
    return None


def _emit(event: str, **fields: object) -> None:
    record: dict[str, object] = {
        "event": event,
        "ts": datetime.now().isoformat(),
    }
    record.update(fields)

    toast = _toast_message(event, record)
    if toast:
        record["toast"] = toast
        record["toast_ms"] = TOAST_DURATIONS_MS.get(event, 3500)

    level = EVENT_LOG_LEVELS.get(event, logging.INFO)
    log_line = toast or json.dumps(record, ensure_ascii=False)
    logger.log(level, "event %s: %s", event, log_line)

    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    from failure_watchdog import maybe_capture_from_event

    maybe_capture_from_event(record)


def read_events(
    *,
    after_index: int = 0,
    limit: int = 100,
    events_path: Path | None = None,
) -> dict[str, Any]:
    path = events_path or EVENTS_FILE
    if not path or not path.exists():
        return {"events": [], "total": 0, "next_index": 0}
    lines = path.read_text(encoding="utf-8").splitlines()
    total = len(lines)
    out: list[dict[str, Any]] = []
    for index in range(after_index, total):
        line = lines[index].strip()
        if not line:
            continue
        ev = json.loads(line)
        ev["index"] = index
        out.append(ev)
    if len(out) > limit:
        out = out[-limit:]
    return {"events": out, "total": total, "next_index": total}


def agent_started(agent_id: str, model: str) -> None:
    _emit("agent_started", agent_id=agent_id, model=model)


def agent_stopped(agent_id: str) -> None:
    _emit("agent_stopped", agent_id=agent_id)


def task_started(agent_id: str, thread: str, model: str, msg_id: str | None = None) -> None:
    payload: dict[str, object] = {"agent_id": agent_id, "thread": thread, "model": model}
    if msg_id:
        payload["msg_id"] = msg_id
    _emit("task_started", **payload)


def task_completed(agent_id: str, thread: str, model: str, msg_id: str | None = None) -> None:
    payload: dict[str, object] = {"agent_id": agent_id, "thread": thread, "model": model}
    if msg_id:
        payload["msg_id"] = msg_id
    _emit("task_completed", **payload)


def task_cancelled(agent_id: str, thread: str, model: str, msg_id: str | None = None) -> None:
    payload: dict[str, object] = {"agent_id": agent_id, "thread": thread, "model": model}
    if msg_id:
        payload["msg_id"] = msg_id
    _emit("task_cancelled", **payload)


def task_error(agent_id: str, thread: str, model: str, error: str, msg_id: str | None = None) -> None:
    payload: dict[str, object] = {
        "agent_id": agent_id, "thread": thread, "model": model, "error": error,
    }
    if msg_id:
        payload["msg_id"] = msg_id
    _emit("task_error", **payload)


def task_recursion_limit(agent_id: str, thread: str, model: str, msg_id: str | None = None) -> None:
    payload: dict[str, object] = {"agent_id": agent_id, "thread": thread, "model": model}
    if msg_id:
        payload["msg_id"] = msg_id
    _emit("task_recursion_limit", **payload)


def summarizing(agent_id: str, thread: str | None = None) -> None:
    payload: dict[str, object] = {"agent_id": agent_id}
    if thread:
        payload["thread"] = thread
    _emit("summarizing", **payload)


def summarizing_done(
    agent_id: str,
    thread: str | None = None,
    error: str | None = None,
    *,
    prefetched: bool = False,
) -> None:
    payload: dict[str, object] = {"agent_id": agent_id, "prefetched": prefetched}
    if thread:
        payload["thread"] = thread
    if error:
        payload["error"] = error
    _emit("summarizing_done", **payload)


def model_switched(agent_id: str, model: str, thread: str | None = None) -> None:
    payload: dict[str, object] = {"agent_id": agent_id, "model": model}
    if thread:
        payload["thread"] = thread
    _emit("model_switched", **payload)


def turn_heartbeat(agent_id: str, thread: str, model: str, seconds: float) -> None:
    _emit(
        "turn_heartbeat",
        agent_id=agent_id,
        thread=thread,
        model=model,
        seconds=round(seconds, 1),
    )
