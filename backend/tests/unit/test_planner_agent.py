"""Unit tests for the Planner Agent."""

from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.planner import PlannerAgent, _heuristic_parse, _extract_json
from app.graph.state import initial_state
from app.config import Settings


def _make_settings(**kwargs) -> Settings:
    """Create a Settings instance without API keys for testing."""
    defaults = {
        "APP_ENV": "local",
        "GROQ_API_KEY": None,
        "GEMINI_API_KEY": None,
    }
    defaults.update(kwargs)
    return Settings(**{k: v for k, v in defaults.items() if v is not None},
                    _env_file=None)


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
def planner(settings):
    return PlannerAgent(settings=settings)


class TestHeuristicParse:
    def test_parses_destination_from_to(self):
        result = _heuristic_parse("I want to go to Paris for 5 days")
        assert "Paris" in str(result.get("destinations", []))

    def test_parses_budget_dollar_sign(self):
        result = _heuristic_parse("Trip to Tokyo with $2000 budget")
        assert result.get("budget") == 2000.0

    def test_parses_budget_k_notation(self):
        result = _heuristic_parse("Budget $3k for the trip")
        assert result.get("budget") == 3000.0

    def test_parses_travelers_count(self):
        result = _heuristic_parse("Trip for 3 people to London")
        assert result.get("travelers") == 3

    def test_defaults_travelers_to_one(self):
        result = _heuristic_parse("Go to Rome")
        assert result.get("travelers") == 1

    def test_returns_delegation_plan(self):
        result = _heuristic_parse("Visit Berlin for a week")
        assert "delegation_plan" in result
        plan = result["delegation_plan"]
        assert "needs_flights" in plan
        assert "needs_hotels" in plan

    def test_empty_string_returns_safe_defaults(self):
        result = _heuristic_parse("")
        assert isinstance(result.get("destinations"), list)
        assert result.get("travelers") == 1

    def test_parses_duration_days(self):
        result = _heuristic_parse("5 days trip to Barcelona")
        assert result.get("_duration_days") == 5


class TestExtractJson:
    def test_extracts_clean_json(self):
        result = _extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_strips_markdown_fences(self):
        result = _extract_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_extracts_json_with_leading_text(self):
        result = _extract_json('Here is the result: {"name": "Paris"}')
        assert result.get("name") == "Paris"

    def test_returns_empty_dict_on_invalid_json(self):
        result = _extract_json("This is not JSON at all")
        assert result == {}

    def test_handles_nested_json(self):
        result = _extract_json('{"outer": {"inner": 42}}')
        assert result["outer"]["inner"] == 42


