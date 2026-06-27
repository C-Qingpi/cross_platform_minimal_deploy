"""Materialized message log for fast frontend reads.

Decoupled from LangGraph checkpoint deserialization.
Extracts messages from raw MsgPack checkpoint blobs on sync,
then serves them via flat SQL queries (~1-5ms).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Message serialization (mirrors arion_reader._serialize_message) ──


def _get_msg_attr(msg: Any, attr: str) -> Any:
    if isinstance(msg, dict):
        return msg.get(attr)
    return getattr(msg, attr, None)


_TYPE_ALIASES = {
    "human": "human",
    "ai": "ai",
    "tool": "tool",
    "AIMessage": "ai",
    "HumanMessage": "human",
    "ToolMessage": "tool",
    "SystemMessage": "system",
}


def _serialize_message(msg: Any) -> dict[str, Any]:
    raw_type = _get_msg_attr(msg, "type") or type(msg).__name__
    msg_type = _TYPE_ALIASES.get(raw_type, raw_type)
    result: dict[str, Any] = {"type": msg_type, "id": _get_msg_attr(msg, "id")}

    # Content extraction
    content = _get_msg_attr(msg, "content")
    if isinstance(content, (str, list)):
        result["content"] = content
    elif content is not None:
        result["content"] = str(content)
    else:
        result["content"] = ""

    # Reasoning
    reasoning = _get_msg_attr(msg, "reasoning")
    if reasoning:
        result["reasoning"] = reasoning

    # Name
    name = _get_msg_attr(msg, "name")
    if name:
        result["name"] = name

    # Tool calls
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

    # Tool call ID
    tool_call_id = _get_msg_attr(msg, "tool_call_id")
    if tool_call_id:
        result["tool_call_id"] = tool_call_id

    return result


# ── Message Log ─────────────────────────────────────────────────


class MessageLogger:
    """SQLite-backed materialized view of agent messages.

    One DB per agent, stored alongside checkpoints.sqlite.
    """

    def __init__(self, identity_dir: Path):
        self.db_path = identity_dir / "message_log.db"
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    thread_id    TEXT NOT NULL,
                    msg_index    INTEGER NOT NULL,
                    msg_json     TEXT NOT NULL,
                    PRIMARY KEY (thread_id, msg_index)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS summaries (
                    thread_id    TEXT PRIMARY KEY,
                    summary_text TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            # Schema version — if missing, wipe and recreate
            existing = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            if not existing or existing[0] != "1":
                conn.execute("DELETE FROM messages")
                conn.execute("DELETE FROM summaries")
                conn.execute("DELETE FROM meta")
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', '1')"
                )
            conn.commit()
        finally:
            conn.close()

    # ── Read ────────────────────────────────────────────────────

    def get_messages(
        self,
        thread_id: str,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return (messages, total_count) for a thread."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()[0]

            if limit is None:
                rows = conn.execute(
                    "SELECT msg_json FROM messages WHERE thread_id = ? ORDER BY msg_index",
                    (thread_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT msg_json FROM messages WHERE thread_id = ? ORDER BY msg_index LIMIT ? OFFSET ?",
                    (thread_id, limit, offset),
                ).fetchall()

            messages = [json.loads(r[0]) for r in rows]
            return messages, total
        finally:
            conn.close()

    def get_summary(self, thread_id: str) -> str:
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT summary_text FROM summaries WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            return row[0] if row else ""
        finally:
            conn.close()

    # ── Sync (checkpoint → message_log) ─────────────────────────

    def sync(self, checkpoint_path: Path, thread_id: str) -> int:
        """Extract messages from the latest checkpoint and append to log.

        Uses LangGraph's SqliteSaver for deserialization (checkpoints use
        custom msgpack ExtType that requires LangGraph to decode). Only
        fetches the LATEST checkpoint (O(1), not O(n)).

        Handles compression: if the checkpoint has fewer messages than the log,
        rebuilds from scratch.

        Skips entirely if the latest checkpoint_id hasn't changed since last sync.

        Returns number of new messages appended (or -1 if rebuilt, 0 if skipped).
        """
        if not checkpoint_path.exists():
            return 0

        # Quick fingerprint: latest checkpoint_id (raw SQL, no deserialization)
        conn = sqlite3.connect(str(checkpoint_path))
        try:
            row = conn.execute(
                "SELECT checkpoint_id FROM checkpoints WHERE thread_id = ? "
                "ORDER BY checkpoint_id DESC LIMIT 1",
                (thread_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return 0

        latest_cid = row[0]
        meta_key = f"last_synced/{thread_id}"

        log_conn = sqlite3.connect(str(self.db_path))
        try:
            stored = log_conn.execute(
                "SELECT value FROM meta WHERE key = ?", (meta_key,),
            ).fetchone()
        finally:
            log_conn.close()

        if stored and stored[0] == latest_cid:
            return 0  # Nothing new

        # Deserialize ONLY the latest checkpoint via LangGraph
        from langgraph.checkpoint.sqlite import SqliteSaver
        conn = sqlite3.connect(str(checkpoint_path))
        try:
            saver = SqliteSaver(conn)
            cp_tuple = saver.get_tuple({"configurable": {"thread_id": thread_id}})
        finally:
            conn.close()

        if not cp_tuple:
            return 0

        channel_values = cp_tuple.checkpoint.get("channel_values", {})
        raw_messages = channel_values.get("messages", [])
        summary = channel_values.get("summary", "")

        if not raw_messages:
            return 0

        # Serialize messages (now genuine LangChain objects, not ExtType)
        serialized = _serialize_message_list(raw_messages)
        checkpoint_count = len(serialized)

        log_conn = sqlite3.connect(str(self.db_path))
        try:
            current_count = log_conn.execute(
                "SELECT COUNT(*) FROM messages WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()[0]

            if checkpoint_count < current_count:
                # Compression happened — rebuild
                log_conn.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
                for i, msg in enumerate(serialized):
                    log_conn.execute(
                        "INSERT INTO messages (thread_id, msg_index, msg_json) VALUES (?, ?, ?)",
                        (thread_id, i, json.dumps(msg, ensure_ascii=False)),
                    )
                log_conn.commit()
                logger.info(
                    "Rebuilt message_log for %s: %d → %d messages (compression)",
                    thread_id, current_count, checkpoint_count,
                )
                return -1

            # Normal: append new messages only
            new_count = 0
            for i in range(current_count, checkpoint_count):
                msg = serialized[i]
                cur = log_conn.execute(
                    "INSERT OR IGNORE INTO messages (thread_id, msg_index, msg_json) VALUES (?, ?, ?)",
                    (thread_id, i, json.dumps(msg, ensure_ascii=False)),
                )
                if cur.rowcount > 0:
                    new_count += 1

            if summary:
                log_conn.execute(
                    "INSERT OR REPLACE INTO summaries (thread_id, summary_text) VALUES (?, ?)",
                    (thread_id, str(summary)),
                )

            # Mark synced
            log_conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (meta_key, latest_cid),
            )

            log_conn.commit()
            return new_count
        finally:
            log_conn.close()


def _serialize_message_list(raw_messages: list[Any]) -> list[dict[str, Any]]:
    """Serialize a list of raw messages, skipping unwanted types."""
    SKIP_TYPES = {"summarization", "summary_prompt", "RemoveMessage"}
    result = []
    for m in raw_messages:
        if isinstance(m, dict):
            msg_type = m.get("type", "")
            if msg_type in SKIP_TYPES:
                continue
        serialized = _serialize_message(m)
        result.append(serialized)
    return result
