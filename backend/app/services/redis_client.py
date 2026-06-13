"""Redis client that switches between local Redis and Upstash based on APP_ENV."""

from __future__ import annotations

from typing import Any, Optional

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_settings = get_settings()


# Redis client
_client: Any = None


async def get_redis() -> Any:
    """Get the Redis client (local Redis or Upstash)."""
    global _client
    import asyncio

    if _client is not None:
        try:
            current_loop = asyncio.get_running_loop()
            client_loop = getattr(_client.connection_pool, "_loop", None)
            if client_loop is not None and client_loop is not current_loop:
                # Event loop changed, reset client
                _client = None
        except (RuntimeError, AttributeError):
            _client = None

    if _client is not None:
        return _client

    try:
        import redis.asyncio as aioredis

        # Determine which Redis URL to use
        if _settings.app_env in ("staging", "production"):
            # Use Upstash
            redis_url = _settings.upstash_redis_url
            if not redis_url:
                raise ValueError("UPSTASH_REDIS_URL required for production")

            # Fix URL format if needed
            if not redis_url.startswith(("redis://", "rediss://")):
                if redis_url.startswith("https://"):
                    redis_url = redis_url.replace("https://", "rediss://")
                elif redis_url.startswith("http://"):
                    redis_url = redis_url.replace("http://", "redis://")
                else:
                    redis_url = f"rediss://{redis_url}"

            logger.info("Using Upstash Redis", extra={"event": {"backend": "upstash"}})
        else:
            # Use local Redis
            redis_url = _settings.redis_url or "redis://localhost:6379/0"
            logger.info("Using local Redis", extra={"event": {"backend": "local"}})

        redis_kwargs = {
            "encoding": "utf-8",
            "decode_responses": True,
        }

        # Add password for Upstash
        if _settings.upstash_redis_token:
            redis_kwargs["password"] = _settings.upstash_redis_token

        _client = aioredis.from_url(redis_url, **redis_kwargs)

        # Test connection
        await _client.ping()
        logger.info("Redis client connected successfully")
        return _client

    except ImportError:
        logger.error("redis package not installed - Redis operations will fail")
        raise
    except Exception as e:
        logger.error(f"Failed to create Redis client: {e}")
        raise


async def close_redis() -> None:
    """Close the Redis client."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("Redis client closed")


# Redis operations
async def get(key: str) -> Optional[str]:
    """Get a value from Redis."""
    client = await get_redis()
    return await client.get(key)


async def set(key: str, value: str, ex: Optional[int] = None) -> bool:
    """Set a value in Redis with optional expiration."""
    client = await get_redis()
    return await client.set(key, value, ex=ex)


async def delete(key: str) -> int:
    """Delete a key from Redis."""
    client = await get_redis()
    return await client.delete(key)


async def exists(key: str) -> bool:
    """Check if a key exists in Redis."""
    client = await get_redis()
    return await client.exists(key) > 0


async def hget(name: str, key: str) -> Optional[str]:
    """Get a hash field value."""
    client = await get_redis()
    return await client.hget(name, key)


async def hset(name: str, key: str, value: str) -> int:
    """Set a hash field value."""
    client = await get_redis()
    return await client.hset(name, key, value)


async def hgetall(name: str) -> dict[str, str]:
    """Get all hash fields and values."""
    client = await get_redis()
    return await client.hgetall(name)


async def hdel(name: str, *keys: str) -> int:
    """Delete hash fields."""
    client = await get_redis()
    return await client.hdel(name, *keys)


async def lpush(name: str, *values: str) -> int:
    """Push values onto the left of a list."""
    client = await get_redis()
    return await client.lpush(name, *values)


async def rpop(name: str) -> Optional[str]:
    """Pop a value from the right of a list."""
    client = await get_redis()
    return await client.rpop(name)


async def lrange(name: str, start: int, end: int) -> list[str]:
    """Get a range of elements from a list."""
    client = await get_redis()
    return await client.lrange(name, start, end)


async def ltrim(name: str, start: int, end: int) -> bool:
    """Trim a list to a range."""
    client = await get_redis()
    return await client.ltrim(name, start, end)


async def expire(key: str, seconds: int) -> bool:
    """Set a key's expiration time."""
    client = await get_redis()
    return await client.expire(key, seconds)
