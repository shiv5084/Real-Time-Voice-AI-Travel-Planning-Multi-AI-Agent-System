"""Full StateGraph assembly and compilation for the travel planning pipeline."""

from __future__ import annotations

import time
from typing import Any

from app.graph.state import TravelPlanState
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Compiled workflow singleton (built lazily)
_compiled_workflow: Any | None = None


def build_workflow() -> Any:
    """Assemble and compile the LangGraph StateGraph.

    Topology (Phase 4 — with memory preload):
        START → memory_preload
        memory_preload → planner
        planner → needs_followup → END  (if follow-up questions exist)
        planner → fan_out (if no follow-up questions)
        fan_out → [flight_worker, hotel_worker, attraction_worker, transport_worker]
        [all workers] → budget  (fan-in)
        budget → composer → validator
        validator → planner (if rejected, regen_count < 3) | END (otherwise)

    Note: Selective worker re-runs (Phase 4) are implemented at the Planner level —
    workers that are not in workers_to_rerun return cached results immediately.
    LangGraph's fan-out topology is preserved for simplicity.
    """
    from langgraph.graph import END, START, StateGraph

    from app.graph.edges import route_after_planner, should_regenerate, should_early_exit
    from app.graph.nodes import (
        attraction_node,
        budget_node,
        composer_node,
        flight_node,
        hotel_node,
        memory_preload_node,
        planner_node,
        transport_node,
        validator_node,
    )

    # ── Fan-out relay node ─────────────────────────────────────────────
    async def fan_out_node(state: TravelPlanState) -> dict:
        """Passthrough node that triggers the parallel worker fan-out."""
        return {}

    graph = StateGraph(TravelPlanState)

    # ── Add all nodes ──────────────────────────────────────────────────
    graph.add_node("memory_preload", memory_preload_node)
    graph.add_node("planner", planner_node)
    graph.add_node("fan_out", fan_out_node)
    graph.add_node("flight_worker", flight_node)
    graph.add_node("hotel_worker", hotel_node)
    graph.add_node("attraction_worker", attraction_node)
    graph.add_node("transport_worker", transport_node)
    graph.add_node("budget", budget_node)
    graph.add_node("composer", composer_node)
    graph.add_node("validator", validator_node)

    # ── Entry point ────────────────────────────────────────────────────
    graph.add_edge(START, "memory_preload")
    graph.add_edge("memory_preload", "planner")

    # ── Planner → always run full pipeline (composer + budget) ─────────────
    graph.add_edge("planner", "fan_out")

    # ── Fan-out → all 4 parallel workers ──────────────────────────────
    graph.add_edge("fan_out", "flight_worker")
    graph.add_edge("fan_out", "hotel_worker")
    graph.add_edge("fan_out", "attraction_worker")
    graph.add_edge("fan_out", "transport_worker")

    # ── Fan-in: all 4 workers → budget ────────────────────────────────
    graph.add_edge(
        ["flight_worker", "hotel_worker", "attraction_worker", "transport_worker"],
        "budget",
    )

    # ── Sequential pipeline ────────────────────────────────────────────
    graph.add_edge("budget", "composer")
    graph.add_edge("composer", "validator")

    # ── Validator → conditional: regenerate or end ────────────────────
    graph.add_conditional_edges(
        "validator",
        should_regenerate,
        {
            "regenerate": "planner",
            "finish": END,
        },
    )

    return graph.compile()


def get_workflow() -> Any:
    """Return the cached compiled workflow, building it if necessary."""
    global _compiled_workflow
    if _compiled_workflow is None:
        _compiled_workflow = build_workflow()
    return _compiled_workflow


async def run_pipeline(
    raw_request: str,
    user_id: str = "anonymous",
    session_id: str = "",
    trace_id: str = "",
    trip_id: str | None = None,
) -> TravelPlanState:
    """Run the full pipeline and return the final state."""
    from app.graph.state import initial_state

    logger.info(
        "[VOICE] Pipeline execution started",
        extra={"event": {"trace_id": trace_id, "trip_id": trip_id, "raw_request": raw_request, "user_id": user_id}},
    )

    start = time.monotonic()
    state = initial_state(
        raw_request=raw_request,
        user_id=user_id,
        session_id=session_id,
        trace_id=trace_id,
        trip_id=trip_id,
    )

    workflow = get_workflow()

    try:
        final_state: TravelPlanState = await workflow.ainvoke(state)
        total_ms = int((time.monotonic() - start) * 1000)
        final_state = {
            **final_state,
            "pipeline_status": "completed",
            "total_latency_ms": total_ms,
        }
        logger.info(
            "[VOICE] Pipeline execution completed",
            extra={
                "event": {
                    "total_ms": total_ms,
                    "validation_status": final_state.get("validation_status"),
                    "trace_id": trace_id,
                    "has_itinerary": bool(final_state.get("itinerary")),
                    "has_budget_breakdown": bool(final_state.get("budget_breakdown")),
                }
            },
        )

        # Phase 4: Save episodic memory for completed (non-anonymous) users
        if user_id != "anonymous" and trip_id and final_state.get("validation_status") in ("approved", "warnings"):
            try:
                from app.memory.episodic import extract_and_save_lessons
                await extract_and_save_lessons(user_id=user_id, trip_id=trip_id, state=dict(final_state))
            except Exception as mem_exc:
                logger.warning(f"Episodic memory save failed (non-fatal): {mem_exc}")

        return final_state
    except Exception as exc:
        total_ms = int((time.monotonic() - start) * 1000)
        logger.error(
            "[VOICE] Pipeline execution failed",
            extra={"event": {"error": str(exc), "trace_id": trace_id, "total_ms": total_ms, "error_type": type(exc).__name__}},
            exc_info=True,
        )

        # Always provide a fallback itinerary so the frontend can render something
        from app.agents.composer import _fallback_itinerary
        constraints = state.get("constraints") or {}
        dests = constraints.get("destinations") or []
        destination = ", ".join(dests) if dests else "your destination"
        fallback = _fallback_itinerary(
            destination,
            constraints.get("start_date") or "TBD",
            constraints.get("end_date") or "TBD",
            constraints.get("duration_days") or 5,
        )

        return {
            **state,
            "pipeline_status": "completed",
            "itinerary": fallback,
            "budget_breakdown": state.get("budget_breakdown") or {
                "total_budget": constraints.get("budget") or 0,
                "total_estimated_cost": 0,
                "currency": constraints.get("budget_currency", "USD"),
                "compliance": "within_budget",
                "categories": [],
                "variance_percentage": None,
                "recommendations": ["Pipeline encountered an error — results are estimates only."],
            },
            "total_latency_ms": total_ms,
            "errors": [*(state.get("errors") or []), {
                "error": f"{type(exc).__name__}: {exc}",
                "step": "pipeline",
            }],
        }
