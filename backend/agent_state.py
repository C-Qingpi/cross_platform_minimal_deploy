"""In-memory state machine driven by deploy-level events.jsonl."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("minimal-backend.state")


@dataclass
class ThreadState:
    thread_id: str
    status: str = "idle"
    finish_reason: str | None = None
    error: str | None = None
    active: bool = False
    active_message_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "thread_id": self.thread_id,
            "status": self.status,
            "active": self.active,
        }
        if self.finish_reason:
            data["finish_reason"] = self.finish_reason
        if self.error:
            data["error"] = self.error
        if self.active_message_id:
            data["active_message_id"] = self.active_message_id
        return data


@dataclass
class AgentStateView:
    agent_id: str
    status: str = "offline"
    model: str | None = None
    thread_models: dict[str, str] = field(default_factory=dict)
    threads: dict[str, ThreadState] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        threads_out = {}
        for tid, thread in sorted(self.threads.items()):
            d = thread.to_dict()
            d["model"] = self.thread_models.get(tid) or self.model
            threads_out[tid] = d
        active = sorted(tid for tid, t in self.threads.items() if t.active)
        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "model": self.model,
            "active_threads": active,
            "threads": threads_out,
        }


class AgentStateMachine:
    on_event: Callable[[dict], None] | None = None

    def __init__(self, events_file: Path) -> None:
        self._events_file = events_file
        self._file_pos = 0
        self._agents: dict[str, AgentStateView] = {}
        self._task: asyncio.Task | None = None

    def _agent(self, agent_id: str) -> AgentStateView:
        if agent_id not in self._agents:
            self._agents[agent_id] = AgentStateView(agent_id=agent_id)
        return self._agents[agent_id]

    def _thread(self, agent_id: str, thread_id: str) -> ThreadState:
        view = self._agent(agent_id)
        if thread_id not in view.threads:
            view.threads[thread_id] = ThreadState(thread_id=thread_id)
        return view.threads[thread_id]

    def get_agent_state(self, agent_id: str) -> dict[str, Any]:
        return self._agent(agent_id).to_dict()

    def set_model(self, agent_id: str, model: str, thread_id: str | None = None) -> None:
        view = self._agent(agent_id)
        if thread_id:
            view.thread_models[thread_id] = model
            self._thread(agent_id, thread_id)
        else:
            view.model = model

    def get_all_states(self) -> dict[str, dict[str, Any]]:
        return {aid: view.to_dict() for aid, view in self._agents.items()}

    def replay(self) -> None:
        if not self._events_file.exists():
            return
        text = self._events_file.read_text(encoding="utf-8")
        for line in text.strip().split("\n"):
            if line.strip():
                self._apply(json.loads(line), notify=False)
        self._file_pos = self._events_file.stat().st_size if self._events_file.exists() else 0

    def poll_new_events(self) -> None:
        if not self._events_file.exists():
            return
        size = self._events_file.stat().st_size
        if size < self._file_pos:
            self._file_pos = 0
            self._agents = {}
            self.replay()
            return
        if size == self._file_pos:
            return
        with open(self._events_file, "r", encoding="utf-8") as f:
            f.seek(self._file_pos)
            new_data = f.read()
        self._file_pos = size
        for line in new_data.strip().split("\n"):
            if line.strip():
                self._apply(json.loads(line), notify=True)

    def _apply(self, ev: dict, notify: bool = False) -> None:
        event_type = ev.get("event", "")
        agent_id = ev.get("agent_id", "default")
        view = self._agent(agent_id)

        if event_type == "agent_started":
            view.status = "online"
            view.model = ev.get("model")
        elif event_type == "agent_stopped":
            view.status = "offline"
            for thread in view.threads.values():
                thread.active = False
                thread.status = "idle"
        elif event_type == "task_started":
            thread_id = ev.get("thread", f"{agent_id}-main")
            thread = self._thread(agent_id, thread_id)
            model = ev.get("model")
            if model:
                view.thread_models[thread_id] = model
                view.model = model
            thread.active = True
            thread.status = "processing"
            thread.finish_reason = None
            thread.error = None
            thread.active_message_id = ev.get("msg_id")
        elif event_type == "task_completed":
            thread_id = ev.get("thread", f"{agent_id}-main")
            thread = self._thread(agent_id, thread_id)
            thread.active = False
            thread.status = "idle"
            thread.finish_reason = "completed"
        elif event_type == "task_cancelled":
            thread_id = ev.get("thread", f"{agent_id}-main")
            thread = self._thread(agent_id, thread_id)
            thread.active = False
            thread.status = "idle"
            thread.finish_reason = "cancelled"
        elif event_type == "task_error":
            thread_id = ev.get("thread", f"{agent_id}-main")
            thread = self._thread(agent_id, thread_id)
            thread.active = False
            thread.status = "idle"
            thread.finish_reason = "error"
            thread.error = ev.get("error")
        elif event_type == "task_recursion_limit":
            thread_id = ev.get("thread", f"{agent_id}-main")
            thread = self._thread(agent_id, thread_id)
            thread.active = False
            thread.status = "idle"
            thread.finish_reason = "recursion_limit"
        elif event_type == "summarizing":
            thread_id = ev.get("thread", f"{agent_id}-main")
            thread = self._thread(agent_id, thread_id)
            thread.status = "summarizing"
        elif event_type == "summarizing_done":
            thread_id = ev.get("thread", f"{agent_id}-main")
            thread = self._thread(agent_id, thread_id)
            if thread.active:
                thread.status = "processing"
            elif thread.status == "summarizing":
                thread.status = "idle"
        elif event_type == "model_switched":
            model = ev.get("model")
            thread_id = ev.get("thread")
            if thread_id:
                view.thread_models[thread_id] = model
                self._thread(agent_id, thread_id)
            view.model = model

        if notify and self.on_event:
            self.on_event(ev)

    async def start(self, interval: float = 0.25) -> None:
        self.replay()
        self._task = asyncio.create_task(self._loop(interval))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self, interval: float) -> None:
        while True:
            try:
                self.poll_new_events()
            except asyncio.CancelledError:
                break
            await asyncio.sleep(interval)
