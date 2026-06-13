"""Unit tests — response caching layer.

Tests that:
  - Cache hits return cached responses and skip the external call
  - Cache misses trigger the external call and store the result
  - Cache TTL is set correctly per tool type
  - Gmail calls are never cached
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp_clients.aviationstack import AviationStackMCPClient
from app.mcp_clients.gmail import GmailMCPClient
from app.mcp_clients.maps import MapsMCPClient
from app.mcp_clients.tavily import TavilyMCPClient


@pytest.fixture
def aviation_client():
    return AviationStackMCPClient()


@pytest.fixture
def maps_client():
    return MapsMCPClient()


@pytest.fixture
def gmail_client():
    return GmailMCPClient()


# ─────────────────────────────────────────────────────────────────────────────
# Cache get tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_value(aviation_client):
    """Cache get should return parsed dict on hit."""
    cached_data = {"flights": [{"flight_number": "AA100", "price_usd": 300.0}]}
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

    with patch("app.memory.session.get_redis", return_value=mock_redis):
        result = await aviation_client._cache_get("mcp_cache:aviationstack:search_flights:abc123")

    assert result == cached_data


@pytest.mark.asyncio
async def test_cache_miss_returns_none(aviation_client):
    """Cache get should return None on miss."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch("app.memory.session.get_redis", return_value=mock_redis):
        result = await aviation_client._cache_get("mcp_cache:aviationstack:search_flights:miss")

    assert result is None


@pytest.mark.asyncio
async def test_cache_get_returns_none_when_redis_unavailable(aviation_client):
    """Cache get should return None gracefully if Redis is down."""
    with patch("app.memory.session.get_redis", return_value=None):
        result = await aviation_client._cache_get("any_key")
    assert result is None


