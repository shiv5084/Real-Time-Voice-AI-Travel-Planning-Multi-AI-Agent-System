"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["local", "staging", "production"]


def _find_env_file() -> str:
    """Walk up from the current file to find the nearest .env file.

    Search order (stops at first match):
      1. backend/.env          (next to app/)
      2. project root .env     (one level above backend/)
    Falls back to ".env" so pydantic-settings uses its own default behaviour.
    """
    here = Path(__file__).resolve().parent  # app/
    candidates = [
        here.parent / ".env",          # backend/.env
        here.parent.parent / ".env",   # project-root/.env
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return ".env"  # let pydantic-settings handle the miss gracefully


class Settings(BaseSettings):
    """Environment-aware configuration (local Docker vs managed cloud)."""

    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: AppEnv = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Local development (Docker Compose)
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")

    # Production / staging (managed services — Phase 7+)
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_anon_key: str | None = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_KEY")
    supabase_db_password: str | None = Field(default=None, alias="SUPABASE_DB_PASSWORD")
    upstash_redis_url: str | None = Field(default=None, alias="UPSTASH_REDIS_URL")
    upstash_redis_token: str | None = Field(default=None, alias="UPSTASH_REDIS_TOKEN")

    cors_origins: str | list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://localhost:3002",
            "http://127.0.0.1:3002",
        ],
        alias="CORS_ORIGINS",
    )

    # Phase 2 — MCP Server URL (external, configurable)
    mcp_server_url: str = Field(
        default="https://multi-mcp-servers.onrender.com",
        alias="MCP_SERVER_URL",
    )

    # Phase 2 — MCP Client rate limits (requests per minute)
    mcp_rate_limit_aviationstack: int = Field(default=60, alias="MCP_RATE_LIMIT_AVIATIONSTACK")
    mcp_rate_limit_skyscanner: int = Field(default=60, alias="MCP_RATE_LIMIT_SKYSCANNER")
    mcp_rate_limit_tavily: int = Field(default=100, alias="MCP_RATE_LIMIT_TAVILY")
    mcp_rate_limit_maps: int = Field(default=120, alias="MCP_RATE_LIMIT_MAPS")
    mcp_rate_limit_graphhopper: int = Field(default=120, alias="MCP_RATE_LIMIT_GRAPHHOPPER")
    mcp_rate_limit_gmail: int = Field(default=30, alias="MCP_RATE_LIMIT_GMAIL")

    # Phase 2 — Cache TTL (seconds)
    cache_ttl_flights: int = Field(default=3600, alias="CACHE_TTL_FLIGHTS")  # 1 hour
    cache_ttl_hotels: int = Field(default=3600, alias="CACHE_TTL_HOTELS")  # 1 hour
    cache_ttl_attractions: int = Field(default=86400, alias="CACHE_TTL_ATTRACTIONS")  # 24 hours
    cache_ttl_geocoding: int = Field(default=604800, alias="CACHE_TTL_GEOCODING")  # 7 days
    cache_ttl_routes: int = Field(default=86400, alias="CACHE_TTL_ROUTES")  # 24 hours

    # Phase 3 — LLM API keys
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")

    # Phase 4 — Memory & Personalization
    mem0_api_key: str | None = Field(default=None, alias="MEM0_API_KEY")

    # Phase 5 — Voice Pipeline
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str | None = Field(
        default="cgSgspJ2msm6clMCkdW9", alias="ELEVENLABS_VOICE_ID"
    )
    # Gemini Native TTS fallback configuration
    gemini_tts_model: str = Field(default="models/gemini-2.5-flash-preview-tts", alias="GEMINI_TTS_MODEL")
    gemini_tts_voice: str = Field(default="Zephyr", alias="GEMINI_TTS_VOICE")
    # STT uses Groq Whisper API — reuses groq_api_key; no local model needed
    groq_whisper_model: str = Field(default="whisper-large-v3-turbo", alias="GROQ_WHISPER_MODEL")
    vad_aggressiveness: int = Field(default=2, alias="VAD_AGGRESSIVENESS")
    vad_sample_rate: int = Field(default=16000, alias="VAD_SAMPLE_RATE")

    # Phase 3 — Agent step limits
    agent_steps_planner: int = Field(default=5, alias="AGENT_STEPS_PLANNER")
    agent_steps_worker: int = Field(default=3, alias="AGENT_STEPS_WORKER")
    agent_steps_budget: int = Field(default=2, alias="AGENT_STEPS_BUDGET")
    agent_steps_composer: int = Field(default=3, alias="AGENT_STEPS_COMPOSER")
    agent_steps_validator: int = Field(default=2, alias="AGENT_STEPS_VALIDATOR")

    # Phase 3 — LLM model names (configurable)
    groq_model_large: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL_LARGE")
    groq_model_small: str = Field(default="llama-3.1-8b-instant", alias="GROQ_MODEL_SMALL")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    # Latency Optimization — Response Streaming
    enable_llm_streaming: bool = Field(default=True, alias="ENABLE_LLM_STREAMING")
    stream_chunk_size: int = Field(default=100, alias="STREAM_CHUNK_SIZE")

    # Latency Optimization — LLM Response Caching
    enable_llm_cache: bool = Field(default=True, alias="ENABLE_LLM_CACHE")
    llm_cache_ttl_short: int = Field(default=300, alias="LLM_CACHE_TTL_SHORT")  # 5 minutes
    llm_cache_ttl_medium: int = Field(default=1800, alias="LLM_CACHE_TTL_MEDIUM")  # 30 minutes
    llm_cache_ttl_long: int = Field(default=7200, alias="LLM_CACHE_TTL_LONG")  # 2 hours

    # Latency Optimization — Database
    db_pool_min_size: int = Field(default=5, alias="DB_POOL_MIN_SIZE")
    db_pool_max_size: int = Field(default=20, alias="DB_POOL_MAX_SIZE")

    # Latency Optimization — MCP Connection Pooling
    mcp_pool_connections: int = Field(default=10, alias="MCP_POOL_CONNECTIONS")
    mcp_pool_max_keepalive: int = Field(default=5, alias="MCP_POOL_MAX_KEEPALIVE")

    # Latency Optimization — Early Exit
    enable_early_exit: bool = Field(default=True, alias="ENABLE_EARLY_EXIT")
    early_exit_budget_threshold: float = Field(default=1.5, alias="EARLY_EXIT_BUDGET_THRESHOLD")

    # Latency Optimization — Request Batching
    enable_batching: bool = Field(default=True, alias="ENABLE_BATCHING")
    batch_size: int = Field(default=10, alias="BATCH_SIZE")
    batch_timeout_ms: int = Field(default=100, alias="BATCH_TIMEOUT_MS")

    # Cost Optimization — Cache Compression
    enable_cache_compression: bool = Field(default=True, alias="ENABLE_CACHE_COMPRESSION")
    cache_compression_min_size: int = Field(default=1024, alias="CACHE_COMPRESSION_MIN_SIZE")  # 1KB

    # Cost Optimization — Selective Caching
    enable_selective_caching: bool = Field(default=True, alias="ENABLE_SELECTIVE_CACHING")
    cache_max_size_bytes: int = Field(default=1048576, alias="CACHE_MAX_SIZE_BYTES")  # 1MB

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str] | None) -> list[str]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:3001",
                "http://127.0.0.1:3001",
                "http://localhost:3002",
                "http://127.0.0.1:3002",
            ]
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_env_profile(self) -> Settings:
        if self.app_env == "local":
            if not self.database_url:
                object.__setattr__(
                    self,
                    "database_url",
                    "postgresql://postgres:postgres@postgres:5432/travel_db",
                )
            if not self.redis_url:
                object.__setattr__(self, "redis_url", "redis://redis:6379/0")
        elif self.app_env in ("staging", "production"):
            missing = [
                name
                for name, value in (
                    ("SUPABASE_URL", self.supabase_url),
                    ("SUPABASE_ANON_KEY", self.supabase_anon_key),
                    ("UPSTASH_REDIS_URL", self.upstash_redis_url),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"{self.app_env} requires: {', '.join(missing)}"
                )
            # Construct database_url from Supabase URL and password
            if not self.database_url and self.supabase_url and self.supabase_db_password:
                # Extract project ID from Supabase URL
                # https://dqbhkfzfotvxruqcyhod.supabase.co -> dqbhkfzfotvxruqcyhod
                project_id = self.supabase_url.replace("https://", "").replace(".supabase.co", "")
                # URL-encode the password to handle special characters like @
                encoded_password = quote_plus(self.supabase_db_password)
                object.__setattr__(
                    self,
                    "database_url",
                    f"postgresql://postgres:{encoded_password}@db.{project_id}.supabase.co:5432/postgres",
                )
            # Construct redis_url from Upstash URL
            if not self.redis_url and self.upstash_redis_url:
                object.__setattr__(self, "redis_url", self.upstash_redis_url)
        return self

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
