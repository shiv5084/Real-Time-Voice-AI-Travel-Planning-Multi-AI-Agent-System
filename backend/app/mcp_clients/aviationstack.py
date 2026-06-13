"""AviationStack MCP Client — flight search/status.

Supported tools:
  - get_flight_status: Get flight status and schedule information
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.mcp_clients.base import BaseMCPClient
from app.mcp_clients.schemas import get_arg_schema, get_response_schema

_SCHEMA_FILE = "aviationstack_schemas.json"


class AviationStackMCPClient(BaseMCPClient):
    """MCP Client for AviationStack flight data.

    Calls the external MCP server's /get_flight_status endpoint.
    URL is read from MCP_SERVER_URL environment variable — never hardcoded.
    """

    @property
    def client_name(self) -> str:
        return "aviationstack"

    @property
    def base_path(self) -> str:
        return "/aviationstack"

    @property
    def rate_limit_per_minute(self) -> int:
        return get_settings().mcp_rate_limit_aviationstack

    def arg_schema(self, tool_name: str) -> dict[str, Any]:
        return get_arg_schema(_SCHEMA_FILE, tool_name)

    def response_schema(self, tool_name: str) -> dict[str, Any]:
        return get_response_schema(_SCHEMA_FILE, tool_name)

    def cache_ttl(self, tool_name: str) -> int:
        return get_settings().cache_ttl_flights  # 1h

    def supports_batching(self, tool_name: str) -> bool:
        # Flight status doesn't support batching (each flight is unique)
        return False

    # ------------------------------------------------------------------
    # Convenience typed wrappers (used by Flight Agent in Phase 3)
    # ------------------------------------------------------------------

    async def get_flight_status(
        self,
        dep_iata: str,
        arr_iata: str,
        flight_date: str | None = None,
        *,
        agent: str = "flight_agent",
    ) -> dict[str, Any]:
        """Get flight status information.
        
        Matches the MCP server's get_flight_status function signature.
        """
        args: dict[str, Any] = {
            "dep_iata": dep_iata.upper(),
            "arr_iata": arr_iata.upper(),
        }
        if flight_date:
            args["flight_date"] = flight_date
        return await self.call("get_flight_status", args, agent=agent)
