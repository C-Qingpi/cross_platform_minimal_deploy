"""Prefab identity templates for minimal deploy.

System prompt: arion_agent ships BASE_ARION_PROMPT via IdentityMiddleware
(identity/middleware.py) — always injected as <role>. Do not duplicate here.

User prompt: wrap_user_message wraps each user message with a timestamp prefix
and a workflow methodology suffix that guides the agent's process.
"""

from __future__ import annotations

from datetime import datetime, timezone

from arion_agent.identity.templates import STANDARD_DEEPMEMORY, STANDARD_SOUL

DEFAULT_SOUL = STANDARD_SOUL
DEFAULT_DEEPMEMORY = STANDARD_DEEPMEMORY

# ---------------------------------------------------------------------------
# Workflow methodology — appended to every user message
# ---------------------------------------------------------------------------

WORKFLOW_METHODOLOGY = """\
<workflow>
WORKFLOW: GATHER → REVIEW → DO → TEST → FIX → CLEANUP → DELIVER.

- RECONCILE: Check prior user prompts for unfinished work before starting the new
  request. Only skip when the user explicitly says "focus on the new task" or similar.
- GATHER: Read all relevant files before editing. Context windows evict — re-read before acting.
  Start broad, then narrow: use semantic search to grasp context and locate relevant areas,
  then list files to orient, then use targeted grep/glob for precise information.
  Particularly, refresh memory on skills, guidelines, pinned instructions, and README files
  that may have been evicted from conversation history — these are your compass.
- REVIEW: Before acting, present an overall plan and confirm with the user.
  Once confirmed, proceed without re-asking or stalling unless a user decision is
  genuinely required.
- DO: Make surgical, minimal changes. One step at a time.
- TEST: Validate with real container smoke tests and end-to-end checks — not just
  unit tests. Verify the application actually works in its target environment.
- FIX: If a test fails, diagnose the root cause, not the symptom. Re-read the
  relevant code before fixing.
- CLEANUP: Tidy up one-time scripts, organize new files and folders into existing
  project directories, and update record/log/plan files if needed.
- DELIVER: Confirm all tests pass and the result is correct. Read the actual output
  files (HTML, logs, etc.) to verify content — do not rely on labels or summary flags alone.
</workflow>"""

# ---------------------------------------------------------------------------
# User message wrapper
# ---------------------------------------------------------------------------

_TIMESTAMP_FMT = "%Y-%m-%d-(%A)-%Z-%H-%M-%S"


def _local_now() -> datetime:
    """Current local datetime (with timezone info)."""
    return datetime.now(timezone.utc).astimezone()


def wrap_user_message(content: str) -> str:
    """Wrap user input with timestamp prefix and workflow suffix.

    Format:
      <timestamp> RECEIVED FROM USER: <stripped content>
      --- END OF USER MESSAGE ---
      <workflow>
      WORKFLOW: GATHER → REVIEW → DO → TEST → FIX → DELIVER.
      ...
      </workflow>

    The --- END OF USER MESSAGE --- delimiter and <workflow> tags ensure
    the LLM sees the workflow as meta-instruction, not user content.

    Example:
      2026-06-19-(Thursday)-CST-14-30-00 RECEIVED FROM USER: hello
      --- END OF USER MESSAGE ---
      <workflow>
      WORKFLOW: GATHER → REVIEW → DO → TEST → FIX → DELIVER.
      ...
      </workflow>
    """
    now = _local_now()
    ts = now.strftime(_TIMESTAMP_FMT)
    stripped = content.strip()
    wrapper = f"{ts} RECEIVED FROM USER: {stripped}"
    if stripped:
        wrapper += f"\n--- END OF USER MESSAGE ---\n{WORKFLOW_METHODOLOGY}"
    return wrapper
