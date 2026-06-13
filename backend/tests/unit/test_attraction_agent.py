"""Unit tests for the Attraction Agent."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.attraction import AttractionAgent
from app.graph.state import initial_state
from app.config import Settings


@pytest.fixture
def settings():
    return Settings.model_validate({"app_env": "local", "groq_api_key": None, "gemini_api_key": None})


@pytest.fixture
def agent(settings):
    return AttractionAgent(settings=settings)


class TestAttractionAgent:
    def test_agent_properties(self, agent):
        assert agent.agent_name == "attraction_agent"
        assert agent.model_provider == "groq"
        assert agent.max_steps == 3

    @pytest.mark.asyncio
    async def test_run_with_mocked_clients(self, agent):
        mock_tavily = AsyncMock()
        mock_tavily.call = AsyncMock(return_value={
            "status": "success",
            "data": {"results": [{"title": "Eiffel Tower", "content": "Iconic Paris landmark"}]}
        })
        mock_maps = AsyncMock()
        mock_maps.call = AsyncMock(return_value={
            "status": "success",
            "data": {"results": [{"geometry": {"location": {"lat": 48.8566, "lng": 2.3522}}}]}
        })

        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"attractions": [{"name": "Eiffel Tower", "cost_usd": 25}]}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.attraction.TavilyMCPClient", return_value=mock_tavily), \
             patch("app.agents.attraction.MapsMCPClient", return_value=mock_maps):
            state = initial_state("Paris attractions")
            state = {**state, "constraints": {"destinations": ["Paris"], "travelers": 1}}
            result = await agent.run(state)

        assert result["attraction_results"] is not None
        assert len(result["agent_responses"]) == 1

    @pytest.mark.asyncio
    async def test_run_handles_maps_failure(self, agent):
        mock_tavily = AsyncMock()
        mock_tavily.call = AsyncMock(return_value={"status": "success", "data": {"results": []}})
        mock_maps = AsyncMock()
        mock_maps.call = AsyncMock(side_effect=Exception("Maps down"))

        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"attractions": []}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.attraction.TavilyMCPClient", return_value=mock_tavily), \
             patch("app.agents.attraction.MapsMCPClient", return_value=mock_maps):
            state = initial_state("test")
            state = {**state, "constraints": {"destinations": ["Madrid"], "travelers": 1}}
            result = await agent.run(state)

        # Maps failure should not crash pipeline
        assert result["attraction_results"] is not None

    @pytest.mark.asyncio
    async def test_run_appends_agent_response(self, agent):
        mock_tavily = AsyncMock()
        mock_tavily.call = AsyncMock(return_value={"status": "success", "data": {"results": []}})
        mock_maps = AsyncMock()
        mock_maps.call = AsyncMock(return_value={"status": "success", "data": {"results": []}})
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"attractions": []}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.attraction.TavilyMCPClient", return_value=mock_tavily), \
             patch("app.agents.attraction.MapsMCPClient", return_value=mock_maps):
            state = initial_state("test")
            state = {**state, "constraints": {"destinations": ["Amsterdam"], "travelers": 1}}
            result = await agent.run(state)

        assert result["agent_responses"][-1]["agent_name"] == "attraction_agent"
