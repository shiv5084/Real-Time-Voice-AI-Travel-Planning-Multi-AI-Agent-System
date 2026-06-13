"""Skyscanner MCP Client — flight search.

Supported tools:
  - search_flight: Search for available flights using Skyscanner API
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.mcp_clients.base import BaseMCPClient
from app.mcp_clients.schemas import get_arg_schema, get_response_schema

_SCHEMA_FILE = "skyscanner_schemas.json"


class SkyscannerMCPClient(BaseMCPClient):
    """MCP Client for Skyscanner flight search.

    Calls the external MCP server's /search_flight endpoint.
    URL is read from MCP_SERVER_URL environment variable — never hardcoded.
    """

    @property
    def client_name(self) -> str:
        return "skyscanner"

    @property
    def base_path(self) -> str:
        return "/skyscanner"

    @property
    def rate_limit_per_minute(self) -> int:
        return get_settings().mcp_rate_limit_skyscanner

    def arg_schema(self, tool_name: str) -> dict[str, Any]:
        return get_arg_schema(_SCHEMA_FILE, tool_name)

    def response_schema(self, tool_name: str) -> dict[str, Any]:
        return get_response_schema(_SCHEMA_FILE, tool_name)

    def cache_ttl(self, tool_name: str) -> int:
        return get_settings().cache_ttl_flights  # 1h

    def supports_batching(self, tool_name: str) -> bool:
        # Flight search doesn't support batching (each search is unique)
        return False

    # ------------------------------------------------------------------
    # Convenience typed wrappers (used by Flight Agent)
    # ------------------------------------------------------------------

    async def search_flight(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        adults: int = 1,
        cabin_class: str = "economy",
        *,
        agent: str = "flight_agent",
    ) -> dict[str, Any]:
        """Search for available flights using Skyscanner.
        
        Matches the MCP server's search_flight function signature.
        """
        args: dict[str, Any] = {
            "origin": origin.upper(),
            "destination": destination.upper(),
            "departure_date": departure_date,
            "adults": adults,
            "cabin_class": cabin_class,
        }
        if return_date:
            args["return_date"] = return_date
        return await self.call("search_flight", args, agent=agent)
