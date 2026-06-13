"""TravelPlanState TypedDict — shared state for the LangGraph pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Reducer helpers
# ---------------------------------------------------------------------------

def _last_wins(a: Any, b: Any) -> Any:
    """For scalar fields written by multiple concurrent nodes — last write wins."""
    return b if b is not None else a


def _merge_lists(a: list, b: list) -> list:
    """Append b onto a — used for list fields written by concurrent workers."""
    return list(a or []) + list(b or [])


# ---------------------------------------------------------------------------
# TravelPlanState
# ---------------------------------------------------------------------------

class TravelPlanState(TypedDict, total=False):
    """Shared mutable state passed between all nodes in the pipeline.

    Keys written by multiple concurrent worker nodes use Annotated reducers
    so LangGraph can merge parallel writes without raising InvalidUpdateError.
    """

    # ── Input ──────────────────────────────────────────────────────────
    user_id: Annotated[str, _last_wins]
    session_id: Annotated[str, _last_wins]
    trace_id: Annotated[str, _last_wins]
    raw_request: Annotated[str, _last_wins]
    trip_id: Annotated[Optional[str], _last_wins]

    # ── Planner output ─────────────────────────────────────────────────
    constraints: Annotated[Optional[dict[str, Any]], _last_wins]
    delegation_plan: Annotated[Optional[dict[str, Any]], _last_wins]
    follow_up_questions: Annotated[list[str], _merge_lists]

    # ── Phase 4: Memory & Personalization ──────────────────────────────
    # Long-term user preferences retrieved from Mem0
    user_preferences: Annotated[Optional[dict[str, Any]], _last_wins]
    # Episodic context for the current destination(s)
    episodic_context: Annotated[Optional[dict[str, Any]], _last_wins]
    # Which workers need to be re-run on regeneration (selective re-planning)
    workers_to_rerun: Annotated[Optional[list[str]], _last_wins]
    # Feedback from Validator to Planner on what to fix
    regeneration_feedback: Annotated[Optional[str], _last_wins]

    # ── Worker outputs (parallel) — each worker writes its own key ─────
    flight_results: Annotated[Optional[dict[str, Any]], _last_wins]
    hotel_results: Annotated[Optional[dict[str, Any]], _last_wins]
    attraction_results: Annotated[Optional[dict[str, Any]], _last_wins]
    transport_results: Annotated[Optional[dict[str, Any]], _last_wins]

    # ── Accumulator fields — concurrent workers append to these ────────
    agent_responses: Annotated[list[dict[str, Any]], _merge_lists]
    errors: Annotated[list[dict[str, Any]], _merge_lists]

    # ── Sequential pipeline outputs ────────────────────────────────────
    budget_breakdown: Annotated[Optional[dict[str, Any]], _last_wins]
    itinerary: Annotated[Optional[dict[str, Any]], _last_wins]

    # ── Validation ─────────────────────────────────────────────────────
    validation_status: Annotated[str, _last_wins]
    validation_issues: Annotated[list[dict[str, Any]], _merge_lists]
    regeneration_count: Annotated[int, _last_wins]

    # ── Metadata ───────────────────────────────────────────────────────
    pipeline_status: Annotated[str, _last_wins]
    current_step: Annotated[str, _last_wins]
    total_latency_ms: Annotated[Optional[int], _last_wins]


def initial_state(
    raw_request: str,
    user_id: str = "anonymous",
    session_id: str = "",
    trace_id: str = "",
    trip_id: str | None = None,
) -> TravelPlanState:
    """Return a TravelPlanState pre-populated with safe default values."""
    return TravelPlanState(
        user_id=user_id,
        session_id=session_id,
        trace_id=trace_id,
        raw_request=raw_request,
        trip_id=trip_id,
        constraints=None,
        delegation_plan=None,
        follow_up_questions=[],
        # Phase 4 memory fields
        user_preferences=None,
        episodic_context=None,
        workers_to_rerun=None,
        regeneration_feedback=None,
        flight_results=None,
        hotel_results=None,
        attraction_results=None,
        transport_results=None,
        budget_breakdown=None,
        itinerary=None,
        validation_status="pending",
        validation_issues=[],
        regeneration_count=0,
        agent_responses=[],
        errors=[],
        pipeline_status="running",
        current_step="init",
        total_latency_ms=None,
    )
