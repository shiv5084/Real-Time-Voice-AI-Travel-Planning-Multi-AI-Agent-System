"""Tavily Search MCP Client — general web search.

Supported tools:
  - tavily_search: General web search using Tavily API
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.mcp_clients.base import BaseMCPClient
from app.mcp_clients.schemas import get_arg_schema, get_response_schema

_SCHEMA_FILE = "tavily_schemas.json"


class TavilyMCPClient(BaseMCPClient):
    """MCP Client for Tavily web search.

    Calls the external MCP server's /tavily endpoint.
    URL is read from MCP_SERVER_URL environment variable — never hardcoded.
    """

    @property
    def client_name(self) -> str:
        return "tavily"

    @property
    def base_path(self) -> str:
        return "/tavily"

    @property
    def rate_limit_per_minute(self) -> int:
        return get_settings().mcp_rate_limit_tavily

    def arg_schema(self, tool_name: str) -> dict[str, Any]:
        return get_arg_schema(_SCHEMA_FILE, tool_name)

    def response_schema(self, tool_name: str) -> dict[str, Any]:
        return get_response_schema(_SCHEMA_FILE, tool_name)

    def cache_ttl(self, tool_name: str) -> int:
        return get_settings().cache_ttl_attractions  # 24h

    def supports_batching(self, tool_name: str) -> bool:
        # Web search doesn't support batching (each search is unique)
        return False

    # ------------------------------------------------------------------
    # Convenience typed wrappers
    # ------------------------------------------------------------------

    async def tavily_search(
        self,
        query: str,
        *,
        search_depth: str = "basic",
        agent: str = "planner_agent",
    ) -> dict[str, Any]:
        """General web search — used by Planner for destination research.
        
        Matches the MCP server's tavily_search function signature.
        """
        args: dict[str, Any] = {
            "query": query,
            "search_depth": search_depth,
        }
        return await self.call("tavily_search", args, agent=agent)
