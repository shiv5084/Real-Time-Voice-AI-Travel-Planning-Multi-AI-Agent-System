"""Unit tests for the Transport Agent."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.transport import TransportAgent
from app.graph.state import initial_state
from app.config import Settings


@pytest.fixture
def settings():
    return Settings.model_validate({"app_env": "local", "groq_api_key": None, "gemini_api_key": None})


@pytest.fixture
def agent(settings):
    return TransportAgent(settings=settings)


class TestTransportAgent:
    def test_agent_properties(self, agent):
        assert agent.agent_name == "transport_agent"
        assert agent.model_provider == "groq"
        assert agent.max_steps == 3

    @pytest.mark.asyncio
    async def test_run_with_mocked_clients(self, agent):
        mock_maps = AsyncMock()
        mock_maps.call = AsyncMock(return_value={
            "status": "success",
            "data": {
                "results": [{"geometry": {"location": {"lat": 48.8566, "lng": 2.3522}}}],
                "routes": [{"distanceMeters": 15000, "duration": "1800s"}]
            }
        })
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"transport_options": [{"mode": "taxi", "duration_minutes": 30, "estimated_cost_usd": 25}]}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.transport.MapsMCPClient", return_value=mock_maps):
            state = initial_state("Paris transport")
            state = {**state, "constraints": {"destinations": ["Paris"], "travelers": 1}}
            result = await agent.run(state)

        assert result["transport_results"] is not None
        assert len(result["agent_responses"]) == 1

    @pytest.mark.asyncio
    async def test_run_handles_maps_failure(self, agent):
        mock_maps = AsyncMock()
        mock_maps.call = AsyncMock(side_effect=Exception("Maps unavailable"))
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"transport_options": []}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.transport.MapsMCPClient", return_value=mock_maps):
            state = initial_state("Tokyo transport")
            state = {**state, "constraints": {"destinations": ["Tokyo"], "travelers": 1}}
            result = await agent.run(state)

        # Should not crash on Maps failure
        assert result["transport_results"] is not None
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_run_appends_agent_response(self, agent):
        mock_maps = AsyncMock()
        mock_maps.call = AsyncMock(return_value={"status": "success", "data": {}})
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"transport_options": []}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.transport.MapsMCPClient", return_value=mock_maps):
            state = initial_state("test")
            state = {**state, "constraints": {"destinations": ["Sydney"], "travelers": 2}}
            result = await agent.run(state)

        assert result["agent_responses"][-1]["agent_name"] == "transport_agent"
