"""MCP Client middleware layer — all external tool calls go through this package."""

from app.mcp_clients.aviationstack import AviationStackMCPClient
from app.mcp_clients.gmail import GmailMCPClient
from app.mcp_clients.maps import MapsMCPClient
from app.mcp_clients.tavily import TavilyMCPClient
from app.mcp_clients.skyscanner import SkyscannerMCPClient

__all__ = [
    "AviationStackMCPClient",
    "GmailMCPClient",
    "MapsMCPClient",
    "TavilyMCPClient",
    "SkyscannerMCPClient",
]
