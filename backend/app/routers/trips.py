"""Trip planning API routes — POST /api/trips/plan, /followup, GET /{id}/status."""

from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.middleware.auth import get_current_user_optional, get_current_user_required
from app.models.user import User
from app.services.database import (
    delete_trip as db_delete_trip,
    get_itinerary,
    get_trip as db_get_trip,
    insert_itinerary,
    insert_trip,
    list_trips as db_list_trips,
    update_trip_status,
)
from app.utils.logging import get_logger
from app.utils.tracing import generate_trace_id, get_trace_id, set_trace_id

logger = get_logger(__name__)

router = APIRouter(prefix="/api/trips", tags=["trips"])


# ── Request / Response models ──────────────────────────────────────────────

class TripPlanRequest(BaseModel):
    raw_request: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class TripPlanResponse(BaseModel):
    trip_id: str
    trace_id: str
    pipeline_status: str
    validation_status: Optional[str] = None
    itinerary: Optional[dict] = None
    budget_breakdown: Optional[dict] = None
    constraints: Optional[dict] = None
    follow_up_questions: list[str] = []
    errors: list[dict] = []
    total_latency_ms: Optional[int] = None


class FollowUpRequest(BaseModel):
    trip_id: str
    answer: str
    session_id: str


class FollowUpResponse(BaseModel):
    trip_id: str
    trace_id: str
    message: str


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("", status_code=status.HTTP_200_OK)
async def list_trips(current_user: User = Depends(get_current_user_required)) -> list[dict]:
    """Return all trips for the authenticated user from the database."""
    trips_db = await db_list_trips(user_id=str(current_user.id))
    trips = []
    for trip in trips_db:
        constraints = trip.get("constraints") or {}
        itinerary = await get_itinerary(trip["id"])
        content = itinerary.get("content") if itinerary else {}
        days_list = content.get("days") or content.get("day_plans") or []

        trips.append({
            "id": trip["id"],
            "destination": (
                # constraints.destinations is a list — take the first entry
                (constraints.get("destinations") or [None])[0]
                or constraints.get("destination")  # legacy single-value fallback
                or "Unknown"
            ),
            "startDate": constraints.get("start_date") or constraints.get("departure_date"),
            "endDate": constraints.get("end_date") or constraints.get("return_date"),
            "status": "planned" if trip.get("status") == "completed" else "draft",
            "thumbnailEmoji": "✈️",
            "daysCount": len(days_list) if days_list else None,
            "totalBudget": (trip.get("budget_breakdown") or {}).get("total_cost"),
            "currency": constraints.get("currency", "USD"),
        })
    return trips


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(trip_id: str):
    """Remove a trip from the database."""
    trip = await db_get_trip(trip_id)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip '{trip_id}' not found",
        )
    await db_delete_trip(trip_id)


