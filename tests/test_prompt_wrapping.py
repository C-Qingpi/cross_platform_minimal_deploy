"""Tests for the user prompt appendum (wrap_user_message + WORKFLOW_METHODOLOGY).

Verifies:
  1. wrap_user_message prepends a timestamp in the correct format.
  2. The timestamp includes: date, weekday, timezone, hours/minutes/seconds.
  3. The phrase "RECEIVED FROM USER:" appears after the timestamp.
  4. Content is preserved (stripped) after the prefix.
  5. WORKFLOW_METHODOLOGY constant is a non-empty string.
  6. WORKFLOW_METHODOLOGY mentions all five phases.
  7. Edge cases: empty content, whitespace-only content, content with leading/trailing spaces.
  8. Timestamp reflects local timezone (not UTC).
  9. pinned_instructions is wired correctly in agent_runner.py.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

DEPLOY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPLOY_DIR))
sys.path.insert(0, str(DEPLOY_DIR / "agent"))

from prompts import WORKFLOW_METHODOLOGY, wrap_user_message


# ---------------------------------------------------------------------------
# wrap_user_message format tests
# ---------------------------------------------------------------------------

# Pattern: YYYY-MM-DD-(Weekday)-TZ-HH-MM-SS RECEIVED FROM USER: <content>
TIMESTAMP_PREFIX_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}-\([A-Z][a-z]+\)-"
    r"[A-Z]{2,5}-"
    r"\d{2}-\d{2}-\d{2}"
    r" RECEIVED FROM USER: "
)


class TestWrapUserMessageFormat:
    """The timestamp prefix must match the expected format exactly."""

    def test_prefix_format(self) -> None:
        result = wrap_user_message("hello")
        assert TIMESTAMP_PREFIX_RE.match(result), (
            f"Prefix does not match expected format.\n"
            f"  Got: {result!r}\n"
            f"  Expected pattern: {TIMESTAMP_PREFIX_RE.pattern}"
        )

    def test_output_ends_with_original_content(self) -> None:
        content = "Run the tests please."
        result = wrap_user_message(content)
        assert result.endswith(content), f"Expected suffix {content!r}, got {result!r}"

    def test_content_stripped(self) -> None:
        result = wrap_user_message("  hello world  ")
        assert result.endswith("hello world"), (
            f"Content should be stripped, got: {result!r}"
        )

    def test_empty_content(self) -> None:
        result = wrap_user_message("")
        assert result.endswith("RECEIVED FROM USER: "), (
            f"Empty content should produce prefix-only, got: {result!r}"
        )

    def test_whitespace_only_content(self) -> None:
        result = wrap_user_message("   \t\n  ")
        assert result.endswith("RECEIVED FROM USER: "), (
            f"Whitespace content should become empty, got: {result!r}"
        )

    def test_receives_distinct_prefix(self) -> None:
        """Every call gets a fresh timestamp — confirm 'RECEIVED FROM USER:' appears."""
        result = wrap_user_message("test")
        assert "RECEIVED FROM USER:" in result

    def test_multiple_calls_different_timestamps(self) -> None:
        """Two rapid calls may produce different timestamps (time moves)."""
        r1 = wrap_user_message("first")
        r2 = wrap_user_message("second")
        # They should both be valid
        assert TIMESTAMP_PREFIX_RE.match(r1), f"First call failed: {r1!r}"
        assert TIMESTAMP_PREFIX_RE.match(r2), f"Second call failed: {r2!r}"
        # The timestamps may be identical if called in the same second — that's OK
        # but the prefix must still have the right shape

    def test_special_characters_preserved(self) -> None:
        content = "price is $50, look at file 'foo.py', env=TEST"
        result = wrap_user_message(content)
        assert result.endswith(content), f"Special chars not preserved: {result!r}"

    def test_newlines_in_content(self) -> None:
        content = "line1\nline2\nline3"
        result = wrap_user_message(content)
        assert result.endswith(content), f"Newlines not preserved: {result!r}"


class TestWrapUserMessageTimezone:
    """Timestamp should reflect the local timezone, not UTC."""

    def test_uses_local_timezone(self) -> None:
        """The timezone abbreviation in the timestamp should match local."""
        result = wrap_user_message("tzcheck")
        local_tz = datetime.now(timezone.utc).astimezone().strftime("%Z")
        assert local_tz in result, (
            f"Expected local timezone {local_tz!r} in result, got: {result!r}"
        )


# ---------------------------------------------------------------------------
# WORKFLOW_METHODOLOGY tests
# ---------------------------------------------------------------------------


class TestWorkflowMethodology:
    """The methodology constant must contain all five phases."""

    PHASES = ["GATHER", "DO", "TEST", "FIX", "DELIVER"]

    def test_is_non_empty_string(self) -> None:
        assert isinstance(WORKFLOW_METHODOLOGY, str)
        assert len(WORKFLOW_METHODOLOGY) > 200

    def test_contains_all_phases(self) -> None:
        for phase in self.PHASES:
            assert phase in WORKFLOW_METHODOLOGY, (
                f"Phase {phase!r} not found in WORKFLOW_METHODOLOGY"
            )

    def test_phases_in_order(self) -> None:
        """Check the five phase headings appear in GATHER→DO→TEST→FIX→DELIVER order."""
        indices = [WORKFLOW_METHODOLOGY.index(phase) for phase in self.PHASES]
        assert indices == sorted(indices), (
            f"Phases not in order. Found at indices: "
            f"{list(zip(self.PHASES, indices))}"
        )

    def test_gather_emphasises_reading_evicted_files(self) -> None:
        """Gather section must mention re-reading files evicted from context."""
        section = self._section_between("1. GATHER", "2. DO")
        assert "re-read" in section.lower() or "reread" in section.lower(), (
            f"Gather section should mention re-reading. Section:\n{section}"
        )

    def _section_between(self, start: str, end: str) -> str:
        idx_start = WORKFLOW_METHODOLOGY.index(f"### {start}")
        idx_end = WORKFLOW_METHODOLOGY.index(f"### {end}")
        return WORKFLOW_METHODOLOGY[idx_start:idx_end]


# ---------------------------------------------------------------------------
# Integration: agent_runner passes pinned_instructions
# ---------------------------------------------------------------------------


class TestPinnedInstructionsWired:
    """Verify create_agent_instance passes WORKFLOW_METHODOLOGY as pinned_instructions."""

    def test_pinned_instructions_in_create_call(self) -> None:
        """agent_runner.create_agent_instance must pass pinned_instructions=WORKFLOW_METHODOLOGY."""
        agent_runner_path = DEPLOY_DIR / "agent" / "agent_runner.py"
        source = agent_runner_path.read_text(encoding="utf-8")

        assert "pinned_instructions=WORKFLOW_METHODOLOGY" in source, (
            "agent_runner.py must pass pinned_instructions=WORKFLOW_METHODOLOGY "
            "to create_arion_agent. Check the create_agent_instance function."
        )


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
