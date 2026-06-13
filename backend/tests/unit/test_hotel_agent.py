"""Unit tests for the Hotel Agent."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.hotel import HotelAgent
from app.graph.state import initial_state
from app.config import Settings
from app.utils.errors import ToolError


@pytest.fixture
def settings():
    return Settings.model_validate({"app_env": "local", "groq_api_key": None, "gemini_api_key": None})


@pytest.fixture
def agent(settings):
    return HotelAgent(settings=settings)


class TestHotelAgent:
    def test_agent_properties(self, agent):
        assert agent.agent_name == "hotel_agent"
        assert agent.model_provider == "groq"
        assert agent.max_steps == 3

    @pytest.mark.asyncio
    async def test_run_with_mocked_client_and_llm(self, agent):
        mock_tavily = AsyncMock()
        mock_tavily.call = AsyncMock(return_value={
            "results": [
                {"title": "Hotel Le Marais", "content": "4-star hotel in Paris, $200/night"},
                {"title": "Ibis Paris", "content": "Budget hotel, $90/night"},
            ]
        })
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"hotels": [{"name": "Hotel Le Marais", "price_per_night_usd": 200}]}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.hotel.TavilyMCPClient", return_value=mock_tavily):
            state = initial_state("Paris hotel")
            state = {**state, "constraints": {"destinations": ["Paris"], "budget": 1500.0, "travelers": 1}}
            result = await agent.run(state)

        assert result["hotel_results"] is not None
        assert len(result["agent_responses"]) == 1

    @pytest.mark.asyncio
    async def test_run_handles_tool_error_gracefully(self, agent):
        mock_tavily = AsyncMock()
        mock_tavily.call = AsyncMock(side_effect=ToolError("Tavily unavailable", tool="tavily"))
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"hotels": []}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.hotel.TavilyMCPClient", return_value=mock_tavily):
            state = initial_state("test")
            state = {**state, "constraints": {"destinations": ["Rome"], "travelers": 1}}
            result = await agent.run(state)

        assert result["hotel_results"] is not None
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_run_appends_agent_response(self, agent):
        mock_tavily = AsyncMock()
        mock_tavily.call = AsyncMock(return_value={"results": []})
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"hotels": []}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.hotel.TavilyMCPClient", return_value=mock_tavily):
            state = initial_state("test")
            state = {**state, "constraints": {"destinations": ["Berlin"], "travelers": 1}}
            result = await agent.run(state)

        assert result["agent_responses"][-1]["agent_name"] == "hotel_agent"
