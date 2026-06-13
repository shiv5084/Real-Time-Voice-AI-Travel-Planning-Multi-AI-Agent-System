"""PostgreSQL episodic memory — read/write past trip learnings.

Episodic memory stores structured lessons learned from completed trips
so the Planner Agent can personalise future plans for repeat destinations.

Schema is the ``episodic_memory`` table created in 001_initial_schema.sql:

    id UUID, user_id UUID, trip_id UUID,
    destination TEXT, summary TEXT,
    lessons_learned JSONB, created_at TIMESTAMPTZ, expires_at TIMESTAMPTZ
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# How long to keep episodic memories (1 year as per plan)
MEMORY_RETENTION_DAYS = 365


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

async def _get_conn():
    """Return an asyncpg connection from the pool, or None if unavailable."""
    settings = get_settings()
    db_url = settings.database_url
    if not db_url:
        return None
    try:
        import asyncpg  # type: ignore[import]
        # Add 5-second timeout to prevent hanging on unresponsive DB
        conn = await asyncio.wait_for(
            asyncpg.connect(db_url),
            timeout=5.0
        )
        return conn
    except asyncio.TimeoutError:
        logger.warning("DB connection timed out (5s) — episodic memory unavailable")
        return None
    except ImportError:
        logger.warning("asyncpg not installed — episodic memory unavailable")
        return None
    except Exception as exc:
        logger.warning(f"DB connection failed: {exc} — episodic memory unavailable")
        return None


# ---------------------------------------------------------------------------
# Core CRUD operations
# ---------------------------------------------------------------------------

async def save_trip_memory(
    user_id: str,
    trip_id: str,
    destination: str,
    summary: str,
    lessons_learned: dict[str, Any],
) -> bool:
    """Persist a trip memory entry to the ``episodic_memory`` table.

    Args:
        user_id: The profile UUID of the user.
        trip_id: The UUID of the completed trip.
        destination: Primary destination (city or country).
        summary: Short natural language summary of the trip.
        lessons_learned: Structured dict with keys like:
            - what_worked: list of positive experiences
            - what_to_avoid: list of negative experiences
            - preferred_areas: list of neighbourhoods
            - timing_notes: string advice on best time to visit
            - cost_notes: string advice on budget
    """
    conn = await _get_conn()
    if conn is None:
        logger.warning("Episodic memory: DB unavailable, memory not saved")
        return False

    try:
        expires_at = datetime.now(timezone.utc) + timedelta(days=MEMORY_RETENTION_DAYS)
        await conn.execute(
            """
            INSERT INTO episodic_memory
                (user_id, trip_id, destination, summary, lessons_learned, expires_at)
            VALUES
                ($1::uuid, $2::uuid, $3, $4, $5, $6)
            ON CONFLICT DO NOTHING
            """,
            user_id,
            trip_id,
            destination.lower(),
            summary,
            json.dumps(lessons_learned),
            expires_at,
        )
        logger.info(
            "Episodic memory saved",
            extra={"event": {"user_id": user_id, "destination": destination}},
        )
        return True
    except Exception as exc:
        logger.error(f"Failed to save episodic memory: {exc}", exc_info=True)
        return False
    finally:
        await conn.close()


async def get_memories_for_destination(
    user_id: str,
    destination: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve past trip memories for a specific destination.

    Returns fresh memories (not expired) ordered by recency.
    """
    conn = await _get_conn()
    if conn is None:
        return []

    try:
        rows = await conn.fetch(
            """
            SELECT id, trip_id, destination, summary, lessons_learned,
                   created_at, expires_at
            FROM episodic_memory
            WHERE user_id = $1::uuid
              AND destination ILIKE $2
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at DESC
            LIMIT $3
            """,
            user_id,
            f"%{destination.lower()}%",
            limit,
        )
        return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        logger.warning(f"Failed to retrieve episodic memories: {exc}")
        return []
    finally:
        await conn.close()