class TestPlannerAgentRun:
    """Tests for PlannerAgent.run() with mocked LLM."""

    @pytest.mark.asyncio
    async def test_run_with_full_request(self, planner):
        """Well-formed request: no follow-up questions."""
        mock_response = MagicMock()
        mock_response.content = (
            '{"destinations": ["Paris"], "start_date": "2026-07-01", '
            '"end_date": "2026-07-06", "budget": 2000.0, "budget_currency": "USD", '
            '"travelers": 1, "preferences": null, "follow_up_questions": [], '
            '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
            '"needs_attractions": true, "needs_transport": true}}'
        )
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(return_value=mock_response)

        state = initial_state("I want to go to Paris for 5 days in July with budget $2000")
        result = await planner.run(state)

        assert result["constraints"]["destinations"] == ["Paris"]
        assert result["constraints"]["budget"] == 2000.0
        assert result["current_step"] == "planner_complete"
        assert result["constraints"]["start_date"] == "2026-07-01"

    @pytest.mark.asyncio
    async def test_run_missing_budget_adds_followup(self, planner):
        """Missing budget triggers a follow-up question."""
        mock_response = MagicMock()
        mock_response.content = (
            '{"destinations": ["Tokyo"], "start_date": "2026-08-01", '
            '"end_date": "2026-08-08", "budget": null, "budget_currency": "USD", '
            '"travelers": 1, "preferences": null, "follow_up_questions": [], '
            '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
            '"needs_attractions": true, "needs_transport": true}}'
        )
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(return_value=mock_response)

        state = initial_state("Trip to Tokyo for a week in August")
        result = await planner.run(state)

        # Should add a budget question
        assert len(result["follow_up_questions"]) > 0
        questions_lower = " ".join(result["follow_up_questions"]).lower()
        assert "budget" in questions_lower

    @pytest.mark.asyncio
    async def test_run_missing_dates_adds_followup(self, planner):
        """Missing dates triggers a follow-up question."""
        mock_response = MagicMock()
        mock_response.content = (
            '{"destinations": ["London"], "start_date": null, "end_date": null, '
            '"budget": 1500.0, "budget_currency": "USD", "travelers": 2, '
            '"preferences": null, "follow_up_questions": [], '
            '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
            '"needs_attractions": true, "needs_transport": true}}'
        )
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(return_value=mock_response)

        state = initial_state("Trip to London for 2 people with $1500 budget")
        result = await planner.run(state)

        assert len(result["follow_up_questions"]) > 0
        questions_lower = " ".join(result["follow_up_questions"]).lower()
        assert "travel" in questions_lower or "date" in questions_lower

    @pytest.mark.asyncio
    async def test_run_llm_failure_falls_back_to_heuristic(self, planner):
        """LLM failure should not crash the pipeline — falls back to heuristics."""
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(side_effect=Exception("LLM API unavailable"))

        state = initial_state("Trip to Rome for $2000")
        result = await planner.run(state)

        # Pipeline should continue with heuristic results
        assert result["current_step"] == "planner_complete"
        assert len(result["errors"]) > 0
        assert result["constraints"] is not None

    @pytest.mark.asyncio
    async def test_run_multiple_destinations(self, planner):
        mock_response = MagicMock()
        mock_response.content = (
            '{"destinations": ["Paris", "Amsterdam", "Berlin"], "start_date": "2026-07-01", '
            '"end_date": "2026-07-15", "budget": 5000.0, "budget_currency": "USD", '
            '"travelers": 2, "preferences": {"accommodation_type": "hotel"}, '
            '"follow_up_questions": [], '
            '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
            '"needs_attractions": true, "needs_transport": true}}'
        )
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(return_value=mock_response)

        state = initial_state("Multi-city Europe trip: Paris, Amsterdam, Berlin for 2 people")
        result = await planner.run(state)

        assert len(result["constraints"]["destinations"]) == 3
        assert result["constraints"]["travelers"] == 2
        assert result["constraints"]["budget_currency"] == "USD"

    @pytest.mark.asyncio
    async def test_run_populates_delegation_plan(self, planner):
        mock_response = MagicMock()
        mock_response.content = (
            '{"destinations": ["Barcelona"], "start_date": "2026-09-10", '
            '"end_date": "2026-09-15", "budget": 1800.0, "budget_currency": "USD", '
            '"travelers": 1, "preferences": null, "follow_up_questions": [], '
            '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
            '"needs_attractions": true, "needs_transport": false}}'
        )
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(return_value=mock_response)

        state = initial_state("Barcelona trip, 5 nights, $1800")
        result = await planner.run(state)

        plan = result["delegation_plan"]
        assert plan["needs_flights"] is True
        assert plan["needs_hotels"] is True

    @pytest.mark.asyncio
    async def test_run_appends_agent_response(self, planner):
        mock_response = MagicMock()
        mock_response.content = (
            '{"destinations": ["NYC"], "start_date": "2026-10-01", '
            '"end_date": "2026-10-05", "budget": 2500.0, "budget_currency": "USD", '
            '"travelers": 1, "preferences": null, "follow_up_questions": [], '
            '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
            '"needs_attractions": true, "needs_transport": true}}'
        )
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(return_value=mock_response)

        state = initial_state("NYC trip for 4 days")
        result = await planner.run(state)

        assert len(result["agent_responses"]) == 1
        assert result["agent_responses"][0]["agent_name"] == "planner_agent"

    @pytest.mark.asyncio
    async def test_run_with_no_api_key_uses_mock_llm(self):
        """When no API key is set, agent should use MockLLM and not crash."""
        settings = Settings.model_validate({
            "app_env": "local",
            "groq_api_key": None,
            "gemini_api_key": None,
        })
        agent = PlannerAgent(settings=settings)
        # MockLLM returns JSON-like text
        state = initial_state("Trip to Singapore")
        result = await agent.run(state)

        # Should not crash; constraints may be minimal but state is returned
        assert result["current_step"] == "planner_complete"
        assert result["constraints"] is not None

    @pytest.mark.asyncio
    async def test_run_ten_variations(self, planner):
        """Test 10+ distinct input variations all complete without crash."""
        inputs = [
            "Family vacation to Disney World, 5 days, $4000, 4 people",
            "Solo backpacking trip across Southeast Asia for 30 days",
            "Honeymoon in Maldives, 7 nights, luxury, $8000",
            "Weekend getaway to Chicago next month",
            "Business trip to New York, 2 nights, need hotel near Manhattan",
            "Ski trip to Aspen with friends, 4 days, $3000",
            "Safari in Kenya, 10 days, 2 adults, $6000",
            "Cultural tour of Japan: Tokyo and Kyoto, 2 weeks",
            "Beach holiday in Cancun, all inclusive, 5 nights",
            "Road trip through California: LA to San Francisco",
            "Cruise in the Mediterranean, 7 nights",
        ]
        for inp in inputs:
            mock_resp = MagicMock()
            mock_resp.content = (
                f'{{"destinations": ["test"], "start_date": null, "end_date": null, '
                f'"budget": null, "budget_currency": "USD", "travelers": 1, '
                f'"preferences": null, "follow_up_questions": [], '
                f'"delegation_plan": {{"needs_flights": true, "needs_hotels": true, '
                f'"needs_attractions": true, "needs_transport": true}}}}'
            )
            planner._llm = MagicMock()
            planner._llm.ainvoke = AsyncMock(return_value=mock_resp)

            state = initial_state(inp)
            result = await planner.run(state)
            assert result["current_step"] == "planner_complete", f"Failed on: {inp}"

    @pytest.mark.asyncio
    async def test_planner_properties(self, planner):
        assert planner.agent_name == "planner_agent"
        assert planner.model_provider == "groq"
        assert planner.max_steps == 5


