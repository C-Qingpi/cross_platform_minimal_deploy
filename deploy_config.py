"""Deploy checkout configuration: mode, ports, pinned root."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

MODE_PORTS: dict[str, tuple[int, int]] = {
    "dev": (8920, 5174),
    "prod": (8921, 5175),
}


@dataclass(frozen=True)
class DeployConfig:
    mode: str
    deploy_root: Path
    backend_port: int
    frontend_port: int

    @property
    def is_dev(self) -> bool:
        return self.mode == "dev"


def _parse_config_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid deploy.config line: {raw!r}")
        key, val = line.split("=", 1)
        data[key.strip().lower()] = val.strip()
    return data


def load(deploy_dir: Path) -> DeployConfig:
    deploy_dir = deploy_dir.resolve()
    cfg_path = deploy_dir / "deploy.config"
    if not cfg_path.is_file():
        example = deploy_dir / "deploy.config.example"
        raise FileNotFoundError(
            f"missing {cfg_path.name} — copy {example.name} to deploy.config "
            "and set mode=dev or mode=prod"
        )
    data = _parse_config_file(cfg_path)
    mode = data.get("mode", "").lower()
    if mode not in MODE_PORTS:
        raise ValueError(f"deploy.config mode must be dev or prod, got {mode!r}")
    default_backend, default_frontend = MODE_PORTS[mode]
    backend_port = int(data["backend_port"]) if "backend_port" in data else default_backend
    frontend_port = int(data["frontend_port"]) if "frontend_port" in data else default_frontend
    return DeployConfig(
        mode=mode,
        deploy_root=deploy_dir,
        backend_port=backend_port,
        frontend_port=frontend_port,
    )


def apply_runtime_env(deploy_dir: Path) -> DeployConfig:
    """Pin DEPLOY_ROOT to this checkout; set ports and ARION_DEPLOY_MODE from deploy.config."""
    cfg = load(deploy_dir)
    os.environ["DEPLOY_ROOT"] = str(cfg.deploy_root)
    os.environ["BACKEND_PORT"] = str(cfg.backend_port)
    os.environ["FRONTEND_PORT"] = str(cfg.frontend_port)
    if cfg.is_dev:
        os.environ["ARION_DEPLOY_MODE"] = "dev"
    else:
        os.environ.pop("ARION_DEPLOY_MODE", None)
    return cfg


def _emit_shell(deploy_dir: Path, *, shell: str) -> None:
    cfg = load(deploy_dir)
    root = str(cfg.deploy_root)
    lines: list[str]
    if shell == "bash":
        lines = [
            f'export DEPLOY_MODE="{cfg.mode}"',
            f'export DEPLOY_ROOT="{root}"',
            f"export BACKEND_PORT={cfg.backend_port}",
            f"export FRONTEND_PORT={cfg.frontend_port}",
        ]
        if cfg.is_dev:
            lines.append('export ARION_DEPLOY_MODE=dev')
        else:
            lines.append("unset ARION_DEPLOY_MODE")
    elif shell == "cmd":
        lines = [
            f"set DEPLOY_MODE={cfg.mode}",
            f"set DEPLOY_ROOT={root}",
            f"set BACKEND_PORT={cfg.backend_port}",
            f"set FRONTEND_PORT={cfg.frontend_port}",
        ]
        if cfg.is_dev:
            lines.append("set ARION_DEPLOY_MODE=dev")
    else:
        raise ValueError(f"unsupported shell: {shell!r}")
    sys.stdout.write("\n".join(lines) + "\n")


def main() -> None:
    deploy_dir = Path(__file__).resolve().parent
    if len(sys.argv) >= 2 and sys.argv[1] == "--emit-bash":
        _emit_shell(deploy_dir, shell="bash")
        return
    if len(sys.argv) >= 2 and sys.argv[1] == "--emit-cmd":
        _emit_shell(deploy_dir, shell="cmd")
        return
    cfg = load(deploy_dir)
    print(f"mode={cfg.mode} root={cfg.deploy_root} backend={cfg.backend_port} frontend={cfg.frontend_port}")


if __name__ == "__main__":
    main()
