"""Unit tests for the self-correcting validation loop (Phase 4).

Tests cover:
- should_regenerate edge function routing
- regeneration counter enforcement (max 3)
- regeneration_feedback generation in Validator
- workers_to_rerun selective logic
- _infer_workers_to_rerun from feedback text
- Graceful degradation after max regen
- Preference merge and override
- Follow-up question suppression when memory has the answer
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Test: should_regenerate edge routing
# ---------------------------------------------------------------------------

def test_should_regenerate_triggers_on_rejected():
    """Rejected itinerary below max iterations should route to 'regenerate'."""
    from app.graph.edges import should_regenerate

    state = {"validation_status": "rejected", "regeneration_count": 0}
    assert should_regenerate(state) == "regenerate"


def test_should_regenerate_stops_at_max_count():
    """At regen_count == 3, should always route to 'finish' even if rejected."""
    from app.graph.edges import should_regenerate

    state = {"validation_status": "rejected", "regeneration_count": 3}
    assert should_regenerate(state) == "finish"


def test_should_regenerate_approved_routes_to_finish():
    """Approved itinerary always routes to 'finish'."""
    from app.graph.edges import should_regenerate

    state = {"validation_status": "approved", "regeneration_count": 0}
    assert should_regenerate(state) == "finish"


def test_should_regenerate_warnings_routes_to_finish():
    """Warnings-only itinerary routes to 'finish' (not blocking)."""
    from app.graph.edges import should_regenerate

    state = {"validation_status": "warnings", "regeneration_count": 1}
    assert should_regenerate(state) == "finish"


def test_should_regenerate_count_2_still_triggers():
    """At regen_count == 2, a rejection should still trigger one more re-plan."""
    from app.graph.edges import should_regenerate

    state = {"validation_status": "rejected", "regeneration_count": 2}
    assert should_regenerate(state) == "regenerate"


# ---------------------------------------------------------------------------
# Test: selective worker re-run logic
# ---------------------------------------------------------------------------

def test_selective_worker_run_first_pass():
    """On first pass (regen_count == 0), all workers should run."""
    from app.graph.edges import (
        should_run_flight_worker,
        should_run_hotel_worker,
        should_run_attraction_worker,
        should_run_transport_worker,
    )

    state = {"regeneration_count": 0, "workers_to_rerun": None}
    assert should_run_flight_worker(state) == "run"
    assert should_run_hotel_worker(state) == "run"
    assert should_run_attraction_worker(state) == "run"
    assert should_run_transport_worker(state) == "run"


def test_selective_worker_only_flight_reruns():
    """When only flight_worker is in workers_to_rerun, only it should run."""
    from app.graph.edges import (
        should_run_flight_worker,
        should_run_hotel_worker,
    )

    state = {"regeneration_count": 1, "workers_to_rerun": ["flight_worker"]}
    assert should_run_flight_worker(state) == "run"
    assert should_run_hotel_worker(state) == "skip"


def test_selective_worker_empty_list_runs_all():
    """Empty workers_to_rerun list should re-run all workers."""
    from app.graph.edges import should_run_transport_worker

    state = {"regeneration_count": 1, "workers_to_rerun": []}
    assert should_run_transport_worker(state) == "run"


# ---------------------------------------------------------------------------
# Test: _infer_workers_to_rerun from feedback text
# ---------------------------------------------------------------------------

def test_infer_flight_worker_from_feedback():
    """Flight-related feedback should infer flight_worker."""
    from app.agents.planner import _infer_workers_to_rerun

    feedback = "The departure flight timing conflicts with the hotel check-in"
    workers = _infer_workers_to_rerun(feedback)
    assert "flight_worker" in workers


def test_infer_hotel_worker_from_feedback():
    """Hotel-related feedback should infer hotel_worker."""
    from app.agents.planner import _infer_workers_to_rerun

    feedback = "Hotel check-in is before the standard check-in time"
    workers = _infer_workers_to_rerun(feedback)
    assert "hotel_worker" in workers


def test_infer_all_workers_on_vague_feedback():
    """Vague feedback should return all 4 workers."""
    from app.agents.planner import _infer_workers_to_rerun

    feedback = "General quality issues with the plan"
    workers = _infer_workers_to_rerun(feedback)
    assert len(workers) == 4


def test_infer_attraction_and_transport_workers():
    """Feedback mentioning attractions and routes infers both workers."""
    from app.agents.planner import _infer_workers_to_rerun

    feedback = "The route between museum and restaurant is too long, and some attractions are overcrowded"
    workers = _infer_workers_to_rerun(feedback)
    assert "attraction_worker" in workers
    assert "transport_worker" in workers


# ---------------------------------------------------------------------------
# Test: Regeneration feedback generation in Validator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validator_generates_feedback_on_rejection():
    """Validator should populate regeneration_feedback when rejecting."""
    from app.agents.validator import ValidatorAgent
    from app.graph.state import initial_state
    from app.config import get_settings

    agent = ValidatorAgent(settings=get_settings())
    # Mock LLM to return empty issues (structural validation drives the rejection)
    agent._llm = MagicMock()
    agent._llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"issues": []}'))

    # Create a state with critical issue (empty itinerary)
    state = {
        **initial_state("test"),
        "constraints": {"destinations": [], "budget": 1000},
        "itinerary": {"days": []},  # Empty days → critical issue
        "budget_breakdown": {"total_estimated_cost": 0, "compliance": "within_budget"},
        "regeneration_count": 0,
    }

    with patch("app.agents.validator.MapsMCPClient") as mock_maps:
        mock_maps.return_value = MagicMock()
        mock_maps.return_value.call = AsyncMock(return_value={"status": "success", "data": {"results": []}})
        result = await agent.run(state)

    assert result["validation_status"] == "rejected"
    assert result.get("regeneration_feedback") is not None
    assert "validation attempt" in result["regeneration_feedback"].lower()


@pytest.mark.asyncio
async def test_validator_graceful_degradation_at_max_regen():
    """At regen_count >= 3, critical issues should be downgraded to warnings."""
    from app.agents.validator import ValidatorAgent
    from app.graph.state import initial_state
    from app.config import get_settings

    agent = ValidatorAgent(settings=get_settings())
    agent._llm = MagicMock()
    agent._llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"issues": []}'))

    state = {
        **initial_state("test"),
        "constraints": {"destinations": [], "budget": 1000},
        "itinerary": {"days": []},  # Critical issue: empty days
        "budget_breakdown": {"total_estimated_cost": 0, "compliance": "within_budget"},
        "regeneration_count": 3,  # Max regen reached
    }

    with patch("app.agents.validator.MapsMCPClient") as mock_maps:
        mock_maps.return_value = MagicMock()
        mock_maps.return_value.call = AsyncMock(return_value={"status": "success", "data": {"results": []}})
        result = await agent.run(state)

    # At max regen, should NOT be "rejected" — should deliver with warnings
    assert result["validation_status"] in ("warnings", "approved")
    assert result.get("regeneration_feedback") is None  # No feedback on final pass


# ---------------------------------------------------------------------------
# Test: Preference merge and override
# ---------------------------------------------------------------------------

def test_merge_preferences_stored_fills_gaps():
    """Stored preferences should fill fields not mentioned in the request."""
    from app.agents.planner import _merge_preferences

    stored = {"food": "Japanese", "crowd_tolerance": "low"}
    parsed = {"accommodation_type": "hotel"}
    result = _merge_preferences(stored, parsed, "I want to go to Tokyo")
    assert result["food"] == "Japanese"
    assert result["crowd_tolerance"] == "low"
    assert result["accommodation_type"] == "hotel"


def test_merge_preferences_explicit_override_wins():
    """Explicit preference mention in raw request should override stored value."""
    from app.agents.planner import _merge_preferences

    stored = {"accommodation_type": "budget", "budget_style": "budget"}
    parsed = {}
    result = _merge_preferences(stored, parsed, "this time I want luxury hotels")
    assert result["accommodation_type"] == "luxury"
    assert result["budget_style"] == "luxury"


def test_merge_preferences_dietary_override():
    """Dietary restriction mentioned explicitly should override stored value."""
    from app.agents.planner import _merge_preferences

    stored = {}
    parsed = {}
    result = _merge_preferences(stored, parsed, "I'm vegetarian, please no meat")
    assert result.get("dietary_restrictions") == "vegetarian"


def test_merge_preferences_empty_inputs():
    """Both empty inputs should return empty dict."""
    from app.agents.planner import _merge_preferences

    result = _merge_preferences({}, {}, "trip to Paris")
    assert result == {}


# ---------------------------------------------------------------------------
# Test: Follow-up question suppression with memory
# ---------------------------------------------------------------------------

def test_memory_context_builder_with_preferences():
    """Memory context string should include formatted preferences."""
    from app.agents.planner import _build_memory_context

    prefs = {"food": "Italian", "crowd_tolerance": "low"}
    context = _build_memory_context(prefs, None)
    assert "Italian" in context
    assert "low" in context.lower() or "crowd" in context.lower()


def test_memory_context_builder_with_episodic():
    """Memory context should include repeat destination info."""
    from app.agents.planner import _build_memory_context

    episodic = {
        "repeat_destinations": ["Paris"],
        "destination_memories": {"Paris": ["What worked: Staying in Marais"]},
        "general_patterns": [],
    }
    context = _build_memory_context({}, episodic)
    assert "Paris" in context
    assert "Marais" in context


def test_memory_context_builder_empty():
    """No preferences and no episodic context should return empty string."""
    from app.agents.planner import _build_memory_context

    result = _build_memory_context(None, None)
    assert result == ""
