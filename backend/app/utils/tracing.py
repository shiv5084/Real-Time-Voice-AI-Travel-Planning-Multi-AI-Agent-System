"""Trace ID generation and request-scoped propagation."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def generate_trace_id(prefix: str = "trip") -> str:
    """Return a unique trace ID for correlating logs and audit entries."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def set_trace_id(trace_id: str) -> None:
    """Bind trace ID to the current async context."""
    _trace_id.set(trace_id)


def get_trace_id() -> str | None:
    """Return the trace ID for the current context, if set."""
    return _trace_id.get()
