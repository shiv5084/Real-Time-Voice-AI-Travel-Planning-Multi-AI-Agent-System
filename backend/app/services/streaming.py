"""SSE streaming service for real-time pipeline status updates."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from app.utils.logging import get_logger

logger = get_logger(__name__)


async def stream_pipeline_events(
    state_updates: list[dict[str, Any]],
) -> AsyncGenerator[dict[str, str], None]:
    """Yield SSE events from a list of pre-collected state update snapshots.

    Each yielded dict has keys 'event' and 'data', matching the format
    expected by sse-starlette's EventSourceResponse.

    Args:
        state_updates: Ordered list of pipeline state snapshots or update dicts.
    """
    for update in state_updates:
        yield {
            "event": "pipeline_update",
            "data": json.dumps(update, default=str),
        }
        await asyncio.sleep(0)  # Yield control to the event loop between events

    # Final sentinel event
    yield {
        "event": "pipeline_complete",
        "data": json.dumps({"status": "done"}),
    }


async def stream_from_pipeline(
    raw_request: str,
    user_id: str = "anonymous",
    session_id: str = "",
    trace_id: str = "",
    trip_id: str | None = None,
) -> AsyncGenerator[dict[str, str], None]:
    """Run the full pipeline and stream state updates as SSE events.

    This is the real-time streaming variant — each agent completion emits an event.
    """
    from app.graph.workflow import run_pipeline

    # Emit a "started" event immediately
    yield {
        "event": "pipeline_update",
        "data": json.dumps({"current_step": "pipeline_started", "trip_id": trip_id}),
    }
    await asyncio.sleep(0)

    # Run pipeline (non-streaming for Phase 3 — Phase 4+ can hook into LangGraph callbacks)
    try:
        final_state = await run_pipeline(
            raw_request=raw_request,
            user_id=user_id,
            session_id=session_id,
            trace_id=trace_id,
            trip_id=trip_id,
        )
        yield {
            "event": "pipeline_complete",
            "data": json.dumps(
                {
                    "pipeline_status": final_state.get("pipeline_status"),
                    "validation_status": final_state.get("validation_status"),
                    "current_step": final_state.get("current_step"),
                    "total_latency_ms": final_state.get("total_latency_ms"),
                    "has_itinerary": final_state.get("itinerary") is not None,
                    "error_count": len(final_state.get("errors") or []),
                },
                default=str,
            ),
        }
    except Exception as exc:
        logger.error("Streaming pipeline failed", extra={"event": {"error": str(exc)}}, exc_info=True)
        yield {
            "event": "pipeline_error",
            "data": json.dumps({"error": str(exc)}),
        }


def create_sse_response(generator: AsyncGenerator[dict[str, str], None]) -> Any:
    """Wrap an async generator in an EventSourceResponse for FastAPI."""
    try:
        from sse_starlette.sse import EventSourceResponse
        return EventSourceResponse(generator)
    except ImportError:
        logger.warning("sse_starlette not installed — SSE responses unavailable")
        raise ImportError("sse-starlette must be installed to use SSE streaming")
