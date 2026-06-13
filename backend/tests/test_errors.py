"""Custom exception hierarchy tests."""

import pytest

from app.utils.errors import AgentError, ToolError, TravelPlanningError, ValidationError


def test_travel_planning_error_to_dict():
    exc = TravelPlanningError("something failed", code="custom", details={"x": 1})
    data = exc.to_dict()
    assert data["error"] == "custom"
    assert data["message"] == "something failed"
    assert data["details"]["x"] == 1


def test_validation_error_includes_field():
    exc = ValidationError("bad date", field="start_date")
    assert exc.code == "validation_error"
    assert exc.details["field"] == "start_date"


def test_agent_error_includes_agent():
    exc = AgentError("planner failed", agent="planner")
    assert exc.code == "agent_error"
    assert exc.details["agent"] == "planner"


def test_tool_error_includes_tool():
    exc = ToolError("mcp timeout", tool="tavily_search")
    assert exc.code == "tool_error"
    assert exc.details["tool"] == "tavily_search"


def test_errors_are_catchable_as_base():
    with pytest.raises(TravelPlanningError):
        raise ValidationError("invalid")
