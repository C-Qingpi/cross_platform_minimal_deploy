"""Reproduce prefetch vs blocked compress.

Phase 1: deterministic registry simulation (no API).
Phase 2: live agent with deepseek:deepseek_v4_flash (needs DEEPSEEK_API_KEY).

Usage (from cross_platform_minimal_deploy):
  python scripts/repro/summarization_prefetch.py --live-only --prefetch 12 --trigger 28
  python scripts/repro/summarization_prefetch.py --live-only --preload 26 --rounds 3
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

DEPLOY_DIR = Path(__file__).resolve().parents[2]
ARION_DIR = DEPLOY_DIR.parent / "arion_agent"
sys.path.insert(0, str(DEPLOY_DIR))
sys.path.insert(0, str(ARION_DIR))

load_dotenv(DEPLOY_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("repro.summarization")

PREFETCH_MESSAGES = 12
TRIGGER_MESSAGES = 28
KEEP_MESSAGES = 8


@dataclass
class CompressEvent:
    phase: str
    prefetched: bool | None = None
    at: float = field(default_factory=time.monotonic)


def _policy(
    prefetch: int = PREFETCH_MESSAGES,
    trigger: int = TRIGGER_MESSAGES,
    keep: int = KEEP_MESSAGES,
):
    from arion_agent.summarization.config import SummarizationPolicy

    return SummarizationPolicy(
        prefetch_messages=prefetch,
        trigger_messages=trigger,
        keep_messages=keep,
    )


def _make_messages(n: int) -> list:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    msgs = []
    for i in range(n):
        if i % 3 == 0:
            msgs.append(HumanMessage(content=f"user-{i}", id=f"h{i}"))
        elif i % 3 == 1:
            msgs.append(
                AIMessage(
                    content="",
                    tool_calls=[{"name": "t", "args": {}, "id": f"tc{i}"}],
                    id=f"a{i}",
                )
            )
        else:
            msgs.append(
                ToolMessage(content=f"tool-{i}", tool_call_id=f"tc{i-1}", name="t", id=f"t{i}")
            )
    return msgs


async def run_registry_simulation(
    *,
    prefetch: int,
    trigger: int,
    keep: int,
) -> None:
    """Show PrefetchRegistry.start skips refresh while first prefetch is in-flight."""
    from arion_agent.summarization.compress import PrefetchRegistry, find_safe_cutoff
    from arion_agent.summarization.config import PolicyDecision

    registry = PrefetchRegistry()
    thread_id = "sim-thread"
    slow_secs = 8.0
    first_prefetch_at = prefetch + 1
    hard_at = trigger + 1
    decision = PolicyDecision(keep_last_messages=keep)

    async def slow_prefetch(cutoff: int, message_count: int):
        await asyncio.sleep(slow_secs)
        from arion_agent.summarization.compress import _PrefetchResult

        return _PrefetchResult(
            cutoff=cutoff,
            message_count=message_count,
            summary_wrapper=f"summary@{cutoff}",
            evictions=[],
            messages_summarized=cutoff,
            messages_kept=message_count - cutoff,
            summary_tokens=100,
            file_path=None,
        )

    msgs_first = _make_messages(first_prefetch_at)
    cutoff_first = find_safe_cutoff(msgs_first, decision, None)
    registry.start(
        thread_id,
        message_count=first_prefetch_at,
        cutoff=cutoff_first,
        coro_factory=lambda: slow_prefetch(cutoff_first, first_prefetch_at),
    )
    logger.info(
        "SIM: prefetch started at messages=%d cutoff=%d (LLM sleep %.1fs)",
        first_prefetch_at,
        cutoff_first,
        slow_secs,
    )

    skipped: list[int] = []
    midpoints = [
        first_prefetch_at + int((hard_at - first_prefetch_at) * f)
        for f in (0.25, 0.45, 0.65, 0.85, 0.95)
    ]
    for n in midpoints:
        await asyncio.sleep(0.05)
        msgs = _make_messages(n)
        cutoff_n = find_safe_cutoff(msgs, decision, None)
        before = registry.get(thread_id)
        registry.start(
            thread_id,
            message_count=n,
            cutoff=cutoff_n,
            coro_factory=lambda c=cutoff_n, m=n: slow_prefetch(c, m),
        )
        after = registry.get(thread_id)
        if (
            before is not None
            and after is not None
            and before.task is after.task
            and before.message_count == first_prefetch_at
        ):
            skipped.append(n)
            logger.info(
                "SIM: prefetch refresh SKIPPED at messages=%d (still on cutoff=%d task)",
                n,
                before.cutoff,
            )

    msgs_hard = _make_messages(hard_at)
    cutoff_hard = find_safe_cutoff(msgs_hard, decision, None)
    t0 = time.monotonic()
    prefetched = await registry.await_result(thread_id, cutoff=cutoff_hard)
    waited = time.monotonic() - t0

    if prefetched is None:
        logger.error("SIM: compress would run FULL SYNC (no prefetch result)")
    elif prefetched.cutoff == cutoff_hard:
        logger.info(
            "SIM: compress FAST PATH cutoff=%d (waited %.2fs for in-flight prefetch)",
            cutoff_hard,
            waited,
        )
    else:
        delta = cutoff_hard - prefetched.cutoff
        logger.warning(
            "SIM: compress DELTA/BLOCKED path prefetch_cutoff=%d compress_cutoff=%d "
            "delta_messages=%d (waited %.2fs for stale prefetch)",
            prefetched.cutoff,
            cutoff_hard,
            delta,
            waited,
        )

    logger.info(
        "SIM summary: prefetch=%d trigger=%d; skipped refresh at %s",
        prefetch,
        trigger,
        skipped,
    )


async def run_live_deepseek(
    *,
    rounds: int,
    single_chain: int,
    preload_messages: int,
    prefetch: int,
    trigger: int,
    keep: int,
) -> None:
    from langchain_core.messages import HumanMessage

    from arion_agent import create_arion_agent
    from arion_agent.summarization.config import SummarizationConfig

    from config import apply_provider_env, load_config, register_proxies

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        logger.error("LIVE: DEEPSEEK_API_KEY missing in .env — skipping live phase")
        return

    apply_provider_env(load_config())
    register_proxies()

    events: list[CompressEvent] = []
    prefetch_log: list[str] = []

    class _PrefetchLogHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            msg = record.getMessage()
            if "Prefetch started" in msg or "Prefetch complete" in msg:
                prefetch_log.append(f"{time.monotonic():.1f} {msg}")
            if (
                "Compression fast path" in msg
                or "Compression delta path" in msg
                or "Compression sync" in msg
            ):
                prefetch_log.append(f"{time.monotonic():.1f} {msg}")

    compress_logger = logging.getLogger("arion_agent.summarization.compress")
    handler = _PrefetchLogHandler()
    compress_logger.addHandler(handler)
    compress_logger.setLevel(logging.INFO)

    def on_compress(ev) -> None:
        if ev.phase == "before":
            events.append(CompressEvent(phase="before", prefetched=False))
            logger.warning("LIVE: BLOCKED summarizing (sync LLM) starting")
        elif ev.phase == "after":
            had_before = events and events[-1].phase == "before"
            events.append(
                CompressEvent(phase="after", prefetched=not had_before)
            )
            if had_before:
                logger.warning("LIVE: BLOCKED summarizing done (user would see toast)")
            else:
                logger.info("LIVE: prefetched fast path applied (no blocking toast)")

    tmp = tempfile.mkdtemp(prefix="repro-sum-")
    workspace = Path(tmp)
    agent_id = f"repro-{uuid.uuid4().hex[:8]}"
    thread_id = "repro-thread"
    model = "deepseek:deepseek_v4_flash"

    summarization = SummarizationConfig(
        policy=_policy(prefetch, trigger, keep),
    )

    agent = create_arion_agent(
        model=model,
        workspace_dir=str(workspace),
        agent_id=agent_id,
        soul="test",
        deep_memory="",
        subagents=None,
        summarization=summarization,
        planning=False,
        confinement="none",
        network_allowed=True,
        session_log=False,
        checkpointer=True,
        on_compress=on_compress,
    )

    config = {"configurable": {"thread_id": thread_id, "model": model}}

    logger.info(
        "LIVE: policy prefetch=%d trigger=%d keep=%d model=%s rounds=%d "
        "single_chain=%d preload=%d",
        prefetch,
        trigger,
        keep,
        model,
        rounds,
        single_chain,
        preload_messages,
    )

    if preload_messages > 0:
        seed = _make_messages(preload_messages)
        await agent.aupdate_state(config, {"messages": seed})
        snap = await agent.aget_state(config)
        logger.info(
            "LIVE: preloaded %d synthetic messages (checkpoint now has %d)",
            preload_messages,
            len(snap.values.get("messages", [])),
        )

    t_start = time.monotonic()
    n_msgs = len((await agent.aget_state(config)).values.get("messages", []))

    if single_chain > 0:
        commands = " ".join(f"echo chain-{i};" for i in range(single_chain))
        user_text = (
            f"Run exactly one run_command with shell command: {commands} "
            "Do not reply with text."
        )
        logger.info("LIVE: single-chain mode with %d echo segments", single_chain)
        t0 = time.monotonic()
        try:
            state = await agent.ainvoke(
                {"messages": [HumanMessage(content=user_text)]},
                config=config,
            )
            n_msgs = len(state.get("messages", []))
            logger.info(
                "LIVE: single-chain done messages=%d invoke_sec=%.2f",
                n_msgs,
                time.monotonic() - t0,
            )
        except Exception as exc:
            logger.error("LIVE: single-chain invoke failed: %s", exc)
    else:
        prompt = "Call run_command once with the given command. Tool only, no text."
        for i in range(rounds):
            cmd = f"echo repro-{i}"
            t0 = time.monotonic()
            try:
                state = await agent.ainvoke(
                    {"messages": [HumanMessage(content=f"{prompt}\n{cmd}")]},
                    config=config,
                )
            except Exception as exc:
                logger.error("LIVE: invoke failed round=%d: %s", i, exc)
                break
            elapsed = time.monotonic() - t0
            n_msgs = len(state.get("messages", []))
            logger.info(
                "LIVE: round=%d messages=%d invoke_sec=%.2f",
                i,
                n_msgs,
                elapsed,
            )
            if n_msgs > trigger:
                logger.info("LIVE: passed hard trigger at round=%d", i)
                break

    total = time.monotonic() - t_start
    blocked = [e for e in events if e.phase == "before"]
    fast = [e for e in events if e.phase == "after" and e.prefetched]

    logger.info("LIVE: total_sec=%.1f final_messages=%d", total, n_msgs)
    logger.info(
        "LIVE: compress events blocked=%d fast_prefetch=%d",
        len(blocked),
        len(fast),
    )
    for line in prefetch_log:
        logger.info("LIVE log: %s", line)

    if blocked:
        logger.warning(
            "LIVE: REPRODUCED blocked summarization — prefetch did not prevent sync compress"
        )
    elif fast:
        logger.info("LIVE: hard trigger used prefetched fast path (no block)")
    else:
        logger.info(
            "LIVE: did not hit hard compress (need messages>%d, got %d)",
            trigger,
            n_msgs,
        )

    compress_logger.removeHandler(handler)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim-only", action="store_true")
    parser.add_argument("--live-only", action="store_true")
    parser.add_argument("--prefetch", type=int, default=PREFETCH_MESSAGES)
    parser.add_argument("--trigger", type=int, default=TRIGGER_MESSAGES)
    parser.add_argument("--keep", type=int, default=KEEP_MESSAGES)
    parser.add_argument("--rounds", type=int, default=15)
    parser.add_argument("--single-chain", type=int, default=0)
    parser.add_argument(
        "--preload",
        type=int,
        default=0,
        help="seed checkpoint with N synthetic messages before live invokes",
    )
    args = parser.parse_args()

    if not args.live_only:
        asyncio.run(
            run_registry_simulation(
                prefetch=args.prefetch,
                trigger=args.trigger,
                keep=args.keep,
            )
        )

    if not args.sim_only:
        asyncio.run(
            run_live_deepseek(
                rounds=args.rounds,
                single_chain=args.single_chain,
                preload_messages=args.preload,
                prefetch=args.prefetch,
                trigger=args.trigger,
                keep=args.keep,
            )
        )


if __name__ == "__main__":
    main()
