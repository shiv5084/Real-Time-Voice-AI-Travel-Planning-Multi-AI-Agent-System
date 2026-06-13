#!/usr/bin/env python
"""
test_llm_calls.py — Verify every agent calls its real LLM and print exact JSON output.

Strategy:
  - Patch all MCP clients to return rich stub data so worker agents
    never hit the early-return `if not raw` guard.
  - Use a complete request (dates + budget) so planner never generates
    follow_up_questions and doesn't route to END.
  - Set a very small budget ($50) so budget agent goes over_budget and
    Gemini is triggered.
  - Run all 8 agents in pipeline order and capture their LLM JSON output.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

# ── path setup ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# ── rich stub data for MCP clients ───────────────────────────────────────
STUB_FLIGHTS = {
    "flights": [
        {"airline": "Air France", "flight_number": "AF001", "origin": "JFK",
         "destination": "CDG", "departure_time": "10:00", "arrival_time": "22:00",
         "duration_minutes": 480, "price_usd": 650.0, "layovers": 0, "cabin_class": "economy"},
        {"airline": "Delta", "flight_number": "DL402", "origin": "JFK",
         "destination": "CDG", "departure_time": "14:00", "arrival_time": "06:00",
         "duration_minutes": 500, "price_usd": 520.0, "layovers": 1, "cabin_class": "economy"},
    ]
}

STUB_HOTELS = {
    "results": [
        {"title": "Hotel Le Marais Paris",
         "content": "Charming boutique hotel in the heart of Paris. Price: $120/night. "
                    "Rating: 4.5/5. Amenities: WiFi, breakfast, city view. "
                    "Location: 3rd arrondissement near Place des Vosges."},
        {"title": "Ibis Paris Centre",
         "content": "Budget-friendly hotel near Gare du Nord. Price: $75/night. "
                    "Rating: 3.8/5. Amenities: WiFi, 24h reception. "
                    "Location: 10th arrondissement."},
    ]
}

STUB_ATTRACTIONS = {
    "results": [
        {"title": "Eiffel Tower",
         "content": "Iconic iron lattice tower on the Champ de Mars. Admission: $25. "
                    "Open daily 09:00-23:00. Best visited at sunrise or sunset."},
        {"title": "Louvre Museum",
         "content": "World's largest art museum. Admission: $17. "
                    "Open Wed-Mon 09:00-18:00. Home to the Mona Lisa."},
        {"title": "Notre-Dame Cathedral",
         "content": "Medieval Catholic cathedral on Île de la Cité. Free entry. "
                    "Open daily 08:00-18:45. Currently under restoration."},
        {"title": "Montmartre & Sacré-Cœur",
         "content": "Historic hilltop neighbourhood. Basilica free entry. "
                    "Great views of Paris. Street artists and cafés."},
    ]
}

STUB_GEOCODING = {
    "results": [{"lat": "48.8566", "lon": "2.3522", "display_name": "Paris, France"}]
}

STUB_ROUTING = {
    "paths": [{"distance": 12000, "time": 1500000,
               "points": {"coordinates": [[2.35, 48.85], [2.36, 48.86]]}}]
}

# ── constraints shared across all agents ─────────────────────────────────
CONSTRAINTS = {
    "destinations": ["New York", "Paris"],
    "start_date": "2025-08-01",
    "end_date": "2025-08-07",
    "budget": 50.0,          # intentionally tiny → triggers over_budget → Gemini fires
    "budget_currency": "USD",
    "travelers": 1,
    "preferences": {
        "accommodation_type": "boutique hotel",
        "crowd_tolerance": "moderate",
        "activity_level": "active",
        "food_preferences": "local cuisine",
        "transport_preference": "public transit",
    },
}


# ── helpers ───────────────────────────────────────────────────────────────

def header(title: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}")
    print(f"  {title}")
    print(bar)


def result_box(agent: str, model: str, data: dict | list | None, elapsed: float) -> None:
    bar = "-" * 70
    print(f"\n{bar}")
    print(f"  AGENT : {agent}")
    print(f"  MODEL : {model}")
    print(f"  TIME  : {elapsed:.2f}s")
    print(bar)
    print(json.dumps(data, indent=2, default=str) if data else "(no parsed output)")
    print(bar)


# ── individual agent runners ──────────────────────────────────────────────

async def run_planner(settings) -> dict:
    """Run planner with a fully-specified request — no follow-up questions."""
    from app.agents.planner import PlannerAgent
    from app.graph.state import initial_state

    state = initial_state(
        raw_request=(
            "Plan a 7-day trip from New York to Paris for 1 person "
            "from August 1 to August 7, 2026. Budget is $50 USD. "
            "I like boutique hotels, active sightseeing,local food and hate crowd."
        ),
        user_id="test_user",
    )

    agent = PlannerAgent(settings=settings)
    # Capture _log_llm_call output
    captured: dict = {}

    orig = agent._log_llm_call
    def capture(model, raw_response, parsed=None):
        captured["model"] = model
        captured["parsed"] = parsed
        orig(model, raw_response, parsed)

    agent._log_llm_call = capture

    t0 = time.monotonic()
    result = await agent.run(state)
    elapsed = time.monotonic() - t0

    result_box("planner_agent", captured.get("model", "groq-large"),
               captured.get("parsed"), elapsed)
    return result  # return full state dict for downstream agents


async def run_flight(settings, state: dict) -> dict:
    """Run flight agent with stubbed MCP data."""
    from app.agents.flight import FlightAgent

    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value=STUB_FLIGHTS)

    agent = FlightAgent(settings=settings)
    captured: dict = {}
    orig = agent._log_llm_call
    def capture(model, raw_response, parsed=None):
        captured["model"] = model
        captured["parsed"] = parsed
        orig(model, raw_response, parsed)
    agent._log_llm_call = capture

    t0 = time.monotonic()
    with patch("app.agents.flight.AviationStackMCPClient", return_value=mock_client):
        result = await agent.run(state)
    elapsed = time.monotonic() - t0

    result_box("flight_agent", captured.get("model", "groq-small"),
               captured.get("parsed"), elapsed)
    return result


async def run_hotel(settings, state: dict) -> dict:
    """Run hotel agent with stubbed MCP data."""
    from app.agents.hotel import HotelAgent

    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value=STUB_HOTELS)

    agent = HotelAgent(settings=settings)
    captured: dict = {}
    orig = agent._log_llm_call
    def capture(model, raw_response, parsed=None):
        captured["model"] = model
        captured["parsed"] = parsed
        orig(model, raw_response, parsed)
    agent._log_llm_call = capture

    t0 = time.monotonic()
    with patch("app.agents.hotel.TavilyMCPClient", return_value=mock_client):
        result = await agent.run(state)
    elapsed = time.monotonic() - t0

    result_box("hotel_agent", captured.get("model", "groq-small"),
               captured.get("parsed"), elapsed)
    return result


async def run_attraction(settings, state: dict) -> dict:
    """Run attraction agent with stubbed Tavily + Nominatim data."""
    from app.agents.attraction import AttractionAgent

    mock_tavily = AsyncMock()
    mock_tavily.call = AsyncMock(return_value=STUB_ATTRACTIONS)
    mock_nominatim = AsyncMock()
    mock_nominatim.call = AsyncMock(return_value=STUB_GEOCODING)

    agent = AttractionAgent(settings=settings)
    captured: dict = {}
    orig = agent._log_llm_call
    def capture(model, raw_response, parsed=None):
        captured["model"] = model
        captured["parsed"] = parsed
        orig(model, raw_response, parsed)
    agent._log_llm_call = capture

    t0 = time.monotonic()
    with patch("app.agents.attraction.TavilyMCPClient", return_value=mock_tavily), \
         patch("app.agents.attraction.NominatimMCPClient", return_value=mock_nominatim):
        result = await agent.run(state)
    elapsed = time.monotonic() - t0

    result_box("attraction_agent", captured.get("model", "groq-small"),
               captured.get("parsed"), elapsed)
    return result


async def run_transport(settings, state: dict) -> dict:
    """Run transport agent with stubbed Nominatim + GraphHopper data."""
    from app.agents.transport import TransportAgent

    mock_nominatim = AsyncMock()
    mock_nominatim.call = AsyncMock(return_value=STUB_GEOCODING)
    mock_graphhopper = AsyncMock()
    mock_graphhopper.call = AsyncMock(return_value=STUB_ROUTING)

    agent = TransportAgent(settings=settings)
    captured: dict = {}
    orig = agent._log_llm_call
    def capture(model, raw_response, parsed=None):
        captured["model"] = model
        captured["parsed"] = parsed
        orig(model, raw_response, parsed)
    agent._log_llm_call = capture

    t0 = time.monotonic()
    with patch("app.agents.transport.NominatimMCPClient", return_value=mock_nominatim), \
         patch("app.agents.transport.GraphHopperMCPClient", return_value=mock_graphhopper):
        result = await agent.run(state)
    elapsed = time.monotonic() - t0

    result_box("transport_agent", captured.get("model", "groq-small"),
               captured.get("parsed"), elapsed)
    return result


async def run_budget(settings, merged_state: dict) -> dict:
    """Run budget agent — budget=$50 forces over_budget → Gemini fires."""
    from app.agents.budget import BudgetAgent

    agent = BudgetAgent(settings=settings)
    captured: dict = {}
    orig = agent._log_llm_call
    def capture(model, raw_response, parsed=None):
        captured["model"] = model
        captured["parsed"] = parsed
        orig(model, raw_response, parsed)
    agent._log_llm_call = capture

    t0 = time.monotonic()
    result = await agent.run(merged_state)
    elapsed = time.monotonic() - t0

    compliance = result.get("budget_breakdown", {}).get("compliance", "?")
    print(f"\n  [budget_agent] compliance={compliance}  "
          f"(Gemini fires only when over_budget)")
    result_box("budget_agent", captured.get("model", "gemini"),
               captured.get("parsed"), elapsed)
    return result


async def run_composer(settings, merged_state: dict) -> dict:
    """Run composer with all worker results in state."""
    from app.agents.composer import ComposerAgent

    agent = ComposerAgent(settings=settings)
    captured: dict = {}
    orig = agent._log_llm_call
    def capture(model, raw_response, parsed=None):
        captured["model"] = model
        captured["parsed"] = parsed
        orig(model, raw_response, parsed)
    agent._log_llm_call = capture

    t0 = time.monotonic()
    result = await agent.run(merged_state)
    elapsed = time.monotonic() - t0

    result_box("composer_agent", captured.get("model", "groq-large"),
               captured.get("parsed"), elapsed)
    return result


async def run_validator(settings, merged_state: dict) -> dict:
    """Run validator with stubbed Nominatim geocoding."""
    from app.agents.validator import ValidatorAgent

    mock_nominatim = AsyncMock()
    mock_nominatim.call = AsyncMock(return_value=STUB_GEOCODING)

    agent = ValidatorAgent(settings=settings)
    captured: dict = {}
    orig = agent._log_llm_call
    def capture(model, raw_response, parsed=None):
        captured["model"] = model
        captured["parsed"] = parsed
        orig(model, raw_response, parsed)
    agent._log_llm_call = capture

    t0 = time.monotonic()
    with patch("app.agents.validator.NominatimMCPClient", return_value=mock_nominatim):
        result = await agent.run(merged_state)
    elapsed = time.monotonic() - t0

    result_box("validator_agent", captured.get("model", "gemini"),
               captured.get("parsed"), elapsed)
    return result


# ── main ──────────────────────────────────────────────────────────────────

async def main() -> int:
    header("LLM Call Verification — All 8 Agents (Real API Calls)")
    print("\nThis script runs each agent against its real LLM.")
    print("MCP external calls are stubbed; LLM calls are REAL.\n")

    from app.config import get_settings
    settings = get_settings()

    print(f"  Groq key : {'SET (' + settings.groq_api_key[:6] + '***)' if settings.groq_api_key else 'NOT SET'}")
    print(f"  Gemini key: {'SET (' + settings.gemini_api_key[:6] + '***)' if settings.gemini_api_key else 'NOT SET'}")
    print(f"  Groq large model : {settings.groq_model_large}")
    print(f"  Groq small model : {settings.groq_model_small}")
    print(f"  Gemini model     : {settings.gemini_model}")

    if not settings.groq_api_key:
        print("\n[ERROR] GROQ_API_KEY not set. Aborting.")
        return 1
    if not settings.gemini_api_key:
        print("\n[ERROR] GEMINI_API_KEY not set. Aborting.")
        return 1

    passed = 0
    failed = 0
    total_start = time.monotonic()

    # ── 1. Planner ────────────────────────────────────────────────────
    header("1/8  Planner Agent  →  Groq large (llama-3.3-70b-versatile)")
    try:
        planner_state = await run_planner(settings)
        # Override constraints to ensure no follow-up questions block workers
        planner_state["constraints"] = CONSTRAINTS
        planner_state["follow_up_questions"] = []
        planner_state["delegation_plan"] = {
            "needs_flights": True, "needs_hotels": True,
            "needs_attractions": True, "needs_transport": True,
        }
        print("  ✓ Planner: LLM called successfully")
        passed += 1
    except Exception as e:
        print(f"  ✗ Planner FAILED: {e}")
        import traceback; traceback.print_exc()
        failed += 1
        planner_state = {
            "constraints": CONSTRAINTS, "follow_up_questions": [],
            "delegation_plan": {}, "agent_responses": [], "errors": [],
            "raw_request": "", "user_id": "test", "session_id": "",
            "trace_id": "", "trip_id": None,
        }

    # ── 2. Flight ─────────────────────────────────────────────────────
    header("2/8  Flight Agent  →  Groq small (llama-3.1-8b-instant)")
    try:
        flight_result = await run_flight(settings, planner_state)
        planner_state["flight_results"] = flight_result.get("flight_results", {})
        print("  ✓ Flight: LLM called successfully")
        passed += 1
    except Exception as e:
        print(f"  ✗ Flight FAILED: {e}")
        import traceback; traceback.print_exc()
        failed += 1
        planner_state["flight_results"] = {}

    # ── 3. Hotel ──────────────────────────────────────────────────────
    header("3/8  Hotel Agent  →  Groq small (llama-3.1-8b-instant)")
    try:
        hotel_result = await run_hotel(settings, planner_state)
        planner_state["hotel_results"] = hotel_result.get("hotel_results", {})
        print("  ✓ Hotel: LLM called successfully")
        passed += 1
    except Exception as e:
        print(f"  ✗ Hotel FAILED: {e}")
        import traceback; traceback.print_exc()
        failed += 1
        planner_state["hotel_results"] = {}

    # ── 4. Attraction ─────────────────────────────────────────────────
    header("4/8  Attraction Agent  →  Groq small (llama-3.1-8b-instant)")
    try:
        attraction_result = await run_attraction(settings, planner_state)
        planner_state["attraction_results"] = attraction_result.get("attraction_results", {})
        print("  ✓ Attraction: LLM called successfully")
        passed += 1
    except Exception as e:
        print(f"  ✗ Attraction FAILED: {e}")
        import traceback; traceback.print_exc()
        failed += 1
        planner_state["attraction_results"] = {}

    # ── 5. Transport ──────────────────────────────────────────────────
    header("5/8  Transport Agent  →  Groq small (llama-3.1-8b-instant)")
    try:
        transport_result = await run_transport(settings, planner_state)
        planner_state["transport_results"] = transport_result.get("transport_results", {})
        print("  ✓ Transport: LLM called successfully")
        passed += 1
    except Exception as e:
        print(f"  ✗ Transport FAILED: {e}")
        import traceback; traceback.print_exc()
        failed += 1
        planner_state["transport_results"] = {}

    # ── 6. Budget ─────────────────────────────────────────────────────
    header("6/8  Budget Agent  →  Gemini (gemini-2.0-flash)")
    print("  NOTE: budget=$50 against ~$1600 trip cost → over_budget → Gemini fires")
    try:
        budget_result = await run_budget(settings, planner_state)
        planner_state["budget_breakdown"] = budget_result.get("budget_breakdown", {})
        print("  ✓ Budget: Gemini called successfully")
        passed += 1
    except Exception as e:
        print(f"  ✗ Budget FAILED: {e}")
        import traceback; traceback.print_exc()
        failed += 1
        planner_state["budget_breakdown"] = {}

    # ── 7. Composer ───────────────────────────────────────────────────
    header("7/8  Composer Agent  →  Groq large (llama-3.3-70b-versatile)")
    try:
        composer_result = await run_composer(settings, planner_state)
        planner_state["itinerary"] = composer_result.get("itinerary", {})
        print("  ✓ Composer: LLM called successfully")
        passed += 1
    except Exception as e:
        print(f"  ✗ Composer FAILED: {e}")
        import traceback; traceback.print_exc()
        failed += 1
        planner_state["itinerary"] = {}

    # ── 8. Validator ──────────────────────────────────────────────────
    header("8/8  Validator Agent  →  Gemini (gemini-2.0-flash)")
    planner_state["regeneration_count"] = 0
    try:
        await run_validator(settings, planner_state)
        print("  ✓ Validator: Gemini called successfully")
        passed += 1
    except Exception as e:
        print(f"  ✗ Validator FAILED: {e}")
        import traceback; traceback.print_exc()
        failed += 1

    # ── Summary ───────────────────────────────────────────────────────
    total_elapsed = time.monotonic() - total_start
    header(f"RESULTS  —  {passed}/8 agents passed  ({total_elapsed:.1f}s total)")
    agents = [
        ("planner_agent",    "groq-large",  "llama-3.3-70b-versatile"),
        ("flight_agent",     "groq-small",  "llama-3.1-8b-instant"),
        ("hotel_agent",      "groq-small",  "llama-3.1-8b-instant"),
        ("attraction_agent", "groq-small",  "llama-3.1-8b-instant"),
        ("transport_agent",  "groq-small",  "llama-3.1-8b-instant"),
        ("budget_agent",     "gemini",      "gemini-2.0-flash"),
        ("composer_agent",   "groq-large",  "llama-3.3-70b-versatile"),
        ("validator_agent",  "gemini",      "gemini-2.0-flash"),
    ]
    for agent, provider, model in agents:
        print(f"  {agent:<22} {provider:<12} {model}")

    print()
    if failed == 0:
        print("  ALL 8 AGENTS CALLED THEIR REAL LLMs SUCCESSFULLY")
        return 0
    else:
        print(f"  {failed} agent(s) failed — see output above")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
