"""Graph node wrapper functions — each wraps an agent as a LangGraph node.

Phase 4: Added ``memory_preload_node`` which loads episodic context before
the Planner runs, enabling destination-aware personalisation.
"""

from __future__ import annotations

from app.config import get_settings
from app.graph.state import TravelPlanState


async def memory_preload_node(state: TravelPlanState) -> dict:
    """Pre-load episodic memory context for the destination(s).

    This node runs before the Planner on the first pass only (regen_count == 0).
    It fetches destination-specific memories and stores them in state so the
    Planner can build a personalised brief without adding latency to agent runs.
    """
    regen_count = state.get("regeneration_count", 0)
    user_id = state.get("user_id", "anonymous")

    # Skip memory preload on re-planning passes to avoid redundant DB calls
    if regen_count > 0 or user_id == "anonymous":
        return {}

    # We don't know destinations yet (Planner hasn't run), so we do a
    # light general-pattern fetch only. Destination-specific fetch happens
    # in Planner after it has extracted destinations from the raw request.
    try:
        from app.memory.episodic import get_all_memories
        memories = await get_all_memories(user_id, limit=5)
        if memories:
            general_patterns = [m.get("summary", "")[:150] for m in memories if m.get("summary")]
            return {
                "episodic_context": {
                    "repeat_destinations": [],
                    "destination_memories": {},
                    "general_patterns": general_patterns[:5],
                }
            }
    except Exception:
        pass  # Memory preload failure is non-fatal

    return {}


async def planner_node(state: TravelPlanState) -> TravelPlanState:
    """Planner Agent node — parses request, extracts constraints, applies memory."""
    from app.agents.planner import PlannerAgent
    agent = PlannerAgent(settings=get_settings())
    return await agent.run(state)


async def flight_node(state: TravelPlanState) -> TravelPlanState:
    """Flight Agent node — searches and filters flights."""
    from app.agents.flight import FlightAgent
    agent = FlightAgent(settings=get_settings())
    return await agent.run(state)


async def hotel_node(state: TravelPlanState) -> TravelPlanState:
    """Hotel Agent node — searches and filters hotels."""
    from app.agents.hotel import HotelAgent
    agent = HotelAgent(settings=get_settings())
    return await agent.run(state)


async def attraction_node(state: TravelPlanState) -> TravelPlanState:
    """Attraction Agent node — discovers POIs and validates via geocoding."""
    # Early exit check
    from app.graph.edges import should_early_exit
    if should_early_exit(state) == "skip_optional":
        # Skip this worker - return state unchanged
        return state
    
    from app.agents.attraction import AttractionAgent
    agent = AttractionAgent(settings=get_settings())
    return await agent.run(state)


async def transport_node(state: TravelPlanState) -> TravelPlanState:
    """Transport Agent node — calculates routes between key locations."""
    # Early exit check
    from app.graph.edges import should_early_exit
    if should_early_exit(state) == "skip_optional":
        # Skip this worker - return state unchanged
        return state
    
    from app.agents.transport import TransportAgent
    agent = TransportAgent(settings=get_settings())
    return await agent.run(state)


async def budget_node(state: TravelPlanState) -> TravelPlanState:
    """Budget Agent node — aggregates costs and checks compliance."""
    from app.agents.budget import BudgetAgent
    agent = BudgetAgent(settings=get_settings())
    return await agent.run(state)


async def composer_node(state: TravelPlanState) -> TravelPlanState:
    """Composer Agent node — builds the day-by-day itinerary."""
    from app.agents.composer import ComposerAgent
    agent = ComposerAgent(settings=get_settings())
    return await agent.run(state)


async def validator_node(state: TravelPlanState) -> TravelPlanState:
    """Validator Agent node — quality checks and conflict detection."""
    from app.agents.validator import ValidatorAgent
    agent = ValidatorAgent(settings=get_settings())
    return await agent.run(state)
