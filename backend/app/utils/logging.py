"""Structured JSON logging with trace ID support."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.utils.tracing import get_trace_id


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        trace_id = get_trace_id()
        if trace_id:
            payload["trace_id"] = trace_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key in ("event", "extra"):
            if hasattr(record, key):
                value = getattr(record, key)
                if isinstance(value, dict):
                    payload.update(value)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger for structured JSON output."""
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (call configure_logging once at startup)."""
    return logging.getLogger(name)
