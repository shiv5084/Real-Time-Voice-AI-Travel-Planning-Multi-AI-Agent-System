"""Redis session state management.

Note: For production/staging environments, the actual Redis connectivity switching
(including support for upstash_redis_url and upstash_redis_token) is encapsulated 
within app.services.redis_client.
"""

import json
from typing import Any, Optional

from app.services.redis_client import (
    delete as redis_delete,
    exists as redis_exists,
    get as redis_get,
    set as redis_set,
)

# ---------------------------------------------------------------------------
# Module-level helper used by BaseMCPClient (rate limiting & caching)
# ---------------------------------------------------------------------------

async def get_redis():
    """Return a shared async Redis client, or None if Redis is unavailable."""
    from app.services.redis_client import get_redis
    return await get_redis()


class SessionManager:
    """Manages user sessions using Redis."""

    def __init__(self):
        """Initialize Redis connection."""
        self._client = None

    @property
    def redis_url(self) -> str:
        """Get the configured Redis URL based on APP_ENV."""
        from app.config import get_settings
        settings = get_settings()
        if settings.app_env in ("staging", "production"):
            url = settings.upstash_redis_url or ""
            if url.startswith("https://"):
                url = url.replace("https://", "rediss://")
            elif url.startswith("http://"):
                url = url.replace("http://", "redis://")
            elif url and not url.startswith(("redis://", "rediss://")):
                url = f"rediss://{url}"
            return url
        return settings.redis_url or "redis://localhost:6379/0"

    @property
    def redis_token(self) -> Optional[str]:
        """Get the configured Redis token based on APP_ENV."""
        from app.config import get_settings
        settings = get_settings()
        if settings.app_env in ("staging", "production"):
            return settings.upstash_redis_token
        return None

    async def get_client(self):
        """Get or create Redis client."""
        from app.services.redis_client import get_redis
        return await get_redis()

    async def set(
        self,
        session_id: str,
        data: dict[str, Any],
        ttl: int = 3600,
    ) -> bool:
        """Store session data in Redis with TTL."""
        try:
            await redis_set(session_id, json.dumps(data), ex=ttl)
            return True
        except Exception as e:
            print(f"Error setting session: {e}")
            return False

    async def get(self, session_id: str) -> Optional[dict[str, Any]]:
        """Retrieve session data from Redis."""
        try:
            data = await redis_get(session_id)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            print(f"Error getting session: {e}")
            return None

    async def delete(self, session_id: str) -> bool:
        """Delete session from Redis."""
        try:
            await redis_delete(session_id)
            return True
        except Exception as e:
            print(f"Error deleting session: {e}")
            return False

    async def exists(self, session_id: str) -> bool:
        """Check if session exists."""
        try:
            return await redis_exists(session_id)
        except Exception as e:
            print(f"Error checking session existence: {e}")
            return False

    async def close(self):
        """Close Redis connection."""
        from app.services.redis_client import close_redis
        await close_redis()


# Global session manager instance
session_manager = SessionManager()
