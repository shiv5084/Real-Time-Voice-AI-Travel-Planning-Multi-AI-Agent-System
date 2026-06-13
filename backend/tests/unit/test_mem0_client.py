"""Unit tests for the Mem0 long-term preference client.

Tests cover:
- Store and retrieve preferences via Redis fallback
- Parse preferences from memory entries
- Natural language preference extraction
- Preference merge logic
- Delete memories
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    """Return a mock Redis client for testing the Redis fallback path."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.setex = AsyncMock(return_value=True)
    redis.expire = AsyncMock(return_value=True)
    redis.lpush = AsyncMock(return_value=1)
    redis.ltrim = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    return redis


# ---------------------------------------------------------------------------
# Test: Preference storage and retrieval (Redis fallback)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_and_retrieve_preferences_redis(mock_redis):
    """Preferences stored via Redis fallback should be retrievable."""
    from app.memory.mem0_client import Mem0Client

    client = Mem0Client()
    client._initialized = True
    client._redis = mock_redis
    client._client = None  # Force Redis fallback

    prefs = {
        "food": "Japanese",
        "accommodation_type": "hotel",
        "crowd_tolerance": "low",
    }

    # Store
    stored = await client.store_preferences("user_123", prefs)
    assert stored is True
    mock_redis.set.assert_called_once()

    # Simulate Redis returning the stored value
    mock_redis.get.return_value = json.dumps(prefs)

    # Retrieve
    retrieved = await client.get_preferences("user_123")
    assert "food" in retrieved or "accommodation_type" in retrieved  # At least some fields returned


@pytest.mark.asyncio
async def test_store_preferences_merges_with_existing(mock_redis):
    """Storing new preferences should merge with existing ones, not overwrite."""
    from app.memory.mem0_client import Mem0Client

    existing_prefs = {"food": "Italian", "crowd_tolerance": "low"}
    mock_redis.get.return_value = json.dumps(existing_prefs)

    client = Mem0Client()
    client._initialized = True
    client._redis = mock_redis
    client._client = None

    new_prefs = {"accommodation_type": "luxury"}
    stored = await client.store_preferences("user_123", new_prefs)
    assert stored is True

    # Verify set was called with merged result
    call_args = mock_redis.set.call_args
    merged = json.loads(call_args[0][1])
    assert merged.get("food") == "Italian"  # Original preserved
    assert merged.get("accommodation_type") == "luxury"  # New added


@pytest.mark.asyncio
async def test_delete_user_memories_redis(mock_redis):
    """Delete should remove all keys for the user."""
    from app.memory.mem0_client import Mem0Client

    client = Mem0Client()
    client._initialized = True
    client._redis = mock_redis
    client._client = None

    deleted = await client.delete_user_memories("user_abc")
    assert deleted is True
    mock_redis.delete.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Memory parsing helpers
# ---------------------------------------------------------------------------

def test_parse_preferences_from_structured_memories():
    """Structured Redis-style memories should parse into preference dict."""
    from app.memory.mem0_client import _parse_preferences_from_memories

    memories = [
        {"memory": "food: Japanese", "metadata": {"category": "food"}},
        {"memory": "crowd_tolerance: low", "metadata": {"category": "crowd_tolerance"}},
        {"memory": "accommodation_type: luxury", "metadata": {"category": "accommodation_type"}},
    ]

    result = _parse_preferences_from_memories(memories)
    assert result.get("food") == "Japanese"
    assert result.get("crowd_tolerance") == "low"
    assert result.get("accommodation_type") == "luxury"


def test_parse_preferences_from_natural_language_memories():
    """Natural language memories from Mem0 cloud should be parsed into preferences."""
    from app.memory.mem0_client import _parse_preferences_from_memories

    memories = [
        {"memory": "The user is vegetarian and avoids meat", "metadata": {}},
        {"memory": "The user prefers luxury hotels", "metadata": {}},
        {"memory": "The user avoids crowded tourist spots", "metadata": {}},
    ]

    result = _parse_preferences_from_memories(memories)
    assert "vegetarian" in str(result.get("dietary_restrictions", "")).lower()
    assert result.get("accommodation_type") == "luxury"
    assert result.get("crowd_tolerance") == "low"


def test_parse_preferences_empty_memories():
    """Empty memory list should return empty dict."""
    from app.memory.mem0_client import _parse_preferences_from_memories

    result = _parse_preferences_from_memories([])
    assert result == {}


def test_prefs_to_natural_language():
    """Preference dict should convert to readable natural language."""
    from app.memory.mem0_client import _prefs_to_natural_language

    prefs = {
        "food": "Japanese",
        "accommodation_type": "luxury hotel",
        "dietary_restrictions": "vegetarian",
    }
    result = _prefs_to_natural_language(prefs)
    assert "Japanese" in result
    assert "luxury hotel" in result
    assert "vegetarian" in result


def test_prefs_to_natural_language_empty():
    """Empty preferences dict should return a 'no preferences' string."""
    from app.memory.mem0_client import _prefs_to_natural_language

    result = _prefs_to_natural_language({})
    assert "no specific preferences" in result.lower()


# ---------------------------------------------------------------------------
# Test: Mem0Client gracefully handles missing mem0ai package
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mem0_client_handles_import_error(mock_redis):
    """Client should fall back to Redis if mem0ai package is not installed."""
    from app.memory.mem0_client import Mem0Client

    with patch.dict("sys.modules", {"mem0": None}):
        client = Mem0Client()
        client._initialized = False  # Force re-init

        with patch("app.memory.session.get_redis", return_value=mock_redis):
            # Should not raise even without mem0ai
            mock_redis.get.return_value = json.dumps({"food": "Italian"})
            memories = await client.get_memories("user_test")
            # Either returns memories (if Redis has them) or empty list
            assert isinstance(memories, list)


# ---------------------------------------------------------------------------
# Test: get_mem0_client singleton
# ---------------------------------------------------------------------------

def test_get_mem0_client_returns_singleton():
    """get_mem0_client should return the same instance on subsequent calls."""
    import app.memory.mem0_client as mem0_module

    # Reset singleton
    mem0_module._mem0_client = None

    from app.memory.mem0_client import get_mem0_client
    c1 = get_mem0_client()
    c2 = get_mem0_client()
    assert c1 is c2

    # Cleanup
    mem0_module._mem0_client = None
