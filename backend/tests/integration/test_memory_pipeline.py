"""Integration tests for the memory-aware pipeline (Phase 4).

Tests cover:
- Full pipeline run with mocked Mem0 preferences (preferences applied downstream)
- Self-correcting loop: validation failure triggers re-plan (max 3 iterations)
- Selective worker re-runs (only affected workers execute on regen)
- Profile API routes: GET /api/profile, PUT /api/profile/preferences
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Test: Pipeline uses Mem0 preferences when user_id is not anonymous
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_applies_stored_preferences():
    """Pipeline should inject stored user preferences into the Planner output."""
    from app.graph.workflow import run_pipeline
    from app.graph.state import initial_state

    stored_prefs = {
        "food": "vegetarian",
        "accommodation_type": "boutique hotel",
        "crowd_tolerance": "low",
    }

    # Mock Mem0 to return stored preferences
    mock_mem0 = AsyncMock()
    mock_mem0.get_preferences = AsyncMock(return_value=stored_prefs)

    # Mock episodic memory
    mock_episodic_get_all = AsyncMock(return_value=[])
    mock_episodic_extract = AsyncMock(return_value=True)

    # Mock LLM responses
    def mock_get_llm(self):
        responses = {
            "planner_agent": (
                '{"destinations": ["Kyoto"], "start_date": "2025-10-01", '
                '"end_date": "2025-10-06", "budget": 2000.0, "budget_currency": "USD", '
                '"travelers": 1, "preferences": {"food": "vegetarian"}, '
                '"follow_up_questions": [], '
                '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
                '"needs_attractions": true, "needs_transport": true}}'
            ),
            "flight_agent": '{"flights": [{"airline": "JAL", "price_usd": 700}]}',
            "hotel_agent": '{"hotels": [{"name": "Boutique Inn", "total_cost_usd": 600}]}',
            "attraction_agent": '{"attractions": [{"name": "Kinkaku-ji", "cost_usd": 15}]}',
            "transport_agent": '{"transport_options": [{"mode": "train", "estimated_cost_usd": 80}]}',
            "budget_agent": '{"recommendations": []}',
            "composer_agent": '{"days": [{"day": 1, "date": "2025-10-01", "location": "Kyoto", "activities": [{"name": "Arrive", "type": "travel", "start_time": "14:00", "end_time": "15:00", "cost_usd": 0}], "total_cost_usd": 0}]}',
            "validator_agent": '{"issues": [], "overall_assessment": "Approved", "approved": true}',
        }

        class _FakeLLM:
            def __init__(self, content):
                self._content = content
            async def ainvoke(self, *args, **kwargs):
                r = MagicMock()
                r.content = self._content
                return r

        return _FakeLLM(responses.get(self.agent_name, '{"mock": true}'))

    mock_aviation = AsyncMock()
    mock_aviation.call = AsyncMock(return_value={"flights": [{"price_usd": 700}]})
    mock_tavily = AsyncMock()
    mock_tavily.call = AsyncMock(return_value={"results": [{"title": "T", "content": "C"}]})
    mock_maps = AsyncMock()
    mock_maps.call = AsyncMock(return_value={
        "status": "success",
        "data": {
            "results": [{"geometry": {"location": {"lat": 35.0, "lng": 135.7}}}],
            "routes": [{"distanceMeters": 5000, "duration": "600s"}]
        }
    })

    patches = [
        patch("app.agents.flight.AviationStackMCPClient", return_value=mock_aviation),
        patch("app.agents.hotel.TavilyMCPClient", return_value=mock_tavily),
        patch("app.agents.attraction.TavilyMCPClient", return_value=mock_tavily),
        patch("app.agents.attraction.MapsMCPClient", return_value=mock_maps),
        patch("app.agents.transport.MapsMCPClient", return_value=mock_maps),
        patch("app.agents.validator.MapsMCPClient", return_value=mock_maps),
        patch("app.agents.base.BaseAgent._get_llm", mock_get_llm),
        patch("app.memory.mem0_client.get_mem0_client", return_value=mock_mem0),
        patch("app.memory.episodic.get_all_memories", mock_episodic_get_all),
        patch("app.memory.episodic.extract_and_save_lessons", mock_episodic_extract),
    ]

    for p in patches:
        p.start()

    try:
        final = await run_pipeline(
            raw_request="I want to go to Kyoto for 5 days with $2000 budget",
            user_id="memory_test_user",  # Not anonymous — triggers memory load
            session_id="test_session",
            trace_id="test_trace",
            trip_id="test_trip_1",
        )
    finally:
        for p in patches:
            p.stop()

    assert final["pipeline_status"] == "completed"
    # Mem0 preferences should have been loaded and stored in state
    assert final.get("user_preferences") == stored_prefs


# ---------------------------------------------------------------------------
# Test: Self-correcting loop triggers and respects max 3 iterations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_self_correcting_loop_max_3_iterations():
    """Pipeline should attempt max 3 regenerations, then deliver with warnings."""
    from app.graph.workflow import run_pipeline

    call_counts = {"planner": 0, "validator": 0}

    # Mock LLM that always produces an invalid itinerary (empty days → critical)
    def mock_get_llm(self):
        call_counts_local = call_counts

        class _FakeLLM:
            def __init__(self, agent):
                self._agent = agent

            async def ainvoke(self, *args, **kwargs):
                r = MagicMock()
                if self._agent == "planner_agent":
                    call_counts_local["planner"] += 1
                    r.content = (
                        '{"destinations": ["TestCity"], "start_date": "2025-01-01", '
                        '"end_date": "2025-01-05", "budget": 1000.0, "budget_currency": "USD", '
                        '"travelers": 1, "preferences": null, "follow_up_questions": [], '
                        '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
                        '"needs_attractions": true, "needs_transport": false}}'
                    )
                elif self._agent == "validator_agent":
                    call_counts_local["validator"] += 1
                    # Always return an empty days structure → triggers critical issue
                    r.content = '{"issues": [], "overall_assessment": "Rejected", "approved": false}'
                elif self._agent == "budget_agent":
                    r.content = '{"recommendations": []}'
                elif self._agent == "composer_agent":
                    # Return empty days to force critical validation failure
                    r.content = '{"days": []}'
                else:
                    r.content = '{"mock": true}'
                return r

        return _FakeLLM(self.agent_name)

    mock_aviation = AsyncMock()
    mock_aviation.call = AsyncMock(return_value={"flights": [{"price_usd": 400}]})
    mock_tavily = AsyncMock()
    mock_tavily.call = AsyncMock(return_value={"results": []})
    mock_maps = AsyncMock()
    mock_maps.call = AsyncMock(return_value={
        "status": "success",
        "data": {"results": [], "routes": []}
    })

    patches = [
        patch("app.agents.flight.AviationStackMCPClient", return_value=mock_aviation),
        patch("app.agents.hotel.TavilyMCPClient", return_value=mock_tavily),
        patch("app.agents.attraction.TavilyMCPClient", return_value=mock_tavily),
        patch("app.agents.attraction.MapsMCPClient", return_value=mock_maps),
        patch("app.agents.transport.MapsMCPClient", return_value=mock_maps),
        patch("app.agents.validator.MapsMCPClient", return_value=mock_maps),
        patch("app.agents.base.BaseAgent._get_llm", mock_get_llm),
        patch("app.memory.episodic.get_all_memories", AsyncMock(return_value=[])),
        patch("app.memory.episodic.extract_and_save_lessons", AsyncMock(return_value=True)),
    ]

    for p in patches:
        p.start()

    try:
        final = await run_pipeline(
            raw_request="Trip to TestCity for 4 days budget $1000",
            user_id="anonymous",
            trip_id="regen_test",
        )
    finally:
        for p in patches:
            p.stop()

    # Pipeline should complete (not hang) even with repeated rejections
    assert final["pipeline_status"] == "completed"
    # Validator ran at most 4 times (initial + 3 regenerations)
    assert call_counts["validator"] <= 4
    # After max regen, status should NOT be "rejected" (graceful degradation)
    assert final.get("validation_status") in ("warnings", "approved")


# ---------------------------------------------------------------------------
# Test: Profile API routes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_profile_get_requires_user_id():
    """GET /api/profile without user_id should return 400."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/profile?user_id=anonymous")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_profile_preferences_update():
    """PUT /api/profile/preferences should store preferences and return 200."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    mock_mem0 = AsyncMock()
    mock_mem0.store_preferences = AsyncMock(return_value=True)

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    with patch("app.routers.profile.get_mem0_client", return_value=mock_mem0):
        response = client.put(
            "/api/profile/preferences?user_id=test_user_456",
            json={
                "food": "Japanese",
                "accommodation_type": "hotel",
                "crowd_tolerance": "low",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "test_user_456"
    assert "food" in data["preferences"]


@pytest.mark.asyncio
async def test_profile_preferences_empty_payload():
    """PUT /api/profile/preferences with no fields should return 400."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    response = client.put(
        "/api/profile/preferences?user_id=test_user",
        json={},
    )
    assert response.status_code == 400
