"""Unit tests — rate limiting layer.

Tests that the Redis-backed sliding window rate limiter blocks calls when
the per-minute limit is exceeded, and allows calls within the limit.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp_clients.aviationstack import AviationStackMCPClient
from app.utils.errors import ToolError


@pytest.fixture
def client() -> AviationStackMCPClient:
    return AviationStackMCPClient()


def _make_pipeline_mock(counter_value: int) -> MagicMock:
    """Build a pipeline mock that returns [counter_value, True] on execute().

    redis-py pipeline: pipeline() is sync, incr/expire are sync (queued),
    execute() is async and returns the list of command results.
    """
    pipeline = MagicMock()           # sync object — pipeline() returns this
    pipeline.incr = MagicMock()      # sync queue call
    pipeline.expire = MagicMock()    # sync queue call
    pipeline.execute = AsyncMock(return_value=[counter_value, True])  # async
    return pipeline


@pytest.mark.asyncio
async def test_rate_limit_allows_within_limit(client):
    """Requests within rate limit should not raise."""
    mock_redis = MagicMock()
    mock_redis.pipeline.return_value = _make_pipeline_mock(1)

    with patch("app.memory.session.get_redis", new=AsyncMock(return_value=mock_redis)):
        await client._check_rate_limit()  # Should not raise


@pytest.mark.asyncio
async def test_rate_limit_blocks_when_exceeded(client):
    """Requests exceeding rate limit must raise ToolError."""
    over_limit = client.rate_limit_per_minute + 1
    mock_redis = MagicMock()
    mock_redis.pipeline.return_value = _make_pipeline_mock(over_limit)

    with patch("app.memory.session.get_redis", new=AsyncMock(return_value=mock_redis)):
        with pytest.raises(ToolError, match="Rate limit exceeded"):
            await client._check_rate_limit()


@pytest.mark.asyncio
async def test_rate_limit_at_exact_boundary(client):
    """Request exactly at the rate limit should be allowed."""
    mock_redis = MagicMock()
    mock_redis.pipeline.return_value = _make_pipeline_mock(client.rate_limit_per_minute)

    with patch("app.memory.session.get_redis", new=AsyncMock(return_value=mock_redis)):
        await client._check_rate_limit()  # Should not raise


@pytest.mark.asyncio
async def test_rate_limit_skipped_when_redis_unavailable(client):
    """If Redis is unavailable, rate limiting is skipped gracefully."""
    with patch("app.memory.session.get_redis", new=AsyncMock(return_value=None)):
        await client._check_rate_limit()  # Should not raise


@pytest.mark.asyncio
async def test_rate_limit_skipped_on_redis_error(client):
    """Redis errors during rate limiting should not block the call."""
    mock_redis = MagicMock()
    pipeline = MagicMock()
    pipeline.incr = MagicMock()
    pipeline.expire = MagicMock()
    pipeline.execute = AsyncMock(side_effect=Exception("Redis connection error"))
    mock_redis.pipeline.return_value = pipeline

    with patch("app.memory.session.get_redis", new=AsyncMock(return_value=mock_redis)):
        await client._check_rate_limit()  # Should not raise — degrades gracefully


@pytest.mark.asyncio
async def test_rate_limit_uses_correct_redis_key(client):
    """Rate limit check should use the right Redis key pattern for incr()."""
    captured_keys = []

    pipeline = MagicMock()

    def capture_incr(key):
        captured_keys.append(key)

    pipeline.incr = MagicMock(side_effect=capture_incr)
    pipeline.expire = MagicMock()
    pipeline.execute = AsyncMock(return_value=[1, True])

    mock_redis = MagicMock()
    mock_redis.pipeline.return_value = pipeline

    with patch("app.memory.session.get_redis", new=AsyncMock(return_value=mock_redis)):
        await client._check_rate_limit()

    expected_key = f"ratelimit:{client.client_name}:rpm"
    assert expected_key in captured_keys, (
        f"Expected Redis key '{expected_key}' not found. Got: {captured_keys}"
    )
