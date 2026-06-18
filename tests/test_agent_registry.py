"""Tests for agent registry workspace handling."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPLOY_DIR))

from agent_registry import AgentRegistry


def test_normalize_workspaces_parent_to_agent_folder():
    with tempfile.TemporaryDirectory() as td:
        deploy = Path(td)
        reg = AgentRegistry(deploy)
        result = reg.create_agent("lab", workspace=str(deploy / "workspaces"))
        assert "error" not in result
        assert result["workspace"] == str((deploy / "workspaces" / "lab").resolve())


def test_existing_folder_as_workspace_root():
    with tempfile.TemporaryDirectory() as td:
        deploy = Path(td)
        project = deploy / "my-project"
        project.mkdir()
        reg = AgentRegistry(deploy)
        result = reg.create_agent("lab", workspace=str(project))
        assert result["workspace"] == str(project.resolve())
        assert (project / ".arion" / "inbox").is_dir()


def test_reject_workspace_inside_another_agent():
    with tempfile.TemporaryDirectory() as td:
        deploy = Path(td)
        reg = AgentRegistry(deploy)
        reg.create_agent("default")
        nested = deploy / "workspaces" / "default" / "nested"
        nested.mkdir(parents=True)
        result = reg.create_agent("child", workspace=str(nested))
        assert result["error"]
        assert "inside agent 'default'" in result["error"]


def test_skip_mount_same_as_workspace():
    with tempfile.TemporaryDirectory() as td:
        deploy = Path(td)
        project = deploy / "my-project"
        project.mkdir()
        reg = AgentRegistry(deploy)
        reg.create_agent(
            "lab",
            workspace=str(project),
            mounts=[{"name": "dup", "path": str(project)}],
        )
        data = json.loads(reg.registry_path.read_text(encoding="utf-8"))
        assert data["agents"]["lab"]["mounts"] == []
