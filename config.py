"""Persistent TOML configuration for minimal deploy."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEPLOY_DIR = Path(__file__).resolve().parent
CONFIG_PATH = DEPLOY_DIR / "agent_config.toml"

KNOWN_PROVIDERS = ("deepseek", "openai", "anthropic", "google_genai", "moonshot")

DEFAULT_MODEL = "deepseek:deepseek_v4_flash"

_ENV_SEED_MAP: dict[str, dict[str, str]] = {
    "deepseek": {"api_key": "DEEPSEEK_API_KEY", "base_url": "DEEPSEEK_API_BASE"},
    "openai": {"api_key": "OPENAI_API_KEY", "base_url": "OPENAI_API_BASE"},
    "anthropic": {"api_key": "ANTHROPIC_API_KEY", "base_url": "ANTHROPIC_API_URL"},
    "google_genai": {"api_key": "GOOGLE_API_KEY", "base_url": "GOOGLE_API_BASE"},
    "moonshot": {"api_key": "MOONSHOT_API_KEY"},
}

_ENV_APPLY_MAP: dict[str, dict[str, str | list[str]]] = {
    "deepseek": {"api_key": ["DEEPSEEK_API_KEY"], "base_url": ["DEEPSEEK_API_BASE"]},
    "openai": {"api_key": ["OPENAI_API_KEY"], "base_url": ["OPENAI_API_BASE", "OPENAI_BASE_URL"]},
    "anthropic": {"api_key": ["ANTHROPIC_API_KEY"], "base_url": ["ANTHROPIC_API_URL"]},
    "google_genai": {"api_key": ["GOOGLE_API_KEY"], "base_url": ["GOOGLE_API_BASE"]},
    "moonshot": {"api_key": ["MOONSHOT_API_KEY"]},
}

_TEMPLATE = """\
# Minimal Agent Deploy Configuration

[model]
default = "{model}"

{providers_block}
"""


def _providers_to_toml(providers: dict[str, dict[str, str]]) -> str:
    blocks: list[str] = []
    for name in KNOWN_PROVIDERS:
        settings = providers.get(name, {})
        if not settings:
            continue
        lines = [f"[providers.{name}]"]
        for key in ("api_key", "base_url"):
            val = settings.get(key, "")
            if val:
                lines.append(f'{key} = "{val}"')
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _seed_from_env() -> dict:
    model = os.environ.get("DEFAULT_MODEL", DEFAULT_MODEL)
    providers: dict[str, dict[str, str]] = {}
    for provider, mapping in _ENV_SEED_MAP.items():
        cfg: dict[str, str] = {}
        for key, env_var in mapping.items():
            val = os.environ.get(env_var)
            if val:
                cfg[key] = val
        if cfg:
            providers[provider] = cfg
    return {"model": {"default": model}, "providers": providers}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[no-redef]
        try:
            with open(CONFIG_PATH, "rb") as f:
                return tomllib.load(f)
        except Exception:
            logger.exception("Failed to parse %s, re-seeding", CONFIG_PATH)

    config = _seed_from_env()
    _write_config(config)
    logger.info("Seeded agent_config.toml (model=%s)", config["model"]["default"])
    return config


def _write_config(config: dict) -> None:
    model = config.get("model", {}).get("default", DEFAULT_MODEL)
    providers = config.get("providers", {})
    content = _TEMPLATE.format(
        model=model,
        providers_block=_providers_to_toml(providers),
    )
    tmp = CONFIG_PATH.with_suffix(".toml.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def save_config(config: dict) -> None:
    _write_config(config)
    logger.info("Saved agent_config.toml")


def get_model() -> str:
    config = load_config()
    return config.get("model", {}).get("default", DEFAULT_MODEL)


def update_config(*, model: str | None = None, providers: dict | None = None) -> dict:
    config = load_config()
    if model is not None:
        config.setdefault("model", {})["default"] = model
    if providers is not None:
        existing = config.get("providers", {})
        for prov_name, prov_settings in providers.items():
            if prov_name not in existing:
                existing[prov_name] = {}
            for key, value in prov_settings.items():
                if value:
                    existing[prov_name][key] = value
        config["providers"] = existing
    save_config(config)
    return config


def apply_provider_env(config: dict | None = None) -> None:
    if config is None:
        config = load_config()
    providers = config.get("providers", {})
    for provider_name in KNOWN_PROVIDERS:
        env_map = _ENV_APPLY_MAP.get(provider_name, {})
        if provider_name not in providers:
            continue
        for _key, env_vars in env_map.items():
            targets = env_vars if isinstance(env_vars, list) else [env_vars]
            for ev in targets:
                os.environ.pop(ev, None)
        settings = providers[provider_name]
        for key, env_vars in env_map.items():
            value = settings.get(key)
            if not value:
                continue
            targets = env_vars if isinstance(env_vars, list) else [env_vars]
            for ev in targets:
                os.environ[ev] = value


def register_proxies() -> None:
    from arion_agent.providers.moonshot import ChatMoonshot
    from arion_agent.providers.resolver import ProxySpec, register_proxy

    register_proxy("moonshot", ProxySpec(
        api_key_env="MOONSHOT_API_KEY",
        default_base_url="https://api.moonshot.cn/v1",
        style="openai",
        model_adapter=ChatMoonshot,
    ))


def config_to_safe_dict(config: dict | None = None) -> dict:
    if config is None:
        config = load_config()
    safe = {"model": config.get("model", {}).get("default", "")}
    safe["providers"] = {}
    for prov_name, settings in config.get("providers", {}).items():
        safe_settings: dict[str, str] = {}
        for key, value in settings.items():
            if key == "api_key" and value:
                safe_settings[key] = value[:8] + "..." if len(value) > 8 else "***"
            else:
                safe_settings[key] = value
        safe["providers"][prov_name] = safe_settings
    return safe
