"""Multi-agent runner: polls inboxes, invokes arion_agent, writes events."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
from collections import defaultdict, deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langgraph.errors import GraphRecursionError

SCRIPT_DIR = Path(__file__).resolve().parent
DEPLOY_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(DEPLOY_DIR))

load_dotenv(DEPLOY_DIR / ".env")

from deploy_config import apply_runtime_env

_runtime_cfg = apply_runtime_env(DEPLOY_DIR)

from deploy_logging import install_signal_logging, setup_service_logging
from failure_watchdog import init as init_failure_watchdog
from agent_registry import AgentRegistry, default_thread_id
from config import apply_provider_env, get_model, load_config, register_proxies

import agent_events as events
from arion_agent.util.streaming import LlmStreamUpdate
from prompts import DEFAULT_DEEPMEMORY, DEFAULT_SOUL, WORKFLOW_METHODOLOGY, wrap_user_message

DEPLOY_ROOT = _runtime_cfg.deploy_root
setup_service_logging("agent", DEPLOY_ROOT)
init_failure_watchdog(DEPLOY_ROOT, service="agent")
install_signal_logging("agent")

logger = logging.getLogger("minimal.agent")
POLL_INTERVAL = float(os.environ.get("AGENT_POLL_INTERVAL", "0.5"))

registry = AgentRegistry(DEPLOY_ROOT)
events.init(DEPLOY_ROOT / ".arion" / "events.jsonl")

_agent_cache: dict[str, object] = {}
_thread_models: dict[str, dict[str, str]] = {}
_active_models: dict[str, str] = {}
_shutdown = asyncio.Event()
_current_abort: ContextVar[asyncio.Event | None] = ContextVar("abort", default=None)


@dataclass
class ThreadRuntime:
    queue: deque[dict] = field(default_factory=deque)
    task: asyncio.Task | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    in_turn: bool = False
    zombie_task: asyncio.Task | None = None


@dataclass
class AgentRuntime:
    agent_id: str
    workspace: Path
    threads: dict[str, ThreadRuntime] = field(default_factory=dict)


_runtimes: dict[str, AgentRuntime] = {}


_pending_compress: dict[tuple[str, str | None], bool] = {}


def _make_compress_handler(agent_id: str):
    def handler(ev) -> None:
        thread = getattr(ev, "thread_id", None)
        key = (agent_id, thread)
        if ev.phase == "before":
            _pending_compress[key] = True
            events.summarizing(agent_id, thread)
            logger.info("Summarizing started agent=%s thread=%s", agent_id, thread)
        elif ev.phase == "after":
            err = getattr(ev, "error", None)
            prefetched = not _pending_compress.pop(key, False)
            events.summarizing_done(agent_id, thread, error=err, prefetched=prefetched)
            if err:
                logger.error("Summarizing failed agent=%s thread=%s: %s", agent_id, thread, err)
            elif prefetched:
                logger.info(
                    "Summarizing applied from prefetch agent=%s thread=%s",
                    agent_id,
                    thread,
                )
            else:
                logger.info("Summarizing done agent=%s thread=%s", agent_id, thread)

    return handler


def _abort_check() -> bool:
    ev = _current_abort.get()
    return ev.is_set() if ev is not None else False


def _build_mounts(agent_id: str) -> list:
    from arion_agent.environments._sandbox.config import MountSpec

    mounts = []
    for name, path in registry.mount_map(agent_id).items():
        if path.is_dir():
            mounts.append(MountSpec(name=name, source=path, readonly=False))
    return mounts


def _stream_draft_path(workspace: Path, agent_id: str, thread_id: str) -> Path:
    return workspace / ".arion" / "agents" / agent_id / "stream_draft" / f"{thread_id}.json"


def _clear_stream_draft(workspace: Path, agent_id: str, thread_id: str) -> None:
    _stream_draft_path(workspace, agent_id, thread_id).unlink(missing_ok=True)


def _write_stream_draft(path: Path, payload: dict[str, str]) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _make_llm_stream_handler(agent_id: str, workspace: Path):
    draft_dir = workspace / ".arion" / "agents" / agent_id / "stream_draft"

    def handler(ev: LlmStreamUpdate) -> None:
        path = draft_dir / f"{ev.thread_id}.json"
        if ev.phase == "end":
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".tmp").unlink(missing_ok=True)
            return
        if ev.phase == "start":
            draft_dir.mkdir(parents=True, exist_ok=True)
            return
        _write_stream_draft(
            path,
            {
                "content": ev.content,
                "reasoning": ev.reasoning,
                "updated_at": datetime.now().isoformat(),
            },
        )

    return handler


def _deploy_summarization_config():
    from arion_agent.summarization.config import SummarizationConfig, SummarizationPolicy

    return SummarizationConfig(
        policy=SummarizationPolicy(
            prefetch_messages=150,
            trigger_messages=225,
            keep_messages=50,
        ),
    )


def _is_dev_deploy() -> bool:
    return os.environ.get("ARION_DEPLOY_MODE", "").strip().lower() == "dev"


def _optional_middleware(workspace: Path) -> list:
    if not _is_dev_deploy():
        return []
    from arion_agent.environments.search import SearchEnvironment, is_search_available

    if not is_search_available():
        logger.warning("Dev deploy: search extras not installed; skip SearchEnvironment")
        return []
    return [SearchEnvironment(workspace_dir=str(workspace))]


def _warm_dev_search_indexers() -> None:
    if not _is_dev_deploy():
        return
    from arion_agent.environments.search import SearchEnvironment, is_search_available

    if not is_search_available():
        logger.warning("Dev deploy: search extras not installed; skip search indexer warmup")
        return
    for entry in registry.list_agents():
        ws = Path(entry["workspace"])
        SearchEnvironment(ws, system_prompt=False).service.start()
        logger.info("Search indexer warmup started for %s", ws)


def create_agent_instance(agent_id: str, model_spec: str) -> object:
    from arion_agent import create_arion_agent

    info = registry.get_agent(agent_id)
    if info is None:
        raise ValueError(f"Unknown agent: {agent_id}")

    workspace = Path(info["workspace"])
    mounts = _build_mounts(agent_id)

    return create_arion_agent(
        model=model_spec,
        workspace_dir=str(workspace),
        agent_id=agent_id,
        soul=DEFAULT_SOUL,
        deep_memory=DEFAULT_DEEPMEMORY,
        pinned_instructions=WORKFLOW_METHODOLOGY,
        subagents=None,
        summarization=_deploy_summarization_config(),
        planning=False,
        mounts=mounts if mounts else None,
        confinement="none",
        network_allowed=True,
        session_log=True,
        checkpointer=True,
        middleware=_optional_middleware(workspace) or None,
        on_compress=_make_compress_handler(agent_id),
        abort_check=_abort_check,
        on_llm_stream=_make_llm_stream_handler(agent_id, workspace),
    )


def _load_persisted_thread_models(agent_id: str) -> dict[str, str]:
    info = registry.get_agent(agent_id)
    if not info:
        return {}
    threads_file = Path(info["workspace"]) / ".arion" / "threads.json"
    if not threads_file.exists():
        return {}
    data = json.loads(threads_file.read_text(encoding="utf-8-sig"))
    return {
        tid: entry["model"]
        for tid, entry in data.items()
        if isinstance(entry, dict) and entry.get("model")
    }


def _resolve_model(agent_id: str, thread_id: str) -> str:
    on_disk = _load_persisted_thread_models(agent_id).get(thread_id)
    if on_disk:
        cached = _thread_models.get(agent_id, {}).get(thread_id)
        if cached != on_disk:
            _thread_models.setdefault(agent_id, {})[thread_id] = on_disk
        return on_disk
    in_memory = _thread_models.get(agent_id, {}).get(thread_id)
    if in_memory:
        return in_memory
    return (
        _active_models.get(agent_id)
        or registry.get_agent(agent_id).get("model")
        or get_model()
    )


def _get_agent(agent_id: str) -> object:
    if agent_id not in _agent_cache:
        default = _active_models.get(agent_id) or registry.get_agent(agent_id).get("model") or get_model()
        _agent_cache[agent_id] = create_agent_instance(agent_id, default)
    return _agent_cache[agent_id]


def _runtime(agent_id: str) -> AgentRuntime:
    if agent_id not in _runtimes:
        info = registry.get_agent(agent_id)
        ws = Path(info["workspace"]) if info else DEPLOY_ROOT
        _runtimes[agent_id] = AgentRuntime(agent_id=agent_id, workspace=ws)
    return _runtimes[agent_id]


def _thread_runtime(agent_id: str, thread_id: str) -> ThreadRuntime:
    rt = _runtime(agent_id)
    if thread_id not in rt.threads:
        rt.threads[thread_id] = ThreadRuntime()
    return rt.threads[thread_id]


def _inbox_path(workspace: Path) -> Path:
    return workspace / ".arion" / "inbox" / "messages.jsonl"


def _stop_signal_dir(workspace: Path) -> Path:
    return workspace / ".arion" / "inbox" / "stop"


def _apply_stop(agent_id: str, thread_id: str) -> None:
    rt = _thread_runtime(agent_id, thread_id)
    rt.queue.clear()
    info = registry.get_agent(agent_id)
    if info:
        _clear_stream_draft(Path(info["workspace"]), agent_id, thread_id)
    if rt.in_turn:
        rt.cancel_event.set()
        logger.info("Stop: cancelling active turn %s/%s", agent_id, thread_id)
    else:
        logger.info("Stop: cleared queue %s/%s", agent_id, thread_id)


def _poll_stop_signals(agent_id: str, workspace: Path) -> None:
    stop_dir = _stop_signal_dir(workspace)
    if not stop_dir.exists():
        return
    for path in list(stop_dir.glob("*.stop")):
        thread_id = path.read_text(encoding="utf-8-sig").strip() or default_thread_id(agent_id)
        _apply_stop(agent_id, thread_id)
        path.unlink(missing_ok=True)


def _read_inbox_batch(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8-sig").strip()
    if not raw:
        path.unlink(missing_ok=True)
        return []
    tmp = path.with_suffix(".processing")
    path.replace(tmp)
    items = []
    for line in raw.split("\n"):
        line = line.strip()
        if line:
            items.append(json.loads(line))
    tmp.unlink(missing_ok=True)
    return items


async def _drain_zombie(runtime: ThreadRuntime) -> None:
    if runtime.zombie_task and not runtime.zombie_task.done():
        try:
            await asyncio.wait_for(runtime.zombie_task, timeout=15.0)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            pass
    runtime.zombie_task = None


def _ack_cancel(
    agent_id: str,
    thread_id: str,
    model: str,
    msg_id: str | None,
    runtime: ThreadRuntime,
) -> None:
    events.task_cancelled(agent_id, thread_id, model, msg_id)
    runtime.cancel_event.clear()


async def _run_turn(
    agent_id: str,
    agent,
    invoke_input,
    msg_id: str,
    *,
    thread_id: str,
    model: str,
    runtime: ThreadRuntime,
) -> None:
    from arion_agent import AgentAborted

    await _drain_zombie(runtime)
    runtime.cancel_event.clear()
    runtime.in_turn = True
    events.task_started(agent_id, thread_id, model, msg_id)
    logger.info("Turn started agent=%s thread=%s model=%s msg=%s", agent_id, thread_id, model, msg_id)

    token = _current_abort.set(runtime.cancel_event)
    config = {"configurable": {"thread_id": thread_id, "model": model}}
    loop = asyncio.get_running_loop()
    turn_started = loop.time()
    heartbeat_stop = asyncio.Event()

    async def _heartbeat() -> None:
        while not heartbeat_stop.is_set():
            await asyncio.sleep(30)
            if heartbeat_stop.is_set() or not runtime.in_turn:
                return
            elapsed = loop.time() - turn_started
            events.turn_heartbeat(agent_id, thread_id, model, elapsed)
            logger.info(
                "Turn heartbeat agent=%s thread=%s elapsed=%.0fs in_turn=%s",
                agent_id, thread_id, elapsed, runtime.in_turn,
            )

    heartbeat_task = asyncio.create_task(_heartbeat())
    try:
        invoke_task = asyncio.create_task(agent.ainvoke(invoke_input, config=config))
        cancel_task = asyncio.create_task(runtime.cancel_event.wait())
        done, _ = await asyncio.wait({invoke_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)

        if invoke_task in done:
            cancel_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cancel_task
            try:
                invoke_task.result()
            except AgentAborted:
                logger.info("Turn aborted agent=%s thread=%s", agent_id, thread_id)
                _ack_cancel(agent_id, thread_id, model, msg_id, runtime)
                return
            except GraphRecursionError:
                logger.error("Turn recursion limit agent=%s thread=%s", agent_id, thread_id)
                events.task_recursion_limit(agent_id, thread_id, model, msg_id)
                return
            logger.info("Turn completed agent=%s thread=%s", agent_id, thread_id)
            events.task_completed(agent_id, thread_id, model, msg_id)
        else:
            invoke_task.cancel()
            runtime.zombie_task = invoke_task
            logger.info("Turn cancel requested agent=%s thread=%s", agent_id, thread_id)
            _ack_cancel(agent_id, thread_id, model, msg_id, runtime)
    except asyncio.CancelledError:
        logger.info("Turn cancelled agent=%s thread=%s", agent_id, thread_id)
        _ack_cancel(agent_id, thread_id, model, msg_id, runtime)
        raise
    except Exception as exc:
        logger.exception("Turn failed agent=%s thread=%s", agent_id, thread_id)
        error_line = str(exc).strip().split("\n")[-1][:300]
        events.task_error(agent_id, thread_id, model, error_line, msg_id)
        raise
    finally:
        heartbeat_stop.set()
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        runtime.in_turn = False
        _current_abort.reset(token)


def _wrapping_enabled(workspace: Path, thread_id: str) -> bool:
    """Read wrapping_enabled from threads.json (default True)."""
    threads_file = workspace / ".arion" / "threads.json"
    meta = json.loads(threads_file.read_text(encoding="utf-8-sig"))
    return meta.get(thread_id, {}).get("wrapping_enabled", True)


async def _process_queue(agent_id: str, thread_id: str) -> None:
    runtime = _thread_runtime(agent_id, thread_id)
    if runtime.task and not runtime.task.done():
        return

    async def _worker() -> None:
        agent = _get_agent(agent_id)
        workspace = _runtime(agent_id).workspace
        wrapping_enabled = _wrapping_enabled(workspace, thread_id)
        while runtime.queue:
            msg = runtime.queue.popleft()
            msg_id = msg.get("id", "")
            kind = msg.get("kind", "message")
            if kind == "stop":
                _apply_stop(agent_id, thread_id)
                continue
            model = _resolve_model(agent_id, thread_id)
            logger.info("Invoke %s on %s/%s with model %s (wrapping=%s)", kind, agent_id, thread_id, model, wrapping_enabled)
            if kind == "resume":
                await _run_turn(agent_id, agent, None, msg_id, thread_id=thread_id, model=model, runtime=runtime)
            else:
                content = msg.get("content", "")
                if wrapping_enabled:
                    content = wrap_user_message(content)
                await _run_turn(
                    agent_id, agent,
                    {"messages": [("user", content)]},
                    msg_id, thread_id=thread_id, model=model, runtime=runtime,
                )

    runtime.task = asyncio.create_task(_worker())
    runtime.task.add_done_callback(lambda t: setattr(runtime, "task", None))


def _interrupt_if_in_turn(agent_id: str, thread_id: str) -> None:
    rt = _thread_runtime(agent_id, thread_id)
    if rt.in_turn:
        rt.cancel_event.set()
        logger.info("Interrupt active turn %s/%s", agent_id, thread_id)


def _apply_thread_model(agent_id: str, thread_id: str, model: str) -> None:
    _thread_models.setdefault(agent_id, {})[thread_id] = model
    events.model_switched(agent_id, model, thread=thread_id)
    logger.info("Thread %s model -> %s", thread_id, model)
    _interrupt_if_in_turn(agent_id, thread_id)


def _apply_agent_model(agent_id: str, model: str) -> None:
    _active_models[agent_id] = model
    _agent_cache.pop(agent_id, None)
    events.model_switched(agent_id, model)
    logger.info("Agent %s default model -> %s", agent_id, model)
    for tid, rt in _runtime(agent_id).threads.items():
        if rt.in_turn:
            rt.cancel_event.set()
            logger.info("Agent model switch interrupts turn %s/%s", agent_id, tid)


def _reset_search_index(agent_id: str) -> None:
    if not _is_dev_deploy():
        return
    from arion_agent.environments.search import SearchEnvironment, is_search_available

    if not is_search_available():
        logger.warning("Search index reset skipped: search extras not installed")
        return
    info = registry.get_agent(agent_id)
    if info is None:
        return
    SearchEnvironment.reset_index_for_workspace(Path(info["workspace"]))
    logger.info("Search index reset for agent=%s workspace=%s", agent_id, info["workspace"])


def _enqueue(agent_id: str, items: list[dict]) -> None:
    threads_touched: set[str] = set()
    for item in items:
        thread_id = item.get("thread_id") or default_thread_id(agent_id)
        kind = item.get("kind", "message")
        if kind == "stop":
            _apply_stop(agent_id, thread_id)
            threads_touched.add(thread_id)
            continue
        if kind == "thread_model":
            _apply_thread_model(agent_id, thread_id, item["model"])
            threads_touched.add(thread_id)
            continue
        if kind == "model_switch":
            _apply_agent_model(agent_id, item["model"])
            continue
        if kind == "reset_search_index":
            _reset_search_index(agent_id)
            continue
        rt = _thread_runtime(agent_id, thread_id)
        rt.queue.append(item)
        if kind in ("message", "resume") and rt.in_turn:
            rt.cancel_event.set()
            logger.info("Followup interrupts active turn %s/%s", agent_id, thread_id)
        threads_touched.add(thread_id)
    for thread_id in threads_touched:
        asyncio.create_task(_process_queue(agent_id, thread_id))


async def poll_loop() -> None:
    loop = asyncio.get_running_loop()
    last_idle_log = loop.time()
    while not _shutdown.is_set():
        for entry in registry.list_agents():
            agent_id = entry["agent_id"]
            ws = Path(entry["workspace"])
            _poll_stop_signals(agent_id, ws)
            batch = _read_inbox_batch(_inbox_path(ws))
            if batch:
                _enqueue(agent_id, batch)
        now = loop.time()
        if now - last_idle_log >= 300:
            any_active = any(
                rt.in_turn for rt in _runtimes.values() for rt in rt.threads.values()
            )
            logger.info(
                "Poll loop alive pid=%s active_turns=%s",
                os.getpid(),
                any_active,
            )
            last_idle_log = now
        await asyncio.sleep(POLL_INTERVAL)


async def main() -> None:
    from deploy_logging import install_asyncio_exception_handler

    install_asyncio_exception_handler("agent")
    config = load_config()
    apply_provider_env(config)
    register_proxies()
    default_model = config.get("model", {}).get("default", get_model())

    agents = registry.list_agents()
    if not agents:
        registry.create_agent("default", model=default_model)
        agents = registry.list_agents()
        logger.info("Created default agent")

    for entry in agents:
        aid = entry["agent_id"]
        _active_models[aid] = entry.get("model") or default_model
        persisted = _load_persisted_thread_models(aid)
        if persisted:
            _thread_models[aid] = persisted
        events.agent_started(aid, _active_models[aid])

    logger.info("Agent runner started (%d agents)", len(agents))
    _warm_dev_search_indexers()
    await poll_loop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument(
        "--test-resume",
        action="store_true",
        help="Smoke: cancel mid-turn then resume from checkpoint",
    )
    args = parser.parse_args()

    if args.test or args.test_resume:
        os.environ.setdefault("ARION_DEPLOY_MODE", "dev")
        config = load_config()
        apply_provider_env(config)
        register_proxies()
        agents = registry.list_agents()
        if not agents:
            registry.create_agent("default", model=get_model())
        aid = registry.list_agents()[0]["agent_id"]
        tid = default_thread_id(aid)
        model = get_model()
        runtime = _thread_runtime(aid, tid)

        async def _test_hello() -> None:
            agent = create_agent_instance(aid, model)
            result = await agent.ainvoke(
                {"messages": [("user", wrap_user_message("Say hello in one sentence."))]},
                config={"configurable": {"thread_id": tid}},
            )
            ai = [m for m in result["messages"] if getattr(m, "type", "") == "ai"]
            print(ai[-1].content if ai else "no response")

        async def _test_resume_smoke() -> None:
            class _SlowAgent:
                def __init__(self) -> None:
                    self.calls: list[object | None] = []

                async def ainvoke(self, payload, config=None):
                    self.calls.append(payload)
                    if payload is None:
                        return {"messages": []}
                    await asyncio.sleep(30)
                    return {"messages": []}

            slow = _SlowAgent()
            turn = asyncio.create_task(
                _run_turn(aid, slow, {"messages": [("user", "x")]}, "smoke-1",
                          thread_id=tid, model=model, runtime=runtime)
            )
            await asyncio.sleep(0.3)
            runtime.cancel_event.set()
            await turn
            assert slow.calls and slow.calls[0] is not None
            resume = asyncio.create_task(
                _run_turn(aid, slow, None, "smoke-resume",
                          thread_id=tid, model=model, runtime=runtime)
            )
            await resume
            assert None in slow.calls
            print("interrupt+resume smoke: OK")

        if args.test_resume:
            asyncio.run(_test_resume_smoke())
        else:
            asyncio.run(_test_hello())
    else:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            for entry in registry.list_agents():
                events.agent_stopped(entry["agent_id"])
