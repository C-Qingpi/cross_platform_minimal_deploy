"""Unit tests for stream_draft read/write race handling."""

from __future__ import annotations

import json
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

DEPLOY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPLOY_DIR))
sys.path.insert(0, str(DEPLOY_DIR / "backend"))
sys.path.insert(0, str(DEPLOY_DIR / "agent"))

from adapters.arion_reader import ArionReader
from agent_runner import _make_llm_stream_handler
from arion_agent.util.streaming import LlmStreamUpdate


@pytest.fixture
def reader_ctx():
    with tempfile.TemporaryDirectory() as td:
        workspace = Path(td)
        agent_id = f"draft-{uuid.uuid4().hex[:8]}"
        thread_id = f"{agent_id}-main"
        identity = workspace / ".arion" / "agents" / agent_id / "stream_draft"
        identity.mkdir(parents=True)
        yield {
            "reader": ArionReader(str(workspace), agent_id),
            "workspace": workspace,
            "agent_id": agent_id,
            "thread_id": thread_id,
            "draft_dir": identity,
        }


def test_get_stream_draft_empty_file_returns_none(reader_ctx):
    thread_id = reader_ctx["thread_id"]
    path = reader_ctx["draft_dir"] / f"{thread_id}.json"
    path.write_text("", encoding="utf-8")
    assert reader_ctx["reader"].get_stream_draft(thread_id) is None


def test_get_stream_draft_whitespace_only_returns_none(reader_ctx):
    thread_id = reader_ctx["thread_id"]
    path = reader_ctx["draft_dir"] / f"{thread_id}.json"
    path.write_text("   \n", encoding="utf-8")
    assert reader_ctx["reader"].get_stream_draft(thread_id) is None


def test_stream_handler_writes_valid_json(reader_ctx):
    agent_id = reader_ctx["agent_id"]
    workspace = reader_ctx["workspace"]
    thread_id = reader_ctx["thread_id"]
    handler = _make_llm_stream_handler(agent_id, workspace)
    path = reader_ctx["draft_dir"] / f"{thread_id}.json"

    handler(LlmStreamUpdate(thread_id=thread_id, phase="start"))
    handler(
        LlmStreamUpdate(
            thread_id=thread_id,
            phase="delta",
            content="Hello",
            reasoning="thinking",
        )
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["content"] == "Hello"
    assert data["reasoning"] == "thinking"
    assert reader_ctx["reader"].get_stream_draft(thread_id) == data
