"""Minimal deploy GUI backend — reads workspace files, no arion_agent import."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

DEPLOY_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DEPLOY_DIR))
sys.path.insert(0, str(DEPLOY_DIR / "agent"))
sys.path.insert(0, str(BACKEND_DIR))

from deploy_logging import setup_service_logging
from agent_registry import AgentRegistry, default_thread_id
from adapters.arion_reader import ArionReader
from agent_state import AgentStateMachine
from agent_events import read_events
from fs_browser import browse, list_roots
from message_queue import MessageQueue

load_dotenv(DEPLOY_DIR / ".env")

from deploy_config import apply_runtime_env

_runtime_cfg = apply_runtime_env(DEPLOY_DIR)

DEPLOY_ROOT = _runtime_cfg.deploy_root
setup_service_logging("backend", DEPLOY_ROOT)

logger = logging.getLogger("minimal-backend")

BACKEND_PORT = _runtime_cfg.backend_port

registry = AgentRegistry(DEPLOY_ROOT)
events_file = DEPLOY_ROOT / ".arion" / "events.jsonl"
state_machine = AgentStateMachine(events_file)

_queues: dict[str, MessageQueue] = {}


def _reader(agent_id: str) -> ArionReader:
    info = registry.get_agent(agent_id)
    if info is None:
        raise HTTPException(404, f"Agent not found: {agent_id}")
    mounts = {m["name"]: m["path"] for m in info.get("mounts", [])}
    return ArionReader(info["workspace"], agent_id, mounts=mounts)


def _queue(agent_id: str) -> MessageQueue:
    if agent_id not in _queues:
        info = registry.get_agent(agent_id)
        if info is None:
            raise HTTPException(404, f"Agent not found: {agent_id}")
        qpath = Path(info["workspace"]) / ".arion" / "message_queue.json"
        _queues[agent_id] = MessageQueue(qpath)
    return _queues[agent_id]


async def _queue_dispatcher() -> None:
    while True:
        for entry in registry.list_agents():
            agent_id = entry["agent_id"]
            reader = _reader(agent_id)
            mq = _queue(agent_id)
            for thread_id in mq.all_thread_ids_with_pending():
                item = mq.peek_dispatchable(thread_id)
                if item is None:
                    continue
                if item.kind == "resume":
                    reader._write_inbox({
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "id": item.id,
                        "thread_id": thread_id,
                        "kind": "resume",
                    })
                else:
                    reader.write_inbox_message(item.content, item.id, thread_id)
                mq.mark_dispatched(item.id)
        await asyncio.sleep(0.3)


_dispatcher_task: asyncio.Task | None = None


async def _checkpoint_pruner(interval: float = 60.0) -> None:
    """Background task: prune old checkpoints, keeping at most 350 per thread."""
    while True:
        try:
            for entry in registry.list_agents():
                agent_id = entry["agent_id"]
                info = registry.get_agent(agent_id)
                if not info:
                    continue
                try:
                    mounts = {m["name"]: m["path"] for m in info.get("mounts", [])}
                    reader = ArionReader(info["workspace"], agent_id, mounts=mounts)
                    results = await asyncio.to_thread(reader.prune_all_threads, keep=250)
                    if results:
                        logger.debug("checkpoint prune %s: %s", agent_id, results)
                except Exception:
                    logger.debug("checkpoint prune failed for %s", agent_id, exc_info=True)
        except Exception:
            logger.debug("pruner iteration failed", exc_info=True)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from deploy_logging import install_asyncio_exception_handler

    install_asyncio_exception_handler("backend")
    global _dispatcher_task
    await state_machine.start()
    _dispatcher_task = asyncio.create_task(_queue_dispatcher())
    _pruner_task = asyncio.create_task(_checkpoint_pruner())
    logger.info("Backend started on port %d", BACKEND_PORT)
    yield
    if _dispatcher_task:
        _dispatcher_task.cancel()
        try:
            await _dispatcher_task
        except asyncio.CancelledError:
            pass
    if _pruner_task:
        _pruner_task.cancel()
        try:
            await _pruner_task
        except asyncio.CancelledError:
            pass
    await state_machine.stop()


app = FastAPI(title="MinimalAgentDeploy", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all to ensure all errors are returned as JSON, never plain text."""
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    logger.exception("Unhandled exception in %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def _on_event(ev: dict) -> None:
    if ev.get("event") == "task_started":
        agent_id = ev.get("agent_id", "default")
        thread_id = ev.get("thread", default_thread_id(agent_id))
        consumed = _queue(agent_id).consume_dispatched(thread_id)
        if consumed:
            logger.info("Consumed %s for %s/%s", consumed.id, agent_id, thread_id)
    elif ev.get("event") == "agent_started":
        for q in _queues.values():
            q.reset_dispatched()


state_machine.on_event = _on_event


class SendMessageRequest(BaseModel):
    content: str
    thread_id: str | None = None


class CreateAgentRequest(BaseModel):
    agent_id: str
    workspace: str | None = None
    model: str | None = None
    mounts: list[dict[str, str]] = Field(default_factory=list)


class CreateThreadRequest(BaseModel):
    thread_id: str
    name: str | None = None


class RenameThreadRequest(BaseModel):
    name: str


class ModelSwitchRequest(BaseModel):
    model: str
    thread_id: str | None = None


class ConfigUpdateRequest(BaseModel):
    model: str | None = None
    providers: dict | None = None


@app.get("/api/agents")
async def list_agents():
    agents = registry.list_agents()
    states = state_machine.get_all_states()
    for a in agents:
        a["state"] = states.get(a["agent_id"], {"status": "offline"})
    return agents


@app.post("/api/agents")
async def create_agent(req: CreateAgentRequest):
    from config import get_model
    result = registry.create_agent(
        req.agent_id,
        workspace=req.workspace,
        mounts=req.mounts,
        model=req.model or get_model(),
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str, remove_workspace: bool = Query(False)):
    result = registry.delete_agent(agent_id, remove_workspace=remove_workspace)
    if "error" in result:
        raise HTTPException(404, result["error"])
    _queues.pop(agent_id, None)
    return result


@app.get("/api/agent/state")
async def get_agent_state(agent_id: str = Query("default")):
    state = state_machine.get_agent_state(agent_id)
    mq = _queue(agent_id)
    for tid, tdata in state.get("threads", {}).items():
        pending = mq.list_pending(tid)
        tdata["pending_count"] = len(pending)
        tdata["queue"] = [e.to_dict() for e in pending]
    return state


@app.get("/api/messages")
async def get_messages(
    agent_id: str = Query("default"),
    thread_id: str | None = Query(None),
    num_pages: int = Query(3, ge=1, le=20),
    before_checkpoint_id: str | None = Query(None),
):
    tid = thread_id or default_thread_id(agent_id)
    reader = _reader(agent_id)
    pending = _queue(agent_id).list_pending(tid)
    # Run blocking checkpoint ops in thread pool so event loop stays free
    page = await asyncio.to_thread(
        reader.get_messages_page, tid,
        num_pages=num_pages,
        before_checkpoint_id=before_checkpoint_id,
    )
    roles = page.pop("_roles", [])
    thread_state = state_machine.get_agent_state(agent_id).get("threads", {}).get(tid, {})
    stream_draft = reader.get_stream_draft(tid) if thread_state.get("active") else None
    from turn_models import active_turn_model, load_task_models, slice_turn_models_for_window

    turn_models_full, task_models = load_task_models(events_file, agent_id, tid)
    turn_models = slice_turn_models_for_window(
        roles, page["start_index"], page["end_index"], turn_models_full,
    )
    active_model = active_turn_model(task_models, thread_state.get("active_message_id"))
    return {
        **page,
        "summary": reader.get_summary(tid),
        "thread_state": thread_state,
        "queue": [e.to_dict() for e in pending],
        "stream_draft": stream_draft,
        "turn_models": turn_models,
        "task_models": task_models,
        "active_turn_model": active_model,
    }


@app.post("/api/messages")
async def send_message(req: SendMessageRequest, agent_id: str = Query("default")):
    tid = req.thread_id or default_thread_id(agent_id)
    entry = _queue(agent_id).add(tid, req.content)
    return {"id": entry.id}


@app.post("/api/agent/stop")
async def stop_agent(agent_id: str = Query("default"), thread_id: str | None = Query(None)):
    tid = thread_id or default_thread_id(agent_id)
    _queue(agent_id).clear_thread(tid)
    _reader(agent_id).write_inbox_stop(tid)
    return state_machine.get_agent_state(agent_id)


@app.post("/api/agent/model")
async def switch_model(req: ModelSwitchRequest, agent_id: str = Query("default")):
    reader = _reader(agent_id)
    if req.thread_id:
        reader.write_inbox_thread_model(req.thread_id, req.model)
        state_machine.set_model(agent_id, req.model, req.thread_id)
    else:
        reader.write_inbox_model_switch(req.model)
        registry.update_agent_model(agent_id, req.model)
        state_machine.set_model(agent_id, req.model)
    return state_machine.get_agent_state(agent_id)


@app.post("/api/thread/wrapping")
async def set_thread_wrapping(agent_id: str = Query("default"), thread_id: str | None = Query(None), enabled: bool = Query(True)):
    """Toggle wrapping_enabled for a thread. Pass enabled=true to wrap, false to skip wrapping."""
    tid = thread_id or default_thread_id(agent_id)
    return _reader(agent_id).set_wrapping_enabled(tid, enabled)


@app.get("/api/threads")
async def list_threads(agent_id: str = Query("default")):
    reader = _reader(agent_id)
    default_tid = default_thread_id(agent_id)
    threads = reader.list_threads(default_tid)
    state = state_machine.get_agent_state(agent_id).get("threads", {})
    return [{**state.get(t["thread_id"], {}), **t} for t in threads]


@app.post("/api/threads")
async def create_thread(req: CreateThreadRequest, agent_id: str = Query("default")):
    return _reader(agent_id).create_thread(req.thread_id, req.name)


@app.delete("/api/threads/{thread_id}")
async def delete_thread(thread_id: str, agent_id: str = Query("default")):
    result = _reader(agent_id).delete_thread(thread_id, default_thread_id(agent_id))
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.post("/api/threads/{thread_id}/branch")
async def branch_thread(thread_id: str, agent_id: str = Query("default")):
    return _reader(agent_id).branch_thread(thread_id)


@app.post("/api/threads/{thread_id}/rename")
async def rename_thread(thread_id: str, req: RenameThreadRequest, agent_id: str = Query("default")):
    result = _reader(agent_id).rename_thread(thread_id, req.name)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.get("/api/events")
async def get_events(
    after_index: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    agent_id: str | None = Query(None),
):
    page = read_events(after_index=after_index, limit=limit, events_path=events_file)
    if agent_id:
        page["events"] = [ev for ev in page["events"] if ev.get("agent_id") == agent_id]
    return page


@app.get("/api/config")
async def get_config():
    from config import config_to_safe_dict, load_config
    return config_to_safe_dict(load_config())


@app.get("/api/fs/roots")
async def fs_roots():
    return list_roots(DEPLOY_ROOT)


@app.get("/api/fs/browse")
async def fs_browse(path: str = Query(...)):
    try:
        return browse(path)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/fs/default-workspace")
async def fs_default_workspace(agent_id: str = Query(...)):
    ws = DEPLOY_ROOT / "workspaces" / agent_id
    return {"path": str(ws.resolve())}


@app.put("/api/config")
async def update_config(req: ConfigUpdateRequest):
    from config import config_to_safe_dict, update_config
    config = update_config(model=req.model, providers=req.providers)
    return config_to_safe_dict(config)


@app.post("/api/search/reset-index")
async def reset_search_index(agent_id: str = Query("default")):
    info = registry.get_agent(agent_id)
    if info is None:
        raise HTTPException(404, f"Agent not found: {agent_id}")
    workspace = Path(info["workspace"])
    _reader(agent_id).write_inbox_reset_search_index()
    return {
        "status": "queued",
        "agent_id": agent_id,
        "workspace": str(workspace),
        "message": "Search index reset queued; agent will atomically swap to a new index in the background.",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=BACKEND_PORT)
