"""Integration tests — MCP Client middleware with mocked MCP servers.

Each test verifies a full call through the middleware chain using
respx (httpx mock) to intercept HTTP calls instead of hitting real servers.
The tests ensure the middleware stack works end-to-end.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
import respx
import httpx

from app.mcp_clients.aviationstack import AviationStackMCPClient
from app.mcp_clients.skyscanner import SkyscannerMCPClient
from app.mcp_clients.tavily import TavilyMCPClient
from app.mcp_clients.maps import MapsMCPClient
from app.mcp_clients.gmail import GmailMCPClient
from app.utils.errors import ToolError


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures for disabling Redis and DB (test isolation)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def disable_redis_and_db():
    """Disable Redis and audit logging for all integration tests."""
    with patch("app.memory.session.get_redis", return_value=None):
        with patch("app.mcp_clients.base.BaseMCPClient._audit_log", AsyncMock()):
            yield


# ─────────────────────────────────────────────────────────────────────────────
# AviationStack — full middleware call (mocked HTTP)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aviationstack_get_flight_status_full_call():
    """AviationStack client completes a get_flight_status call through middleware."""
    mock_response = {
        "status": "success",
        "data": {
            "flights": [
                {
                    "flight_number": "AA100",
                    "airline": "American Airlines",
                    "origin": "LAX",
                    "destination": "JFK",
                    "departure_time": "2025-09-01T08:00:00",
                    "arrival_time": "2025-09-01T16:00:00",
                    "price_usd": 350.0,
                    "stops": 0,
                    "cabin_class": "economy",
                    "duration_minutes": 300,
                }
            ],
            "total_found": 1,
            "currency": "USD",
        }
    }

    settings_url = "https://multi-mcp-servers.onrender.com"

    with respx.mock(base_url=settings_url) as respx_mock:
        respx_mock.post("/get_flight_status").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        async with AviationStackMCPClient() as client:
            # Patch mcp_server_url on the settings object
            with patch.object(client._settings, "mcp_server_url", settings_url):
                result = await client.call(
                    "get_flight_status",
                    {
                        "dep_iata": "LAX",
                        "arr_iata": "JFK",
                    },
                    agent="test",
                )

    assert result["status"] == "success"


# ─────────────────────────────────────────────────────────────────────────────
# Skyscanner — full middleware call (mocked HTTP)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_skyscanner_search_flight_full_call():
    """Skyscanner client completes a search_flight call through middleware."""
    mock_response = {
        "status": "success",
        "origin": "LAX",
        "destination": "JFK",
        "departure_date": "2025-09-01",
        "results_count": 1,
        "data": [
            {
                "price": "$350.00",
                "price_raw": 350.0,
                "legs": [
                    {
                        "origin": "LAX",
                        "destination": "JFK",
                        "departure": "2025-09-01T08:00:00",
                        "arrival": "2025-09-01T16:00:00",
                        "duration_minutes": 300,
                        "stop_count": 0,
                        "airlines": ["American Airlines"],
                    }
                ]
            }
        ]
    }

    settings_url = "https://multi-mcp-servers.onrender.com"

    with respx.mock(base_url=settings_url) as respx_mock:
        respx_mock.post("/search_flight").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        async with SkyscannerMCPClient() as client:
            with patch.object(client._settings, "mcp_server_url", settings_url):
                result = await client.call(
                    "search_flight",
                    {
                        "origin": "LAX",
                        "destination": "JFK",
                        "departure_date": "2025-09-01",
                        "adults": 1,
                    },
                    agent="test",
                )

    assert result["status"] == "success"
    assert result["results_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Tavily — full middleware call (mocked HTTP)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tavily_search_full_call():
    """Tavily client completes a tavily_search call through middleware."""
    mock_response = {
        "status": "success",
        "data": {
            "results": [
                {
                    "title": "Best Hotels in Paris",
                    "url": "https://example.com/paris-hotels",
                    "content": "Paris has many great hotels...",
                    "score": 0.95,
                }
            ],
            "query": "best hotels Paris",
        }
    }

    settings_url = "https://multi-mcp-servers.onrender.com"

    with respx.mock(base_url=settings_url) as respx_mock:
        respx_mock.post("/tavily_search").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        async with TavilyMCPClient() as client:
            with patch.object(client._settings, "mcp_server_url", settings_url):
                result = await client.call(
                    "tavily_search",
                    {"query": "best hotels Paris"},
                    agent="test",
                )

    assert result["status"] == "success"


# ─────────────────────────────────────────────────────────────────────────────
# Maps — full middleware call (mocked HTTP)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_maps_google_maps_geocode_full_call():
    """Maps client completes a google_maps_geocode call through middleware."""
    mock_response = {
        "status": "success",
        "data": {
            "results": [
                {
                    "formatted_address": "Paris, Île-de-France, France",
                    "geometry": {
                        "location": {"lat": 48.8566, "lng": 2.3522}
                    }
                }
            ],
            "status": "OK"
        },
        "source": "photon"
    }

    settings_url = "https://multi-mcp-servers.onrender.com"

    with respx.mock(base_url=settings_url) as respx_mock:
        respx_mock.post("/google_maps_geocode").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        async with MapsMCPClient() as client:
            with patch.object(client._settings, "mcp_server_url", settings_url):
                result = await client.call(
                    "google_maps_geocode",
                    {"address": "Paris, France"},
                    agent="test",
                )

    assert result["status"] == "success"
    assert result["data"]["results"][0]["geometry"]["location"]["lat"] == 48.8566


@pytest.mark.asyncio
async def test_maps_google_maps_directions_full_call():
    """Maps client completes a google_maps_directions call through middleware."""
    mock_response = {
        "status": "success",
        "data": {
            "routes": [
                {
                    "legs": [
                        {
                            "startLocation": {"latLng": {"latitude": 48.8566, "longitude": 2.3522}},
                            "endLocation": {"latLng": {"latitude": 51.5074, "longitude": -0.1278}},
                            "steps": [
                                {
                                    "navigationInstruction": {
                                        "instruction": "Head from Paris towards London via driving."
                                    }
                                }
                            ]
                        }
                    ],
                    "distanceMeters": 340000,
                    "duration": "12600s",
                    "localizedValues": {
                        "distance": {"text": "340.0 km"},
                        "duration": {"text": "3 hours 30 mins"}
                    }
                }
            ]
        },
        "source": "graphhopper"
    }

    settings_url = "https://multi-mcp-servers.onrender.com"

    with respx.mock(base_url=settings_url) as respx_mock:
        respx_mock.post("/google_maps_directions").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        async with MapsMCPClient() as client:
            with patch.object(client._settings, "mcp_server_url", settings_url):
                result = await client.call(
                    "google_maps_directions",
                    {
                        "origin": "Paris, France",
                        "destination": "London, UK",
                        "mode": "driving",
                    },
                    agent="test",
                )

    assert result["status"] == "success"
    assert result["data"]["routes"][0]["distanceMeters"] == 340000


# ─────────────────────────────────────────────────────────────────────────────
# Gmail — full middleware call (mocked HTTP)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gmail_send_email_full_call():
    """Gmail client completes a send_email call through middleware."""
    mock_response = {
        "status": "success",
        "message": "Email sent successfully via Gmail API",
        "message_id": "msg_abc123",
    }

    settings_url = "https://multi-mcp-servers.onrender.com"

    with respx.mock(base_url=settings_url) as respx_mock:
        respx_mock.post("/send_email").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        async with GmailMCPClient() as client:
            with patch.object(client._settings, "mcp_server_url", settings_url):
                result = await client.call(
                    "send_email",
                    {
                        "to": "traveler@example.com",
                        "subject": "Your Paris Itinerary",
                        "body": "Your Trip",
                    },
                    agent="test",
                    skip_cache=True,
                )

    assert result["status"] == "success"
    assert result["message_id"] == "msg_abc123"


# ─────────────────────────────────────────────────────────────────────────────
# Retry behavior — transient error triggers retry, succeeds on 2nd attempt
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_on_transient_error_succeeds():
    """Client retries on 500 errors and succeeds on subsequent attempt."""
    success_response = {
        "status": "success",
        "data": {
            "results": [
                {
                    "formatted_address": "Tokyo, Japan",
                    "geometry": {"location": {"lat": 35.6762, "lng": 139.6503}}
                }
            ],
            "status": "OK"
        },
        "source": "photon"
    }

    settings_url = "https://multi-mcp-servers.onrender.com"
    call_count = 0

    with respx.mock(base_url=settings_url) as respx_mock:
        def side_effect(_request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(500, text="Internal Server Error")
            return httpx.Response(200, json=success_response)

        respx_mock.post("/google_maps_geocode").mock(side_effect=side_effect)

        async with MapsMCPClient() as client:
            with patch.object(client._settings, "mcp_server_url", settings_url):
                result = await client.call(
                    "google_maps_geocode",
                    {"address": "Tokyo"},
                    agent="test",
                )

    assert call_count == 2  # Failed once, succeeded on retry
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_retry_exhausted_raises_tool_error():
    """Client raises ToolError after exhausting all 3 retry attempts."""
    settings_url = "https://multi-mcp-servers.onrender.com"

    with respx.mock(base_url=settings_url) as respx_mock:
        respx_mock.post("/google_maps_geocode").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )

        async with MapsMCPClient() as client:
            with patch.object(client._settings, "mcp_server_url", settings_url):
                with pytest.raises(ToolError):
                    await client.call(
                        "google_maps_geocode",
                        {"address": "Tokyo"},
                        agent="test",
                    )


@pytest.mark.asyncio
async def test_client_error_not_retried():
    """400-level errors (non-429) must not be retried."""
    settings_url = "https://multi-mcp-servers.onrender.com"
    call_count = 0

    with respx.mock(base_url=settings_url) as respx_mock:
        def side_effect(_request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(400, text="Bad Request")

        respx_mock.post("/google_maps_geocode").mock(side_effect=side_effect)

        async with MapsMCPClient() as client:
            with patch.object(client._settings, "mcp_server_url", settings_url):
                with pytest.raises(ToolError):
                    await client.call(
                        "google_maps_geocode",
                        {"address": "Tokyo"},
                        agent="test",
                    )

    # 400 is not transient — should only be attempted once (no retries)
    assert call_count == 1
