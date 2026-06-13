import pytest
import json
from app.agents.planner import PlannerAgent
from app.config import get_settings

@pytest.mark.asyncio
async def test_llm_cache_integration():
    """Verify that _call_llm retrieves from and stores to the Redis cache."""
    agent = PlannerAgent()
    settings = get_settings()
    
    # Temporarily force cache to be enabled
    original_cache_enabled = settings.enable_llm_cache
    settings.enable_llm_cache = True
    
    try:
        messages = [{"role": "user", "content": "Hello LLM Cache Test"}]
        
        # Clear any existing cache entry first
        from app.memory.session import get_redis
        redis = await get_redis()
        if redis is None:
            pytest.skip("Redis is not available")
            
        llm = agent._get_llm()
        model_name = getattr(llm, "model", getattr(llm, "model_name", "unknown"))
        cache_key = agent._llm_cache_key(messages, model_name)
        await redis.delete(cache_key)
        
        # 1st Call (Cache Miss)
        content_1 = await agent._call_llm(messages)
        assert content_1 is not None
        
        # Verify it was written to Redis
        exists = await redis.exists(cache_key)
        assert bool(exists) is True
        
        # Modify the Redis value directly to verify cache hit returns the cached value
        cached_val = {"content": "This is cached content!"}
        await redis.set(cache_key, json.dumps(cached_val))
        
        # 2nd Call (Cache Hit)
        content_2 = await agent._call_llm(messages)
        assert content_2 == "This is cached content!"
        
        # Cleanup
        await redis.delete(cache_key)
        
    finally:
        settings.enable_llm_cache = original_cache_enabled
