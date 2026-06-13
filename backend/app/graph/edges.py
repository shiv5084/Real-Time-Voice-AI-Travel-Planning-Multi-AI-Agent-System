"""Conditional edge logic for the LangGraph pipeline.

Phase 4: Selective worker re-run logic added. The `should_rerun_worker`
function checks ``workers_to_rerun`` in state so regeneration only
re-invokes the affected workers rather than all four.

Phase 7B: Early exit logic added to skip unnecessary agent runs.
"""

from __future__ import annotations

from app.config import get_settings
from app.graph.state import TravelPlanState


def should_regenerate(state: TravelPlanState) -> str:
    """Route after validation: regenerate (loop back to planner) or finish.

    Returns:
        'regenerate' — if the itinerary was rejected and we have iterations left.
        'finish'     — if approved/warnings or max regenerations reached.
    """
    status = state.get("validation_status", "pending")
    regen_count = state.get("regeneration_count", 0)

    if status == "rejected" and regen_count < 3:
        return "regenerate"
    return "finish"


def route_after_planner(state: TravelPlanState) -> str:
    """Route after the planner node.

    Returns:
        'start_workers'  — planner has enough info; kick off parallel workers.
        'needs_followup' — planner identified missing critical info; stop and ask.
    """
    questions = state.get("follow_up_questions") or []
    # Always run the full pipeline to generate itinerary and budget_breakdown
    # Follow-up questions will be included in the response for the frontend to handle
    return "start_workers"


def should_run_flight_worker(state: TravelPlanState) -> str:
    """Selective re-run: decide whether to execute the flight worker.

    On first pass (regen_count == 0) always runs. On re-runs, only executes
    if 'flight_worker' is in workers_to_rerun (or list is empty/None → all).
    """
    return _selective_worker_route(state, "flight_worker")


def should_run_hotel_worker(state: TravelPlanState) -> str:
    return _selective_worker_route(state, "hotel_worker")


def should_run_attraction_worker(state: TravelPlanState) -> str:
    return _selective_worker_route(state, "attraction_worker")


def should_run_transport_worker(state: TravelPlanState) -> str:
    return _selective_worker_route(state, "transport_worker")


def _selective_worker_route(state: TravelPlanState, worker_name: str) -> str:
    """Generic logic: 'run' if worker is needed, 'skip' otherwise."""
    regen_count = state.get("regeneration_count", 0)
    if regen_count == 0:
        # First pass — always run all workers
        return "run"
    workers_to_rerun = state.get("workers_to_rerun")
    if not workers_to_rerun:
        # No selective list provided — re-run all workers
        return "run"
    return "run" if worker_name in workers_to_rerun else "skip"


def should_early_exit(state: TravelPlanState) -> str:
    """Check if we can skip certain workers based on early exit conditions.

    Early exit conditions:
    - Budget already exceeded (stop all workers)
    - Simple request with minimal requirements (skip optional workers)

    Returns:
        'continue' — proceed with normal workflow
        'skip_optional' — skip optional workers (attraction, transport)
    """
    settings = get_settings()
    
    if not settings.enable_early_exit:
        return "continue"
    
    # Check if budget is already exceeded
    budget_breakdown = state.get("budget_breakdown") or {}
    total_cost = budget_breakdown.get("total_estimated_cost") or budget_breakdown.get("total") or 0
    constraints = state.get("constraints") or {}
    # Use `or` instead of default= so that an explicit None value is also replaced
    budget_limit = constraints.get("budget") or float("inf")

    if budget_limit > 0 and total_cost > (budget_limit * settings.early_exit_budget_threshold):
        # Budget significantly exceeded - skip optional workers
        return "skip_optional"
    
    # Check if this is a simple request (short, minimal constraints)
    raw_request = state.get("raw_request", "")
    if len(raw_request) < 100 and not constraints.get("preferences"):
        # Simple request - skip optional workers
        return "skip_optional"
    
    return "continue"
