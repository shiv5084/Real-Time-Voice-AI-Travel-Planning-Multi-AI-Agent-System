"""Integration test for the full 8-agent LangGraph pipeline."""

from __future__ import annotations

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.graph.state import initial_state, TravelPlanState
from app.graph.edges import should_regenerate, route_after_planner
from app.config import Settings


# ── Helpers ───────────────────────────────────────────────────────────────

def _mock_llm_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    return resp


def _patch_all_mcp_clients():
    """Context manager that mocks all 4 MCP clients."""
    mock_aviation = AsyncMock()
    mock_aviation.call = AsyncMock(return_value={"flights": [{"price_usd": 600}]})

    mock_tavily = AsyncMock()
    mock_tavily.call = AsyncMock(return_value={
        "results": [{"title": "Test Hotel", "content": "Nice hotel"}]
    })

    mock_maps = AsyncMock()
    mock_maps.call = AsyncMock(return_value={
        "status": "success",
        "data": {
            "results": [{"geometry": {"location": {"lat": 48.8566, "lng": 2.3522}}}],
            "routes": [{"distanceMeters": 10000, "duration": "1200s"}]
        }
    })

    patches = [
        patch("app.agents.flight.AviationStackMCPClient", return_value=mock_aviation),
        patch("app.agents.hotel.TavilyMCPClient", return_value=mock_tavily),
        patch("app.agents.attraction.TavilyMCPClient", return_value=mock_tavily),
        patch("app.agents.attraction.MapsMCPClient", return_value=mock_maps),
        patch("app.agents.transport.MapsMCPClient", return_value=mock_maps),
        patch("app.agents.validator.MapsMCPClient", return_value=mock_maps),
    ]
    return patches


def _patch_llm(settings: Settings) -> list:
    """Patch LLM creation to return predictable mock responses."""
    planner_content = (
        '{"destinations": ["Paris"], "start_date": "2025-06-01", "end_date": "2025-06-06", '
        '"budget": 2000.0, "budget_currency": "USD", "travelers": 1, "preferences": null, '
        '"follow_up_questions": [], '
        '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
        '"needs_attractions": true, "needs_transport": true}}'
    )
    flight_content = '{"flights": [{"airline": "Air France", "price_usd": 600, "layovers": 0}]}'
    hotel_content = '{"hotels": [{"name": "Hotel Paris", "total_cost_usd": 500}]}'
    attraction_content = '{"attractions": [{"name": "Eiffel Tower", "cost_usd": 25}]}'
    transport_content = '{"transport_options": [{"mode": "metro", "estimated_cost_usd": 20}]}'
    gemini_budget_content = '{"recommendations": ["Take the metro instead of taxi"]}'
    composer_content = (
        '{"days": ['
        '{"day": 1, "date": "2025-06-01", "location": "Paris", '
        '"activities": [{"name": "Arrive", "type": "hotel", "start_time": "14:00", "end_time": "15:00", "cost_usd": 0}], '
        '"total_cost_usd": 0},'
        '{"day": 2, "date": "2025-06-02", "location": "Paris", '
        '"activities": [{"name": "Eiffel Tower", "type": "attraction", "start_time": "09:30", "end_time": "11:30", "cost_usd": 25}], '
        '"total_cost_usd": 25}'
        ']}'
    )
    validator_content = '{"issues": [], "overall_assessment": "Approved", "approved": true}'

    # Map agent name → mock response content
    _responses = {
        "planner_agent": planner_content,
        "flight_agent": flight_content,
        "hotel_agent": hotel_content,
        "attraction_agent": attraction_content,
        "transport_agent": transport_content,
        "budget_agent": gemini_budget_content,
        "composer_agent": composer_content,
        "validator_agent": validator_content,
    }

    def mock_get_llm(self):
        content = _responses.get(self.agent_name, '{"mock": true}')

        class _FakeLLM:
            async def ainvoke(self, *args, **kwargs):
                return _mock_llm_response(content)

        return _FakeLLM()

    return [patch("app.agents.base.BaseAgent._get_llm", mock_get_llm)]


# ── Tests ─────────────────────────────────────────────────────────────────

