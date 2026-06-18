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

    def _display_log_path(self, thread_id: str) -> Path:
        return self.identity_dir / "display_log" / f"{thread_id}.jsonl"

    def _stream_draft_path(self, thread_id: str) -> Path:
        return self.identity_dir / "stream_draft" / f"{thread_id}.json"

    def get_stream_draft(self, thread_id: str) -> dict[str, Any] | None:
        path = self._stream_draft_path(thread_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _message_key(self, msg: dict[str, Any]) -> str:
        mid = msg.get("id")
        if mid:
            return f"id:{mid}"
        content = msg.get("content")
        body = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, sort_keys=True)
        return f"{msg.get('type')}:{len(body)}:{body[:200]}"

    def _load_display_log(self, thread_id: str) -> list[dict[str, Any]]:
        path = self._display_log_path(thread_id)
        if not path.exists():
            return []
        messages: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line:
                messages.append(json.loads(line))
        return messages

    def _write_display_log(self, thread_id: str, messages: list[dict[str, Any]]) -> None:
        path = self._display_log_path(thread_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def _merge_messages(self, existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen = {self._message_key(m) for m in existing}
        merged = list(existing)
        for msg in incoming:
            key = self._message_key(msg)
            if key not in seen:
                merged.append(msg)
                seen.add(key)
        return merged

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

    def _bootstrap_display_log_from_checkpoints(self, thread_id: str) -> list[dict[str, Any]]:
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

    def _sync_display_log(self, thread_id: str, current: list[dict[str, Any]]) -> list[dict[str, Any]]:
        path = self._display_log_path(thread_id)
        if not path.exists():
            bootstrapped = self._bootstrap_display_log_from_checkpoints(thread_id)
            self._write_display_log(thread_id, bootstrapped or list(current))

        display = self._load_display_log(thread_id)
        updated = self._merge_messages(display, current)
        if len(updated) != len(display):
            self._write_display_log(thread_id, updated)
        return updated

    def get_all_messages(self, thread_id: str) -> list[dict[str, Any]]:
        current = self._latest_checkpoint_messages(thread_id)
        if self.checkpoint_path.exists():
            return self._sync_display_log(thread_id, current)
        return self._load_display_log(thread_id)

    def get_messages_page(
        self,
        thread_id: str,
        *,
        limit: int = 500,
        before_index: int | None = None,
    ) -> dict[str, Any]:
        all_msgs = self.get_all_messages(thread_id)
        total = len(all_msgs)
        if before_index is None:
            start = max(0, total - limit)
            end = total
        else:
            end = max(0, min(before_index, total))
            start = max(0, end - limit)
        return {
            "messages": all_msgs[start:end],
            "total": total,
            "start_index": start,
            "end_index": end,
            "has_older": start > 0,
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
