"""Unit tests — schema validation across all MCP clients.

≥10 invalid cases per API as required by exit criteria.
"""

from __future__ import annotations

import pytest

from app.mcp_clients.aviationstack import AviationStackMCPClient
from app.mcp_clients.gmail import GmailMCPClient
from app.mcp_clients.maps import MapsMCPClient
from app.mcp_clients.tavily import TavilyMCPClient
from app.mcp_clients.skyscanner import SkyscannerMCPClient
from app.utils.errors import ValidationError


# ─────────────────────────────────────────────────────────────────────────────
# AviationStack — 10 invalid argument cases
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def avia():
    return AviationStackMCPClient()


AVIATIONSTACK_INVALID_CASES = [
    # 1. Missing all required fields
    {},
    # 2. Missing arr_iata
    {"dep_iata": "LAX"},
    # 3. Missing dep_iata
    {"arr_iata": "JFK"},
    # 4. dep_iata too short (2 chars)
    {"dep_iata": "LA", "arr_iata": "JFK"},
    # 5. dep_iata too long (4 chars)
    {"dep_iata": "LAXX", "arr_iata": "JFK"},
    # 6. Lowercase dep_iata
    {"dep_iata": "lax", "arr_iata": "JFK"},
    # 7. arr_iata too short (2 chars)
    {"dep_iata": "LAX", "arr_iata": "JF"},
    # 8. arr_iata too long (4 chars)
    {"dep_iata": "LAX", "arr_iata": "JFKK"},
    # 9. Lowercase arr_iata
    {"dep_iata": "LAX", "arr_iata": "jfk"},
    # 10. Additional unknown property
    {"dep_iata": "LAX", "arr_iata": "JFK", "extra": "bad"},
    # 11. dep_iata is not a string
    {"dep_iata": 123, "arr_iata": "JFK"},
]


@pytest.mark.parametrize("args", AVIATIONSTACK_INVALID_CASES)
def test_aviationstack_rejects_invalid_args(avia, args):
    with pytest.raises(ValidationError):
        avia._validate_args("get_flight_status", args)


def test_aviationstack_accepts_valid_args(avia):
    avia._validate_args("get_flight_status", {
        "dep_iata": "LAX",
        "arr_iata": "JFK",
        "flight_date": "2025-09-01",
    })


def test_aviationstack_accepts_minimal_args(avia):
    avia._validate_args("get_flight_status", {
        "dep_iata": "LAX",
        "arr_iata": "JFK",
    })


# ─────────────────────────────────────────────────────────────────────────────
# Skyscanner — 10 invalid argument cases
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sky():
    return SkyscannerMCPClient()


SKYSCANNER_INVALID_CASES = [
    # 1. Missing all required fields
    {},
    # 2. Missing destination & departure_date
    {"origin": "JFK"},
    # 3. Missing origin & departure_date
    {"destination": "LAX"},
    # 4. Missing origin & destination
    {"departure_date": "2025-06-01"},
    # 5. origin too short (2 chars)
    {"origin": "JF", "destination": "LAX", "departure_date": "2025-06-01"},
    # 6. destination too long (4 chars)
    {"origin": "JFK", "destination": "LAXX", "departure_date": "2025-06-01"},
    # 7. Lowercase IATA code
    {"origin": "jfk", "destination": "LAX", "departure_date": "2025-06-01"},
    # 8. adults is 0 (must be >= 1)
    {"origin": "JFK", "destination": "LAX", "departure_date": "2025-06-01", "adults": 0},
    # 9. adults is 10 (must be <= 9)
    {"origin": "JFK", "destination": "LAX", "departure_date": "2025-06-01", "adults": 10},
    # 10. Invalid cabin_class value
    {"origin": "JFK", "destination": "LAX", "departure_date": "2025-06-01", "cabin_class": "cargo"},
    # 11. Invalid date format
    {"origin": "JFK", "destination": "LAX", "departure_date": "06-01-2025"},
    # 12. Additional unknown property
    {"origin": "JFK", "destination": "LAX", "departure_date": "2025-06-01", "extra": "field"},
]


@pytest.mark.parametrize("args", SKYSCANNER_INVALID_CASES)
def test_skyscanner_rejects_invalid_args(sky, args):
    with pytest.raises(ValidationError):
        sky._validate_args("search_flight", args)


def test_skyscanner_accepts_valid_args(sky):
    sky._validate_args("search_flight", {
        "origin": "LAX",
        "destination": "JFK",
        "departure_date": "2025-09-01",
        "adults": 2,
    })


