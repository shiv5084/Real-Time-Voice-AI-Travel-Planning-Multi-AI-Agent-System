"""BaseMCPClient — 5-layer middleware stack for all external MCP server calls.

Middleware execution order (per phase-wise-implementationPlan.md §4.2):
  1. Schema Validation (pre-call args)
  2. Rate Limit Check (Redis counter)
  3. Cache Check (Redis — cache hit returns immediately)
  4. Request Batching (collect similar requests)
  5. External MCP Server Call + Error Handling & Retry
  6. Response Validation (post-call)
  7. Cache Write (on cache miss)
  8. Audit Log (PostgreSQL audit_log table)

Phase 7B: Request batching added for batchable operations.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any

import httpx
import jsonschema
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.utils.errors import ToolError, ValidationError
from app.utils.logging import get_logger
from app.utils.tracing import get_trace_id

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_transient(exc: BaseException) -> bool:
    """Return True for errors that warrant a retry (network, 5xx, 429)."""
    if isinstance(exc, ToolError):
        code = getattr(exc, "status_code", None)
        if code is not None:
            return code == 429 or code >= 500
        # Timeout / connection errors stored as ToolError with no status code
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    return False


# ---------------------------------------------------------------------------
# BaseMCPClient
# ---------------------------------------------------------------------------


class BaseMCPClient(ABC):
    """Abstract base class that enforces the 5-layer middleware stack.

    Subclasses must implement:
      - ``client_name``: unique snake_case identifier (e.g. "aviationstack")
      - ``base_path``: URL path prefix on the MCP server (e.g. "/aviationstack")
      - ``rate_limit_per_minute``: max requests per minute (from settings)
      - ``arg_schema(tool_name)``: JSON Schema dict for tool arguments
      - ``response_schema(tool_name)``: JSON Schema dict for tool response
      - ``cache_ttl(tool_name)``: Redis TTL in seconds for this tool's responses
    """

    # Maximum retry attempts for transient errors
    MAX_RETRIES: int = 3

    def __init__(self) -> None:
        self._settings = get_settings()
        self._http: httpx.AsyncClient | None = None
        # Batching queue: tool_name -> list of (request_id, arguments, future)
        self._batch_queue: defaultdict[str, list[tuple[str, dict[str, Any], asyncio.Future]]] = defaultdict(list)
        self._batch_lock = asyncio.Lock()
        self._batch_flush_task: asyncio.Task | None = None
        # Cache hit rate tracking
        self._cache_hits: int = 0
        self._cache_misses: int = 0

    # ------------------------------------------------------------------
    # Abstract interface — subclasses define these
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def client_name(self) -> str:
        """Unique snake_case name for this MCP client."""

    @property
    @abstractmethod
    def base_path(self) -> str:
        """URL path prefix on the MCP server, e.g. '/aviationstack'."""

    @property
    @abstractmethod
    def rate_limit_per_minute(self) -> int:
        """Maximum requests allowed per 60-second window."""

    @abstractmethod
    def arg_schema(self, tool_name: str) -> dict[str, Any]:
        """Return the JSON Schema for validating *arguments* of ``tool_name``."""

    @abstractmethod
    def response_schema(self, tool_name: str) -> dict[str, Any]:
        """Return the JSON Schema for validating the *response* of ``tool_name``."""

    @abstractmethod
    def cache_ttl(self, tool_name: str) -> int:
        """Return Redis TTL (seconds) for caching responses of ``tool_name``."""

    @abstractmethod
    def supports_batching(self, tool_name: str) -> bool:
        """Return True if the tool supports batched requests."""

    # ------------------------------------------------------------------
    # Request Batching (Latency Optimization)
    # ------------------------------------------------------------------

    async def _flush_batch(self, tool_name: str) -> None:
        """Flush the batch queue for a specific tool and execute batched requests."""
        async with self._batch_lock:
            if not self._batch_queue[tool_name]:
                return

            # Get all pending requests
            requests = self._batch_queue[tool_name].copy()
            self._batch_queue[tool_name].clear()

        if not requests:
            return

        try:
            # Execute batched requests
            batch_results = await self._execute_batch(tool_name, [r[1] for r in requests])

            # Resolve futures with results
            for (request_id, _, future), result in zip(requests, batch_results):
                if not future.done():
                    future.set_result(result)

        except Exception as exc:
            # Reject all futures on error
            for _, _, future in requests:
                if not future.done():
                    future.set_exception(exc)

    async def _execute_batch(self, tool_name: str, arguments_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute a batch of requests. Override in subclasses for custom batch logic."""
        # Default implementation: execute requests in parallel concurrently
        results = await asyncio.gather(*[
            self._call_without_batching(tool_name, args)
            for args in arguments_list
        ])
        return list(results)

    async def _call_without_batching(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a single request without batching (bypasses batching logic)."""
        return await self._call_impl(tool_name, arguments)

    # ------------------------------------------------------------------
    # Public entry point — enforces the full middleware stack
    # ------------------------------------------------------------------

    async def call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        agent: str = "unknown",
        skip_cache: bool = False,
        skip_batch: bool = False,
    ) -> dict[str, Any]:
        """Execute a tool call through the full 5-layer middleware stack.

        Args:
            tool_name: The tool to invoke on the MCP server.
            arguments: Key-value arguments for the tool.
            agent: Name of the calling agent (used in audit log).
            skip_cache: If True, bypass cache read (but still writes on miss).
            skip_batch: If True, bypass batching logic.

        Returns:
            The validated tool response as a dict.

        Raises:
            ValidationError: If arguments or response fail schema validation.
            ToolError: If the external call fails after all retries.
        """
        # Check if batching is enabled and supported for this tool
        if (
            self._settings.enable_batching
            and not skip_batch
            and self.supports_batching(tool_name)
        ):
            return await self._call_with_batching(tool_name, arguments, agent=agent, skip_cache=skip_cache)

        return await self._call_impl(tool_name, arguments, agent=agent, skip_cache=skip_cache)

    async def _call_with_batching(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        agent: str = "unknown",
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        """Execute a tool call with batching."""
        import uuid
        request_id = str(uuid.uuid4())
        future = asyncio.Future()

        # Add to batch queue
        async with self._batch_lock:
            self._batch_queue[tool_name].append((request_id, arguments, future))

            # Check if we should flush immediately
            should_flush = len(self._batch_queue[tool_name]) >= self._settings.batch_size

            # Start timeout task if not already running
            if self._batch_flush_task is None or self._batch_flush_task.done():
                self._batch_flush_task = asyncio.create_task(self._batch_flush_timeout(tool_name))

        if should_flush:
            await self._flush_batch(tool_name)

        # Wait for result
        result = await future

        # Audit log for batched call
        trace_id = get_trace_id()
        await self._audit_log(
            trace_id=trace_id,
            agent=agent,
            tool=tool_name,
            arguments=arguments,
            result=result,
            latency_ms=0,  # Latency is tracked at batch level
            cache_hit=False,  # Cache is checked before batching
        )

        return result

    async def _batch_flush_timeout(self, tool_name: str) -> None:
        """Flush batch after timeout."""
        await asyncio.sleep(self._settings.batch_timeout_ms / 1000)
        await self._flush_batch(tool_name)

    async def _call_impl(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        agent: str = "unknown",
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        """Implementation of the full middleware stack without batching."""
        start_ts = time.monotonic()
        trace_id = get_trace_id()
        cache_hit = False
        result: dict[str, Any] | None = None

        try:
            # ── Layer 1: Argument schema validation ──────────────────────
            self._validate_args(tool_name, arguments)

            # ── Layer 2: Rate limit check ─────────────────────────────────
            await self._check_rate_limit()

            # ── Layer 3: Cache check ──────────────────────────────────────
            cache_key = self._cache_key(tool_name, arguments)
            if not skip_cache:
                cached = await self._cache_get(cache_key)
                if cached is not None:
                    cache_hit = True
                    result = cached

            # ── Layer 4: External call + retry ───────────────────────────
            if result is None:
                result = await self._call_with_retry(tool_name, arguments)

            # ── Layer 5: Response schema validation ───────────────────────
            self._validate_response(tool_name, result)

            # ── Layer 6: Cache write (only on cache miss) ─────────────────
            if not cache_hit:
                await self._cache_set(cache_key, result, self.cache_ttl(tool_name))

            return result

        finally:
            # ── Layer 7: Audit log ────────────────────────────────────────
            latency_ms = int((time.monotonic() - start_ts) * 1000)
            await self._audit_log(
                trace_id=trace_id,
                agent=agent,
                tool=tool_name,
                arguments=arguments,
                result=result,
                latency_ms=latency_ms,
                cache_hit=cache_hit,
            )

    # ------------------------------------------------------------------
    # Layer 1 — Schema validation
    # ------------------------------------------------------------------

    def _validate_args(self, tool_name: str, arguments: dict[str, Any]) -> None:
        schema = self.arg_schema(tool_name)
        try:
            jsonschema.validate(instance=arguments, schema=schema)
        except jsonschema.ValidationError as exc:
            raise ValidationError(
                f"[{self.client_name}:{tool_name}] Invalid arguments: {exc.message}",
                field=exc.json_path,
            ) from exc

    def _validate_response(self, tool_name: str, response: dict[str, Any]) -> None:
        schema = self.response_schema(tool_name)
        try:
            jsonschema.validate(instance=response, schema=schema)
        except jsonschema.ValidationError as exc:
            raise ValidationError(
                f"[{self.client_name}:{tool_name}] Malformed response: {exc.message}",
                field=exc.json_path,
            ) from exc

    # ------------------------------------------------------------------
    # Layer 2 — Rate limiting (Redis sliding window)
    # ------------------------------------------------------------------

    async def _check_rate_limit(self) -> None:
        """Increment Redis counter and raise ToolError if limit exceeded."""
        from app.memory.session import get_redis  # lazy import to avoid circular deps

        redis = await get_redis()
        if redis is None:
            # Redis unavailable — skip rate limiting but log warning
            logger.warning(
                "Rate limiting skipped — Redis unavailable",
                extra={"event": {"client": self.client_name}},
            )
            return

        key = f"ratelimit:{self.client_name}:rpm"
        try:
            # Use a 60-second sliding window with atomic increment
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, 60)
            count, _ = await pipe.execute()

            if count > self.rate_limit_per_minute:
                raise ToolError(
                    f"Rate limit exceeded for {self.client_name} "
                    f"({count}/{self.rate_limit_per_minute} rpm)",
                    tool=self.client_name,
                )
        except ToolError:
            raise
        except Exception as exc:  # Redis error — degrade gracefully
            logger.warning(
                "Rate limit check failed",
                extra={"event": {"client": self.client_name, "error": str(exc)}},
            )

    # ------------------------------------------------------------------
    # Layer 3 & 6 — Response caching (Redis)
    # ------------------------------------------------------------------

    def _cache_key(self, tool_name: str, arguments: dict[str, Any]) -> str:
        payload = json.dumps({"tool": tool_name, "args": arguments}, sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return f"mcp_cache:{self.client_name}:{tool_name}:{digest}"

    async def _cache_get(self, key: str) -> dict[str, Any] | None:
        from app.memory.session import get_redis

        redis = await get_redis()
        if redis is None:
            self._cache_misses += 1
            return None
        try:
            raw = await redis.get(key)
            if raw:
                # Decompress if compression is enabled
                if self._settings.enable_cache_compression:
                    import gzip
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        # If decompression fails, assume data wasn't compressed
                        pass
                self._cache_hits += 1
                return json.loads(raw)
            self._cache_misses += 1
        except Exception as exc:
            logger.warning(
                "Cache get failed",
                extra={"event": {"key": key, "error": str(exc)}},
            )
            self._cache_misses += 1
        return None

    async def _cache_set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        from app.memory.session import get_redis

        redis = await get_redis()
        if redis is None:
            return

        # Selective caching: skip if data is too large
        if self._settings.enable_selective_caching:
            json_str = json.dumps(value)
            if len(json_str.encode()) > self._settings.cache_max_size_bytes:
                logger.info(
                    "Skipping cache for large data",
                    extra={"event": {"key": key, "size_bytes": len(json_str.encode())}},
                )
                return

        try:
            data = json.dumps(value)
            # Compress if enabled and data is large enough
            if self._settings.enable_cache_compression:
                data_bytes = data.encode()
                if len(data_bytes) >= self._settings.cache_compression_min_size:
                    import gzip
                    data = gzip.compress(data_bytes)
            await redis.setex(key, ttl, data)
        except Exception as exc:
            logger.warning(
                "Cache set failed",
                extra={"event": {"key": key, "error": str(exc)}},
            )

    def get_cache_hit_rate(self) -> float:
        """Return the cache hit rate as a percentage."""
        total = self._cache_hits + self._cache_misses
        if total == 0:
            return 0.0
        return (self._cache_hits / total) * 100

    # ------------------------------------------------------------------
    # Layer 4 — External call with retry (tenacity)
    # ------------------------------------------------------------------

    async def _call_with_retry(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Call the external MCP server with exponential-backoff retry."""

        attempt_count = 0

        @retry(
            retry=retry_if_exception(_is_transient),
            stop=stop_after_attempt(self.MAX_RETRIES),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
            reraise=True,
        )
        async def _attempt() -> dict[str, Any]:
            nonlocal attempt_count
            attempt_count += 1
            return await self._http_call(tool_name, arguments)

        try:
            return await _attempt()
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(
                f"[{self.client_name}:{tool_name}] Call failed after "
                f"{self.MAX_RETRIES} attempts: {exc}",
                tool=f"{self.client_name}:{tool_name}",
            ) from exc

    async def _http_call(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Make the actual HTTP POST to the external MCP server.

        The MCP server exposes direct tool endpoints:
          POST {MCP_SERVER_URL}/{tool_name}
          Body: {arguments}
          Response: {...}
        """
        client = await self._get_http_client()
        url = f"{self._settings.mcp_server_url.rstrip('/')}/{tool_name}"

        try:
            response = await client.post(
                url,
                json=arguments,
                timeout=30.0,
            )
        except httpx.TimeoutException as exc:
            raise ToolError(
                f"[{self.client_name}:{tool_name}] Request timed out",
                tool=f"{self.client_name}:{tool_name}",
            ) from exc
        except httpx.ConnectError as exc:
            raise ToolError(
                f"[{self.client_name}:{tool_name}] Connection failed to MCP server",
                tool=f"{self.client_name}:{tool_name}",
            ) from exc

        # Attach status code for _is_transient() to inspect
        if response.status_code == 429:
            err = ToolError(
                f"[{self.client_name}:{tool_name}] MCP server rate limited (429)",
                tool=f"{self.client_name}:{tool_name}",
            )
            err.status_code = 429  # type: ignore[attr-defined]
            raise err

        if response.status_code >= 500:
            err = ToolError(
                f"[{self.client_name}:{tool_name}] MCP server error ({response.status_code})",
                tool=f"{self.client_name}:{tool_name}",
            )
            err.status_code = response.status_code  # type: ignore[attr-defined]
            raise err

        if response.status_code >= 400:
            err = ToolError(
                f"[{self.client_name}:{tool_name}] Client error ({response.status_code}): "
                f"{response.text[:200]}",
                tool=f"{self.client_name}:{tool_name}",
            )
            err.status_code = response.status_code  # type: ignore[attr-defined]
            raise err

        body = response.json()

        # Check for error status in response
        if body.get("status") == "error":
            raise ToolError(
                f"[{self.client_name}:{tool_name}] MCP error: {body.get('message', 'Unknown error')}",
                tool=f"{self.client_name}:{tool_name}",
            )

        return body

    # ------------------------------------------------------------------
    # Layer 7 — Audit logging (PostgreSQL)
    # ------------------------------------------------------------------

    async def _audit_log(
        self,
        *,
        trace_id: str,
        agent: str,
        tool: str,
        arguments: dict[str, Any],
        result: dict[str, Any] | None,
        latency_ms: int,
        cache_hit: bool,
    ) -> None:
        """Insert a record into the ``audit_log`` PostgreSQL table.

        Failures are swallowed — audit logging must never crash a tool call.
        """
        try:
            from app.services.database import insert_audit_log

            await insert_audit_log(
                trace_id=trace_id,
                trip_id=None,
                agent=agent,
                model=None,
                tool=tool,
                client=self.client_name,
                arguments=arguments,
                result=result,
                latency_ms=latency_ms,
                cost_usd=0.0,  # cost_usd — Phase 3+ will calculate this
                cache_hit=cache_hit,
            )
        except Exception as exc:
            logger.warning(
                "Audit log write failed",
                extra={
                    "event": {
                        "trace_id": trace_id,
                        "tool": tool,
                        "error": str(exc),
                    }
                },
            )

    # ------------------------------------------------------------------
    # HTTP client lifecycle
    # ------------------------------------------------------------------

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            # Connection pooling for better performance
            limits = httpx.Limits(
                max_connections=self._settings.mcp_pool_connections,
                max_keepalive_connections=self._settings.mcp_pool_max_keepalive,
            )
            self._http = httpx.AsyncClient(
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"TravelPlanningBot/{self.client_name}",
                },
                follow_redirects=True,
                limits=limits,
                timeout=30.0,
            )
        return self._http

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    async def __aenter__(self) -> "BaseMCPClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()
