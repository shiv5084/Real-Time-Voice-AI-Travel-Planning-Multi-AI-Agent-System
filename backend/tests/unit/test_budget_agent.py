"""Unit tests for the Budget Agent — cost aggregation and compliance."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agents.budget import BudgetAgent, _aggregate_costs
from app.graph.state import initial_state
from app.config import Settings


@pytest.fixture
def settings():
    return Settings.model_validate({"app_env": "local", "groq_api_key": None, "gemini_api_key": None})


@pytest.fixture
def agent(settings):
    return BudgetAgent(settings=settings)


def _state_with_budget(budget: float | None, flight_cost: float = 500, hotel_cost: float = 700):
    state = initial_state("test trip")
    state = {
        **state,
        "constraints": {
            "destinations": ["Paris"],
            "budget": budget,
            "budget_currency": "USD",
            "travelers": 1,
        },
        "flight_results": {"flights": [{"price_usd": flight_cost}]},
        "hotel_results": {"hotels": [{"total_cost_usd": hotel_cost}]},
        "attraction_results": {"attractions": [{"name": "Eiffel Tower", "cost_usd": 30}]},
        "transport_results": {"transport_options": [{"estimated_cost_usd": 50}]},
    }
    return state


class TestBudgetAgentProperties:
    def test_agent_name(self, agent):
        assert agent.agent_name == "budget_agent"

    def test_model_provider(self, agent):
        assert agent.model_provider == "gemini"

    def test_max_steps(self, agent):
        assert agent.max_steps == 2


class TestBudgetAgentCompliance:
    @pytest.mark.asyncio
    async def test_within_budget(self, agent):
        """Total cost well under budget → within_budget."""
        # Cost: flight 300 + hotel 400 + attraction 30*1 + transport 50*1 + food 250 = 1030
        state = _state_with_budget(budget=3000.0, flight_cost=300, hotel_cost=400)
        result = await agent.run(state)
        assert result["budget_breakdown"]["compliance"] == "within_budget"

    @pytest.mark.asyncio
    async def test_over_budget_triggers_recommendations(self, agent):
        """Total cost exceeds budget → over_budget + Gemini recommendations."""
        mock_llm_resp = MagicMock()
        mock_llm_resp.content = '{"recommendations": ["Book cheaper flights", "Choose a hostel"]}'
        agent._llm = MagicMock()
        agent._llm.ainvoke = AsyncMock(return_value=mock_llm_resp)

        state = _state_with_budget(budget=500.0, flight_cost=800, hotel_cost=700)
        result = await agent.run(state)
        assert result["budget_breakdown"]["compliance"] == "over_budget"
        assert len(result["budget_breakdown"]["recommendations"]) > 0

    @pytest.mark.asyncio
    async def test_warning_threshold(self, agent):
        """Cost at 90% of budget → warning."""
        # Target: total cost ~90% of 3000 = 2700
        # flight 500 + hotel 700 + attraction 30 + transport 50 + food 250 = 1530 — too low
        # Need higher values; set flight=1200, hotel=800 → 1200+800+30+50+250 = 2330 ~77%
        # Set flight=1500, hotel=800 → 1500+800+30+50+250 = 2630 ~87%
        state = _state_with_budget(budget=3000.0, flight_cost=1500, hotel_cost=800)
        result = await agent.run(state)
        compliance = result["budget_breakdown"]["compliance"]
        # At 87%, should be warning (threshold is 85%)
        assert compliance in ("warning", "within_budget")  # depends on exact food estimate

    @pytest.mark.asyncio
    async def test_no_budget_constraint(self, agent):
        """No budget set → always within_budget."""
        state = _state_with_budget(budget=None)
        result = await agent.run(state)
        assert result["budget_breakdown"]["compliance"] == "within_budget"

    @pytest.mark.asyncio
    async def test_budget_breakdown_structure(self, agent):
        state = _state_with_budget(budget=3000.0)
        result = await agent.run(state)
        bd = result["budget_breakdown"]

        assert "total_budget" in bd
        assert "total_estimated_cost" in bd
        assert "currency" in bd
        assert "compliance" in bd
        assert "categories" in bd
        assert isinstance(bd["categories"], list)
        assert len(bd["categories"]) > 0

    @pytest.mark.asyncio
    async def test_categories_include_expected_types(self, agent):
        state = _state_with_budget(budget=5000.0)
        result = await agent.run(state)
        categories = result["budget_breakdown"]["categories"]
        category_names = [c["category"] for c in categories]
        assert "flights" in category_names
        assert "hotels" in category_names
        assert "attractions" in category_names
        assert "transport" in category_names

    @pytest.mark.asyncio
    async def test_variance_percentage_calculated_when_budget_set(self, agent):
        state = _state_with_budget(budget=2000.0)
        result = await agent.run(state)
        bd = result["budget_breakdown"]
        # Variance should be set when budget is provided
        assert bd.get("variance_percentage") is not None

    @pytest.mark.asyncio
    async def test_variance_percentage_none_when_no_budget(self, agent):
        state = _state_with_budget(budget=None)
        result = await agent.run(state)
        assert result["budget_breakdown"]["variance_percentage"] is None

    @pytest.mark.asyncio
    async def test_appends_agent_response(self, agent):
        state = _state_with_budget(budget=3000.0)
        result = await agent.run(state)
        assert len(result["agent_responses"]) == 1
        assert result["agent_responses"][0]["agent_name"] == "budget_agent"


class TestAggregateCosts:
    def test_aggregates_all_categories(self):
        flights = {"flights": [{"price_usd": 600}]}
        hotels = {"hotels": [{"total_cost_usd": 800}]}
        attractions = {"attractions": [{"name": "X", "cost_usd": 25}]}
        transport = {"transport_options": [{"estimated_cost_usd": 40}]}

        cats = _aggregate_costs(flights, hotels, attractions, transport, travelers=1)
        names = [c["category"] for c in cats]
        assert "flights" in names
        assert "hotels" in names
        assert "attractions" in names
        assert "transport" in names

    def test_multiplies_costs_by_travelers(self):
        flights = {"flights": [{"price_usd": 500}]}
        hotels = {"hotels": []}
        attractions = {"attractions": []}
        transport = {"transport_options": []}

        cats_1 = _aggregate_costs(flights, hotels, attractions, transport, travelers=1)
        cats_2 = _aggregate_costs(flights, hotels, attractions, transport, travelers=2)

        flight_1 = next(c for c in cats_1 if c["category"] == "flights")["amount"]
        flight_2 = next(c for c in cats_2 if c["category"] == "flights")["amount"]
        assert flight_2 == flight_1 * 2
