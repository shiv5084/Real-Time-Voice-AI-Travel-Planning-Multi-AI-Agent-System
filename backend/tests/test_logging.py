"""Structured JSON logging tests."""

import json
import logging
from io import StringIO

from app.utils.logging import JsonFormatter, configure_logging
from app.utils.tracing import set_trace_id


def test_json_formatter_outputs_valid_json_with_trace_id():
    set_trace_id("trip_test123")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.json")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info("hello world")

    line = stream.getvalue().strip()
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello world"
    assert payload["trace_id"] == "trip_test123"
    assert "timestamp" in payload


def test_configure_logging_sets_json_handler():
    configure_logging("DEBUG")
    root = logging.getLogger()
    assert root.handlers
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
