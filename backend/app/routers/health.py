"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@router.get("/diag")
async def diag_check():
    """Diagnostic check to verify environment variables presence and DB connectivity."""
    from app.config import get_settings
    from app.services.database import get_pool
    
    settings = get_settings()
    
    # Check Env Vars presence (do not leak actual values, just boolean presence)
    env_status = {
        "APP_ENV": settings.app_env,
        "SUPABASE_URL_set": bool(settings.supabase_url),
        "SUPABASE_ANON_KEY_set": bool(settings.supabase_anon_key),
        "SUPABASE_SERVICE_KEY_set": bool(settings.supabase_service_key),
        "SUPABASE_DB_PASSWORD_set": bool(settings.supabase_db_password),
        "UPSTASH_REDIS_URL_set": bool(settings.upstash_redis_url),
        "UPSTASH_REDIS_TOKEN_set": bool(settings.upstash_redis_token),
        "GROQ_API_KEY_set": bool(settings.groq_api_key),
        "GEMINI_API_KEY_set": bool(settings.gemini_api_key),
        "MEM0_API_KEY_set": bool(settings.mem0_api_key),
        "ELEVENLABS_API_KEY_set": bool(settings.elevenlabs_api_key),
        "MCP_SERVER_URL": settings.mcp_server_url,
    }
    
    # Check Database Connectivity
    db_status = "unknown"
    db_error = None
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1")
            if val == 1:
                db_status = "connected"
    except Exception as e:
        db_status = "failed"
        db_error = str(e)
        
    return {
        "status": "diag_complete",
        "env_variables": env_status,
        "database": {
            "status": db_status,
            "error": db_error
        }
    }