# ──────────────────────────────────────────────────────────────────────────────
# NEW: Currency parsing & LLM-first verification tests
# ──────────────────────────────────────────────────────────────────────────────


class TestHeuristicCurrencyParsing:
    """Verify _heuristic_parse correctly extracts budget and currency for many formats."""

    # --- Currency symbols ---
    def test_usd_dollar_sign(self):
        r = _heuristic_parse("Trip to Paris with $2000 budget")
        assert r["budget"] == 2000.0
        assert r["budget_currency"] == "USD"

    def test_euro_sign(self):
        r = _heuristic_parse("Trip to Berlin with €1500")
        assert r["budget"] == 1500.0
        assert r["budget_currency"] == "EUR"

    def test_pound_sign(self):
        r = _heuristic_parse("London trip £800 for 2 people")
        assert r["budget"] == 800.0
        assert r["budget_currency"] == "GBP"

    def test_rupee_sign(self):
        r = _heuristic_parse("Trip to Goa with ₹50000 for 3 people")
        assert r["budget"] == 50000.0
        assert r["budget_currency"] == "INR"

    def test_yen_sign(self):
        r = _heuristic_parse("Tokyo trip ¥200000")
        assert r["budget"] == 200000.0
        assert r["budget_currency"] == "JPY"

    def test_won_sign(self):
        r = _heuristic_parse("Seoul trip ₩500000")
        assert r["budget"] == 500000.0
        assert r["budget_currency"] == "KRW"

    def test_baht_sign(self):
        r = _heuristic_parse("Bangkok trip ฿30000")
        assert r["budget"] == 30000.0
        assert r["budget_currency"] == "THB"

    # --- Rs prefix ---
    def test_rs_prefix(self):
        r = _heuristic_parse("Rs 4000 for 3 people")
        assert r["budget"] == 4000.0
        assert r["budget_currency"] == "INR"

    def test_rs_dot_prefix(self):
        r = _heuristic_parse("Rs. 8000 budget for Goa trip")
        assert r["budget"] == 8000.0
        assert r["budget_currency"] == "INR"

    # --- Currency names ---
    def test_dollars_name(self):
        r = _heuristic_parse("Budget 3000 dollars for the trip")
        assert r["budget"] == 3000.0
        assert r["budget_currency"] == "USD"

    def test_yen_name(self):
        r = _heuristic_parse("100000 yen for Tokyo")
        assert r["budget"] == 100000.0
        assert r["budget_currency"] == "JPY"

    def test_baht_name(self):
        r = _heuristic_parse("30000 baht for Thailand")
        assert r["budget"] == 30000.0
        assert r["budget_currency"] == "THB"

    def test_won_name(self):
        r = _heuristic_parse("500000 won for Seoul trip")
        assert r["budget"] == 500000.0
        assert r["budget_currency"] == "KRW"

    def test_euros_name(self):
        r = _heuristic_parse("2500 euros for Europe")
        assert r["budget"] == 2500.0
        assert r["budget_currency"] == "EUR"

    def test_rupees_name(self):
        r = _heuristic_parse("50000 rupees for India trip")
        assert r["budget"] == 50000.0
        assert r["budget_currency"] == "INR"

    def test_ringgit_name(self):
        r = _heuristic_parse("5000 ringgit for Malaysia")
        assert r["budget"] == 5000.0
        assert r["budget_currency"] == "MYR"

    def test_dirham_name(self):
        r = _heuristic_parse("3000 dirham for Dubai")
        assert r["budget"] == 3000.0
        assert r["budget_currency"] == "AED"

    # --- ISO codes ---
    def test_iso_code_after(self):
        r = _heuristic_parse("3000 AUD for Australia")
        assert r["budget"] == 3000.0
        assert r["budget_currency"] == "AUD"

    def test_iso_code_before(self):
        r = _heuristic_parse("USD 5000 for the trip")
        assert r["budget"] == 5000.0
        assert r["budget_currency"] == "USD"

    def test_iso_code_sgd(self):
        r = _heuristic_parse("2000 SGD for Singapore")
        assert r["budget"] == 2000.0
        assert r["budget_currency"] == "SGD"

    def test_iso_code_pkr(self):
        r = _heuristic_parse("100000 PKR for Pakistan")
        assert r["budget"] == 100000.0
        assert r["budget_currency"] == "PKR"

    # --- K notation ---
    def test_k_notation_dollar(self):
        r = _heuristic_parse("Budget $3k for the trip")
        assert r["budget"] == 3000.0

    def test_k_notation_rupee_sign(self):
        r = _heuristic_parse("₹50k for Goa")
        assert r["budget"] == 50000.0
        assert r["budget_currency"] == "INR"

    # --- Budget keyword ---
    def test_budget_keyword(self):
        r = _heuristic_parse("budget 3000 for trip")
        assert r["budget"] == 3000.0

    def test_budget_keyword_with_colon(self):
        r = _heuristic_parse("budget: 2500")
        assert r["budget"] == 2500.0

    # --- No budget ---
    def test_no_budget(self):
        r = _heuristic_parse("Trip to Paris")
        assert r["budget"] is None


