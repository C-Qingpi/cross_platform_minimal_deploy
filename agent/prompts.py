"""Prefab identity templates for minimal deploy.

System prompt: arion_agent ships BASE_ARION_PROMPT via IdentityMiddleware
(identity/middleware.py) — always injected as <role>. Do not duplicate here.

User prompt: wrap_user_message prepends a timestamp + "RECEIVED FROM USER:" prefix.

The WORKFLOW_METHODOLOGY constant describes the standard agent workflow
(gather → do → test → fix → deliver). It is injected as pinned_instructions
in the system message by agent_runner.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from arion_agent.identity.templates import STANDARD_DEEPMEMORY, STANDARD_SOUL

DEFAULT_SOUL = STANDARD_SOUL
DEFAULT_DEEPMEMORY = STANDARD_DEEPMEMORY

# ---------------------------------------------------------------------------
# Workflow methodology — injected as pinned_instructions (system prompt)
# ---------------------------------------------------------------------------

WORKFLOW_METHODOLOGY = """\
## GATHER → DO → TEST → FIX → DELIVER

When handling user requests, follow these phases **in order**:

### 1. GATHER
Before taking any action, retrieve and **re-read** all documents relevant to the
user's question. Do not rely on stale context from memory — files that were read
earlier may have been evicted from context by summarization. Re-read the actual
current file contents, especially:

- **README** and any project-level documentation
- **skills.md** (agent skill definitions)
- The file(s) under active development or of editing interest
- Guidelines, configuration files, and any pinned instructions
- SOUL.md, DEEPMEMORY.md, SHALLOW_MEMORY.md (your own identity/memory)

Use `list_files` to survey what exists before diving in.

### 2. DO
Execute the planned changes or actions using available tools. Prefer precise,
minimal edits. Read before editing. Verify before assuming.

### 3. TEST
Run real, executable tests to identify unthought-of issues. Do not skip testing.
Tests must be concrete and verifiable — not hypothetical. Edge cases matter.

### 4. FIX
Address any issues found during testing. Iterate until all tests pass
and the implementation is solid.

### 5. DELIVER
Present the result clearly. Summarise what was done, what was tested, and
any relevant outcomes or decisions.
"""

# ---------------------------------------------------------------------------
# User message wrapper
# ---------------------------------------------------------------------------

_TIMESTAMP_FMT = "%Y-%m-%d-(%A)-%Z-%H-%M-%S"


def _local_now() -> datetime:
    """Current local datetime (with timezone info)."""
    return datetime.now(timezone.utc).astimezone()


def wrap_user_message(content: str) -> str:
    """Wrap user input with a timestamp prefix.

    Returns:  "<timestamp> RECEIVED FROM USER: <stripped content>"

    Example: "2026-06-19-(Thursday)-CST-14-30-00 RECEIVED FROM USER: hello"
    """
    now = _local_now()
    ts = now.strftime(_TIMESTAMP_FMT)
    return f"{ts} RECEIVED FROM USER: {content.strip()}"
