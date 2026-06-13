"""Custom exception hierarchy for agents, tools, and validation."""

from __future__ import annotations

from typing import Any


class TravelPlanningError(Exception):
    """Base exception for the travel planning backend."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "travel_planning_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


class ValidationError(TravelPlanningError):
    """Raised when user or agent input fails validation."""

    def __init__(self, message: str, *, field: str | None = None, **kwargs: Any) -> None:
        details = kwargs.pop("details", {}) or {}
        if field:
            details["field"] = field
        super().__init__(message, code="validation_error", details=details, **kwargs)


class AgentError(TravelPlanningError):
    """Raised when an agent fails during orchestration."""

    def __init__(
        self,
        message: str,
        *,
        agent: str | None = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {}) or {}
        if agent:
            details["agent"] = agent
        super().__init__(message, code="agent_error", details=details, **kwargs)


class ToolError(TravelPlanningError):
    """Raised when an MCP tool call fails after middleware handling."""

    def __init__(
        self,
        message: str,
        *,
        tool: str | None = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {}) or {}
        if tool:
            details["tool"] = tool
        super().__init__(message, code="tool_error", details=details, **kwargs)