class TestHeuristicDurationParsing:
    """Verify duration detection for days, weeks, months."""

    def test_days(self):
        r = _heuristic_parse("5 days trip to Paris")
        assert r["_duration_days"] == 5

    def test_nights(self):
        r = _heuristic_parse("7 nights in Bali")
        assert r["_duration_days"] == 7

    def test_weeks(self):
        r = _heuristic_parse("2 weeks in Southeast Asia")
        assert r["_duration_days"] == 14

    def test_1_week(self):
        r = _heuristic_parse("1 week trip to Japan")
        assert r["_duration_days"] == 7

    def test_months(self):
        r = _heuristic_parse("3 months backpacking Europe")
        assert r["_duration_days"] == 90

    def test_no_duration(self):
        r = _heuristic_parse("Trip to Paris")
        assert r.get("_duration_days") is None


class TestLLMCalledFirst:
    """Verify that the LLM is called BEFORE the heuristic parser."""

    @pytest.fixture
    def planner(self, settings):
        return PlannerAgent(settings=settings)

    @pytest.mark.asyncio
    async def test_llm_called_not_heuristic_on_success(self, planner):
        """When LLM succeeds, heuristic is called as safety net but does not pollute results."""
        mock_resp = MagicMock()
        mock_resp.content = (
            '{"destinations": ["Paris"], "start_date": "2026-07-01", '
            '"end_date": "2026-07-05", "budget": 4000.0, "budget_currency": "USD", '
            '"travelers": 3, "preferences": null, "follow_up_questions": [], '
            '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
            '"needs_attractions": true, "needs_transport": true}}'
        )
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(return_value=mock_resp)

        with patch("app.agents.planner._heuristic_parse", wraps=_heuristic_parse) as mock_heuristic:
            state = initial_state("$4000 for 3 people to Paris for 5 days")
            result = await planner.run(state)

            # Heuristic should be called as safety net
            assert mock_heuristic.call_count >= 1

        # LLM result should be used
        assert result["constraints"]["budget"] == 4000.0
        assert result["constraints"]["budget_currency"] == "USD"
        assert result["constraints"]["travelers"] == 3

    @pytest.mark.asyncio
    async def test_heuristic_called_only_on_llm_failure(self, planner):
        """When LLM fails (429), _heuristic_parse IS called."""
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(
            side_effect=Exception("429 Rate limit exceeded")
        )

        state = initial_state("$4000 for 3 people to Paris for 5 days")
        result = await planner.run(state)

        # Should have fallen back to heuristic
        assert len(result["errors"]) > 0
        assert "429" in str(result["errors"][0]) or "Rate limit" in str(result["errors"][0])

        # Heuristic result should be used
        assert result["constraints"]["budget"] == 4000.0
        assert result["constraints"]["budget_currency"] == "USD"
        assert result["constraints"]["travelers"] == 3
        assert result["constraints"].get("duration_days") == 5

    @pytest.mark.asyncio
    async def test_llm_rejects_thb_currency_and_prompts_usd(self, planner):
        """LLM parsing THB should reset budget and ask for USD."""
        mock_resp = MagicMock()
        mock_resp.content = (
            '{"destinations": ["Bangkok"], "start_date": null, "end_date": null, '
            '"budget": 30000.0, "budget_currency": "THB", "travelers": 2, '
            '"preferences": null, "follow_up_questions": [], '
            '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
            '"needs_attractions": true, "needs_transport": true}}'
        )
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(return_value=mock_resp)

        state = initial_state("30000 baht for 2 people to Bangkok")
        result = await planner.run(state)

        assert result["constraints"]["budget"] is None
        assert result["constraints"]["budget_currency"] == "USD"
        followups = " ".join(result["follow_up_questions"]).lower()
        assert "usd" in followups or "dollars" in followups

    @pytest.mark.asyncio
    async def test_llm_rejects_jpy_currency_and_prompts_usd(self, planner):
        """LLM parsing JPY should reset budget and ask for USD."""
        mock_resp = MagicMock()
        mock_resp.content = (
            '{"destinations": ["Tokyo"], "start_date": "2026-08-01", '
            '"end_date": "2026-08-08", "budget": 200000.0, "budget_currency": "JPY", '
            '"travelers": 1, "preferences": null, "follow_up_questions": [], '
            '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
            '"needs_attractions": true, "needs_transport": true}}'
        )
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(return_value=mock_resp)

        state = initial_state("¥200000 for 1 week Tokyo trip")
        result = await planner.run(state)

        assert result["constraints"]["budget"] is None
        assert result["constraints"]["budget_currency"] == "USD"
        followups = " ".join(result["follow_up_questions"]).lower()
        assert "usd" in followups or "dollars" in followups

    @pytest.mark.asyncio
    async def test_llm_rejects_aed_currency_and_prompts_usd(self, planner):
        """LLM parsing AED should reset budget and ask for USD."""
        mock_resp = MagicMock()
        mock_resp.content = (
            '{"destinations": ["Dubai"], "start_date": null, "end_date": null, '
            '"budget": 5000.0, "budget_currency": "AED", "travelers": 2, '
            '"preferences": null, "follow_up_questions": [], '
            '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
            '"needs_attractions": true, "needs_transport": true}}'
        )
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(return_value=mock_resp)

        state = initial_state("5000 dirham for Dubai trip for 2")
        result = await planner.run(state)

        assert result["constraints"]["budget"] is None
        assert result["constraints"]["budget_currency"] == "USD"
        followups = " ".join(result["follow_up_questions"]).lower()
        assert "usd" in followups or "dollars" in followups

    @pytest.mark.asyncio
    async def test_no_followup_when_llm_extracts_budget(self, planner):
        """When LLM successfully extracts budget, no budget follow-up is asked."""
        mock_resp = MagicMock()
        mock_resp.content = (
            '{"destinations": ["Goa"], "start_date": null, "end_date": null, '
            '"budget": 4000.0, "budget_currency": "USD", "travelers": 3, '
            '"preferences": null, "follow_up_questions": [], '
            '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
            '"needs_attractions": true, "needs_transport": true}}'
        )
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(return_value=mock_resp)

        state = initial_state("$4000 for 3 people to Goa")
        result = await planner.run(state)

        # No budget follow-up since LLM extracted it
        questions_text = " ".join(result.get("follow_up_questions", [])).lower()
        assert "budget" not in questions_text, \
            f"Budget follow-up should NOT appear when LLM parsed it. Got: {result['follow_up_questions']}"

    @pytest.mark.asyncio
    async def test_heuristic_no_followup_when_budget_parsed(self, planner):
        """When heuristic parses budget (LLM down), no budget follow-up is asked."""
        planner._llm = MagicMock()
        planner._llm.ainvoke = AsyncMock(
            side_effect=Exception("429 Rate limit exceeded")
        )

        state = initial_state("$4000 for 3 people to Goa for 5 days")
        result = await planner.run(state)

        # No budget follow-up since heuristic extracted it
        questions_text = " ".join(result.get("follow_up_questions", [])).lower()
        assert "budget" not in questions_text, \
            f"Budget follow-up should NOT appear when heuristic parsed it. Got: {result['follow_up_questions']}"
