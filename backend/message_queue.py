"""Persistent per-thread message queue (per agent workspace)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("minimal-backend.queue")

_STALE_DISPATCH_SECS = 30


@dataclass
class QueueEntry:
    id: str
    thread_id: str
    content: str
    kind: str
    created_at: str
    status: str = "pending"
    dispatched_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("dispatched_at", None)
        return d


class MessageQueue:
    def __init__(self, queue_file: Path) -> None:
        self._file = queue_file
        self._data: dict[str, list[QueueEntry]] = {}
        self._load()

    def _load(self) -> None:
        if not self._file.exists():
            self._data = {}
            return
        raw = json.loads(self._file.read_text(encoding="utf-8"))
        self._data = {tid: [QueueEntry(**e) for e in entries] for tid, entries in raw.items()}

    def _flush(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            tid: [e.to_dict() for e in entries]
            for tid, entries in self._data.items()
            if entries
        }
        self._file.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, thread_id: str, content: str, kind: str = "message", entry_id: str | None = None) -> QueueEntry:
        if not entry_id:
            prefix = "resume" if kind == "resume" else "msg"
            entry_id = f"{prefix}-{int(time.time() * 1000)}"
        entry = QueueEntry(
            id=entry_id,
            thread_id=thread_id,
            content=content,
            kind=kind,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self._data.setdefault(thread_id, []).append(entry)
        self._flush()
        return entry

    def list_pending(self, thread_id: str) -> list[QueueEntry]:
        return [e for e in self._data.get(thread_id, []) if e.status == "pending"]

    def get(self, entry_id: str) -> QueueEntry | None:
        for entries in self._data.values():
            for e in entries:
                if e.id == entry_id:
                    return e
        return None

    def peek_dispatchable(self, thread_id: str) -> QueueEntry | None:
        entries = self._data.get(thread_id, [])
        for e in entries:
            if e.status == "dispatched":
                if time.time() - e.dispatched_at < _STALE_DISPATCH_SECS:
                    return None
                e.status = "pending"
                e.dispatched_at = 0.0
                self._flush()
        for e in entries:
            if e.status == "pending":
                return e
        return None

    def mark_dispatched(self, entry_id: str) -> None:
        entry = self.get(entry_id)
        if entry:
            entry.status = "dispatched"
            entry.dispatched_at = time.time()
            self._flush()

    def consume_dispatched(self, thread_id: str) -> QueueEntry | None:
        entries = self._data.get(thread_id, [])
        for i, e in enumerate(entries):
            if e.status == "dispatched":
                entries.pop(i)
                self._flush()
                return e
        return None

    def clear_thread(self, thread_id: str) -> int:
        entries = self._data.pop(thread_id, [])
        if entries:
            self._flush()
        return len(entries)

    def reset_dispatched(self) -> None:
        changed = False
        for entries in self._data.values():
            for e in entries:
                if e.status == "dispatched":
                    e.status = "pending"
                    e.dispatched_at = 0.0
                    changed = True
        if changed:
            self._flush()

    def all_thread_ids_with_pending(self) -> list[str]:
        return [
            tid for tid, entries in self._data.items()
            if any(e.status == "pending" for e in entries)
        ]
