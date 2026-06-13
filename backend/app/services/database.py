"""Database client that switches between local PostgreSQL and Supabase based on APP_ENV."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_settings = get_settings()


# Database connection pool
_pool: Any = None


async def get_pool() -> Any:
    """Get the database connection pool (local PostgreSQL or Supabase)."""
    global _pool

    if _pool is not None:
        return _pool

    try:
        import asyncpg

        # Determine which database URL to use
        if _settings.app_env in ("staging", "production"):
            if _settings.database_url:
                db_url = _settings.database_url
                logger.info("Using Supabase database from DATABASE_URL", extra={"event": {"backend": "supabase_override"}})
            else:
                # Use Supabase
                if not _settings.supabase_url or not _settings.supabase_db_password:
                    raise ValueError("SUPABASE_URL and SUPABASE_DB_PASSWORD (or DATABASE_URL) required for production")

                # Extract project ref from SUPABASE_URL
                project_ref = _settings.supabase_url.replace("https://", "").replace(".supabase.co", "")

                # Construct connection string
                from urllib.parse import quote
                password_encoded = quote(_settings.supabase_db_password, safe="")
                db_url = f"postgresql://postgres:{password_encoded}@db.{project_ref}.supabase.co:5432/postgres"

                logger.info("Using Supabase database (direct fallback)", extra={"event": {"backend": "supabase"}})
        else:
            # Use local PostgreSQL
            db_url = _settings.database_url or "postgresql://postgres:postgres@localhost:5432/travel_db"
            logger.info("Using local PostgreSQL", extra={"event": {"backend": "local"}})

        async def init_connection(conn):
            import json
            await conn.set_type_codec(
                "json",
                encoder=json.dumps,
                decoder=json.loads,
                schema="pg_catalog"
            )
            await conn.set_type_codec(
                "jsonb",
                encoder=json.dumps,
                decoder=json.loads,
                schema="pg_catalog"
            )

        _pool = await asyncpg.create_pool(
            db_url,
            min_size=_settings.db_pool_min_size,
            max_size=_settings.db_pool_max_size,
            command_timeout=60,
            init=init_connection,
        )
        logger.info("Database pool created successfully")
        return _pool

    except ImportError:
        logger.error("asyncpg not installed - database operations will fail")
        raise
    except Exception as e:
        logger.error(f"Failed to create database pool: {e}")
        raise


async def close_pool() -> None:
    """Close the database connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


# Database operations
async def execute_query(query: str, *args: Any) -> list[dict[str, Any]]:
    """Execute a SELECT query and return results as list of dicts."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(row) for row in rows]


async def execute_command(query: str, *args: Any) -> str:
    """Execute an INSERT/UPDATE/DELETE command and return the affected row count."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(query, *args)
        return result


async def ensure_profile_exists(
    profile_id: str,
    email: Optional[str] = None,
    display_name: Optional[str] = None,
) -> None:
    """Ensure a profile exists in the database. If not, create one."""
    if not email:
        email = f"{profile_id}@placeholder.com"
    if not display_name:
        display_name = f"User {profile_id[:8]}"
        
    query = """
        INSERT INTO profiles (id, email, display_name)
        VALUES ($1, $2, $3)
        ON CONFLICT (id) DO NOTHING
    """
    await execute_command(query, profile_id, email, display_name)


async def insert_trip(
    trip_id: str,
    user_id: str,
    title: str,
    raw_request: str,
    constraints: dict[str, Any],
    status: str = "planning",
) -> None:
    """Insert a trip into the database."""
    # Ensure profile exists first due to foreign key constraint
    await ensure_profile_exists(user_id)

    query = """
        INSERT INTO trips (id, user_id, title, raw_request, constraints, status)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (id) DO UPDATE SET
            raw_request = EXCLUDED.raw_request,
            constraints = EXCLUDED.constraints,
            status = EXCLUDED.status,
            updated_at = NOW()
    """
    await execute_command(query, trip_id, user_id, title, raw_request, constraints, status)


async def get_trip(trip_id: str) -> Optional[dict[str, Any]]:
    """Get a trip by ID."""
    query = "SELECT * FROM trips WHERE id = $1"
    results = await execute_query(query, trip_id)
    return results[0] if results else None


async def list_trips(user_id: Optional[str] = None) -> list[dict[str, Any]]:
    """List all trips, optionally filtered by user_id."""
    if user_id:
        query = "SELECT * FROM trips WHERE user_id = $1 ORDER BY created_at DESC"
        return await execute_query(query, user_id)
    else:
        query = "SELECT * FROM trips ORDER BY created_at DESC"
        return await execute_query(query)


async def delete_trip(trip_id: str) -> None:
    """Delete a trip by ID."""
    query = "DELETE FROM trips WHERE id = $1"
    await execute_command(query, trip_id)


async def update_trip_status(trip_id: str, status: str) -> None:
    """Update a trip's status."""
    query = "UPDATE trips SET status = $1, updated_at = NOW() WHERE id = $2"
    await execute_command(query, status, trip_id)


async def insert_itinerary(
    itinerary_id: str,
    trip_id: str,
    content: dict[str, Any],
    budget_breakdown: Optional[dict[str, Any]] = None,
    validation_status: Optional[str] = None,
) -> None:
    """Insert an itinerary into the database."""
    query = """
        INSERT INTO itineraries (id, trip_id, content, budget_breakdown, validation_status)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (id) DO UPDATE SET
            content = EXCLUDED.content,
            budget_breakdown = EXCLUDED.budget_breakdown,
            validation_status = EXCLUDED.validation_status
    """
    await execute_command(query, itinerary_id, trip_id, content, budget_breakdown, validation_status)


async def get_itinerary(trip_id: str) -> Optional[dict[str, Any]]:
    """Get an itinerary by trip_id."""
    query = "SELECT * FROM itineraries WHERE trip_id = $1"
    results = await execute_query(query, trip_id)
    return results[0] if results else None


async def insert_audit_log(
    trace_id: str,
    trip_id: Optional[str],
    agent: str,
    model: Optional[str],
    tool: Optional[str],
    client: Optional[str],
    arguments: Optional[dict[str, Any]],
    result: Optional[dict[str, Any]],
    latency_ms: Optional[int],
    cost_usd: Optional[float],
    cache_hit: bool = False,
) -> None:
    """Insert an audit log entry."""
    query = """
        INSERT INTO audit_log (
            trace_id, trip_id, agent, model, tool, client,
            arguments, result, latency_ms, cost_usd, cache_hit
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    """
    await execute_command(
        query,
        trace_id,
        trip_id,
        agent,
        model,
        tool,
        client,
        arguments,
        result,
        latency_ms,
        cost_usd,
        cache_hit,
    )
