"""User profile & preference API routes.

Phase 4 routes:
  GET  /api/profile              — return current user's preferences and trip history
  PUT  /api/profile/preferences  — upsert structured travel preferences in database
  GET  /api/profile/memories     — return stored Mem0 memories for the user
  DELETE /api/profile/memories   — delete all stored memories (GDPR)
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.memory.mem0_client import get_mem0_client
from app.services.auth import AuthService
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/profile", tags=["profile"])


# ── Request / Response models ──────────────────────────────────────────────

class TravelPreferences(BaseModel):
    """Structured travel preference update payload."""

    food: Optional[str] = Field(None, description="Cuisine preferences (e.g. 'Italian, Japanese')")
    accommodation_type: Optional[str] = Field(
        None, description="Preferred accommodation type (e.g. 'hotel', 'hostel', 'luxury', 'airbnb')"
    )
    crowd_tolerance: Optional[str] = Field(
        None, description="Crowd preference: 'low', 'medium', or 'high'"
    )
    activity_level: Optional[str] = Field(
        None, description="Pace preference: 'relaxed', 'moderate', or 'active'"
    )
    transport_preference: Optional[str] = Field(
        None, description="Preferred transport mode (e.g. 'public transit', 'rental car', 'walking')"
    )
    dietary_restrictions: Optional[str] = Field(
        None, description="Dietary requirements (e.g. 'vegetarian', 'vegan', 'halal', 'kosher')"
    )
    budget_style: Optional[str] = Field(
        None, description="Budget preference: 'budget', 'mid-range', or 'luxury'"
    )
    travel_style: Optional[str] = Field(
        None, description="Travel style (e.g. 'backpacker', 'cultural', 'adventure', 'relaxation')"
    )
    airline_preference: Optional[str] = Field(
        None, description="Preferred airlines (e.g. 'Singapore Airlines', 'Delta')"
    )



class PreferencesResponse(BaseModel):
    user_id: str
    preferences: dict[str, Any]
    message: str


class ProfileResponse(BaseModel):
    user_id: str
    display_name: Optional[str] = None
    preferences: dict[str, Any]
    memory_count: int
    recent_destinations: list[str]


class MemoriesResponse(BaseModel):
    user_id: str
    memories: list[dict[str, Any]]
    count: int


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("", response_model=ProfileResponse)
async def get_profile(user_id: str = "anonymous") -> ProfileResponse:
    """Return the user's stored preferences and a summary of their trip history."""
    if user_id == "anonymous":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id is required to retrieve a profile",
        )

    # Load preferences from Supabase (structured storage)
    # Use the service role key so RLS does not block the read.
    preferences: dict[str, Any] = {}
    display_name: Optional[str] = None
    try:
        import httpx
        from app.config import get_settings

        settings = get_settings()
        if settings.supabase_url and settings.supabase_service_key:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.supabase_url}/rest/v1/profiles?id=eq.{user_id}&select=preferences,display_name",
                    headers={
                        "apikey": settings.supabase_service_key,
                        "Authorization": f"Bearer {settings.supabase_service_key}",
                    },
                )
                if response.status_code == 200 and response.json():
                    data = response.json()[0]
                    raw_prefs = data.get("preferences")
                    if isinstance(raw_prefs, dict) and raw_prefs:
                        preferences = raw_prefs
                    display_name = data.get("display_name")
    except Exception as exc:
        logger.warning(f"Could not load preferences from Supabase for {user_id}: {exc}")

    # Load recent destinations from episodic memory
    recent_destinations: list[str] = []
    memory_count = 0
    try:
        from app.memory.episodic import get_all_memories
        memories = await get_all_memories(user_id, limit=10)
        memory_count = len(memories)
        seen: set[str] = set()
        for m in memories:
            dest = m.get("destination", "")
            if dest and dest not in seen:
                recent_destinations.append(dest.title())
                seen.add(dest)
    except Exception as exc:
        logger.warning(f"Could not load episodic memories for {user_id}: {exc}")

    return ProfileResponse(
        user_id=user_id,
        display_name=display_name,
        preferences=preferences,
        memory_count=memory_count,
        recent_destinations=recent_destinations[:5],
    )