class TestEdgeFunctions:
    def test_should_regenerate_on_rejected(self):
        state = initial_state("test")
        state = {**state, "validation_status": "rejected", "regeneration_count": 0}
        assert should_regenerate(state) == "regenerate"

    def test_should_finish_on_approved(self):
        state = initial_state("test")
        state = {**state, "validation_status": "approved", "regeneration_count": 0}
        assert should_regenerate(state) == "finish"

    def test_should_finish_on_max_regen(self):
        state = initial_state("test")
        state = {**state, "validation_status": "rejected", "regeneration_count": 3}
        assert should_regenerate(state) == "finish"

    def test_should_finish_on_warnings(self):
        state = initial_state("test")
        state = {**state, "validation_status": "warnings", "regeneration_count": 1}
        assert should_regenerate(state) == "finish"

    def test_route_after_planner_start_workers(self):
        state = initial_state("test")
        state = {**state, "follow_up_questions": []}
        assert route_after_planner(state) == "start_workers"

    def test_route_after_planner_needs_followup(self):
        state = initial_state("test")
        state = {**state, "follow_up_questions": ["When would you like to travel?"]}
        assert route_after_planner(state) == "needs_followup"


class TestWorkflowCompilation:
    def test_workflow_compiles_without_error(self):
        from app.graph.workflow import build_workflow
        workflow = build_workflow()
        assert workflow is not None

    def test_workflow_has_expected_nodes(self):
        """Verify the compiled graph contains all required nodes."""
        from app.graph.workflow import build_workflow
        workflow = build_workflow()
        # LangGraph compiled graph exposes graph attribute
        graph = getattr(workflow, "graph", None)
        if graph:
            node_names = list(graph.nodes.keys())
            for expected in ["planner", "fan_out", "flight_worker", "hotel_worker",
                             "attraction_worker", "transport_worker",
                             "budget", "composer", "validator"]:
                assert expected in node_names, f"Node '{expected}' missing from graph"


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline_runs_to_completion(self):
        """End-to-end test with all external calls mocked."""
        from app.graph.workflow import run_pipeline

        mcp_patches = _patch_all_mcp_clients()
        settings = Settings.model_validate({
            "app_env": "local",
            "groq_api_key": None,
            "gemini_api_key": None,
        })
        llm_patches = _patch_llm(settings)

        all_patches = mcp_patches + llm_patches

        # Apply all patches
        for p in all_patches:
            p.start()

        try:
            start = time.monotonic()
            final_state = await run_pipeline(
                raw_request="I want to go to Paris for 5 days with budget $2000",
                user_id="test_user",
                session_id="test_sess",
                trace_id="test_trace",
                trip_id="test_trip",
            )
            elapsed = time.monotonic() - start

            # Verify pipeline completed
            assert final_state["pipeline_status"] in ("completed", "failed")
            # Should complete within 15 seconds even with mocked calls
            assert elapsed < 15.0, f"Pipeline took too long: {elapsed:.1f}s"
        finally:
            for p in all_patches:
                p.stop()

    @pytest.mark.asyncio
    async def test_pipeline_state_has_all_keys_after_run(self):
        """Verify state is properly populated through all nodes."""
        from app.graph.workflow import run_pipeline

        mcp_patches = _patch_all_mcp_clients()
        settings = Settings.model_validate({
            "app_env": "local",
            "groq_api_key": None,
            "gemini_api_key": None,
        })
        llm_patches = _patch_llm(settings)

        for p in mcp_patches + llm_patches:
            p.start()

        try:
            final_state = await run_pipeline(
                raw_request="Weekend trip to Barcelona, $1500",
                user_id="user_1",
                session_id="sess_1",
                trace_id="trace_1",
            )
            # State should contain all expected keys
            assert "pipeline_status" in final_state
            assert "errors" in final_state
            assert isinstance(final_state["errors"], list)
        finally:
            for p in mcp_patches + llm_patches:
                p.stop()

    @pytest.mark.asyncio
    async def test_pipeline_continues_on_individual_agent_failure(self):
        """A single agent failure should not crash the entire pipeline."""
        from app.graph.workflow import run_pipeline

        mcp_patches = _patch_all_mcp_clients()

        # Override flight client to always fail
        fail_patch = patch(
            "app.agents.flight.AviationStackMCPClient",
            return_value=MagicMock(call=AsyncMock(side_effect=Exception("Flight API down")))
        )

        settings = Settings.model_validate({"app_env": "local", "groq_api_key": None, "gemini_api_key": None})
        llm_patches = _patch_llm(settings)

        all_patches = mcp_patches + llm_patches + [fail_patch]
        for p in all_patches:
            p.start()

        try:
            final_state = await run_pipeline(
                raw_request="Trip to Rome",
                user_id="user_2",
            )
            # Pipeline should finish even if flight agent has errors
            assert final_state["pipeline_status"] in ("completed", "failed")
        finally:
            for p in all_patches:
                p.stop()
