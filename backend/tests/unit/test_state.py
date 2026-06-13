"""Unit tests for TravelPlanState TypedDict."""

from __future__ import annotations

import pytest
from app.graph.state import TravelPlanState, initial_state


class TestTravelPlanState:
    """Verify TravelPlanState can be constructed and has all required keys."""

    REQUIRED_KEYS = [
        "user_id", "session_id", "trace_id", "raw_request", "trip_id",
        "constraints", "delegation_plan", "follow_up_questions",
        "flight_results", "hotel_results", "attraction_results", "transport_results",
        "budget_breakdown", "itinerary",
        "validation_status", "validation_issues", "regeneration_count",
        "agent_responses", "errors", "pipeline_status", "current_step",
        "total_latency_ms",
    ]

    def test_initial_state_creates_valid_state(self):
        state = initial_state("I want to go to Paris for 5 days")
        assert isinstance(state, dict)

    def test_initial_state_has_all_required_keys(self):
        state = initial_state("test request")
        for key in self.REQUIRED_KEYS:
            assert key in state, f"Missing required key: {key}"

    def test_initial_state_defaults(self):
        state = initial_state("test")
        assert state["pipeline_status"] == "running"
        assert state["validation_status"] == "pending"
        assert state["regeneration_count"] == 0
        assert state["follow_up_questions"] == []
        assert state["validation_issues"] == []
        assert state["agent_responses"] == []
        assert state["errors"] == []
        assert state["current_step"] == "init"
        assert state["constraints"] is None
        assert state["itinerary"] is None
        assert state["total_latency_ms"] is None

    def test_initial_state_accepts_custom_user_id(self):
        state = initial_state("test", user_id="user-123")
        assert state["user_id"] == "user-123"

    def test_initial_state_accepts_session_id(self):
        state = initial_state("test", session_id="sess-456")
        assert state["session_id"] == "sess-456"

    def test_initial_state_accepts_trace_id(self):
        state = initial_state("test", trace_id="trace_abc123")
        assert state["trace_id"] == "trace_abc123"

    def test_initial_state_accepts_trip_id(self):
        state = initial_state("test", trip_id="trip-789")
        assert state["trip_id"] == "trip-789"

    def test_state_mutation_via_spread(self):
        state = initial_state("test")
        updated = {**state, "current_step": "planner_complete", "pipeline_status": "running"}
        assert updated["current_step"] == "planner_complete"
        # Original state should not be mutated
        assert state["current_step"] == "init"

    def test_state_validation_status_values(self):
        for status in ("pending", "approved", "warnings", "rejected"):
            state = initial_state("test")
            updated = {**state, "validation_status": status}
            assert updated["validation_status"] == status

    def test_state_pipeline_status_values(self):
        for status in ("running", "completed", "failed"):
            state = initial_state("test")
            updated = {**state, "pipeline_status": status}
            assert updated["pipeline_status"] == status

    def test_state_with_constraints(self):
        state = initial_state("test")
        constraints = {
            "destinations": ["Paris"],
            "start_date": "2025-06-01",
            "end_date": "2025-06-06",
            "budget": 2000.0,
            "budget_currency": "USD",
            "travelers": 2,
            "preferences": None,
        }
        updated = {**state, "constraints": constraints}
        assert updated["constraints"]["destinations"] == ["Paris"]
        assert updated["constraints"]["budget"] == 2000.0

    def test_state_errors_list_is_mutable(self):
        state = initial_state("test")
        new_errors = list(state["errors"])
        new_errors.append({"agent": "test", "error": "test error"})
        updated = {**state, "errors": new_errors}
        assert len(updated["errors"]) == 1
        assert len(state["errors"]) == 0  # original unchanged

    def test_state_agent_responses_accumulation(self):
        state = initial_state("test")
        resp1 = {"agent_name": "planner_agent", "success": True}
        resp2 = {"agent_name": "flight_agent", "success": True}
        updated = {**state, "agent_responses": [resp1, resp2]}
        assert len(updated["agent_responses"]) == 2

    def test_state_regeneration_counter_increments(self):
        state = initial_state("test")
        assert state["regeneration_count"] == 0
        updated = {**state, "regeneration_count": 1}
        assert updated["regeneration_count"] == 1

    def test_full_pipeline_state_simulation(self):
        """Simulate state transitions through all pipeline stages."""
        state = initial_state("Go to Tokyo for a week, budget $3000")

        # After planner
        state = {
            **state,
            "constraints": {
                "destinations": ["Tokyo"],
                "start_date": "2025-08-01",
                "end_date": "2025-08-08",
                "budget": 3000.0,
                "budget_currency": "USD",
                "travelers": 1,
                "preferences": None,
            },
            "follow_up_questions": [],
            "current_step": "planner_complete",
        }

        # After workers
        state = {
            **state,
            "flight_results": {"flights": [{"price_usd": 800}]},
            "hotel_results": {"hotels": [{"total_cost_usd": 700}]},
            "attraction_results": {"attractions": [{"name": "Senso-ji", "cost_usd": 0}]},
            "transport_results": {"transport_options": [{"estimated_cost_usd": 50}]},
        }

        # After budget
        state = {
            **state,
            "budget_breakdown": {
                "total_budget": 3000.0,
                "total_estimated_cost": 1900.0,
                "compliance": "within_budget",
                "categories": [],
            },
        }

        # After composer + validator
        state = {
            **state,
            "itinerary": {"days": []},
            "validation_status": "approved",
            "validation_issues": [],
            "pipeline_status": "completed",
            "total_latency_ms": 5000,
        }

        assert state["pipeline_status"] == "completed"
        assert state["validation_status"] == "approved"
        assert state["constraints"]["destinations"] == ["Tokyo"]