def test_skyscanner_accepts_optional_return_date(sky):
    sky._validate_args("search_flight", {
        "origin": "LAX",
        "destination": "JFK",
        "departure_date": "2025-09-01",
        "return_date": "2025-09-10",
        "cabin_class": "business",
        "adults": 1,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Tavily — 10 invalid argument cases
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tavily():
    return TavilyMCPClient()


TAVILY_SEARCH_INVALID_CASES = [
    # 1. Missing all fields
    {},
    # 2. Missing query but having search_depth
    {"search_depth": "basic"},
    # 3. Query too short
    {"query": "a"},
    # 4. query is not a string
    {"query": 42},
    # 5. query is None
    {"query": None},
    # 6. query is empty string
    {"query": ""},
    # 7. query is list (invalid type)
    {"query": []},
    # 8. Invalid search_depth value
    {"query": "Paris hotels", "search_depth": "ultra"},
    # 9. search_depth is integer
    {"query": "Paris hotels", "search_depth": 42},
    # 10. Unknown property
    {"query": "Paris hotels", "unknown": "field"},
]


@pytest.mark.parametrize("args", TAVILY_SEARCH_INVALID_CASES)
def test_tavily_search_rejects_invalid_args(tavily, args):
    with pytest.raises(ValidationError):
        tavily._validate_args("tavily_search", args)


def test_tavily_accepts_valid_search(tavily):
    tavily._validate_args("tavily_search", {"query": "Best hotels in Paris"})


# ─────────────────────────────────────────────────────────────────────────────
# Maps — 10 invalid argument cases for google_maps_directions
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def maps():
    return MapsMCPClient()


MAPS_INVALID_CASES = [
    # 1. Missing all fields
    {},
    # 2. Missing destination
    {"origin": "Paris"},
    # 3. Missing origin
    {"destination": "London"},
    # 4. Invalid mode
    {"origin": "Paris", "destination": "London", "mode": "hovercraft"},
    # 5. origin is not a string
    {"origin": 123, "destination": "London"},
    # 6. destination is not a string
    {"origin": "Paris", "destination": 456},
    # 7. Unknown top-level property
    {"origin": "Paris", "destination": "London", "speed": 100},
    # 8. Empty origin string
    {"origin": "", "destination": "London"},
    # 9. Empty destination string
    {"origin": "Paris", "destination": ""},
    # 10. Additional unknown property
    {"origin": "Paris", "destination": "London", "extra": "field"},
]


@pytest.mark.parametrize("args", MAPS_INVALID_CASES)
def test_maps_rejects_invalid_directions_args(maps, args):
    with pytest.raises(ValidationError):
        maps._validate_args("google_maps_directions", args)


def test_maps_accepts_valid_directions(maps):
    maps._validate_args("google_maps_directions", {
        "origin": "Paris",
        "destination": "London",
        "mode": "driving",
    })


# ─────────────────────────────────────────────────────────────────────────────
# Maps — 10 invalid argument cases for google_maps_geocode
# ─────────────────────────────────────────────────────────────────────────────

MAPS_GEOCODE_INVALID_CASES = [
    # 1. Missing address
    {},
    # 2. Address too short
    {"address": "P"},
    # 3. address is not a string
    {"address": 123},
    # 4. address is None
    {"address": None},
    # 5. Empty address string
    {"address": ""},
    # 6. Unknown property
    {"address": "Paris", "language": "en"},
    # 7. address is a number
    {"address": 12345},
    # 8. Additional unknown property
    {"address": "Paris", "extra": "field"},
    # 9. address is list (invalid type)
    {"address": []},
    # 10. address is boolean
    {"address": True},
]


@pytest.mark.parametrize("args", MAPS_GEOCODE_INVALID_CASES)
def test_maps_rejects_invalid_geocode_args(maps, args):
    with pytest.raises(ValidationError):
        maps._validate_args("google_maps_geocode", args)


def test_maps_accepts_valid_geocode(maps):
    maps._validate_args("google_maps_geocode", {"address": "Eiffel Tower, Paris"})


# ─────────────────────────────────────────────────────────────────────────────
# Gmail — 10 invalid argument cases
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def gmail():
    return GmailMCPClient()


GMAIL_INVALID_CASES = [
    # 1. Missing all required fields
    {},
    # 2. Missing subject
    {"to": "user@example.com", "body": "Hello"},
    # 3. Missing body
    {"to": "user@example.com", "subject": "Your trip"},
    # 4. Missing to
    {"subject": "Your trip", "body": "Hello"},
    # 5. Invalid email format — no @ sign, fails pattern check
    {"to": "not-an-email", "subject": "Your trip", "body": "Hello"},
    # 6. Subject is list (invalid type)
    {"to": "user@example.com", "subject": [], "body": "Hello"},
    # 7. Empty subject
    {"to": "user@example.com", "subject": "", "body": "Hello"},
    # 8. Empty body
    {"to": "user@example.com", "subject": "Trip", "body": ""},
    # 9. Unknown property
    {"to": "user@example.com", "subject": "Trip", "body": "Hi", "bcc": "other@example.com"},
    # 10. to is not a string
    {"to": 12345, "subject": "Trip", "body": "Hi"},
]


@pytest.mark.parametrize("args", GMAIL_INVALID_CASES)
def test_gmail_rejects_invalid_args(gmail, args):
    with pytest.raises(ValidationError):
        gmail._validate_args("send_email", args)


def test_gmail_accepts_valid_send_email(gmail):
    gmail._validate_args("send_email", {
        "to": "traveler@example.com",
        "subject": "Your Paris Itinerary",
        "body": "Your Trip Details here...",
    })
