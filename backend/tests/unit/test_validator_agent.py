"""Unit tests for the Validator / Critic Agent."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.validator import ValidatorAgent, _structural_validation, _time_diff_minutes
from app.graph.state import initial_state
from app.config import Settings


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
    return ValidatorAgent(settings=settings)


def _state_with_itinerary(itinerary: dict, budget_compliance: str = "within_budget", budget: float = 3000.0, regen: int = 0):
    state = initial_state("test")
    return {
        **state,
        "constraints": {"destinations": ["Paris"], "budget": budget, "travelers": 1},
        "itinerary": itinerary,
        "budget_breakdown": {
            "total_budget": budget,
            "total_estimated_cost": budget * 0.7,
            "compliance": budget_compliance,
        },
        "regeneration_count": regen,
    }


_GOOD_ITINERARY = {
    "days": [
        {
            "day": 1, "date": "2025-06-01", "location": "Paris",
            "activities": [
                {"name": "Arrive", "type": "hotel", "start_time": "14:00", "end_time": "15:00"},
                {"name": "Walk", "type": "attraction", "start_time": "16:00", "end_time": "18:00"},
            ],
        },
        {
            "day": 2, "date": "2025-06-02", "location": "Paris",
            "activities": [
                {"name": "Breakfast", "type": "restaurant", "start_time": "08:00", "end_time": "09:00"},
                {"name": "Louvre", "type": "attraction", "start_time": "09:30", "end_time": "13:00"},
                {"name": "Lunch", "type": "restaurant", "start_time": "13:30", "end_time": "14:30"},
            ],
        },
    ]
}

_BAD_ITINERARY_NO_DAYS = {"days": []}

_BAD_ITINERARY_WRONG_ORDER = {
    "days": [
        {"day": 2, "activities": []},  # Starts at day 2
        {"day": 1, "activities": []},
    ]
}

_BAD_ITINERARY_BUFFER = {
    "days": [
        {
            "day": 1, "activities": [
                {"name": "A", "start_time": "09:00", "end_time": "10:00"},
                {"name": "B", "start_time": "10:10", "end_time": "11:00"},  # only 10 min gap
            ],
        }
    ]
}


class TestValidatorAgent:
    def test_agent_properties(self, agent):
        assert agent.agent_name == "validator_agent"
        assert agent.model_provider == "gemini"
        assert agent.max_steps == 2

    @pytest.mark.asyncio
    async def test_approved_on_good_itinerary(self, agent):
        mock_maps = AsyncMock()
        mock_maps.call = AsyncMock(return_value={
            "status": "success",
            "data": {"results": [{"geometry": {"location": {"lat": 48.8566, "lng": 2.3522}}}]}
        })
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"issues": [], "overall_assessment": "Looks good", "approved": true}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.validator.MapsMCPClient", return_value=mock_maps):
            state = _state_with_itinerary(_GOOD_ITINERARY)
            result = await agent.run(state)

        assert result["validation_status"] == "approved"
        assert result["validation_issues"] is not None

    @pytest.mark.asyncio
    async def test_rejected_on_critical_issues(self, agent):
        mock_maps = AsyncMock()
        mock_maps.call = AsyncMock(return_value={"status": "success", "data": {"results": []}})
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"issues": [{"severity": "critical", "description": "Date conflict", "affected_day": 2}], "approved": false}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.validator.MapsMCPClient", return_value=mock_maps):
            state = _state_with_itinerary(_GOOD_ITINERARY, regen=0)
            result = await agent.run(state)

        assert result["validation_status"] == "rejected"
        assert result["regeneration_count"] == 1  # Incremented from 0

    @pytest.mark.asyncio
    async def test_warnings_on_major_issues(self, agent):
        mock_maps = AsyncMock()
        mock_maps.call = AsyncMock(return_value={"status": "success", "data": {"results": []}})
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"issues": [{"severity": "major", "description": "Over budget", "affected_day": null}], "approved": false}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.validator.MapsMCPClient", return_value=mock_maps):
            state = _state_with_itinerary(_GOOD_ITINERARY, budget_compliance="over_budget")
            result = await agent.run(state)

        assert result["validation_status"] == "warnings"

    @pytest.mark.asyncio
    async def test_max_regen_count_stops_rejection(self, agent):
        """At regen_count=3, should not reject even with critical issues."""
        mock_maps = AsyncMock()
        mock_maps.call = AsyncMock(return_value={"status": "success", "data": {"results": []}})
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"issues": [{"severity": "critical", "description": "Critical issue", "affected_day": 1}], "approved": false}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.validator.MapsMCPClient", return_value=mock_maps):
            state = _state_with_itinerary(_GOOD_ITINERARY, regen=3)
            result = await agent.run(state)

        # With regen_count=3, should not reject (max reached)
        assert result["validation_status"] in ("warnings", "approved")

    @pytest.mark.asyncio
    async def test_appends_agent_response(self, agent):
        mock_maps = AsyncMock()
        mock_maps.call = AsyncMock(return_value={"status": "success", "data": {"results": []}})
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"issues": []}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        with patch("app.agents.validator.MapsMCPClient", return_value=mock_maps):
            state = _state_with_itinerary(_GOOD_ITINERARY)
            result = await agent.run(state)

        assert result["agent_responses"][-1]["agent_name"] == "validator_agent"


class TestStructuralValidation:
    def test_empty_days_is_critical(self):
        issues = _structural_validation({"days": []}, {}, {})
        severities = [i["severity"] for i in issues]
        assert "critical" in severities

    def test_missing_days_key_is_critical(self):
        issues = _structural_validation({}, {}, {})
        severities = [i["severity"] for i in issues]
        assert "critical" in severities

    def test_buffer_violation_detected(self):
        issues = _structural_validation(_BAD_ITINERARY_BUFFER, {}, {})
        descriptions = [i["description"] for i in issues]
        assert any("30" in d or "buffer" in d.lower() for d in descriptions)

    def test_good_itinerary_has_no_critical_issues(self):
        issues = _structural_validation(_GOOD_ITINERARY, {}, {})
        critical = [i for i in issues if i["severity"] == "critical"]
        assert len(critical) == 0

    def test_over_budget_adds_major_issue(self):
        budget = {"total_budget": 1000.0, "total_estimated_cost": 1500.0, "compliance": "over_budget"}
        issues = _structural_validation(_GOOD_ITINERARY, budget, {"budget": 1000.0})
        major_issues = [i for i in issues if i["severity"] == "major"]
        assert len(major_issues) >= 1


class TestTimeDiffMinutes:
    def test_30_min_gap(self):
        assert _time_diff_minutes("09:00", "09:30") == 30

    def test_60_min_gap(self):
        assert _time_diff_minutes("14:00", "15:00") == 60

    def test_negative_gap(self):
        # End before start — negative
        assert _time_diff_minutes("10:00", "09:00") == -60

    def test_invalid_format_returns_none(self):
        assert _time_diff_minutes("invalid", "09:00") is None
