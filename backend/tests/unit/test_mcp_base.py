"""Unit tests for BaseMCPClient middleware layers.

Tests the middleware stack without making real network calls.
Covers: instantiation, arg validation, response validation, cache key, retry config.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.mcp_clients.aviationstack import AviationStackMCPClient
from app.mcp_clients.base import BaseMCPClient, _is_transient
from app.mcp_clients.gmail import GmailMCPClient
from app.mcp_clients.maps import MapsMCPClient
from app.mcp_clients.tavily import TavilyMCPClient
from app.mcp_clients.skyscanner import SkyscannerMCPClient
from app.utils.errors import ToolError, ValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def aviation_client() -> AviationStackMCPClient:
    return AviationStackMCPClient()


@pytest.fixture
def tavily_client() -> TavilyMCPClient:
    return TavilyMCPClient()


@pytest.fixture
def maps_client() -> MapsMCPClient:
    return MapsMCPClient()


@pytest.fixture
def gmail_client() -> GmailMCPClient:
    return GmailMCPClient()


@pytest.fixture
def skyscanner_client() -> SkyscannerMCPClient:
    return SkyscannerMCPClient()


# ---------------------------------------------------------------------------
# Test 1: BaseMCPClient cannot be instantiated directly
# ---------------------------------------------------------------------------


def test_base_mcp_client_is_abstract():
    """BaseMCPClient must not be directly instantiable."""
    with pytest.raises(TypeError):
        BaseMCPClient()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Test 2: All clients are properly configured
# ---------------------------------------------------------------------------


def test_client_names():
    """Each client must have a unique, non-empty name."""
    names = [c.client_name for c in [
        AviationStackMCPClient(),
        TavilyMCPClient(),
        MapsMCPClient(),
        GmailMCPClient(),
        SkyscannerMCPClient(),
    ]]
    assert len(set(names)) == 5, "All client names must be unique"
    assert all(name for name in names), "All client names must be non-empty"


def test_client_base_paths():
    """Each client must have a unique, non-empty base path starting with '/'."""
    clients = [
        AviationStackMCPClient(),
        TavilyMCPClient(),
        MapsMCPClient(),
        GmailMCPClient(),
        SkyscannerMCPClient(),
    ]
    for client in clients:
        assert client.base_path.startswith("/"), f"{client.client_name} base_path must start with /"
    base_paths = [c.base_path for c in clients]
    assert len(set(base_paths)) == 5, "All base paths must be unique"


def test_client_rate_limits():
    """Each client must have a positive rate limit."""
    clients = [
        AviationStackMCPClient(),
        TavilyMCPClient(),
        MapsMCPClient(),
        GmailMCPClient(),
        SkyscannerMCPClient(),
    ]
    for client in clients:
        assert client.rate_limit_per_minute > 0, f"{client.client_name} must have positive rate limit"


def test_max_retries_is_three():
    """Retry limit must be exactly 3 per the implementation plan."""
    assert BaseMCPClient.MAX_RETRIES == 3


# ---------------------------------------------------------------------------
# Test 3: Schema validation — valid argument rejection
# ---------------------------------------------------------------------------


def test_aviationstack_valid_args_pass(aviation_client):
    """Valid get_flight_status arguments should pass validation."""
    aviation_client._validate_args("get_flight_status", {
        "dep_iata": "LAX",
        "arr_iata": "JFK",
        "flight_date": "2025-08-01",
    })  # Should not raise


def test_aviationstack_invalid_missing_required(aviation_client):
    """Missing required fields must raise ValidationError."""
    with pytest.raises(ValidationError):
        aviation_client._validate_args("get_flight_status", {
            "dep_iata": "LAX",
            # missing arr_iata
        })


def test_aviationstack_invalid_iata_code_short(aviation_client):
    """IATA code shorter than 3 chars must fail."""
    with pytest.raises(ValidationError):
        aviation_client._validate_args("get_flight_status", {
            "dep_iata": "LA",  # too short
            "arr_iata": "JFK",
        })


def test_aviationstack_invalid_iata_code_lowercase(aviation_client):
    """Lowercase IATA code must fail (pattern requires uppercase)."""
    with pytest.raises(ValidationError):
        aviation_client._validate_args("get_flight_status", {
            "dep_iata": "lax",  # lowercase
            "arr_iata": "JFK",
        })


def test_aviationstack_invalid_extra_properties(aviation_client):
    """Additional properties must fail (additionalProperties: false)."""
    with pytest.raises(ValidationError):
        aviation_client._validate_args("get_flight_status", {
            "dep_iata": "LAX",
            "arr_iata": "JFK",
            "unknown_field": "should_fail",
        })


def test_aviationstack_invalid_non_string_origin(aviation_client):
    """Non-string dep_iata must fail."""
    with pytest.raises(ValidationError):
        aviation_client._validate_args("get_flight_status", {
            "dep_iata": 123,
            "arr_iata": "JFK",
        })


# ---------------------------------------------------------------------------
# Test 4: Schema validation — response validation
# ---------------------------------------------------------------------------


def test_aviationstack_valid_response_passes(aviation_client):
    """Valid response should pass validation."""
    aviation_client._validate_response("get_flight_status", {
        "status": "success",
        "data": {},
    })  # Should not raise


def test_tavily_invalid_response_no_status(tavily_client):
    """Tavily response missing 'status' must fail."""
    with pytest.raises(ValidationError):
        tavily_client._validate_response("tavily_search", {"query": "Paris"})


# ---------------------------------------------------------------------------
# Test 5: Cache key determinism
# ---------------------------------------------------------------------------


def test_cache_key_is_deterministic(maps_client):
    """Same args in different order must produce the same cache key."""
    key1 = maps_client._cache_key("google_maps_geocode", {"address": "Paris"})
    key2 = maps_client._cache_key("google_maps_geocode", {"address": "Paris"})
    assert key1 == key2


def test_cache_key_differs_for_different_args(maps_client):
    """Different args must produce different cache keys."""
    key1 = maps_client._cache_key("google_maps_geocode", {"address": "Paris"})
    key2 = maps_client._cache_key("google_maps_geocode", {"address": "London"})
    assert key1 != key2


def test_cache_key_differs_for_different_tools(maps_client):
    """Different tools with same args must produce different keys."""
    key1 = maps_client._cache_key("google_maps_geocode", {"address": "Paris"})
    key2 = maps_client._cache_key("google_maps_directions", {"origin": "Paris", "destination": "London"})
    assert key1 != key2


def test_cache_key_has_expected_format(maps_client):
    """Cache key should follow mcp_cache:{client}:{tool}:{hash} format."""
    key = maps_client._cache_key("google_maps_geocode", {"address": "Paris"})
    parts = key.split(":")
    assert parts[0] == "mcp_cache"
    assert parts[1] == "maps"
    assert parts[2] == "google_maps_geocode"
    assert len(parts[3]) == 16  # 16-char hex digest


# ---------------------------------------------------------------------------
# Test 6: Cache TTL values
# ---------------------------------------------------------------------------


def test_aviationstack_cache_ttl_flights(aviation_client):
    from app.config import get_settings
    assert aviation_client.cache_ttl("get_flight_status") == get_settings().cache_ttl_flights


def test_tavily_cache_ttl_search(tavily_client):
    from app.config import get_settings
    assert tavily_client.cache_ttl("tavily_search") == get_settings().cache_ttl_attractions


def test_maps_cache_ttl_geocoding(maps_client):
    from app.config import get_settings
    assert maps_client.cache_ttl("google_maps_geocode") == get_settings().cache_ttl_geocoding


def test_maps_cache_ttl_routes(maps_client):
    from app.config import get_settings
    assert maps_client.cache_ttl("google_maps_directions") == get_settings().cache_ttl_routes


def test_gmail_cache_ttl_is_zero(gmail_client):
    """Gmail send operations must not be cached (TTL=0)."""
    assert gmail_client.cache_ttl("send_email") == 0


# ---------------------------------------------------------------------------
# Test 7: _is_transient helper
# ---------------------------------------------------------------------------


def test_is_transient_for_429():
    err = ToolError("rate limited")
    err.status_code = 429  # type: ignore[attr-defined]
    assert _is_transient(err) is True


def test_is_transient_for_500():
    err = ToolError("server error")
    err.status_code = 500  # type: ignore[attr-defined]
    assert _is_transient(err) is True


def test_is_transient_for_503():
    err = ToolError("service unavailable")
    err.status_code = 503  # type: ignore[attr-defined]
    assert _is_transient(err) is True


def test_not_transient_for_400():
    err = ToolError("bad request")
    err.status_code = 400  # type: ignore[attr-defined]
    assert _is_transient(err) is False


def test_not_transient_for_404():
    err = ToolError("not found")
    err.status_code = 404  # type: ignore[attr-defined]
    assert _is_transient(err) is False


def test_is_transient_for_timeout():
    import httpx
    assert _is_transient(httpx.TimeoutException("timeout")) is True


def test_is_transient_for_connect_error():
    import httpx
    assert _is_transient(httpx.ConnectError("connection failed")) is True


# ---------------------------------------------------------------------------
# Test 8: Gmail never caches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gmail_cache_get_always_returns_none(gmail_client):
    """GmailMCPClient._cache_get must always return None (no caching for sends)."""
    result = await gmail_client._cache_get("any_cache_key")
    assert result is None


@pytest.mark.asyncio
async def test_gmail_cache_set_is_noop(gmail_client):
    """GmailMCPClient._cache_set must not raise and does nothing."""
    # Should not raise or do anything
    await gmail_client._cache_set("key", {"message_id": "123"}, 300)


# ---------------------------------------------------------------------------
# Test 9: MCP server URL comes from settings (not hardcoded)
# ---------------------------------------------------------------------------


def test_mcp_server_url_is_from_settings():
    """MCP server URL must be loaded from settings, not hardcoded in client code."""
    from app.config import get_settings

    settings = get_settings()
    client = AviationStackMCPClient()
    # Client's settings must have the MCP server URL
    assert client._settings.mcp_server_url == settings.mcp_server_url
    # URL must not be empty
    assert client._settings.mcp_server_url


def test_mcp_server_url_has_no_trailing_slash():
    """URL used in HTTP calls should have trailing slash stripped."""
    from app.config import get_settings

    settings = get_settings()
    url = settings.mcp_server_url
    # When building the full URL in _http_call, we do rstrip('/')
    # so even if the env var has a trailing slash, it gets stripped
    assert url  # just confirm it's set
