"""Local filesystem directory browser for agent workspace selection."""

from __future__ import annotations

import os
import string
from pathlib import Path
from typing import Any


def _resolve_dir(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = p.resolve()
    else:
        p = p.resolve()
    if not p.is_dir():
        raise ValueError(f"Not a directory: {path}")
    return p


def list_roots(deploy_root: Path) -> list[dict[str, str]]:
    roots: list[dict[str, str]] = []
    home = Path.home()
    roots.append({"name": "Home", "path": str(home)})

    deploy_ws = deploy_root / "workspaces"
    deploy_ws.mkdir(parents=True, exist_ok=True)
    roots.append({"name": "Deploy workspaces", "path": str(deploy_ws.resolve())})

    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:/")
            if drive.is_dir():
                roots.append({"name": f"{letter}:", "path": str(drive)})
    else:
        roots.append({"name": "Root", "path": "/"})

    return roots


def browse(path: str) -> dict[str, Any]:
    current = _resolve_dir(path)
    parent = str(current.parent) if current.parent != current else None

    entries: list[dict[str, Any]] = []
    try:
        children = sorted(current.iterdir(), key=lambda p: p.name.lower())
    except PermissionError:
        children = []

    for child in children:
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        try:
            has_children = any(
                c.is_dir() and not c.name.startswith(".")
                for c in child.iterdir()
            )
        except PermissionError:
            has_children = False
        entries.append({
            "name": child.name,
            "path": str(child.resolve()),
            "has_children": has_children,
        })

    return {
        "path": str(current),
        "parent": parent,
        "entries": entries,
    }
