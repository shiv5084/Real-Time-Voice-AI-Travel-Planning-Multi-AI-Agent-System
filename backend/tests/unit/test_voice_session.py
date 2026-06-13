"""
Unit tests for VoiceSessionManager.build_augmented_request

Bug condition: collected_texts=[] should return user message content, not empty string.

These tests encode the bug conditions and expected fixed behavior.
Tests marked with "BUG CONDITION" FAIL on unfixed code — failure confirms the bug exists.
Tests marked with "PRESERVATION" PASS on both unfixed and fixed code.
"""

import pytest
from app.voice.session import VoiceSessionManager


class TestBuildAugmentedRequest:
    """Tests for VoiceSessionManager.build_augmented_request."""

    def setup_method(self):
        """Create a fresh VoiceSessionManager for each test."""
        self.manager = VoiceSessionManager()

    # ── Bug Condition Test (Task 1.4) ────────────────────────────────────────

    def test_build_augmented_request_empty_collected_texts_falls_back_to_messages(self):
        """
        BUG CONDITION: collected_texts=[] should return user message content, not empty string.

        Bug: build_augmented_request returns "\n\n".join([]) == "" when collected_texts
        is empty, even if messages contains useful user content.

        EXPECTED OUTCOME on UNFIXED code: FAILS
        (returns "" instead of "5 days in Paris")

        Validates: Requirements 1.5
        """
        session = {
            "session_id": "test-123",
            "collected_texts": [],
            "messages": [
                {"role": "user", "content": "5 days in Paris"},
                {"role": "assistant", "content": "What is your budget?"}
            ]
        }
        result = self.manager.build_augmented_request(session)

        # On UNFIXED code: result == "" (empty string) — test FAILS
        # On FIXED code: result == "5 days in Paris" — test PASSES
        assert result == "5 days in Paris", (
            f"Expected '5 days in Paris', got '{result}'. "
            f"Bug: collected_texts=[] causes build_augmented_request to return "
            f"empty string instead of falling back to user message content."
        )

    def test_build_augmented_request_empty_collected_texts_multiple_user_turns(self):
        """
        BUG CONDITION variant: multiple user turns in messages, empty collected_texts.

        EXPECTED OUTCOME on UNFIXED code: FAILS (returns "" not joined user content)
        """
        session = {
            "session_id": "test-456",
            "collected_texts": [],
            "messages": [
                {"role": "assistant", "content": "Where would you like to go?"},
                {"role": "user", "content": "Tokyo"},
                {"role": "assistant", "content": "How many days?"},
                {"role": "user", "content": "7 days"},
            ]
        }
        result = self.manager.build_augmented_request(session)

        # On UNFIXED code: result == "" — FAILS
        # On FIXED code: result == "Tokyo\n\n7 days" — PASSES
        assert result != "", (
            f"Bug confirmed: build_augmented_request returned empty string "
            f"when collected_texts=[] but messages contains user content. "
            f"Got: '{result}'"
        )
        assert "Tokyo" in result, f"Expected 'Tokyo' in result, got: '{result}'"

    # ── Preservation Tests (Task 2.4) ─────────────────────────────────────────

    def test_build_augmented_request_non_empty_collected_texts_returns_joined_string(self):
        """
        PRESERVATION: non-empty collected_texts returns the exact joined string.
        This test PASSES on both unfixed and fixed code — it verifies no regression.

        Validates: Requirements 3.5
        """
        session = {
            "session_id": "test-789",
            "collected_texts": ["Paris trip", "$3000 budget"],
            "messages": [
                {"role": "user", "content": "Paris trip"},
                {"role": "user", "content": "$3000 budget"},
            ]
        }
        result = self.manager.build_augmented_request(session)

        # Both unfixed and fixed code should return this
        expected = "Paris trip\n\n$3000 budget"
        assert result == expected, (
            f"Regression: non-empty collected_texts should still return "
            f"joined string. Expected '{expected}', got '{result}'"
        )

    def test_build_augmented_request_single_collected_text(self):
        """
        PRESERVATION: single item in collected_texts returns that item unchanged.
        """
        session = {
            "session_id": "test-single",
            "collected_texts": ["5 days in London with $2000 budget"],
            "messages": [
                {"role": "user", "content": "5 days in London with $2000 budget"},
            ]
        }
        result = self.manager.build_augmented_request(session)
        assert result == "5 days in London with $2000 budget"

    def test_build_augmented_request_collected_texts_takes_priority_over_messages(self):
        """
        PRESERVATION: when collected_texts is non-empty, it takes priority over messages.
        The result must equal the joined collected_texts, not the messages.
        """
        session = {
            "session_id": "test-priority",
            "collected_texts": ["Actual trip request"],
            "messages": [
                {"role": "user", "content": "Different content"},
            ]
        }
        result = self.manager.build_augmented_request(session)
        assert result == "Actual trip request", (
            f"collected_texts should take priority. Expected 'Actual trip request', got '{result}'"
        )

    def test_build_augmented_request_completely_empty_session(self):
        """
        PRESERVATION: completely empty session (no texts and no messages)
        should return empty string gracefully (not raise an exception).
        """
        session = {
            "session_id": "test-empty",
            "collected_texts": [],
            "messages": []
        }
        # Should not raise — may return "" which is acceptable for a totally empty session
        result = self.manager.build_augmented_request(session)
        assert isinstance(result, str)  # returns a string, not None or an exception

    def test_build_augmented_request_none_collected_texts_treated_as_empty(self):
        """
        PRESERVATION: collected_texts=None should be treated the same as [].
        The existing code uses `session.get("collected_texts") or []` which
        handles None correctly.
        """
        session = {
            "session_id": "test-none",
            "collected_texts": None,
            "messages": [
                {"role": "user", "content": "Weekend in Rome"},
            ]
        }
        # On UNFIXED code: returns "" (None treated as empty, no fallback)
        # On FIXED code: returns "Weekend in Rome" (fallback to messages)
        result = self.manager.build_augmented_request(session)
        assert isinstance(result, str)
        # The bug condition: result is "" on unfixed code
        # We document this but don't assert fixed behavior here
        # (that assertion is in the primary bug test above)