@pytest.mark.asyncio
async def test_cache_get_returns_none_on_redis_error(aviation_client):
    """Cache get should return None (not raise) on Redis errors."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))

    with patch("app.memory.session.get_redis", return_value=mock_redis):
        result = await aviation_client._cache_get("any_key")
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Cache set tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_set_stores_value(aviation_client):
    """Cache set should call redis.setex with correct key, ttl, and JSON value."""
    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock()
    data = {"flights": []}

    with patch("app.memory.session.get_redis", return_value=mock_redis):
        await aviation_client._cache_set("test_key", data, 3600)

    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args
    key, ttl, value = call_args[0]
    assert key == "test_key"
    assert ttl == 3600
    assert json.loads(value) == data


@pytest.mark.asyncio
async def test_cache_set_is_noop_when_redis_unavailable(aviation_client):
    """Cache set should not raise if Redis is unavailable."""
    with patch("app.memory.session.get_redis", return_value=None):
        await aviation_client._cache_set("key", {"data": 1}, 3600)  # no raise


@pytest.mark.asyncio
async def test_cache_set_is_noop_on_redis_error(aviation_client):
    """Cache set should not raise on Redis errors."""
    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))

    with patch("app.memory.session.get_redis", return_value=mock_redis):
        await aviation_client._cache_set("key", {"data": 1}, 3600)  # no raise


# ─────────────────────────────────────────────────────────────────────────────
# Cache TTL verification per tool
# ─────────────────────────────────────────────────────────────────────────────


def test_aviationstack_flight_ttl():
    from app.config import get_settings
    client = AviationStackMCPClient()
    assert client.cache_ttl("search_flights") == get_settings().cache_ttl_flights  # 3600


def test_maps_geocode_ttl():
    from app.config import get_settings
    client = MapsMCPClient()
    assert client.cache_ttl("google_maps_geocode") == get_settings().cache_ttl_geocoding  # 604800


def test_tavily_search_ttl():
    from app.config import get_settings
    client = TavilyMCPClient()
    assert client.cache_ttl("tavily_search") == get_settings().cache_ttl_attractions  # 86400


def test_gmail_send_email_ttl_is_zero():
    """Gmail must have zero TTL (no caching of email sends)."""
    client = GmailMCPClient()
    assert client.cache_ttl("send_email_directly") == 0


# ─────────────────────────────────────────────────────────────────────────────
# Full call with cache hit — verify external call is skipped
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_call_uses_cache_and_skips_external(maps_client):
    """When cache hits, the external MCP server must not be called."""
    cached_response = {
        "status": "success",
        "data": {
            "results": [
                {
                    "formatted_address": "Paris, France",
                    "geometry": {"location": {"lat": 48.8566, "lng": 2.3522}}
                }
            ],
            "status": "success"
        }
    }

    # Mock rate limit (no-op)
    mock_redis_rl = AsyncMock()
    mock_pipeline = AsyncMock()
    mock_pipeline.execute = AsyncMock(return_value=[1, True])
    mock_redis_rl.pipeline.return_value = mock_pipeline
    mock_redis_rl.get = AsyncMock(return_value=json.dumps(cached_response))
    mock_redis_rl.setex = AsyncMock()

    with patch("app.memory.session.get_redis", return_value=mock_redis_rl):
        with patch.object(maps_client, "_call_with_retry") as mock_ext:
            with patch.object(maps_client, "_audit_log", AsyncMock()):
                result = await maps_client.call(
                    "google_maps_geocode", {"address": "Paris"}, agent="test", skip_batch=True
                )

    # External call should NOT have been made
    mock_ext.assert_not_called()
    assert result["data"]["results"][0]["geometry"]["location"]["lat"] == 48.8566


@pytest.mark.asyncio
async def test_full_call_on_cache_miss_calls_external(maps_client):
    """When cache misses, the external MCP server must be called."""
    external_response = {
        "status": "success",
        "data": {
            "results": [
                {
                    "formatted_address": "London, UK",
                    "geometry": {"location": {"lat": 51.5074, "lng": -0.1278}}
                }
            ],
            "status": "success"
        }
    }

    mock_redis = AsyncMock()
    mock_pipeline = AsyncMock()
    mock_pipeline.execute = AsyncMock(return_value=[1, True])
    mock_redis.pipeline.return_value = mock_pipeline
    mock_redis.get = AsyncMock(return_value=None)  # Cache miss
    mock_redis.setex = AsyncMock()

    with patch("app.memory.session.get_redis", return_value=mock_redis):
        with patch.object(
            maps_client, "_call_with_retry", AsyncMock(return_value=external_response)
        ):
            with patch.object(maps_client, "_audit_log", AsyncMock()):
                result = await maps_client.call(
                    "google_maps_geocode", {"address": "London"}, agent="test", skip_batch=True
                )

    assert result["data"]["results"][0]["geometry"]["location"]["lat"] == 51.5074
    # Verify cache was written after external call
    mock_redis.setex.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Cache compression tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_compresses_large_data(aviation_client):
    """Cache should compress data when size >= min_size (1KB)."""
    import gzip

    # Create data larger than 1KB
    large_data = {"flights": [{"id": i, "data": "x" * 100} for i in range(20)]}
    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock()

    with patch("app.memory.session.get_redis", return_value=mock_redis):
        await aviation_client._cache_set("test_key", large_data, 3600)

    # Verify setex was called
    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args
    key, ttl, value = call_args[0]

    # Verify value is compressed (gzip)
    try:
        decompressed = gzip.decompress(value)
        assert json.loads(decompressed) == large_data
    except Exception:
        pytest.fail("Data should be compressed")


@pytest.mark.asyncio
async def test_cache_decompresses_on_retrieval(aviation_client):
    """Cache should decompress data on retrieval when compression is enabled."""
    import gzip

    cached_data = {"flights": [{"flight_number": "AA100", "price_usd": 300.0}]}
    compressed_data = gzip.compress(json.dumps(cached_data).encode())

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=compressed_data)

    with patch("app.memory.session.get_redis", return_value=mock_redis):
        result = await aviation_client._cache_get("test_key")

    assert result == cached_data


@pytest.mark.asyncio
async def test_cache_skips_compression_for_small_data(aviation_client):
    """Cache should not compress data smaller than min_size (1KB)."""
    small_data = {"flights": [{"flight_number": "AA100"}]}

    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock()

    with patch("app.memory.session.get_redis", return_value=mock_redis):
        await aviation_client._cache_set("test_key", small_data, 3600)

    call_args = mock_redis.setex.call_args
    key, ttl, value = call_args[0]

    # Verify value is NOT compressed (plain JSON)
    assert json.loads(value) == small_data


# ─────────────────────────────────────────────────────────────────────────────
# Selective caching tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_selective_caching_skips_large_data(aviation_client):
    """Cache should skip storing data larger than max_size (1MB)."""
    # Create data larger than 1MB
    large_data = {"flights": [{"id": i, "data": "x" * 10000} for i in range(200)]}

    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock()

    with patch("app.memory.session.get_redis", return_value=mock_redis):
        await aviation_client._cache_set("test_key", large_data, 3600)

    # Verify setex was NOT called (data too large)
    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_selective_caching_stores_small_data(aviation_client):
    """Cache should store data smaller than max_size (1MB)."""
    small_data = {"flights": [{"flight_number": "AA100"}]}

    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock()

    with patch("app.memory.session.get_redis", return_value=mock_redis):
        await aviation_client._cache_set("test_key", small_data, 3600)

    # Verify setex was called (data small enough)
    mock_redis.setex.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Cache hit rate tracking tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_hit_rate_tracking(aviation_client):
    """Cache should track hits and misses correctly."""
    mock_redis = AsyncMock()

    # Simulate cache hit
    mock_redis.get = AsyncMock(return_value=json.dumps({"data": "cached"}))
    with patch("app.memory.session.get_redis", return_value=mock_redis):
        await aviation_client._cache_get("test_key")

    # Simulate cache miss
    mock_redis.get = AsyncMock(return_value=None)
    with patch("app.memory.session.get_redis", return_value=mock_redis):
        await aviation_client._cache_get("test_key")

    # Verify counters
    assert aviation_client._cache_hits == 1
    assert aviation_client._cache_misses == 1
    assert aviation_client.get_cache_hit_rate() == 50.0


@pytest.mark.asyncio
async def test_cache_hit_rate_with_no_requests(aviation_client):
    """Cache hit rate should be 0 when no requests made."""
    assert aviation_client.get_cache_hit_rate() == 0.0


@pytest.mark.asyncio
async def test_cache_hit_rate_all_hits(aviation_client):
    """Cache hit rate should be 100% when all requests hit."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps({"data": "cached"}))

    with patch("app.memory.session.get_redis", return_value=mock_redis):
        for _ in range(5):
            await aviation_client._cache_get("test_key")

    assert aviation_client._cache_hits == 5
    assert aviation_client._cache_misses == 0
    assert aviation_client.get_cache_hit_rate() == 100.0
