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

    # ── Stream draft (kept from legacy) ─────────────────────────

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

    # ── Checkpoint helpers ──────────────────────────────────────

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

    # ── Checkpoint-based pagination ─────────────────────────────
    #
    # Each checkpoint is a full-state snapshot.  Compression boundaries
    # (where message count jumps +30%) are natural pagination anchors.
    # Default: return messages from 3 compression windows.

    def _get_checkpoint_pages(
        self, thread_id: str, *, num_pages: int = 3,
        before_checkpoint_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool, str | None]:
        """Return compression-window pages from checkpoint history.

        Each page = the full message set at a compression boundary.
        Consecutive checkpoints within a window differ by ~1 message,
        so we detect boundaries where message count drops >30%
        (moving from post-compression to pre-compression window).

        Default: last 3 compression windows.
        """
        if not self.checkpoint_path.exists():
            return [], False, None
        from langgraph.checkpoint.sqlite import SqliteSaver

        conn = sqlite3.connect(str(self.checkpoint_path))
        try:
            saver = SqliteSaver(conn)
            config = {"configurable": {"thread_id": thread_id}}
            checkpoints = list(saver.list(config))
        finally:
            conn.close()

        if not checkpoints:
            return [], False, None

        # Walk newest→oldest, collecting boundary checkpoints.
        # A boundary is where message_count drops significantly
        # (pre-compression window has summary + fewer messages).
        boundaries: list[tuple[int, Any, str, int, bool]] = []
        prev_count = -1

        for i, cp_tuple in enumerate(checkpoints):
            cid = cp_tuple.config.get("configurable", {}).get("checkpoint_id", "")
            channel_values = cp_tuple.checkpoint.get("channel_values", {})
            msgs = list(channel_values.get("messages", []))
            summary = channel_values.get("summary", "")
            count = len(msgs)

            # Boundary detection: first checkpoint always starts a page.
            # Subsequent boundaries: message count drops significantly
            # (moving from post-compression to pre-compression window).
            is_boundary = prev_count == -1
            if not is_boundary and prev_count > 0:
                # Compression shrinks messages (summary replaces most).
                # Pre-compression checkpoint has <70% of post-compression count.
                if count < prev_count * 0.7 and prev_count > 30:
                    is_boundary = True

            if is_boundary:
                boundaries.append((i, cp_tuple, cid, count, bool(summary)))

            prev_count = count

        if not boundaries:
            # Fallback: no compression boundaries — return the latest
            # checkpoint as a single page with all its messages.
            if not before_checkpoint_id and checkpoints:
                cp_tuple = checkpoints[0]
                cid = cp_tuple.config.get("configurable", {}).get("checkpoint_id", "")
                channel_values = cp_tuple.checkpoint.get("channel_values", {})
                msgs = list(channel_values.get("messages", []))
                summary = channel_values.get("summary", "")
                serialized = [_serialize_message(m) for m in msgs]
                pages = [{
                    "checkpoint_id": cid,
                    "message_count": len(msgs),
                    "messages": serialized,
                    "has_summary": bool(summary),
                }]
                return pages, False, None
            return [], False, None

        # Apply cursor: skip boundaries before the given checkpoint_id
        if before_checkpoint_id:
            for j, (_, _, cid, _, _) in enumerate(boundaries):
                if cid == before_checkpoint_id:
                    boundaries = boundaries[j + 1:]
                    break

        if not boundaries:
            return [], False, None

        # Take num_pages boundaries
        selected = boundaries[:num_pages]
        has_older = len(boundaries) > num_pages
        next_cursor = selected[-1][2] if has_older else None

        pages: list[dict[str, Any]] = []
        for _, cp_tuple, cid, count, has_summary in selected:
            channel_values = cp_tuple.checkpoint.get("channel_values", {})
            msgs = list(channel_values.get("messages", []))
            serialized = [_serialize_message(m) for m in msgs]
            pages.append({
                "checkpoint_id": cid,
                "message_count": count,
                "messages": serialized,
                "has_summary": has_summary,
            })

        return pages, has_older, next_cursor

    def get_messages_page(
        self,
        thread_id: str,
        *,
        num_pages: int = 3,
        before_checkpoint_id: str | None = None,
    ) -> dict[str, Any]:
        """Return checkpoint-based paginated message history.

        Default: messages from 3 most recent compression windows.
        When before_checkpoint_id is set, loads from the checkpoint
        just before that one, working backward.
        """
        pages, has_older, next_cursor = self._get_checkpoint_pages(
            thread_id, num_pages=num_pages,
            before_checkpoint_id=before_checkpoint_id,
        )

        if not pages:
            return {
                "messages": [],
                "total": 0,
                "start_index": 0,
                "end_index": 0,
                "has_older": False,
                "before_checkpoint_id": None,
                "_roles": [],
            }

        # Concatenate messages from all pages (oldest first = most-recent first reversed)
        all_msgs: list[dict[str, Any]] = []
        for page in reversed(pages):
            all_msgs.extend(page["messages"])

        # Total unique messages across all loaded pages
        total = len(all_msgs)

        # Build role list from concatenated messages
        roles = [(m.get("type", "unknown"), i) for i, m in enumerate(all_msgs)]

        return {
            "messages": all_msgs,
            "total": total,
            "start_index": 0,
            "end_index": len(all_msgs),
            "has_older": has_older,
            "before_checkpoint_id": next_cursor,
            "_roles": roles,
        }

    def get_messages(self, thread_id: str, num_pages: int = 3) -> list[dict[str, Any]]:
        page = self.get_messages_page(thread_id, num_pages=num_pages)
        return page["messages"]

    # ── Checkpoint pruning ──────────────────────────────────────

    def prune_checkpoints(self, thread_id: str, *, keep: int = 350) -> int:
        """Remove old checkpoints for a thread, keeping the most recent `keep`.

        Uses raw SQL for speed (no langgraph deserialization needed).
        Returns number of checkpoints removed.
        """
        if not self.checkpoint_path.exists():
            return 0
        conn = sqlite3.connect(str(self.checkpoint_path))
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()[0]

            if total <= keep:
                return 0

            # Find the checkpoint_id of the (total - keep)-th oldest checkpoint
            # by ordering ascending and skipping
            cutoff = conn.execute(
                "SELECT checkpoint_id FROM checkpoints WHERE thread_id = ? "
                "ORDER BY checkpoint_id ASC LIMIT 1 OFFSET ?",
                (thread_id, total - keep),
            ).fetchone()

            if cutoff is None:
                return 0

            cutoff_id = cutoff[0]
            removed = conn.execute(
                "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ? AND checkpoint_id < ?",
                (thread_id, cutoff_id),
            ).fetchone()[0]

            conn.execute(
                "DELETE FROM checkpoints WHERE thread_id = ? AND checkpoint_id < ?",
                (thread_id, cutoff_id),
            )
            conn.execute(
                "DELETE FROM writes WHERE thread_id = ? AND checkpoint_id < ?",
                (thread_id, cutoff_id),
            )
            conn.commit()

            if removed > 0:
                logger.info(
                    "Pruned %d checkpoints for %s/%s (kept %d)",
                    removed, self.agent_id, thread_id, keep,
                )
            return removed
        finally:
            conn.close()

    def prune_all_threads(self, *, keep: int = 350) -> dict[str, int]:
        """Prune all threads in this agent's checkpoint DB.

        Returns {thread_id: removed_count}.
        """
        results: dict[str, int] = {}
        for t in self.list_threads(""):
            tid = t["thread_id"]
            if t.get("has_checkpoint"):
                try:
                    results[tid] = self.prune_checkpoints(tid, keep=keep)
                except Exception:
                    logger.debug("prune failed for %s/%s", self.agent_id, tid, exc_info=True)
        return results

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