async def get_all_memories(
    user_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Retrieve all fresh episodic memories for a user (for Planner context)."""
    conn = await _get_conn()
    if conn is None:
        return []

    try:
        rows = await conn.fetch(
            """
            SELECT id, trip_id, destination, summary, lessons_learned,
                   created_at, expires_at
            FROM episodic_memory
            WHERE user_id = $1::uuid
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
        return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        logger.warning(f"Failed to retrieve all episodic memories: {exc}")
        return []
    finally:
        await conn.close()


async def build_episodic_context(
    user_id: str,
    destinations: list[str],
) -> dict[str, Any]:
    """Build a curated context dict from episodic memories for the given destinations.

    Returns a dict the Planner Agent can inject into its reasoning context:
        {
            "repeat_destinations": [...],
            "destination_memories": {<dest>: [<lesson>, ...]},
            "general_patterns": [...],
        }
    """
    if not user_id or user_id == "anonymous":
        return {}

    # Fetch destination-specific memories
    destination_memories: dict[str, list[str]] = {}
    repeat_destinations: list[str] = []

    for dest in destinations:
        mems = await get_memories_for_destination(user_id, dest)
        if mems:
            repeat_destinations.append(dest)
            summaries = []
            for m in mems:
                lessons = m.get("lessons_learned") or {}
                what_worked = lessons.get("what_worked") or []
                what_to_avoid = lessons.get("what_to_avoid") or []
                timing = lessons.get("timing_notes", "")
                cost = lessons.get("cost_notes", "")
                if what_worked:
                    summaries.append(f"What worked: {', '.join(what_worked)}")
                if what_to_avoid:
                    summaries.append(f"Avoid: {', '.join(what_to_avoid)}")
                if timing:
                    summaries.append(f"Timing: {timing}")
                if cost:
                    summaries.append(f"Cost tip: {cost}")
            destination_memories[dest] = summaries

    # General patterns from all trips (not destination-specific)
    all_mems = await get_all_memories(user_id, limit=10)
    general_patterns: list[str] = []
    for m in all_mems:
        summary = m.get("summary", "")
        if summary and len(summary) > 20:
            general_patterns.append(summary[:200])

    return {
        "repeat_destinations": repeat_destinations,
        "destination_memories": destination_memories,
        "general_patterns": general_patterns[:5],
    }


async def extract_and_save_lessons(
    user_id: str,
    trip_id: str,
    state: dict[str, Any],
) -> bool:
    """Extract lessons from a completed pipeline state and persist to episodic memory.

    Called at the end of a successful trip plan to capture learnings.
    """
    constraints = state.get("constraints") or {}
    itinerary = state.get("itinerary") or {}
    budget = state.get("budget_breakdown") or {}
    validation_issues = state.get("validation_issues") or []

    destinations = constraints.get("destinations") or []
    if not destinations:
        return False

    primary_dest = destinations[0]
    days = itinerary.get("days") or []
    num_days = len(days)
    total_cost = budget.get("total_estimated_cost", 0)
    compliance = budget.get("compliance", "within_budget")

    # Derive lessons from the pipeline outcome
    lessons: dict[str, Any] = {
        "what_worked": [],
        "what_to_avoid": [],
        "timing_notes": "",
        "cost_notes": f"${total_cost:.0f} for {num_days} days (compliance: {compliance})",
        "regen_count": state.get("regeneration_count", 0),
    }

    if compliance == "within_budget":
        lessons["what_worked"].append("Budget was achievable")
    elif compliance == "over_budget":
        lessons["what_to_avoid"].append("Budget was exceeded — adjust estimates")

    major_issues = [i["description"] for i in validation_issues if i.get("severity") in ("critical", "major")]
    if major_issues:
        lessons["what_to_avoid"].extend(major_issues[:3])

    # Extract preferred areas from itinerary
    preferred_areas = []
    for day in days[:3]:
        loc = day.get("location") or day.get("area") or ""
        if loc and loc.lower() not in [a.lower() for a in preferred_areas]:
            preferred_areas.append(loc)
    if preferred_areas:
        lessons["preferred_areas"] = preferred_areas

    start_date = constraints.get("start_date") or ""
    if start_date:
        lessons["timing_notes"] = f"Visited around {start_date[:7]}"

    summary = (
        f"{num_days}-day trip to {primary_dest} for {constraints.get('travelers', 1)} "
        f"traveler(s). Budget: ${constraints.get('budget', 'unspecified')}. "
        f"Status: {state.get('validation_status', 'unknown')}."
    )

    return await save_trip_memory(
        user_id=user_id,
        trip_id=trip_id,
        destination=primary_dest,
        summary=summary,
        lessons_learned=lessons,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert asyncpg Row to plain dict."""
    d = dict(row)
    for key in ("lessons_learned",):
        if isinstance(d.get(key), str):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                pass
    # Convert datetime objects to ISO strings for JSON serialisation
    for key in ("created_at", "expires_at"):
        if isinstance(d.get(key), datetime):
            d[key] = d[key].isoformat()
    # Convert UUID objects to strings
    for key in ("id", "trip_id", "user_id"):
        if d.get(key) is not None:
            d[key] = str(d[key])
    return d
