"""Maps MCP Client — geocoding and routing.

Supported tools:
  - google_maps_geocode: Forward geocoding (address → lat/lng)
  - google_maps_directions: Route calculation and travel-time estimation
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.mcp_clients.base import BaseMCPClient
from app.mcp_clients.schemas import get_arg_schema, get_response_schema

_SCHEMA_FILE = "maps_schemas.json"


class MapsMCPClient(BaseMCPClient):
    """MCP Client for Maps geocoding and routing.

    Calls the external MCP server's /maps endpoint.
    URL is read from MCP_SERVER_URL environment variable — never hardcoded.
    """

    @property
    def client_name(self) -> str:
        return "maps"

    @property
    def base_path(self) -> str:
        return "/maps"

    @property
    def rate_limit_per_minute(self) -> int:
        return get_settings().mcp_rate_limit_graphhopper

    def arg_schema(self, tool_name: str) -> dict[str, Any]:
        return get_arg_schema(_SCHEMA_FILE, tool_name)

    def response_schema(self, tool_name: str) -> dict[str, Any]:
        return get_response_schema(_SCHEMA_FILE, tool_name)

    def cache_ttl(self, tool_name: str) -> int:
        settings = get_settings()
        if tool_name == "google_maps_geocode":
            return settings.cache_ttl_geocoding  # 7 days
        return settings.cache_ttl_routes  # 24h

    def supports_batching(self, tool_name: str) -> bool:
        # Geocoding supports batching (multiple locations at once)
        return tool_name == "google_maps_geocode"

    # ------------------------------------------------------------------
    # Convenience typed wrappers
    # ------------------------------------------------------------------

    async def google_maps_geocode(
        self,
        address: str,
        *,
        agent: str = "attraction_agent",
    ) -> dict[str, Any]:
        """Geocode an address to coordinates.
        
        Matches the MCP server's google_maps_geocode function signature.
        """
        return await self.call(
            "google_maps_geocode",
            {"address": address},
            agent=agent,
        )

    async def google_maps_directions(
        self,
        origin: str,
        destination: str,
        *,
        mode: str = "driving",
        agent: str = "transport_agent",
    ) -> dict[str, Any]:
        """Get directions, distance, and travel time.
        
        Matches the MCP server's google_maps_directions function signature.
        """
        return await self.call(
            "google_maps_directions",
            {
                "origin": origin,
                "destination": destination,
                "mode": mode,
            },
            agent=agent,
        )
