"""Reset deploy registry to a single default agent and clear runner/UI state.

Usage (from cross_platform_minimal_deploy):
  python scripts/reset_registry.py
  python scripts/reset_registry.py --deploy-root /path/to/cross_platform_minimal_deploy
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def reset(deploy_root: Path, *, model: str = "deepseek:deepseek_v4_flash") -> None:
    deploy_root = deploy_root.resolve()
    workspaces_dir = deploy_root / "workspaces"
    default_ws = workspaces_dir / "default"
    default_ws.mkdir(parents=True, exist_ok=True)

    registry = {
        "agents": {
            "default": {
                "workspace": str(default_ws.resolve()),
                "mounts": [],
                "model": model,
                "created_at": datetime.now().isoformat(),
            }
        }
    }
    registry_path = deploy_root / "agents.json"
    registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {registry_path}")

    events_file = deploy_root / ".arion" / "events.jsonl"
    events_file.parent.mkdir(parents=True, exist_ok=True)
    events_file.write_text("", encoding="utf-8")
    print(f"Cleared {events_file}")

    arion = default_ws / ".arion"
    (arion / "inbox").mkdir(parents=True, exist_ok=True)
    (arion / "message_queue.json").write_text("{}\n", encoding="utf-8")
    (arion / "threads.json").write_text(
        json.dumps(
            {
                "default-main": {
                    "name": "Main",
                    "created_at": datetime.now().isoformat(),
                    "model": model,
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    inbox = arion / "inbox" / "messages.jsonl"
    inbox.write_text("", encoding="utf-8")
    print(f"Reset default workspace state under {arion}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset agents.json to default-only and clear deploy state")
    parser.add_argument(
        "--deploy-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="cross_platform_minimal_deploy directory",
    )
    parser.add_argument("--model", default="deepseek:deepseek_v4_flash")
    args = parser.parse_args()
    reset(args.deploy_root, model=args.model)


if __name__ == "__main__":
    main()
