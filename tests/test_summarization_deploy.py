"""Deploy integration with arion two-tier summarization callbacks."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPLOY_DIR))
sys.path.insert(0, str(DEPLOY_DIR / "agent"))

import agent_events


def test_prefetched_done_skips_toast():
    with tempfile.TemporaryDirectory() as td:
        events_path = Path(td) / "events.jsonl"
        agent_events.init(events_path)
        agent_events.summarizing_done("DESKTOP", "debugger", prefetched=True)

        ev = json.loads(events_path.read_text(encoding="utf-8").strip())
        assert ev["event"] == "summarizing_done"
        assert ev["prefetched"] is True
        assert "toast" not in ev


def test_sync_done_keeps_toast():
    with tempfile.TemporaryDirectory() as td:
        events_path = Path(td) / "events.jsonl"
        agent_events.init(events_path)
        agent_events.summarizing("DESKTOP", "debugger")
        agent_events.summarizing_done("DESKTOP", "debugger", prefetched=False)

        lines = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
        assert lines[0]["event"] == "summarizing"
        assert "toast" in lines[0]
        assert lines[1]["prefetched"] is False
        assert "toast" in lines[1]


def test_arion_core_exports_prefetch():
    from arion_agent.assembly import configure_compression
    from arion_agent.context import AgentContext
    from arion_agent.summarization.policies import STANDARD_PREFETCH_POLICY, STANDARD_POLICY
    from arion_agent.util.stats import AgentStats
    from arion_agent.util.timezone import AgentClock

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        ctx = AgentContext(
            agent_id="test",
            identity_dir=ws / ".arion",
            workspace_dir=ws,
            clock=AgentClock(),
            stats=AgentStats(),
            default_model_spec="deepseek:deepseek_v4_flash",
            extra_model_kwargs={},
        )
        cfg = configure_compression(ctx, summarization=None)
        assert cfg is not None
        assert "prefetch_node" in cfg
        assert "compress_node" in cfg
        assert STANDARD_PREFETCH_POLICY is not None
        assert STANDARD_POLICY is not None
