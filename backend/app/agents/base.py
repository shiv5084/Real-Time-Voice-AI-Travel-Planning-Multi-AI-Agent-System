"""BaseAgent — shared behaviour, model selection, step limits, error handling, logging."""

from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any
import asyncio

from app.config import Settings, get_settings
from app.utils.logging import get_logger
from app.utils.tracing import get_trace_id

if TYPE_CHECKING:
    from app.graph.state import TravelPlanState

logger = get_logger(__name__)


def _safe_print(text: str, end: str = "\n", flush: bool = False) -> None:
    """Print text safely to sys.stdout on Windows, avoiding UnicodeEncodeError."""
    import sys
    try:
        sys.stdout.write(text + end)
        if flush:
            sys.stdout.flush()
    except UnicodeEncodeError:
        safe_text = text.encode('ascii', errors='replace').decode('ascii')
        try:
            sys.stdout.write(safe_text + end)
            if flush:
                sys.stdout.flush()
        except Exception:
            pass



class BaseAgent(ABC):
    """Abstract base class for all travel planning agents.

    Subclasses must define:
    - ``agent_name``  — unique identifier string
    - ``model_provider`` — "groq" or "gemini"
    - ``max_steps`` — maximum reasoning steps allowed
    - ``run(state)`` — the agent's main execution logic
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._llm: Any | None = None  # lazy-initialised on first use

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Unique snake_case name for this agent."""

    @property
    @abstractmethod
    def model_provider(self) -> str:
        """LLM provider — 'groq' or 'gemini'."""

    @property
    @abstractmethod
    def max_steps(self) -> int:
        """Maximum reasoning / tool-call steps this agent may take."""

    @abstractmethod
    async def run(self, state: "TravelPlanState") -> "TravelPlanState":
        """Execute the agent and return the updated state."""

    # ------------------------------------------------------------------
    # LLM factory
    # ------------------------------------------------------------------

    def _create_llm_instance(self, provider: str, model_name: str) -> Any:
        """Helper to create a ChatGroq or ChatGoogleGenerativeAI instance."""
        if provider == "groq":
            from langchain_groq import ChatGroq
            return ChatGroq(
                api_key=self._settings.groq_api_key,
                model=model_name,
                temperature=0.1,
                max_tokens=4096,
                streaming=self._settings.enable_llm_streaming,
                max_retries=0,
            )
        else:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                google_api_key=self._settings.gemini_api_key,
                model=model_name,
                temperature=0.0,
                max_retries=0,
            )

    def _get_llm(self) -> Any:
        """Return a cached LLM instance, or a stub when the key is absent."""
        if self._llm is not None:
            return self._llm

        if self.model_provider == "groq":
            if not self._settings.groq_api_key:
                logger.warning(
                    "GROQ_API_KEY not set — using mock response",
                    extra={"event": {"agent": self.agent_name}},
                )
                self._llm = _MockLLM(self.agent_name)
                return self._llm
            try:
                # Planner and composer use the large model; other Groq agents use small
                use_large = any(
                    tag in self.agent_name
                    for tag in ("planner", "composer")
                )
                model_name = (
                    self._settings.groq_model_large
                    if use_large
                    else self._settings.groq_model_small
                )
                self._llm = self._create_llm_instance("groq", model_name)
            except ImportError:
                logger.warning(
                    "langchain_groq not installed — using mock LLM",
                    extra={"event": {"agent": self.agent_name}},
                )
                self._llm = _MockLLM(self.agent_name)

        else:  # gemini
            if not self._settings.gemini_api_key:
                logger.warning(
                    "GEMINI_API_KEY not set — using mock response",
                    extra={"event": {"agent": self.agent_name}},
                )
                self._llm = _MockLLM(self.agent_name)
                return self._llm
            try:
                self._llm = self._create_llm_instance("gemini", self._settings.gemini_model)
            except ImportError:
                logger.warning(
                    "langchain_google_genai not installed — using mock LLM",
                    extra={"event": {"agent": self.agent_name}},
                )
                self._llm = _MockLLM(self.agent_name)

        return self._llm

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log_step(self, message: str, extra: dict[str, Any] | None = None) -> None:
        """Structured log with agent name and current trace_id."""
        payload: dict[str, Any] = {
            "agent": self.agent_name,
            "trace_id": get_trace_id(),
        }
        if extra:
            payload.update(extra)
        logger.info(message, extra={"event": payload})

    def _log_llm_call(
        self,
        model: str,
        raw_response: str,
        parsed: dict[str, Any] | list | None = None,
    ) -> None:
        """Log the exact LLM request/response for debugging."""
        import json as _json
        payload: dict[str, Any] = {
            "agent": self.agent_name,
            "model": model,
            "raw_response_preview": raw_response[:500],
            "parsed_output": parsed,
        }
        logger.info(
            f"[LLM_RESPONSE] {self.agent_name} ← {model}",
            extra={"event": payload},
        )
        # Also print directly so it always shows in stdout even without log config
        _safe_print(
            f"\n{'='*60}\n"
            f"[LLM_RESPONSE] agent={self.agent_name}  model={model}\n"
            f"{'='*60}\n"
            f"{_json.dumps(parsed, indent=2, default=str) if parsed is not None else raw_response[:1000]}\n"
            f"{'='*60}"
        )

    def _log_error(self, message: str, exc: Exception | None = None) -> None:
        payload: dict[str, Any] = {
            "agent": self.agent_name,
            "trace_id": get_trace_id(),
        }
        if exc:
            payload["error"] = str(exc)
        logger.error(message, extra={"event": payload}, exc_info=exc is not None)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _create_tool_result(
        self,
        tool_name: str,
        success: bool,
        data: dict[str, Any] | None = None,
        error: str | None = None,
        latency_ms: int | None = None,
        cache_hit: bool = False,
    ) -> dict[str, Any]:
        """Return a ToolResult-compatible dict."""
        return {
            "tool_name": tool_name,
            "success": success,
            "data": data,
            "error": error,
            "latency_ms": latency_ms,
            "cache_hit": cache_hit,
        }

    def _create_agent_response(
        self,
        success: bool,
        data: dict[str, Any] | None = None,
        tool_results: list[dict[str, Any]] | None = None,
        errors: list[dict[str, Any]] | None = None,
        steps_taken: int = 0,
        latency_ms: int | None = None,
    ) -> dict[str, Any]:
        """Return an AgentResponse-compatible dict."""
        return {
            "agent_name": self.agent_name,
            "success": success,
            "data": data,
            "tool_results": tool_results or [],
            "errors": errors or [],
            "steps_taken": steps_taken,
            "latency_ms": latency_ms,
            "trace_id": get_trace_id(),
        }

    def _elapsed_ms(self, start: float) -> int:
        """Return milliseconds since ``start`` (from time.monotonic())."""
        return int((time.monotonic() - start) * 1000)

    # ------------------------------------------------------------------
    # LLM Response Caching (Latency Optimization)
    # ------------------------------------------------------------------

    def _llm_cache_key(self, messages: list[dict[str, Any]], model: str) -> str:
        """Generate a cache key for LLM responses based on messages and model."""
        model_str = str(model)
        payload = json.dumps({"messages": messages, "model": model_str}, sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return f"llm_cache:{self.agent_name}:{model}:{digest}"

    async def _llm_cache_get(self, cache_key: str) -> dict[str, Any] | None:
        """Retrieve cached LLM response from Redis."""
        if not self._settings.enable_llm_cache:
            return None

        try:
            from app.memory.session import get_redis
            redis = await get_redis()
            if redis is None:
                return None

            raw = await redis.get(cache_key)
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.warning(
                "LLM cache get failed",
                extra={"event": {"agent": self.agent_name, "error": str(exc)}},
            )
        return None

    async def _llm_cache_set(
        self,
        cache_key: str,
        response: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """Cache LLM response in Redis with TTL."""
        if not self._settings.enable_llm_cache:
            return

        try:
            from app.memory.session import get_redis
            redis = await get_redis()
            if redis is None:
                return

            # Use default TTL if not specified
            if ttl is None:
                ttl = self._settings.llm_cache_ttl_medium

            await redis.set(cache_key, json.dumps(response), ex=ttl)
        except Exception as exc:
            logger.warning(
                "LLM cache set failed",
                extra={"event": {"agent": self.agent_name, "error": str(exc)}},
            )

    def _get_llm_cache_ttl(self) -> int:
        """Determine appropriate cache TTL based on agent type."""
        # Planner and validator use short TTL (dynamic, context-dependent)
        if any(tag in self.agent_name for tag in ("planner", "validator")):
            return self._settings.llm_cache_ttl_short
        # Composer uses medium TTL (semi-dynamic)
        if "composer" in self.agent_name:
            return self._settings.llm_cache_ttl_medium
        # Workers use long TTL (mostly static data)
        return self._settings.llm_cache_ttl_long

    async def _call_llm(self, messages: Any) -> str:
        """Execute LLM call with caching and streaming support."""
        llm = self._get_llm()
        # Safe model name extraction avoiding MagicMock serialization issues
        model_name = "unknown"
        if hasattr(llm, "model") and isinstance(getattr(llm, "model"), str):
            model_name = getattr(llm, "model")
        elif hasattr(llm, "model_name") and isinstance(getattr(llm, "model_name"), str):
            model_name = getattr(llm, "model_name")

        # Serialize messages for cache key
        serializable_messages = []
        for msg in messages:
            if hasattr(msg, "content"):
                role = "user"
                name = msg.__class__.__name__
                if "System" in name:
                    role = "system"
                elif "AI" in name or "Assistant" in name:
                    role = "assistant"
                elif "Function" in name or "Tool" in name:
                    role = "tool"
                serializable_messages.append({"role": role, "content": msg.content})
            elif isinstance(msg, dict):
                serializable_messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                })
            else:
                serializable_messages.append({"role": "user", "content": str(msg)})

        # 1. Check cache first
        cache_key = self._llm_cache_key(serializable_messages, model_name)
        cached = await self._llm_cache_get(cache_key)
        if cached is not None:
            content = cached.get("content", "")
            self._log_step("LLM Cache Hit", {"model": model_name})
            return content

        # Helper to execute the actual call
        # Performance tuning: max_retries=2 (saves one full retry cycle vs 3),
        # per-attempt asyncio.timeout of 45s so slow calls fail fast (not wait full 60s),
        # retry sleep capped at 2s (not exponential 0/2/4s) to avoid wasting time.
        async def execute_call(active_llm: Any) -> str:
            # Safe model name extraction avoiding MagicMock serialization issues
            active_model = "unknown"
            if hasattr(active_llm, "model") and isinstance(getattr(active_llm, "model"), str):
                active_model = getattr(active_llm, "model")
            elif hasattr(active_llm, "model_name") and isinstance(getattr(active_llm, "model_name"), str):
                active_model = getattr(active_llm, "model_name")
            call_content = ""
            max_retries = 2  # reduced from 3 — saves one full retry cycle on failure
            per_attempt_timeout = 90  # 90s: generous for gemini-2.0-flash (3-15s typical);
            # worst case 2 retries × 90s = 180s, still under 300s frontend wall
            for attempt in range(1, max_retries + 1):
                try:
                    is_mock_llm = (
                        isinstance(active_llm, _MockLLM)
                        or hasattr(active_llm, "_mock_self")
                        or type(active_llm).__name__ in ("MagicMock", "AsyncMock", "Mock")
                    )
                    if self._settings.enable_llm_streaming and hasattr(active_llm, "astream") and not is_mock_llm:
                        self._log_step("LLM Call (Streaming Started)", {"model": active_model, "attempt": attempt})
                        _safe_print(f"\n--- streaming {self.agent_name} ({active_model}) attempt {attempt} ---", flush=True)
                        async with asyncio.timeout(per_attempt_timeout):
                            async for chunk in active_llm.astream(messages):
                                chunk_content = chunk.content if hasattr(chunk, "content") else str(chunk)
                                call_content += chunk_content
                                _safe_print(chunk_content, end="", flush=True)
                        _safe_print("\n--- streaming finished ---\n", flush=True)
                    else:
                        async with asyncio.timeout(per_attempt_timeout):
                            response = await active_llm.ainvoke(messages)
                        call_content = response.content if hasattr(response, "content") else str(response)
                    break  # success
                except Exception as exc:
                    self._log_error(f"LLM call attempt {attempt} failed.", exc)
                    
                    # Fast-fail on rate limit / quota errors
                    exc_type_name = type(exc).__name__
                    is_rate_limit = (
                        exc_type_name == "RateLimitError"
                        or "rate limit" in str(exc).lower()
                        or "resource_exhausted" in str(exc).lower()
                        or getattr(exc, "status_code", None) == 429
                    )
                    if is_rate_limit:
                        raise exc
                        
                    if attempt == max_retries:
                        raise
                    await asyncio.sleep(2)  # fixed 2s backoff (not exponential) — avoids 4s/8s stalls
            return call_content

        # 2. Cache miss - execute call with automatic fallback
        content = ""
        try:
            content = await execute_call(llm)
        except Exception as exc:
            fallback_success = False
            
            # Check if the error is a rate limit error
            exc_type_name = type(exc).__name__
            is_rate_limit = (
                exc_type_name == "RateLimitError"
                or "rate limit" in str(exc).lower()
                or "resource_exhausted" in str(exc).lower()
                or getattr(exc, "status_code", None) == 429
            )
            
            # Fallback 1: If Large Groq model failed, try Small Groq model
            # Skip if it is a rate limit error because both models share key limits
            if (
                not is_rate_limit
                and self.model_provider == "groq"
                and model_name == self._settings.groq_model_large
            ):
                self._log_error(
                    f"Primary Groq Large model ({model_name}) failed. "
                    f"Falling back to Groq Small model ({self._settings.groq_model_small})...",
                    exc
                )
                try:
                    fallback_llm = self._create_llm_instance("groq", self._settings.groq_model_small)
                    content = await execute_call(fallback_llm)
                    # Use fallback cache key
                    cache_key = self._llm_cache_key(serializable_messages, self._settings.groq_model_small)
                    fallback_success = True
                except Exception as fallback_exc:
                    self._log_error("Fallback to Groq Small model also failed.", fallback_exc)
                    exc = fallback_exc
            
            # Fallback 2: Try Gemini as a secondary/ultimate fallback if key exists
            if not fallback_success and self._settings.gemini_api_key and model_name != self._settings.gemini_model:
                self._log_error(
                    f"Model failed. Trying secondary fallback to Gemini ({self._settings.gemini_model})...",
                    exc
                )
                try:
                    fallback_llm = self._create_llm_instance("gemini", self._settings.gemini_model)
                    content = await execute_call(fallback_llm)
                    cache_key = self._llm_cache_key(serializable_messages, self._settings.gemini_model)
                    fallback_success = True
                except Exception as fallback_exc:
                    self._log_error("Fallback to Gemini failed.", fallback_exc)
                    raise fallback_exc
            
            if not fallback_success:
                raise exc

        # 3. Cache the new response
        ttl = self._get_llm_cache_ttl()
        await self._llm_cache_set(cache_key, {"content": content}, ttl=ttl)

        return content



# ---------------------------------------------------------------------------
# Stub LLM used when API keys are absent (tests & local dev without keys)
# ---------------------------------------------------------------------------

class _MockLLM:
    """Minimal LLM stub that returns deterministic mock responses."""

    def __init__(self, agent_name: str) -> None:
        self._agent_name = agent_name

    def invoke(self, messages: Any, **_kwargs: Any) -> "_MockMessage":  # noqa: ANN401
        return _MockMessage(
            content=f'{{"mock": true, "agent": "{self._agent_name}", "note": "API key not set"}}'
        )

    async def ainvoke(self, messages: Any, **_kwargs: Any) -> "_MockMessage":  # noqa: ANN401
        return _MockMessage(
            content=f'{{"mock": true, "agent": "{self._agent_name}", "note": "API key not set"}}'
        )


class _MockMessage:
    def __init__(self, content: str) -> None:
        self.content = content
