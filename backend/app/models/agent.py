"""Agent-related Pydantic models."""

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Result from a tool/MCP client call."""

    tool_name: str
    success: bool
    data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    latency_ms: Optional[int] = None
    cache_hit: bool = False
    cost_usd: Optional[float] = None


class AgentError(BaseModel):
    """Error model for agent operations."""

    agent_name: str
    error_type: str
    message: str
    details: Optional[dict[str, Any]] = None
    retryable: bool = False


class AgentResponse(BaseModel):
    """Response from an agent execution."""

    agent_name: str
    success: bool
    data: Optional[dict[str, Any]] = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    errors: list[AgentError] = Field(default_factory=list)
    steps_taken: int = 0
    latency_ms: Optional[int] = None
    trace_id: Optional[str] = None
