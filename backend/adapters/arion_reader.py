"""Read ArionAgent workspace state from disk (no arion_agent import)."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MOUNT_PREFIX = "imported_directories"


class ArionReader:
    def __init__(
        self,
        workspace_dir: str,
        agent_id: str,
        mounts: dict[str, str] | None = None,
    ) -> None:
        self.workspace = Path(workspace_dir)
        self.agent_id = agent_id
        self.identity_dir = self.workspace / ".arion" / "agents" / agent_id
        self.inbox_dir = self.workspace / ".arion" / "inbox"
        self._mount_paths = {n: Path(p).resolve() for n, p in (mounts or {}).items()}

    @property
    def checkpoint_path(self) -> Path:
        return self.identity_dir / "checkpoints.sqlite"

    def _message_log_db_path(self) -> Path:
        return self.identity_dir / "message_log.db"

    def _ensure_message_log_table(self, db: sqlite3.Connection) -> None:
        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                thread_id   TEXT NOT NULL,
                msg_index   INTEGER NOT NULL,
                msg_key     TEXT NOT NULL,
                role        TEXT NOT NULL,
                type        TEXT NOT NULL DEFAULT 'message',
                content     TEXT NOT NULL,
                tool_calls  TEXT,
                name        TEXT,
                msg_id      TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(thread_id, msg_key)
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_msg_thread
            ON messages(thread_id, msg_index)
        """)
        db.commit()

    def _sync_to_message_log(self, thread_id: str) -> int:
        """Sync latest checkpoint messages into the persistent message log.

        Returns the number of new messages added.
        """
        msgs = self._latest_checkpoint_messages(thread_id)
        if not msgs:
            return 0

        db_path = self._message_log_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(db_path))
        try:
            self._ensure_message_log_table(db)

            existing = {
                row[0]
                for row in db.execute(
                    "SELECT msg_key FROM messages WHERE thread_id = ?", (thread_id,)
                )
            }
            max_idx = db.execute(
                "SELECT COALESCE(MAX(msg_index), -1) FROM messages WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()[0]

            new_rows: list[tuple] = []
            for msg in msgs:
                key = self._message_key(msg)
                if key in existing:
                    continue
                max_idx += 1
                existing.add(key)
                role = msg.get("type", "unknown")
                content = json.dumps(msg.get("content", ""), ensure_ascii=False)
                tool_calls = (
                    json.dumps(msg.get("tool_calls"), ensure_ascii=False)
                    if msg.get("tool_calls")
                    else None
                )
                new_rows.append((
                    thread_id, max_idx, key, role,
                    msg.get("type", "message"),
                    content, tool_calls,
                    msg.get("name"), msg.get("id"),
                ))

            if new_rows:
                db.executemany(
                    "INSERT OR IGNORE INTO messages "
                    "(thread_id, msg_index, msg_key, role, type, content, tool_calls, name, msg_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    new_rows,
                )
                db.commit()
            return len(new_rows)
        finally:
            db.close()

    def _get_messages_from_log(self, thread_id: str) -> list[dict[str, Any]]:
        """Return all messages for a thread from the persistent message log."""
        return self._get_messages_from_log_window(thread_id)

    def _get_messages_from_log_window(
        self,
        thread_id: str,
        limit: int = 0,
        before_index: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return a window of messages from the persistent message log.

        When limit=0 and before_index=None, returns all messages (legacy).
        Uses SQL LIMIT/OFFSET — never loads the full table into Python
        when paginated.
        """
        db_path = self._message_log_db_path()
        if not db_path.exists():
            return []
        db = sqlite3.connect(str(db_path))
        try:
            self._ensure_message_log_table(db)
            if before_index is not None:
                if limit:
                    rows = db.execute(
                        "SELECT role, type, content, tool_calls, name, msg_id "
                        "FROM messages WHERE thread_id = ? AND msg_index < ? "
                        "ORDER BY msg_index DESC LIMIT ?",
                        (thread_id, before_index, limit),
                    ).fetchall()
                    rows.reverse()
                else:
                    rows = db.execute(
                        "SELECT role, type, content, tool_calls, name, msg_id "
                        "FROM messages WHERE thread_id = ? AND msg_index < ? "
                        "ORDER BY msg_index",
                        (thread_id, before_index),
                    ).fetchall()
            elif limit:
                rows = db.execute(
                    "SELECT role, type, content, tool_calls, name, msg_id "
                    "FROM messages WHERE thread_id = ? "
                    "ORDER BY msg_index DESC LIMIT ?",
                    (thread_id, limit),
                ).fetchall()
                rows.reverse()
            else:
                rows = db.execute(
                    "SELECT role, type, content, tool_calls, name, msg_id "
                    "FROM messages WHERE thread_id = ? ORDER BY msg_index",
                    (thread_id,),
                ).fetchall()
        finally:
            db.close()
        return self._rows_to_messages(rows)

    @staticmethod
    def _rows_to_messages(rows: list[tuple]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for role, mtype, content_str, tool_calls_str, name, msg_id in rows:
            msg: dict[str, Any] = {
                "type": role,
                "content": json.loads(content_str) if content_str[0] in '"[{' else content_str,
            }
            if msg_id:
                msg["id"] = msg_id
            if name:
                msg["name"] = name
            if tool_calls_str:
                try:
                    msg["tool_calls"] = json.loads(tool_calls_str)
                except json.JSONDecodeError:
                    pass
            messages.append(msg)
        return messages

    def _count_messages_in_log(self, thread_id: str) -> int:
        """Return the total number of messages for a thread."""
        db_path = self._message_log_db_path()
        if not db_path.exists():
            return 0
        db = sqlite3.connect(str(db_path))
        try:
            self._ensure_message_log_table(db)
            return db.execute(
                "SELECT COUNT(*) FROM messages WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()[0]
        finally:
            db.close()

    def _get_message_roles(
        self, thread_id: str, before_index: int | None = None,
    ) -> list[tuple[str, int]]:
        """Return lightweight (role, msg_index) pairs for turn counting.

        Reads only two columns — even for 30K messages this is ~300KB,
        vs multi-MB for full message content.
        """
        db_path = self._message_log_db_path()
        if not db_path.exists():
            return []
        db = sqlite3.connect(str(db_path))
        try:
            self._ensure_message_log_table(db)
            if before_index is not None:
                rows = db.execute(
                    "SELECT role, msg_index FROM messages "
                    "WHERE thread_id = ? AND msg_index < ? ORDER BY msg_index",
                    (thread_id, before_index),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT role, msg_index FROM messages "
                    "WHERE thread_id = ? ORDER BY msg_index",
                    (thread_id,),
                ).fetchall()
            return [(r, i) for r, i in rows]
        finally:
            db.close()

    def _bootstrap_message_log(self, thread_id: str) -> int:
        """Bootstrap: reconstruct full history from all checkpoints.

        Reads every checkpoint snapshot for the thread, deduplicates across
        them, and writes the union into message_log.db.

        Runs on every request but skips quickly once message_log.db has
        caught up with the checkpoint union.
        """
        from_checkpoints = self._reconstruct_from_checkpoints(thread_id)
        if not from_checkpoints:
            return 0

        db_path = self._message_log_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(db_path))
        try:
            self._ensure_message_log_table(db)

            existing_count = db.execute(
                "SELECT COUNT(*) FROM messages WHERE thread_id = ?", (thread_id,)
            ).fetchone()[0]
            if existing_count >= len(from_checkpoints):
                return 0  # already complete

            # Re-bootstrap: clear stale partial entries, rebuild from checkpoints.
            db.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))

            rows: list[tuple] = []
            for idx, msg in enumerate(from_checkpoints):
                key = self._message_key(msg)
                role = msg.get("type", "unknown")
                content = json.dumps(msg.get("content", ""), ensure_ascii=False)
                tool_calls = (
                    json.dumps(msg.get("tool_calls"), ensure_ascii=False)
                    if msg.get("tool_calls")
                    else None
                )
                rows.append((
                    thread_id, idx, key, role,
                    msg.get("type", "message"),
                    content, tool_calls,
                    msg.get("name"), msg.get("id"),
                ))

            if rows:
                db.executemany(
                    "INSERT INTO messages "
                    "(thread_id, msg_index, msg_key, role, type, content, tool_calls, name, msg_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
                db.commit()
            return len(rows)
        finally:
            db.close()

    def _stream_draft_path(self, thread_id: str) -> Path:
        return self.identity_dir / "stream_draft" / f"{thread_id}.json"

    def get_stream_draft(self, thread_id: str) -> dict[str, Any] | None:
        path = self._stream_draft_path(thread_id)
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8-sig").strip()
        if not text:
            return None
        return json.loads(text)

    def _message_key(self, msg: dict[str, Any]) -> str:
        mid = msg.get("id")
        if mid:
            return f"id:{mid}"
        content = msg.get("content")
        body = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, sort_keys=True)
        return f"{msg.get('type')}:{len(body)}:{body[:200]}"

    def _latest_checkpoint_messages(self, thread_id: str) -> list[dict[str, Any]]:
        if not self.checkpoint_path.exists():
            return []
        from langgraph.checkpoint.sqlite import SqliteSaver

        conn = sqlite3.connect(str(self.checkpoint_path))
        saver = SqliteSaver(conn)
        cp_tuple = saver.get_tuple({"configurable": {"thread_id": thread_id}})
        conn.close()
        if not cp_tuple:
            return []
        raw_messages = cp_tuple.checkpoint.get("channel_values", {}).get("messages", [])
        return [_serialize_message(m) for m in raw_messages]

    def _reconstruct_from_checkpoints(self, thread_id: str) -> list[dict[str, Any]]:
        """Read all checkpoint snapshots and union their messages into full history.

        Each checkpoint is a sliding window.  By iterating every snapshot
        in reverse time order (newest first) and deduplicating, we
        reconstruct the complete message history for a thread.
        """
        from langgraph.checkpoint.sqlite import SqliteSaver

        conn = sqlite3.connect(str(self.checkpoint_path))
        saver = SqliteSaver(conn)
        checkpoints = list(saver.list({"configurable": {"thread_id": thread_id}}))
        conn.close()
        if not checkpoints:
            return []

        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for cp_tuple in reversed(checkpoints):
            raw_messages = cp_tuple.checkpoint.get("channel_values", {}).get("messages", [])
            for msg in raw_messages:
                serialized = _serialize_message(msg)
                key = self._message_key(serialized)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(serialized)
        return merged

    def get_all_messages(self, thread_id: str) -> list[dict[str, Any]]:
        # Bootstrap from checkpoint snapshots if needed,
        # sync latest checkpoint messages, then read from message_log.db.
        self._bootstrap_message_log(thread_id)
        self._sync_to_message_log(thread_id)
        from_log = self._get_messages_from_log(thread_id)
        if from_log:
            return from_log
        return self._latest_checkpoint_messages(thread_id)

    def get_messages_page(
        self,
        thread_id: str,
        *,
        limit: int = 500,
        before_index: int | None = None,
    ) -> dict[str, Any]:
        # 1. Bootstrap / sync (idempotent)
        self._bootstrap_message_log(thread_id)
        self._sync_to_message_log(thread_id)

        # 2. Count total from SQL (O(1), not O(n))
        total = self._count_messages_in_log(thread_id)

        # 3. Compute window
        if before_index is None:
            start = max(0, total - limit)
            end = total
        else:
            end = max(0, min(before_index, total))
            start = max(0, end - limit)

        # 4. Load only the window from SQL (never the full list)
        window_limit = end - start
        window_messages = self._get_messages_from_log_window(
            thread_id, limit=window_limit, before_index=end,
        ) if window_limit > 0 else []

        # 5. Lightweight role list for turn_models slicing (two columns only)
        roles = self._get_message_roles(thread_id)

        return {
            "messages": window_messages,
            "total": total,
            "start_index": start,
            "end_index": end,
            "has_older": start > 0,
            "_roles": roles,  # internal — pop before sending to client
        }

    def get_messages(self, thread_id: str, limit: int = 200) -> list[dict[str, Any]]:
        page = self.get_messages_page(thread_id, limit=limit)
        return page["messages"]

    def get_summary(self, thread_id: str) -> str:
        if not self.checkpoint_path.exists():
            return ""
        from langgraph.checkpoint.sqlite import SqliteSaver

        conn = sqlite3.connect(str(self.checkpoint_path))
        saver = SqliteSaver(conn)
        cp_tuple = saver.get_tuple({"configurable": {"thread_id": thread_id}})
        conn.close()
        if not cp_tuple:
            return ""
        return cp_tuple.checkpoint.get("channel_values", {}).get("summary", "")

    @property
    def _threads_file(self) -> Path:
        return self.workspace / ".arion" / "threads.json"

    def _load_threads_meta(self) -> dict[str, Any]:
        if self._threads_file.exists():
            return json.loads(self._threads_file.read_text(encoding="utf-8-sig"))
        return {}

    def _save_threads_meta(self, meta: dict[str, Any]) -> None:
        self._threads_file.parent.mkdir(parents=True, exist_ok=True)
        self._threads_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def list_threads(self, default_thread: str) -> list[dict[str, Any]]:
        meta = self._load_threads_meta()
        checkpoint_threads: set[str] = set()
        if self.checkpoint_path.exists():
            conn = sqlite3.connect(str(self.checkpoint_path))
            rows = conn.execute("SELECT DISTINCT thread_id FROM checkpoints").fetchall()
            conn.close()
            checkpoint_threads = {r[0] for r in rows}

        all_ids = checkpoint_threads | set(meta.keys()) | {default_thread}
        threads = []
        for tid in all_ids:
            info = meta.get(tid, {})
            row = {
                "thread_id": tid,
                "name": info.get("name", "Main" if tid == default_thread else tid),
                "created_at": info.get("created_at", ""),
                "has_checkpoint": tid in checkpoint_threads,
                "wrapping_enabled": info.get("wrapping_enabled", True),
            }
            if info.get("model"):
                row["model"] = info["model"]
            threads.append(row)
        main = [t for t in threads if t["thread_id"] == default_thread]
        rest = [t for t in threads if t["thread_id"] != default_thread]
        rest.sort(key=lambda t: meta.get(t["thread_id"], {}).get("created_at", ""), reverse=True)
        return main + rest

    def create_thread(self, thread_id: str, name: str | None = None) -> dict[str, str]:
        meta = self._load_threads_meta()
        if thread_id in meta:
            return {"status": "exists", "thread_id": thread_id}
        meta[thread_id] = {
            "name": name or thread_id,
            "created_at": datetime.now().isoformat(),
        }
        self._save_threads_meta(meta)
        return {"status": "created", "thread_id": thread_id}

    def branch_thread(self, source_id: str) -> dict[str, str]:
        """Create a fresh thread branched from source_id. Auto-generates name with suffix.

        Branches get ids like 'source-01', 'source-02' etc. The display name includes
        a suffix so branches are visually distinct in the sidebar.
        """
        meta = self._load_threads_meta()
        source = meta.get(source_id, {})
        source_name = source.get("name", source_id)

        # Find the next available suffix for this source thread
        existing = set(meta.keys())
        suffix = 1
        while f"{source_id}-{suffix:02d}" in existing:
            suffix += 1
        new_id = f"{source_id}-{suffix:02d}"
        new_name = f"{source_name} ({suffix:02d})"

        meta[new_id] = {
            "name": new_name,
            "created_at": datetime.now().isoformat(),
            "branched_from": source_id,
            "wrapping_enabled": source.get("wrapping_enabled", True),
            "model": source.get("model"),
        }
        self._save_threads_meta(meta)
        return {"status": "created", "thread_id": new_id, "name": new_name}

    def rename_thread(self, thread_id: str, name: str) -> dict[str, str]:
        """Change the display name of a thread. Thread_id stays the same."""
        if not name or not name.strip():
            return {"error": "name cannot be empty"}
        meta = self._load_threads_meta()
        meta.setdefault(thread_id, {})
        meta[thread_id]["name"] = name.strip()
        self._save_threads_meta(meta)
        return {"status": "renamed", "thread_id": thread_id, "name": name.strip()}

    def delete_thread(self, thread_id: str, default_thread: str) -> dict[str, str]:
        if thread_id == default_thread:
            return {"error": "cannot delete main thread"}
        meta = self._load_threads_meta()
        meta.pop(thread_id, None)
        self._save_threads_meta(meta)
        if self.checkpoint_path.exists():
            conn = sqlite3.connect(str(self.checkpoint_path))
            conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
            conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
            conn.commit()
            conn.close()
        # Delete message-log entries so old messages don't reappear.
        msg_log = self._message_log_db_path()
        if msg_log.exists():
            db = sqlite3.connect(str(msg_log))
            db.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
            db.commit()
            db.close()
        # Delete stream-draft so stale drafts don't show for a recreated thread.
        stream_draft = self._stream_draft_path(thread_id)
        if stream_draft.exists():
            stream_draft.unlink()
        return {"status": "deleted", "thread_id": thread_id}

    def get_persisted_thread_models(self) -> dict[str, dict[str, str]]:
        meta = self._load_threads_meta()
        result: dict[str, dict[str, str]] = {}
        for tid, info in meta.items():
            if isinstance(info, dict) and info.get("model"):
                result[tid] = {"model": info["model"]}
        return result

    def _write_inbox(self, entry: dict[str, Any]) -> dict[str, str]:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        inbox_file = self.inbox_dir / "messages.jsonl"
        with open(inbox_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {"status": "queued"}

    def write_inbox_message(self, content: str, msg_id: str | None, thread_id: str) -> dict[str, str]:
        if not msg_id:
            msg_id = f"msg-{int(datetime.now().timestamp() * 1000)}"
        return self._write_inbox({
            "timestamp": datetime.now().isoformat(),
            "id": msg_id,
            "thread_id": thread_id,
            "kind": "message",
            "content": content,
        })

    def write_inbox_stop(self, thread_id: str) -> dict[str, str]:
        stop_dir = self.inbox_dir / "stop"
        stop_dir.mkdir(parents=True, exist_ok=True)
        signal_file = stop_dir / f"{int(datetime.now().timestamp() * 1000)}.stop"
        signal_file.write_text(thread_id, encoding="utf-8")
        return self._write_inbox({
            "timestamp": datetime.now().isoformat(),
            "id": f"stop-{int(datetime.now().timestamp() * 1000)}",
            "thread_id": thread_id,
            "kind": "stop",
        })

    def write_inbox_model_switch(self, model: str) -> dict[str, str]:
        return self._write_inbox({
            "timestamp": datetime.now().isoformat(),
            "id": f"cmd-{int(datetime.now().timestamp() * 1000)}",
            "thread_id": "*",
            "kind": "model_switch",
            "model": model,
        })

    def write_inbox_thread_model(self, thread_id: str, model: str) -> dict[str, str]:
        meta = self._load_threads_meta()
        meta.setdefault(thread_id, {})
        meta[thread_id]["model"] = model
        if "created_at" not in meta[thread_id]:
            meta[thread_id]["created_at"] = datetime.now().isoformat()
        self._save_threads_meta(meta)
        return self._write_inbox({
            "timestamp": datetime.now().isoformat(),
            "id": f"cmd-{int(datetime.now().timestamp() * 1000)}",
            "thread_id": thread_id,
            "kind": "thread_model",
            "model": model,
        })

    def write_inbox_reset_search_index(self) -> dict[str, str]:
        return self._write_inbox({
            "timestamp": datetime.now().isoformat(),
            "id": f"reset-search-{int(datetime.now().timestamp() * 1000)}",
            "thread_id": "*",
            "kind": "reset_search_index",
        })

    def set_wrapping_enabled(self, thread_id: str, enabled: bool) -> dict[str, str]:
        """Persist wrapping_enabled for a thread (no inbox message needed — agent runner reads threads.json directly)."""
        meta = self._load_threads_meta()
        meta.setdefault(thread_id, {})
        meta[thread_id]["wrapping_enabled"] = enabled
        if "created_at" not in meta[thread_id]:
            meta[thread_id]["created_at"] = datetime.now().isoformat()
        self._save_threads_meta(meta)
        return {"status": "updated", "thread_id": thread_id, "wrapping_enabled": enabled}


def _get_msg_attr(msg: Any, key: str, default: Any = None) -> Any:
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


_TYPE_ALIASES = {
    "AIMessage": "ai", "ai": "ai",
    "HumanMessage": "human", "human": "human",
    "ToolMessage": "tool", "tool": "tool",
    "SystemMessage": "system", "system": "system",
}

_THINKING_BLOCK_TYPES = frozenset({"thinking", "thought", "reasoning"})
_THINKING_TEXT_KEYS = ("thinking", "text", "thought", "reasoning")
_REASONING_KWARGS_KEYS = ("thinking", "reasoning_content", "reasoning", "thought")


def _thinking_text_from_block(block: dict[str, Any]) -> str:
    for key in _THINKING_TEXT_KEYS:
        val = block.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _ai_requests_tools(msg: Any) -> bool:
    tcs = _get_msg_attr(msg, "tool_calls")
    if isinstance(tcs, list) and len(tcs) > 0:
        return True
    inv = _get_msg_attr(msg, "invalid_tool_calls")
    if isinstance(inv, list) and len(inv) > 0:
        return True
    extra = _get_msg_attr(msg, "additional_kwargs")
    if isinstance(extra, dict):
        fc = extra.get("function_call")
        if isinstance(fc, dict) and fc.get("name"):
            return True
    return False


def raw_message_to_viewer_shape(msg: Any, msg_type: str) -> dict[str, Any]:
    content = _get_msg_attr(msg, "content", "")
    extra = _get_msg_attr(msg, "additional_kwargs")
    if not isinstance(extra, dict):
        extra = {}

    out: dict[str, Any] = {}
    if msg_type == "human":
        out["content"] = content if isinstance(content, str) else str(content)
        return out
    if msg_type == "tool":
        out["content"] = content if isinstance(content, str) else str(content)
        name = _get_msg_attr(msg, "name")
        if name:
            out["name"] = name
        return out
    if msg_type != "ai":
        out["content"] = content if isinstance(content, str) else str(content)
        return out

    thinking_from_blocks: list[str] = []
    has_tool_calls = _ai_requests_tools(msg)
    if isinstance(content, str):
        out["content"] = content
    elif isinstance(content, list):
        parts: list[dict[str, Any]] = []
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type", "")
                if btype in _THINKING_BLOCK_TYPES:
                    text = _thinking_text_from_block(block)
                    if text:
                        parts.append({"type": "thinking", "text": text})
                        thinking_from_blocks.append(text)
                    continue
                if btype == "tool_use":
                    continue
                if btype == "text" and has_tool_calls:
                    text = block.get("text", "")
                    if isinstance(text, str) and text.strip():
                        thinking_from_blocks.append(text.strip())
                        parts.append({"type": "thinking", "text": text.strip()})
                    continue
                parts.append(block)
            elif isinstance(block, str):
                parts.append({"type": "thinking" if has_tool_calls else "text", "text": block})
        out["content"] = parts[0].get("text", "") if len(parts) == 1 and parts[0].get("type") == "text" else parts
    else:
        out["content"] = str(content)

    reasoning = None
    for key in _REASONING_KWARGS_KEYS:
        val = extra.get(key)
        if isinstance(val, str) and val.strip():
            reasoning = val.strip()
            break
    if not reasoning and thinking_from_blocks:
        reasoning = "\n\n".join(thinking_from_blocks)
    if reasoning:
        out["reasoning"] = reasoning

    if has_tool_calls and (out.get("content") in (None, "", []) or out.get("content") == ""):
        tcs = _get_msg_attr(msg, "tool_calls") or []
        names = [tc.get("name", "?") if isinstance(tc, dict) else getattr(tc, "name", "?") for tc in tcs]
        out["content"] = f"[Invoking: {', '.join(names)}]" if names else "[Invoking tools]"

    return out


def _serialize_message(msg: Any) -> dict[str, Any]:
    raw_type = _get_msg_attr(msg, "type") or type(msg).__name__
    msg_type = _TYPE_ALIASES.get(raw_type, raw_type)
    result: dict[str, Any] = {"type": msg_type, "id": _get_msg_attr(msg, "id")}
    viewer = raw_message_to_viewer_shape(msg, msg_type)
    result["content"] = viewer["content"]
    if "reasoning" in viewer:
        result["reasoning"] = viewer["reasoning"]
    if "name" in viewer:
        result["name"] = viewer["name"]

    tool_calls = _get_msg_attr(msg, "tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        result["tool_calls"] = [
            {
                "name": tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", ""),
                "args": tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {}),
                "id": tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", ""),
            }
            for tc in tool_calls
        ]
    tool_call_id = _get_msg_attr(msg, "tool_call_id")
    if tool_call_id:
        result["tool_call_id"] = tool_call_id
    return result
