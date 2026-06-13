"""Unit tests for the Itinerary Composer Agent."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agents.composer import ComposerAgent, _fallback_itinerary
from app.graph.state import initial_state
from app.config import Settings


@pytest.fixture
def settings():
    return Settings.model_validate({"app_env": "local", "groq_api_key": None, "gemini_api_key": None})


@pytest.fixture
def agent(settings):
    return ComposerAgent(settings=settings)


def _rich_state():
    state = initial_state("Paris trip")
    return {
        **state,
        "constraints": {
            "destinations": ["Paris"],
            "start_date": "2025-06-01",
            "end_date": "2025-06-06",
            "budget": 2000.0,
            "budget_currency": "USD",
            "travelers": 1,
        },
        "flight_results": {"flights": [{"airline": "Air France", "price_usd": 650}]},
        "hotel_results": {"hotels": [{"name": "Hotel Paris", "total_cost_usd": 500}]},
        "attraction_results": {"attractions": [
            {"name": "Eiffel Tower", "cost_usd": 25, "estimated_duration_hours": 2},
            {"name": "Louvre", "cost_usd": 15, "estimated_duration_hours": 3},
        ]},
        "transport_results": {"transport_options": [{"mode": "metro", "estimated_cost_usd": 20}]},
        "budget_breakdown": {"total_estimated_cost": 1900, "compliance": "within_budget"},
    }


class TestComposerAgent:
    def test_agent_properties(self, agent):
        assert agent.agent_name == "composer_agent"
        assert agent.model_provider == "groq"
        assert agent.max_steps == 3

    @pytest.mark.asyncio
    async def test_run_produces_itinerary(self, agent):
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = (
            '{"days": ['
            '{"day": 1, "date": "2025-06-01", "location": "Paris", '
            '"activities": [{"name": "Arrive", "type": "hotel", "start_time": "14:00", "end_time": "15:00", "cost_usd": 0}], '
            '"total_cost_usd": 0, "notes": "Arrival day"},'
            '{"day": 2, "date": "2025-06-02", "location": "Paris", '
            '"activities": [{"name": "Eiffel Tower", "type": "attraction", "start_time": "09:30", "end_time": "11:30", "cost_usd": 25}], '
            '"total_cost_usd": 25, "notes": ""}'
            ']}'
        )
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        state = _rich_state()
        result = await agent.run(state)

        assert result["itinerary"] is not None
        assert "days" in result["itinerary"]
        assert len(result["itinerary"]["days"]) >= 1

    @pytest.mark.asyncio
    async def test_run_falls_back_on_llm_failure(self, agent):
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(side_effect=Exception("LLM failed"))

        state = _rich_state()
        result = await agent.run(state)

        # Should use fallback itinerary
        assert result["itinerary"] is not None
        assert "days" in result["itinerary"]

    @pytest.mark.asyncio
    async def test_run_appends_agent_response(self, agent):
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"days": []}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        state = _rich_state()
        result = await agent.run(state)

        assert len(result["agent_responses"]) == 1
        assert result["agent_responses"][0]["agent_name"] == "composer_agent"

    def test_fallback_itinerary_structure(self):
        itinerary = _fallback_itinerary("Barcelona", "2025-07-01", "2025-07-06")
        assert "days" in itinerary
        assert len(itinerary["days"]) >= 1
        for day in itinerary["days"]:
            assert "day" in day
            assert "activities" in day
            assert isinstance(day["activities"], list)
