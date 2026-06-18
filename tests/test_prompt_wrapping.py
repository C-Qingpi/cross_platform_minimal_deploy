"""Tests for user prompt wrapping (timestamp prefix + workflow methodology suffix).

Verifies:
  1. wrap_user_message prepends a timestamp in the correct format.
  2. The timestamp includes: date, weekday, timezone, hours/minutes/seconds.
  3. The phrase "RECEIVED FROM USER:" appears after the timestamp.
  4. Content is preserved (stripped) after the prefix.
  5. The workflow methodology is appended after the user content.
  6. WORKFLOW_METHODOLOGY is a short non-empty string with all five phases.
  7. Edge cases: empty content, whitespace-only content, content with leading/trailing spaces.
  8. Timestamp reflects local timezone (not UTC).
  9. agent_runner passes WORKFLOW_METHODOLOGY as pinned_instructions AND it appears in wrap_user_message.
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

    def test_output_contains_original_content(self) -> None:
        content = "Run the tests please."
        result = wrap_user_message(content)
        assert content in result, f"Expected {content!r} in result, got {result!r}"

    def test_content_stripped(self) -> None:
        result = wrap_user_message("  hello world  ")
        assert "hello world" in result, (
            f"Content should be stripped, got: {result!r}"
        )
        assert "  hello world  " not in result

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

    def test_special_characters_preserved(self) -> None:
        content = "price is $50, look at file 'foo.py', env=TEST"
        result = wrap_user_message(content)
        assert content in result, f"Special chars not preserved: {result!r}"

    def test_newlines_in_content(self) -> None:
        content = "line1\nline2\nline3"
        result = wrap_user_message(content)
        assert content in result, f"Newlines not preserved: {result!r}"


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
# Workflow methodology suffix tests
# ---------------------------------------------------------------------------


class TestWorkflowMethodologySuffix:
    """The workflow methodology must be appended to non-empty user messages."""

    PHASES = ["GATHER", "DO", "TEST", "FIX", "DELIVER"]

    def test_methodology_appended_to_content(self) -> None:
        """Non-empty content gets the methodology suffix after a newline."""
        result = wrap_user_message("hello")
        assert WORKFLOW_METHODOLOGY in result, (
            f"Workflow methodology should appear in wrapped message.\n"
            f"  Got: {result!r}"
        )

    def test_methodology_not_appended_to_empty(self) -> None:
        """Empty content should not get the methodology suffix."""
        result = wrap_user_message("")
        assert WORKFLOW_METHODOLOGY not in result, (
            f"Empty content should not include methodology.\n"
            f"  Got: {result!r}"
        )

    def test_methodology_is_short(self) -> None:
        """Methodology should be a few sentences, not a long document."""
        assert isinstance(WORKFLOW_METHODOLOGY, str)
        assert 30 < len(WORKFLOW_METHODOLOGY) < 800, (
            f"Methodology should be concise (30-800 chars), got {len(WORKFLOW_METHODOLOGY)}"
        )

    def test_contains_all_phases(self) -> None:
        for phase in self.PHASES:
            assert phase in WORKFLOW_METHODOLOGY, (
                f"Phase {phase!r} not found in WORKFLOW_METHODOLOGY"
            )

    def test_phases_in_order(self) -> None:
        """Check the five phases appear in GATHER→DO→TEST→FIX→DELIVER order."""
        indices = [WORKFLOW_METHODOLOGY.index(phase) for phase in self.PHASES]
        assert indices == sorted(indices), (
            f"Phases not in order. Found at indices: "
            f"{list(zip(self.PHASES, indices))}"
        )

    def test_newline_separates_content_from_methodology(self) -> None:
        """The methodology should be clearly separated from user content by a delimiter."""
        result = wrap_user_message("hello")
        assert "--- END OF USER MESSAGE ---" in result, (
            f"Expected separator line in result.\n"
            f"  Got: {result!r}"
        )
        assert "<workflow>" in result, (
            f"Expected <workflow> opening tag in result.\n"
            f"  Got: {result!r}"
        )
        assert "</workflow>" in result, (
            f"Expected </workflow> closing tag in result.\n"
            f"  Got: {result!r}"
        )
        # Verify ordering: user message → separator → workflow tags
        parts = result.split("\n")
        user_line = next(i for i, p in enumerate(parts) if "RECEIVED FROM USER:" in p)
        sep_line = next(i for i, p in enumerate(parts) if "END OF USER MESSAGE" in p)
        wf_open = next(i for i, p in enumerate(parts) if "<workflow>" in p)
        assert user_line < sep_line < wf_open, (
            f"Order should be: user message → separator → workflow.\n"
            f"  Line indices: user={user_line}, sep={sep_line}, workflow={wf_open}\n"
            f"  Parts: {parts}"
        )


# ---------------------------------------------------------------------------
# Integration: agent_runner passes pinned_instructions AND wrap_user_message
# ---------------------------------------------------------------------------


class TestPinnedInstructionsWired:
    """Methodology is in pinned_instructions (system prompt) AND user messages."""

    def test_pinned_instructions_in_create_call(self) -> None:
        """agent_runner.create_agent_instance must pass pinned_instructions=WORKFLOW_METHODOLOGY."""
        agent_runner_path = DEPLOY_DIR / "agent" / "agent_runner.py"
        source = agent_runner_path.read_text(encoding="utf-8")

        assert "pinned_instructions=WORKFLOW_METHODOLOGY" in source, (
            "agent_runner.py must pass pinned_instructions=WORKFLOW_METHODOLOGY "
            "to create_arion_agent. Check the create_agent_instance function."
        )

    def test_workflow_import_present(self) -> None:
        """WORKFLOW_METHODOLOGY must be imported in agent_runner.py."""
        agent_runner_path = DEPLOY_DIR / "agent" / "agent_runner.py"
        source = agent_runner_path.read_text(encoding="utf-8")

        assert "WORKFLOW_METHODOLOGY" in source, (
            "agent_runner.py must import WORKFLOW_METHODOLOGY from prompts. "
            "It is used as pinned_instructions in create_agent_instance."
        )


# ---------------------------------------------------------------------------
# Sanity check
# ---------------------------------------------------------------------------


class TestSanityCheck:
    """Quick functional check — run manually with pytest -s to see output."""

    def test_real_output_example(self) -> None:
        result = wrap_user_message("run tests")
        print(f"\nWrapped output:\n{result}")
        assert result.startswith("20")  # starts with year
        assert "RECEIVED FROM USER: run tests" in result
        assert "--- END OF USER MESSAGE ---" in result
        assert "<workflow>" in result
        assert "GATHER" in result


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
