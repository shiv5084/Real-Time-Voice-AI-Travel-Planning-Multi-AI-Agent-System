"""Unit tests for the PostgreSQL episodic memory module.

Tests cover:
- save_trip_memory
- get_memories_for_destination
- get_all_memories
- build_episodic_context
- extract_and_save_lessons
- _row_to_dict helper
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers to simulate asyncpg rows
# ---------------------------------------------------------------------------

def _make_row(**kwargs):
    """Return a dict-like object simulating an asyncpg Row."""
    return kwargs


# ---------------------------------------------------------------------------
# Test: save_trip_memory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_trip_memory_success():
    """save_trip_memory should execute an INSERT and return True."""
    from app.memory import episodic

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()

    with patch.object(episodic, "_get_conn", return_value=mock_conn):
        result = await episodic.save_trip_memory(
            user_id="11111111-1111-1111-1111-111111111111",
            trip_id="22222222-2222-2222-2222-222222222222",
            destination="Tokyo",
            summary="Amazing 7-day trip to Tokyo",
            lessons_learned={
                "what_worked": ["Staying in Shinjuku", "JR Pass"],
                "what_to_avoid": ["Tsukiji on weekends — too crowded"],
                "timing_notes": "Cherry blossom season in April is beautiful",
            },
        )
    assert result is True
    mock_conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_save_trip_memory_db_unavailable():
    """save_trip_memory should return False when DB is unavailable."""
    from app.memory import episodic

    with patch.object(episodic, "_get_conn", return_value=None):
        result = await episodic.save_trip_memory(
            user_id="user1",
            trip_id="trip1",
            destination="Paris",
            summary="Short trip",
            lessons_learned={},
        )
    assert result is False


# ---------------------------------------------------------------------------
# Test: get_memories_for_destination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_memories_for_destination_found():
    """Should return memories for a matching destination."""
    from app.memory import episodic

    mock_rows = [
        _make_row(
            id="aaa",
            trip_id="bbb",
            user_id="ccc",
            destination="tokyo",
            summary="Great trip to Tokyo",
            lessons_learned=json.dumps({"what_worked": ["JR Pass"]}),
            created_at=datetime.now(timezone.utc),
            expires_at=None,
        )
    ]
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=mock_rows)
    mock_conn.close = AsyncMock()

    with patch.object(episodic, "_get_conn", return_value=mock_conn):
        memories = await episodic.get_memories_for_destination("user1", "Tokyo")

    assert len(memories) == 1
    assert memories[0]["destination"] == "tokyo"


@pytest.mark.asyncio
async def test_get_memories_for_destination_none_found():
    """Should return empty list when no memories exist for destination."""
    from app.memory import episodic

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.close = AsyncMock()

    with patch.object(episodic, "_get_conn", return_value=mock_conn):
        memories = await episodic.get_memories_for_destination("user1", "NonExistentCity")

    assert memories == []


@pytest.mark.asyncio
async def test_get_memories_returns_empty_when_db_unavailable():
    """Should return empty list gracefully when DB is unavailable."""
    from app.memory import episodic

    with patch.object(episodic, "_get_conn", return_value=None):
        memories = await episodic.get_memories_for_destination("user1", "Paris")

    assert memories == []


# ---------------------------------------------------------------------------
# Test: build_episodic_context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_episodic_context_anonymous_user():
    """Anonymous user should get empty context without DB calls."""
    from app.memory.episodic import build_episodic_context

    context = await build_episodic_context("anonymous", ["Paris"])
    assert context == {}


@pytest.mark.asyncio
async def test_build_episodic_context_repeat_destination():
    """Repeat destination should appear in context with lessons."""
    from app.memory import episodic

    mock_memories = [
        {
            "destination": "paris",
            "summary": "Wonderful 5-day Paris trip",
            "lessons_learned": {
                "what_worked": ["Staying near Marais"],
                "what_to_avoid": ["Champs-Elysées in July — very crowded"],
                "timing_notes": "Spring is ideal",
            },
        }
    ]

    with patch.object(episodic, "get_memories_for_destination", AsyncMock(return_value=mock_memories)):
        with patch.object(episodic, "get_all_memories", AsyncMock(return_value=mock_memories)):
            context = await episodic.build_episodic_context("user1", ["Paris"])

    assert "Paris" in context.get("repeat_destinations", [])
    assert "Paris" in context.get("destination_memories", {})
    lessons = context["destination_memories"]["Paris"]
    assert any("Marais" in lesson for lesson in lessons)


@pytest.mark.asyncio
async def test_build_episodic_context_no_prior_visits():
    """New destination should not appear as repeat."""
    from app.memory import episodic

    with patch.object(episodic, "get_memories_for_destination", AsyncMock(return_value=[])):
        with patch.object(episodic, "get_all_memories", AsyncMock(return_value=[])):
            context = await episodic.build_episodic_context("user1", ["NewCity"])

    assert context.get("repeat_destinations") == []
    assert context.get("destination_memories") == {}


# ---------------------------------------------------------------------------
# Test: extract_and_save_lessons
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_and_save_lessons_success():
    """Should extract lessons from state and call save_trip_memory."""
    from app.memory import episodic

    state = {
        "constraints": {
            "destinations": ["Tokyo"],
            "budget": 3000,
            "travelers": 2,
            "start_date": "2025-04-01",
        },
        "itinerary": {
            "days": [
                {"day": 1, "location": "Shinjuku", "activities": []},
                {"day": 2, "location": "Shibuya", "activities": []},
                {"day": 3, "location": "Asakusa", "activities": []},
            ]
        },
        "budget_breakdown": {
            "total_estimated_cost": 2800,
            "compliance": "within_budget",
        },
        "validation_status": "approved",
        "validation_issues": [],
        "regeneration_count": 0,
    }

    save_called = {}

    async def mock_save(user_id, trip_id, destination, summary, lessons_learned):
        save_called["args"] = {
            "user_id": user_id,
            "destination": destination,
            "lessons": lessons_learned,
        }
        return True

    with patch.object(episodic, "save_trip_memory", side_effect=mock_save):
        result = await episodic.extract_and_save_lessons("user1", "trip1", state)

    assert result is True
    assert save_called["args"]["destination"] == "Tokyo"
    lessons = save_called["args"]["lessons"]
    assert "within_budget" in lessons.get("cost_notes", "")
    assert "Shinjuku" in lessons.get("preferred_areas", [])


@pytest.mark.asyncio
async def test_extract_and_save_lessons_no_destinations():
    """Should return False when state has no destinations."""
    from app.memory.episodic import extract_and_save_lessons

    state = {"constraints": {"destinations": []}}
    result = await extract_and_save_lessons("user1", "trip1", state)
    assert result is False


# ---------------------------------------------------------------------------
# Test: _row_to_dict helper
# ---------------------------------------------------------------------------

def test_row_to_dict_converts_json_strings():
    """lessons_learned stored as JSON string should be deserialized."""
    from app.memory.episodic import _row_to_dict

    row = {
        "id": "abc123",
        "trip_id": "def456",
        "user_id": "ghi789",
        "destination": "paris",
        "summary": "test",
        "lessons_learned": '{"what_worked": ["Marais"]}',
        "created_at": datetime.now(timezone.utc),
        "expires_at": None,
    }
    result = _row_to_dict(row)
    assert isinstance(result["lessons_learned"], dict)
    assert result["lessons_learned"]["what_worked"] == ["Marais"]
    assert isinstance(result["created_at"], str)