@router.put("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    preferences: TravelPreferences,
    user_id: str = "anonymous",
) -> PreferencesResponse:
    """Upsert travel preferences in the profiles table (persistent storage).

    Only non-null fields are stored. Existing preferences for other keys
    are preserved (deep merge on the server side).

    The user_id must match the auth user's UUID (from Supabase Auth).
    Uses the service role key to bypass RLS.
    """
    if user_id == "anonymous":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id is required to update preferences",
        )

    pref_dict = {k: v for k, v in preferences.model_dump().items() if v is not None}
    if not pref_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one preference field must be provided",
        )

    import httpx
    from app.config import get_settings

    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_service_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured on this server",
        )

    # Headers using the service role key to bypass RLS
    service_headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    try:
        async with httpx.AsyncClient() as client:
            # 1. Fetch the current profile to get existing preferences (for merge)
            # Profile PK is `id` = Supabase auth user UUID.
            fetch_resp = await client.get(
                f"{settings.supabase_url}/rest/v1/profiles?id=eq.{user_id}&select=id,preferences",
                headers=service_headers,
            )
            existing_rows = fetch_resp.json() if fetch_resp.status_code == 200 else []

            if existing_rows:
                # 2a. Profile exists — deep-merge preferences then PATCH
                existing_prefs: dict[str, Any] = {}
                raw = existing_rows[0].get("preferences")
                if isinstance(raw, dict):
                    existing_prefs = raw

                merged = {**existing_prefs, **pref_dict}  # new values override old

                patch_resp = await client.patch(
                    f"{settings.supabase_url}/rest/v1/profiles?id=eq.{user_id}",
                    headers={**service_headers, "Prefer": "return=minimal"},
                    json={"preferences": merged},
                )
                if patch_resp.status_code not in (200, 204):
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Supabase PATCH failed: {patch_resp.status_code} {patch_resp.text}",
                    )

                logger.info(
                    "Preferences merged and updated in Supabase",
                    extra={"event": {"user_id": user_id, "keys": list(pref_dict.keys())}},
                )

            else:
                # 2b. No profile row yet — create one with preferences.
                # This is a fallback for users who registered via the Supabase
                # SDK directly and whose profile row wasn't created yet.
                post_resp = await client.post(
                    f"{settings.supabase_url}/rest/v1/profiles",
                    headers={**service_headers, "Prefer": "return=minimal"},
                    json={
                        "id": user_id,          # PK = Supabase auth UID
                        "email": f"{user_id}@placeholder.com",
                        "preferences": pref_dict,
                    },
                )
                if post_resp.status_code not in (200, 201):
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Supabase INSERT failed: {post_resp.status_code} {post_resp.text}",
                    )

                logger.info(
                    "Profile created with preferences in Supabase",
                    extra={"event": {"user_id": user_id, "keys": list(pref_dict.keys())}},
                )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"Failed to store preferences in Supabase for {user_id}: {exc}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store preferences: {exc}",
        )

    # Also store in Mem0 for conversational retrieval (best-effort)
    try:
        from app.memory.mem0_client import get_mem0_client
        mem0 = get_mem0_client()
        await mem0.store_preferences(user_id, pref_dict)
    except Exception as exc:
        logger.warning(f"Mem0 preference sync failed (non-fatal): {exc}")

    return PreferencesResponse(
        user_id=user_id,
        preferences=pref_dict,
        message=f"Preferences updated: {', '.join(pref_dict.keys())}",
    )


@router.get("/memories", response_model=MemoriesResponse)
async def get_memories(
    user_id: str = "anonymous",
    query: Optional[str] = None,
    limit: int = 10,
) -> MemoriesResponse:
    """Return raw Mem0 memories for the user (useful for debugging)."""
    if user_id == "anonymous":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id is required",
        )

    memories: list[dict[str, Any]] = []
    try:
        client = get_mem0_client()
        memories = await client.get_memories(user_id, query=query, limit=limit)
    except Exception as exc:
        logger.warning(f"Could not retrieve memories for {user_id}: {exc}")

    return MemoriesResponse(
        user_id=user_id,
        memories=memories,
        count=len(memories),
    )


@router.delete("/memories", status_code=status.HTTP_200_OK)
async def delete_memories(user_id: str = "anonymous") -> dict[str, str]:
    """Delete all Mem0 memories for the user (GDPR / account deletion)."""
    if user_id == "anonymous":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id is required",
        )

    deleted = False
    try:
        client = get_mem0_client()
        deleted = await client.delete_user_memories(user_id)
    except Exception as exc:
        logger.error(f"Failed to delete memories for {user_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete memories: {exc}",
        )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory service unavailable — memories not deleted",
        )

    return {"message": f"All memories deleted for user {user_id}"}
