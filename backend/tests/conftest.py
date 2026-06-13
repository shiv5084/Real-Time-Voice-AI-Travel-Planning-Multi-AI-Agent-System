"""Pytest configuration — ensure backend package is importable."""

import sys
from pathlib import Path
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Load .env file from project root
PROJECT_ROOT = BACKEND_ROOT.parent
ENV_FILE = PROJECT_ROOT / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


import pytest

@pytest.fixture(autouse=True)
async def reset_redis_client():
    """Reset the global Redis client before and after each test to avoid event loop sharing issues."""
    try:
        from app.services import redis_client
        # Close connection if it exists
        if redis_client._client is not None:
            try:
                await redis_client.close_redis()
            except Exception:
                pass
        redis_client._client = None
    except ImportError:
        pass
    
    yield
    
    try:
        from app.services import redis_client
        if redis_client._client is not None:
            try:
                await redis_client.close_redis()
            except Exception:
                pass
        redis_client._client = None
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def mock_env_keys(request, monkeypatch):
    """Automatically mock API keys and disable LLM cache/streaming for all unit tests."""
    path_str = str(getattr(request, "path", getattr(request, "fspath", "")))
    if "unit" in path_str.replace("\\", "/"):
        monkeypatch.setenv("GROQ_API_KEY", "")
        monkeypatch.setenv("GEMINI_API_KEY", "")
        monkeypatch.setenv("ENABLE_LLM_CACHE", "False")
        monkeypatch.setenv("ENABLE_LLM_STREAMING", "False")

