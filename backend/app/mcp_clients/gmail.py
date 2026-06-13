"""Gmail MCP Client — email delivery.

Supported tools:
  - send_email: Send email directly via Gmail API or SMTP fallback
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.mcp_clients.base import BaseMCPClient
from app.mcp_clients.schemas import get_arg_schema, get_response_schema

_SCHEMA_FILE = "gmail_schemas.json"


class GmailMCPClient(BaseMCPClient):
    """MCP Client for Gmail email delivery.

    Calls the external MCP server's /send_email endpoint.
    URL is read from MCP_SERVER_URL environment variable — never hardcoded.
    """

    @property
    def client_name(self) -> str:
        return "gmail"

    @property
    def base_path(self) -> str:
        return "/gmail"

    @property
    def rate_limit_per_minute(self) -> int:
        return get_settings().mcp_rate_limit_gmail

    def arg_schema(self, tool_name: str) -> dict[str, Any]:
        return get_arg_schema(_SCHEMA_FILE, tool_name)

    def response_schema(self, tool_name: str) -> dict[str, Any]:
        return get_response_schema(_SCHEMA_FILE, tool_name)

    def cache_ttl(self, tool_name: str) -> int:
        # Email sends are never cached — they are side effects, not queries
        return 0

    def supports_batching(self, tool_name: str) -> bool:
        # Email sends don't support batching (each email is unique)
        return False

    async def _cache_get(self, key: str) -> dict[str, Any] | None:
        """Email sends are never cached — always skip cache read."""
        return None

    async def _cache_set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        """Email sends are never cached — skip cache write."""
        return

    # ------------------------------------------------------------------
    # Convenience typed wrappers
    # ------------------------------------------------------------------

    async def send_email_directly(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        agent: str = "composer_agent",
    ) -> dict[str, Any]:
        """Send email directly via Gmail API or SMTP fallback.

        Matches the MCP server's send_email function signature.
        """
        args: dict[str, Any] = {
            "to": to,
            "subject": subject,
            "body": body,
        }
        return await self.call("send_email", args, agent=agent, skip_cache=True)
