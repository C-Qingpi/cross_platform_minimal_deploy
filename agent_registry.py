"""Agent registry: create/list/delete agents and their workspaces."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MOUNT_PREFIX = "imported_directories"


def default_thread_id(agent_id: str) -> str:
    return f"{agent_id}-main"


class AgentRegistry:
    def __init__(self, deploy_dir: Path) -> None:
        self.deploy_dir = deploy_dir.resolve()
        self.workspaces_dir = self.deploy_dir / "workspaces"
        self.registry_path = self.deploy_dir / "agents.json"
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"agents": {}}
        return json.loads(self.registry_path.read_text(encoding="utf-8-sig"))

    def _save(self, data: dict[str, Any]) -> None:
        self.registry_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def list_agents(self) -> list[dict[str, Any]]:
        data = self._load()
        agents = []
        for agent_id, info in sorted(data.get("agents", {}).items()):
            workspace = Path(info["workspace"])
            agents.append({
                "agent_id": agent_id,
                "workspace": str(workspace),
                "mounts": info.get("mounts", []),
                "model": info.get("model"),
                "created_at": info.get("created_at", ""),
            })
        return agents

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        return self._load().get("agents", {}).get(agent_id)

    def create_agent(
        self,
        agent_id: str,
        *,
        workspace: str | None = None,
        mounts: list[dict[str, str]] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        data = self._load()
        if agent_id in data.get("agents", {}):
            return {"error": "agent already exists", "agent_id": agent_id}

        ws = Path(workspace) if workspace else self.workspaces_dir / agent_id
        ws.mkdir(parents=True, exist_ok=True)
        (ws / ".arion" / "inbox").mkdir(parents=True, exist_ok=True)

        mount_specs = []
        for m in mounts or []:
            name = m.get("name", "").strip()
            path = m.get("path", "").strip()
            if not name or not path:
                continue
            mount_specs.append({"name": name, "path": str(Path(path).resolve())})

        data.setdefault("agents", {})[agent_id] = {
            "workspace": str(ws.resolve()),
            "mounts": mount_specs,
            "model": model,
            "created_at": datetime.now().isoformat(),
        }
        self._save(data)

        self._ensure_main_thread(agent_id, ws)
        return {"status": "created", "agent_id": agent_id, "workspace": str(ws)}

    def delete_agent(self, agent_id: str, *, remove_workspace: bool = False) -> dict[str, Any]:
        data = self._load()
        info = data.get("agents", {}).pop(agent_id, None)
        if info is None:
            return {"error": "agent not found"}
        self._save(data)
        if remove_workspace:
            ws = Path(info["workspace"])
            if ws.exists() and ws.is_dir():
                shutil.rmtree(ws)
        return {"status": "deleted", "agent_id": agent_id}

    def update_agent_model(self, agent_id: str, model: str) -> dict[str, Any]:
        data = self._load()
        if agent_id not in data.get("agents", {}):
            return {"error": "agent not found"}
        data["agents"][agent_id]["model"] = model
        self._save(data)
        return {"status": "ok", "agent_id": agent_id, "model": model}

    def _ensure_main_thread(self, agent_id: str, workspace: Path) -> None:
        threads_file = workspace / ".arion" / "threads.json"
        tid = default_thread_id(agent_id)
        meta: dict[str, Any] = {}
        if threads_file.exists():
            meta = json.loads(threads_file.read_text(encoding="utf-8-sig"))
        if tid not in meta:
            meta[tid] = {
                "name": "Main",
                "created_at": datetime.now().isoformat(),
            }
            threads_file.parent.mkdir(parents=True, exist_ok=True)
            threads_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def mount_map(self, agent_id: str) -> dict[str, Path]:
        info = self.get_agent(agent_id)
        if not info:
            return {}
        return {
            m["name"]: Path(m["path"]).resolve()
            for m in info.get("mounts", [])
        }
