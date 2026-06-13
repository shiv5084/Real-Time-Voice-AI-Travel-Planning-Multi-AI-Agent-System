"""Unit tests for the Flight Agent."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.flight import FlightAgent
from app.graph.state import initial_state
from app.config import Settings
from app.utils.errors import ToolError


@pytest.fixture
def settings():
    return Settings.model_validate({
        "app_env": "local",
        "groq_api_key": "",
        "gemini_api_key": "",
        "enable_llm_cache": False,
        "enable_llm_streaming": False,
    })


@pytest.fixture
def agent(settings):
    return FlightAgent(settings=settings)


class TestFlightAgent:
    def test_agent_properties(self, agent):
        assert agent.agent_name == "flight_agent"
        assert agent.model_provider == "groq"
        assert agent.max_steps == 3

    @pytest.mark.asyncio
    async def test_run_with_mocked_client_and_llm(self, agent):
        mock_aviation = AsyncMock()
        mock_aviation.call = AsyncMock(return_value={
            "flights": [
                {"airline": "Air France", "price_usd": 650, "duration_minutes": 420, "layovers": 0},
                {"airline": "British Airways", "price_usd": 700, "duration_minutes": 460, "layovers": 1},
            ]
        })
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"flights": [{"airline": "Air France", "price_usd": 650}]}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.flight.SkyscannerMCPClient", return_value=mock_aviation):
            state = initial_state("Paris trip")
            state = {**state, "constraints": {
                "destinations": ["NYC", "Paris"],
                "start_date": "2025-06-01",
                "end_date": "2025-06-08",
                "budget": 3000.0,
                "travelers": 1,
            }}
            result = await agent.run(state)

        assert result["flight_results"] is not None
        assert len(result["agent_responses"]) == 1

    @pytest.mark.asyncio
    async def test_run_handles_tool_error_gracefully(self, agent):
        mock_aviation = AsyncMock()
        mock_aviation.call = AsyncMock(side_effect=ToolError("API unavailable", tool="aviation"))

        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"flights": []}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.flight.SkyscannerMCPClient", return_value=mock_aviation):
            state = initial_state("Paris trip")
            state = {**state, "constraints": {"destinations": ["Paris"], "travelers": 1}}
            result = await agent.run(state)

        # Pipeline should continue even with tool error
        assert result["flight_results"] is not None
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_run_without_api_keys(self, agent):
        """Agent with no keys should use MockLLM and not crash."""
        state = initial_state("London trip")
        state = {**state, "constraints": {"destinations": ["London"], "travelers": 2}}

        with patch("app.agents.flight.SkyscannerMCPClient") as mock_cls:
            mock_inst = AsyncMock()
            mock_inst.call = AsyncMock(side_effect=Exception("No key"))
            mock_cls.return_value = mock_inst
            result = await agent.run(state)

        assert result["flight_results"] is not None

    @pytest.mark.asyncio
    async def test_run_adds_agent_response_to_state(self, agent):
        mock_aviation = AsyncMock()
        mock_aviation.call = AsyncMock(return_value={"flights": []})
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"flights": []}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.flight.SkyscannerMCPClient", return_value=mock_aviation):
            state = initial_state("test")
            state = {**state, "constraints": {"destinations": ["Tokyo"], "travelers": 1}}
            prev_responses = list(state["agent_responses"])
            result = await agent.run(state)

        assert len(result["agent_responses"]) == len(prev_responses) + 1
        assert result["agent_responses"][-1]["agent_name"] == "flight_agent"
