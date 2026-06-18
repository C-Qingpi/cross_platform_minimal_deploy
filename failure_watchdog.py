"""Capture failure/stop events with a rolling log tail for diagnosis."""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

TAIL_LINES = 300

FAILURE_EVENTS = frozenset({
    "task_error",
    "task_recursion_limit",
    "agent_stopped",
})

STOP_EVENTS = frozenset({
    "task_cancelled",
})

RUNTIME_FAILURE_KINDS = frozenset({
    "unhandled_exception",
    "asyncio_error",
    "signal",
})

_log = logging.getLogger("minimal.failure_watchdog")
_watchdog: FailureWatchdog | None = None


class RingBufferHandler(logging.Handler):
    def __init__(self, tail_lines: int = TAIL_LINES) -> None:
        super().__init__()
        self._lines: deque[str] = deque(maxlen=tail_lines)
        self.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        self._lines.append(self.format(record))

    def tail(self) -> list[str]:
        return list(self._lines)


class FailureWatchdog:
    def __init__(self, deploy_root: Path, *, service: str, tail_lines: int = TAIL_LINES) -> None:
        self.deploy_root = deploy_root.resolve()
        self.service = service
        self.tail_lines = tail_lines
        self.log_dir = self.deploy_root / ".run" / "logs"
        self.events_file = self.log_dir / "failure_events.jsonl"
        self.snapshots_dir = self.log_dir / "failure_snapshots"
        self._buffer = RingBufferHandler(tail_lines)

    def attach(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        logging.getLogger().addHandler(self._buffer)
        _log.info(
            "Failure watchdog enabled service=%s tail_lines=%d events=%s snapshots=%s",
            self.service,
            self.tail_lines,
            self.events_file,
            self.snapshots_dir,
        )

    def maybe_capture_from_event(self, record: dict[str, Any]) -> None:
        event = str(record.get("event", ""))
        if event == "summarizing_done" and record.get("error"):
            self.capture("summarizing_error", dict(record))
            return
        if event in FAILURE_EVENTS:
            self.capture(event, dict(record))
            return
        if event in STOP_EVENTS:
            self.capture(event, dict(record))

    def capture(self, kind: str, detail: dict[str, Any] | None = None) -> None:
        detail = detail or {}
        tail = self._buffer.tail()
        ts = datetime.now()
        entry = {
            "ts": ts.isoformat(),
            "service": self.service,
            "kind": kind,
            "pid": os.getpid(),
            "detail": detail,
            "log_tail_lines": len(tail),
            "log_tail": tail,
        }
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        stamp = ts.strftime("%Y%m%dT%H%M%S")
        agent = detail.get("agent_id", "unknown")
        thread = detail.get("thread", "")
        suffix = f"_{thread}" if thread else ""
        snapshot_name = f"{stamp}_{kind}_{agent}{suffix}.log"
        snapshot_path = self.snapshots_dir / snapshot_name
        header = (
            f"# failure snapshot kind={kind} service={self.service} "
            f"pid={os.getpid()} ts={ts.isoformat()}\n"
            f"# detail={json.dumps(detail, ensure_ascii=False)}\n"
            f"# log_tail_lines={len(tail)}\n"
            "---\n"
        )
        snapshot_path.write_text(header + "\n".join(tail) + "\n", encoding="utf-8")

        _log.warning(
            "Captured failure kind=%s agent=%s thread=%s snapshot=%s",
            kind,
            agent,
            thread or "-",
            snapshot_path.name,
        )


def init(deploy_root: Path, *, service: str = "agent", tail_lines: int = TAIL_LINES) -> FailureWatchdog:
    global _watchdog
    _watchdog = FailureWatchdog(deploy_root, service=service, tail_lines=tail_lines)
    _watchdog.attach()
    return _watchdog


def maybe_capture_from_event(record: dict[str, Any]) -> None:
    if _watchdog is not None:
        _watchdog.maybe_capture_from_event(record)


def capture(kind: str, detail: dict[str, Any] | None = None) -> None:
    if _watchdog is not None:
        _watchdog.capture(kind, detail)
