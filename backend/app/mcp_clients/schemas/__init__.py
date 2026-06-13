"""Schema loader — reads JSON Schema files from this package directory."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SCHEMA_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def load_schemas(filename: str) -> dict[str, Any]:
    """Load and cache a JSON schema file by filename (e.g. 'aviationstack_schemas.json')."""
    path = _SCHEMA_DIR / filename
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def get_arg_schema(filename: str, tool_name: str) -> dict[str, Any]:
    """Return the argument schema for a specific tool."""
    schemas = load_schemas(filename)
    if tool_name not in schemas:
        raise ValueError(f"No schema found for tool '{tool_name}' in {filename}")
    return schemas[tool_name]["args"]


def get_response_schema(filename: str, tool_name: str) -> dict[str, Any]:
    """Return the response schema for a specific tool."""
    schemas = load_schemas(filename)
    if tool_name not in schemas:
        raise ValueError(f"No schema found for tool '{tool_name}' in {filename}")
    return schemas[tool_name]["response"]
