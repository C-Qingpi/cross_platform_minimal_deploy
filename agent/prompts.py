"""Prefab identity templates for minimal deploy.

System prompt: arion_agent ships BASE_ARION_PROMPT via IdentityMiddleware
(identity/middleware.py) — always injected as <role>. Do not duplicate here.

User prompt: arion has no built-in user wrapper; pass-through is the default.
"""

from __future__ import annotations

from arion_agent.identity.templates import STANDARD_DEEPMEMORY, STANDARD_SOUL

DEFAULT_SOUL = STANDARD_SOUL
DEFAULT_DEEPMEMORY = STANDARD_DEEPMEMORY


def wrap_user_message(content: str) -> str:
    """Pass user input through unchanged (no deploy-specific wrapper)."""
    return content.strip()