@router.post("/plan", response_model=TripPlanResponse, status_code=status.HTTP_200_OK)
async def plan_trip(
    request: TripPlanRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> TripPlanResponse:
    """Run the full 8-agent LangGraph pipeline and return the structured itinerary."""
    from app.graph.workflow import run_pipeline

    trip_id = str(uuid.uuid4())
    trace_id = get_trace_id() or generate_trace_id(prefix="trip")
    set_trace_id(trace_id)
    session_id = request.session_id or str(uuid.uuid4())

    # Use the authenticated user's real ID; fall back to a random UUID for anonymous users
    if current_user is not None:
        user_id = str(current_user.id)
    else:
        try:
            user_id = str(uuid.UUID(request.user_id)) if request.user_id else str(uuid.uuid4())
        except (ValueError, AttributeError):
            user_id = str(uuid.uuid4())

    logger.info(
        "Trip planning request received",
        extra={
            "event": {
                "trip_id": trip_id,
                "trace_id": trace_id,
                "request_length": len(request.raw_request),
            }
        },
    )

    # Pipeline-level hard timeout: 280 s (4.6 min).
    # This gives a 20 s buffer before the Next.js frontend AbortController fires
    # at 300 s, ensuring the user gets a clean JSON error rather than a
    # connection-reset / blank page.
    PIPELINE_TIMEOUT_S = 280

    try:
        final_state = await asyncio.wait_for(
            run_pipeline(
                raw_request=request.raw_request,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
                trip_id=trip_id,
            ),
            timeout=PIPELINE_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.error(
            "Pipeline timed out",
            extra={"event": {"trip_id": trip_id, "timeout_s": PIPELINE_TIMEOUT_S}},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The trip planning pipeline took too long to respond. "
                "This is usually caused by high API load. Please try again in a moment."
            ),
        )
    except Exception as exc:
        logger.error(
            "Pipeline execution failed",
            extra={"event": {"trip_id": trip_id, "error": str(exc)}},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline execution failed: {exc}",
        )

    # Persist to database
    await insert_trip(
        trip_id=trip_id,
        user_id=user_id,
        title=request.raw_request[:100],
        raw_request=request.raw_request,
        constraints=final_state.get("constraints") or {},
        status=final_state.get("pipeline_status", "completed"),
    )

    # Persist itinerary if available
    if final_state.get("itinerary"):
        itinerary_id = str(uuid.uuid4())
        await insert_itinerary(
            itinerary_id=itinerary_id,
            trip_id=trip_id,
            content=final_state.get("itinerary"),
            budget_breakdown=final_state.get("budget_breakdown"),
            validation_status=final_state.get("validation_status"),
        )

    # Enrich itinerary with destination from constraints if the LLM omitted it
    itinerary = final_state.get("itinerary")
    constraints = final_state.get("constraints") or {}
    if itinerary and not itinerary.get("destination"):
        dests = constraints.get("destinations") or []
        itinerary = dict(itinerary)  # shallow copy so we don't mutate shared state
        itinerary["destination"] = ", ".join(dests) if dests else None

    # Debug logging
    logger.info(
        "Plan response data",
        extra={
            "event": {
                "trip_id": trip_id,
                "has_itinerary": bool(itinerary),
                "destination": (itinerary or {}).get("destination"),
                "has_budget_breakdown": bool(final_state.get("budget_breakdown")),
                "follow_up_questions_count": len(final_state.get("follow_up_questions") or []),
                "pipeline_status": final_state.get("pipeline_status"),
            }
        },
    )

    return TripPlanResponse(
        trip_id=trip_id,
        trace_id=trace_id,
        pipeline_status=final_state.get("pipeline_status", "completed"),
        validation_status=final_state.get("validation_status"),
        itinerary=itinerary,  # use the enriched copy
        budget_breakdown=final_state.get("budget_breakdown"),
        constraints=final_state.get("constraints"),
        follow_up_questions=final_state.get("follow_up_questions") or [],
        errors=final_state.get("errors") or [],
        total_latency_ms=final_state.get("total_latency_ms"),
    )


@router.post("/followup", response_model=FollowUpResponse, status_code=status.HTTP_200_OK)
async def trip_followup(request: FollowUpRequest) -> FollowUpResponse:
    """Resume planning after the user answers a follow-up question."""
    from app.graph.workflow import run_pipeline

    stored = await db_get_trip(request.trip_id)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip '{request.trip_id}' not found",
        )

    trace_id = generate_trace_id(prefix="followup")
    set_trace_id(trace_id)

    # Append the answer to the original request and re-run
    original_request = stored.get("raw_request", "")
    augmented_request = f"{original_request}\n\nUser clarification: {request.answer}"

    final_state = await run_pipeline(
        raw_request=augmented_request,
        user_id=stored.get("user_id", "anonymous"),
        session_id=request.session_id,
        trace_id=trace_id,
        trip_id=request.trip_id,
    )

    # Update trip in database
    await update_trip_status(request.trip_id, final_state.get("pipeline_status", "completed"))

    # Update itinerary if available
    if final_state.get("itinerary"):
        itinerary = await get_itinerary(request.trip_id)
        if itinerary:
            itinerary_id = itinerary["id"]
            await insert_itinerary(
                itinerary_id=itinerary_id,
                trip_id=request.trip_id,
                content=final_state.get("itinerary"),
                budget_breakdown=final_state.get("budget_breakdown"),
                validation_status=final_state.get("validation_status"),
            )

    return FollowUpResponse(
        trip_id=request.trip_id,
        trace_id=trace_id,
        message="Follow-up processed. Pipeline re-run with your answer.",
    )


@router.get("/{trip_id}/status")
async def get_trip_status(trip_id: str) -> dict:
    """Return the current status and key outputs for a trip."""
    stored = await db_get_trip(trip_id)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip '{trip_id}' not found",
        )
    return {
        "trip_id": trip_id,
        "pipeline_status": stored.get("status", "unknown"),
        "validation_status": None,
        "current_step": None,
        "total_latency_ms": None,
        "error_count": 0,
    }
