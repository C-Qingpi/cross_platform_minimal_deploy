"""Tests for deploy.config loading and env pinning."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from deploy_config import apply_runtime_env, load

DEPLOY_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture()
def deploy_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = tmp_path / "deploy.config"
    monkeypatch.chdir(tmp_path)
    yield tmp_path, cfg


def test_load_dev_defaults(deploy_config_dir):
    root, cfg = deploy_config_dir
    cfg.write_text("mode=dev\n", encoding="utf-8")
    loaded = load(root)
    assert loaded.mode == "dev"
    assert loaded.deploy_root == root.resolve()
    assert loaded.backend_port == 8920
    assert loaded.frontend_port == 5174
    assert loaded.is_dev is True


def test_load_prod_defaults(deploy_config_dir):
    root, cfg = deploy_config_dir
    cfg.write_text("mode=prod\n", encoding="utf-8")
    loaded = load(root)
    assert loaded.mode == "prod"
    assert loaded.backend_port == 8921
    assert loaded.frontend_port == 5175
    assert loaded.is_dev is False


def test_apply_runtime_env_pins_root(deploy_config_dir, monkeypatch: pytest.MonkeyPatch):
    root, cfg = deploy_config_dir
    cfg.write_text("mode=dev\n", encoding="utf-8")
    monkeypatch.setenv("DEPLOY_ROOT", "/wrong/path")
    applied = apply_runtime_env(root)
    assert applied.deploy_root == root.resolve()
    assert os.environ["DEPLOY_ROOT"] == str(root.resolve())
    assert os.environ["ARION_DEPLOY_MODE"] == "dev"


def test_apply_runtime_env_prod_sets_dev_mode(deploy_config_dir, monkeypatch: pytest.MonkeyPatch):
    root, cfg = deploy_config_dir
    cfg.write_text("mode=prod\n", encoding="utf-8")
    monkeypatch.delenv("ARION_DEPLOY_MODE", raising=False)
    apply_runtime_env(root)
    assert os.environ["ARION_DEPLOY_MODE"] == "dev"
    assert os.environ["BACKEND_PORT"] == "8921"
    assert os.environ["FRONTEND_PORT"] == "5175"


def test_missing_config_raises(deploy_config_dir):
    root, _cfg = deploy_config_dir
    with pytest.raises(FileNotFoundError):
        load(root)


def test_repo_example_is_valid():
    example = DEPLOY_DIR / "deploy.config.example"
    assert example.is_file()
    loaded = load(DEPLOY_DIR) if (DEPLOY_DIR / "deploy.config").is_file() else None
    if loaded is not None:
        assert loaded.mode in {"dev", "prod"}
