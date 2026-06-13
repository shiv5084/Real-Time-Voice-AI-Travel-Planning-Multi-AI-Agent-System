"""Mem0 long-term preference client.

Stores and retrieves user preferences (food style, accommodation type,
crowd tolerance, activity level, transport mode) via the Mem0 platform.

If MEM0_API_KEY is not configured, falls back to a Redis-backed local
preference store so the pipeline keeps working in local dev.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Preference categories we care about
PREFERENCE_KEYS = [
    "food",
    "accommodation_type",
    "crowd_tolerance",
    "activity_level",
    "transport_preference",
    "dietary_restrictions",
    "budget_style",
    "travel_style",
    "airline_preference",
]


# ---------------------------------------------------------------------------
# Mem0 client wrapper
# ---------------------------------------------------------------------------

class Mem0Client:
    """Wraps the Mem0 Python SDK.

    Falls back to Redis-backed local storage when MEM0_API_KEY is absent.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: Any = None
        self._redis: Any = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Initialization (lazy)
    # ------------------------------------------------------------------

    async def _ensure_init(self) -> None:
        if self._initialized:
            return

        api_key = getattr(self._settings, "mem0_api_key", None)
        if api_key:
            try:
                from mem0 import AsyncMemoryClient  # type: ignore[import]
                self._client = AsyncMemoryClient(api_key=api_key)
                logger.info("Mem0 async client initialized", extra={"event": {"backend": "mem0_cloud"}})
            except ImportError:
                logger.warning(
                    "mem0ai package not installed — falling back to Redis preference store",
                    extra={"event": {"backend": "redis_fallback"}},
                )
                await self._init_redis_fallback()
            except Exception as exc:
                logger.warning(
                    f"Mem0 client init failed ({exc}) — falling back to Redis",
                    extra={"event": {"backend": "redis_fallback"}},
                )
                await self._init_redis_fallback()
        else:
            logger.info(
                "MEM0_API_KEY not set — using Redis preference store",
                extra={"event": {"backend": "redis_fallback"}},
            )
            await self._init_redis_fallback()

        self._initialized = True

    async def _init_redis_fallback(self) -> None:
        try:
            from app.memory.session import get_redis
            self._redis = await get_redis()
        except Exception as exc:
            logger.warning(f"Redis fallback unavailable: {exc}")
            self._redis = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def add_memory(
        self,
        user_id: str,
        messages: list[dict[str, str]],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add a memory entry derived from a conversation exchange.

        ``messages`` should be a list of ``{"role": ..., "content": ...}`` dicts
        in chronological order. Mem0 will extract and store relevant facts.
        """
        await self._ensure_init()
        if self._client is not None:
            try:
                result = await self._client.add(messages, user_id=user_id, metadata=metadata or {})
                return result if isinstance(result, dict) else {"status": "added"}
            except Exception as exc:
                logger.warning(f"Mem0 add_memory failed: {exc} — falling back to Redis")

        # Redis fallback: store the raw messages as a recent conversation snippet
        if self._redis:
            key = f"mem0:messages:{user_id}"
            await self._redis.lpush(key, json.dumps(messages))
            await self._redis.ltrim(key, 0, 19)  # keep last 20 conversation turns
            await self._redis.expire(key, 60 * 60 * 24 * 365)  # 1 year
        return {"status": "stored_in_redis"}

    async def get_memories(
        self,
        user_id: str,
        query: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant memories for a user, optionally filtered by query."""
        await self._ensure_init()
        if self._client is not None:
            try:
                results = await self._client.search(
                    query=query or "travel preferences",
                    user_id=user_id,
                    limit=limit,
                )
                if isinstance(results, list):
                    return results
                if isinstance(results, dict):
                    return results.get("results", [])
            except Exception as exc:
                logger.warning(f"Mem0 get_memories failed: {exc} — falling back to Redis")

        # Redis fallback: return stored preference object
        if self._redis:
            pref_key = f"mem0:prefs:{user_id}"
            raw = await self._redis.get(pref_key)
            if raw:
                try:
                    prefs = json.loads(raw)
                    return [{"memory": k + ": " + str(v), "metadata": {"category": k}} for k, v in prefs.items()]
                except Exception:
                    pass
        return []

    async def store_preferences(
        self,
        user_id: str,
        preferences: dict[str, Any],
    ) -> bool:
        """Directly upsert a structured preference dict for a user.

        This is used when the user explicitly sets preferences via the profile API.
        For inferred preferences from conversations, use ``add_memory``.
        """
        await self._ensure_init()

        if self._client is not None:
            try:
                messages = [
                    {
                        "role": "user",
                        "content": _prefs_to_natural_language(preferences),
                    }
                ]
                await self._client.add(messages, user_id=user_id, metadata={"source": "profile_update"})
                return True
            except Exception as exc:
                logger.warning(f"Mem0 store_preferences failed: {exc} — falling back to Redis")

        # Redis fallback: merge into existing preferences
        if self._redis:
            pref_key = f"mem0:prefs:{user_id}"
            raw = await self._redis.get(pref_key)
            existing: dict[str, Any] = {}
            if raw:
                try:
                    existing = json.loads(raw)
                except Exception:
                    pass
            existing.update({k: v for k, v in preferences.items() if v is not None})
            await self._redis.set(pref_key, json.dumps(existing))
            await self._redis.expire(pref_key, 60 * 60 * 24 * 365)  # 1 year
            return True
        return False

    async def get_preferences(self, user_id: str) -> dict[str, Any]:
        """Return a structured preference dict for a user.

        Parses the raw memory entries into a clean dict with known keys.
        """
        memories = await self.get_memories(user_id, query="travel preferences food accommodation")
        return _parse_preferences_from_memories(memories)

    async def delete_user_memories(self, user_id: str) -> bool:
        """Delete all stored memories for a user (GDPR / account deletion)."""
        await self._ensure_init()
        if self._client is not None:
            try:
                await self._client.delete_all(user_id=user_id)
                return True
            except Exception as exc:
                logger.warning(f"Mem0 delete failed: {exc}")

        if self._redis:
            await self._redis.delete(f"mem0:prefs:{user_id}", f"mem0:messages:{user_id}")
            return True
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prefs_to_natural_language(prefs: dict[str, Any]) -> str:
    """Convert a structured preference dict to a natural language statement."""
    parts = []
    mapping = {
        "food": "I prefer {} cuisine",
        "accommodation_type": "I prefer {} accommodation",
        "crowd_tolerance": "My crowd tolerance is {}",
        "activity_level": "My activity level preference is {}",
        "transport_preference": "I prefer {} for transport",
        "dietary_restrictions": "My dietary restrictions are: {}",
        "budget_style": "My budget style is {}",
        "travel_style": "My travel style is {}",
        "airline_preference": "I prefer flying with {} airlines",
    }
    for key, template in mapping.items():
        val = prefs.get(key)
        if val:
            parts.append(template.format(val))
    return ". ".join(parts) + "." if parts else "No specific preferences."


def _parse_preferences_from_memories(memories: list[dict[str, Any]]) -> dict[str, Any]:
    """Best-effort extraction of structured preferences from Mem0 memory entries."""
    result: dict[str, Any] = {}

    for mem in memories:
        memory_text = mem.get("memory", "")
        metadata = mem.get("metadata") or {}
        category = metadata.get("category")

        # Structured entry (from Redis fallback)
        if category and category in PREFERENCE_KEYS:
            # Extract value from "key: value" format
            if ": " in memory_text:
                val = memory_text.split(": ", 1)[-1].strip()
                result[category] = val
            continue

        # Natural language parsing (from Mem0 cloud)
        lower = memory_text.lower()
        if "vegetarian" in lower or "vegan" in lower:
            result.setdefault("dietary_restrictions", "vegetarian/vegan")
        if "halal" in lower:
            result.setdefault("dietary_restrictions", "halal")
        if "kosher" in lower:
            result.setdefault("dietary_restrictions", "kosher")
        if "luxury" in lower:
            result.setdefault("accommodation_type", "luxury")
            result.setdefault("budget_style", "luxury")
        if "budget" in lower and "style" not in lower:
            result.setdefault("budget_style", "budget")
        if "backpacker" in lower:
            result.setdefault("travel_style", "backpacker")
        if "crowd" in lower and "avoid" in lower:
            result.setdefault("crowd_tolerance", "low")
        if "active" in lower or "hiking" in lower:
            result.setdefault("activity_level", "high")
        if "relaxed" in lower or "slow" in lower:
            result.setdefault("activity_level", "low")

    return result


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_mem0_client: Mem0Client | None = None


def get_mem0_client() -> Mem0Client:
    """Return the module-level Mem0 client singleton."""
    global _mem0_client
    if _mem0_client is None:
        _mem0_client = Mem0Client()
    return _mem0_client
