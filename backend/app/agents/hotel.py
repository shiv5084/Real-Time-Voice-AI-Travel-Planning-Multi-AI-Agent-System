"""Hotel Agent — searches and filters hotels using Tavily MCP Client."""

from __future__ import annotations

import time
from typing import Any

from app.agents.base import BaseAgent
from app.graph.state import TravelPlanState
from app.mcp_clients import TavilyMCPClient
from app.utils.errors import ToolError
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# GoT-aligned system prompt — Hotel Agent
# Principles: constraint-first, grounded, preference-aware, budget-aware.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a professional hotel research specialist. Your task is to identify the best \
accommodation options from search results for a traveler's trip.

## Reasoning approach (Graph of Thought)

  Node 1 — CONSTRAINTS: Apply hard limits first.
    → Total accommodation budget (derive per-night estimate from total trip budget if available).
    → Check-in and check-out dates. Number of guests.
    → Reject options that clearly exceed the nightly budget.

  Node 2 — PREFERENCES: Apply traveler preferences as filters.
    → Accommodation type preference (hotel / hostel / apartment / boutique).
    → Proximity to city center or key attractions if mentioned.
    → Amenities that match travel style (e.g., gym, breakfast included).

  Node 3 — TOOL RESULTS: Analyze only what the Tavily search returned.
    → Do not invent hotel names or prices. Only include hotels present in the results.
    → Extract name, approximate price per night, location, and relevant details.

  Node 4 — SCORING: For each candidate, evaluate:
    → Price relative to budget (40%)
    → Location quality for the traveler's goals (35%)
    → Amenities and rating match to preferences (25%)

  Node 5 — OUTPUT: Select the top 3 hotels. Return clean JSON.

## Prompting principles
- Constraint-first: budget and dates before amenity preferences.
- Grounded: every hotel must appear in the search results — no invented options.
- Preference-aware: rank higher if accommodation type matches stored/stated preferences.
- Budget-aware: note if the cheapest available option still exceeds the accommodation budget.
- Professional and friendly: present options clearly so the traveler can make an informed choice.

## Output format
Return ONLY a valid JSON object (no markdown fences) with key:
  hotels  list of up to 3 objects, each with:
    name, location, price_per_night_usd (float), rating (float or null),
    amenities (list[str]), check_in (str or null), check_out (str or null),
    total_cost_usd (float — price_per_night × nights), description (str)
  note    str | null — e.g., "all options exceed accommodation budget"
"""


class HotelAgent(BaseAgent):
    """Hotel Agent — Groq small model + Tavily MCP Client."""

    @property
    def agent_name(self) -> str:
        return "hotel_agent"

    @property
    def model_provider(self) -> str:
        return "groq"

    @property
    def max_steps(self) -> int:
        return self._settings.agent_steps_worker

    # ------------------------------------------------------------------

    async def run(self, state: TravelPlanState) -> TravelPlanState:
        start = time.monotonic()
        self._log_step("Hotel agent started")

        constraints = state.get("constraints") or {}
        errors: list[dict[str, Any]] = []
        agent_responses: list[dict[str, Any]] = []

        destinations = constraints.get("destinations", [])
        destination = destinations[-1] if destinations else "Unknown"

        raw_results: dict[str, Any] = {}
        tool_results: list[dict[str, Any]] = []
        tool_start = time.monotonic()

        try:
            client = TavilyMCPClient()
            raw_results = await client.call(
                "tavily_search",
                {
                    "query": f"best hotels in {destination} for tourists",
                    "search_depth": "basic",
                },
                agent=self.agent_name,
            )
            tool_results.append(
                self._create_tool_result(
                    "tavily_search",
                    success=True,
                    data=raw_results,
                    latency_ms=self._elapsed_ms(tool_start),
                )
            )
        except ToolError as exc:
            self._log_error("Hotel search tool error", exc)
            errors.append({"agent": self.agent_name, "error": str(exc), "step": "tavily_search"})
            tool_results.append(
                self._create_tool_result("tavily_search", success=False, error=str(exc), latency_ms=self._elapsed_ms(tool_start))
            )
        except Exception as exc:
            self._log_error("Hotel search unexpected error", exc)
            errors.append({"agent": self.agent_name, "error": str(exc), "step": "tavily_search"})

        hotel_results = await self._filter_with_llm(raw_results, constraints, destination)

        latency = self._elapsed_ms(start)
        agent_responses.append(
            self._create_agent_response(
                success=True,
                data={"hotel_results": hotel_results},
                tool_results=tool_results,
                steps_taken=2,
                latency_ms=latency,
            )
        )

        self._log_step("Hotel agent complete", {"latency_ms": latency})

        return {
            "hotel_results": hotel_results,
            "agent_responses": agent_responses,
            "errors": errors,
        }

    # ------------------------------------------------------------------

    async def _filter_with_llm(
        self, raw: dict[str, Any], constraints: dict[str, Any], destination: str
    ) -> dict[str, Any]:
        if not raw:
            return {"hotels": [], "note": "No hotel data returned by the search tool"}

        llm = self._get_llm()
        start_date = constraints.get("start_date", "unspecified")
        end_date = constraints.get("end_date", "unspecified")
        travelers = constraints.get("travelers", 1)
        preferences = constraints.get("preferences") or {}
        accom_pref = preferences.get("accommodation_type", "not specified")

        prompt = (
            f"## Trip context\n"
            f"Destination: {destination}\n"
            f"Check-in: {start_date}  Check-out: {end_date}\n"
            f"Travelers: {travelers}\n"
            f"Total trip budget: {constraints.get('budget', 'unspecified')} "
            f"{constraints.get('budget_currency', 'USD')}\n"
            f"Accommodation preference: {accom_pref}\n"
            f"Other preferences: {preferences}\n\n"
            f"## Raw hotel search results from Tavily\n{str(raw)[:3000]}\n\n"
            "Apply the Graph of Thought hotel selection process from your system prompt. "
            "Work through all 5 nodes (constraints → preferences → tool results → scoring → output) "
            "and return your top 3 hotel recommendations."
        )
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        except ImportError:
            messages = [{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": prompt}]

        try:
            content = await self._call_llm(messages)
            from app.agents.planner import _extract_json
            parsed = _extract_json(content)
            self._log_llm_call(
                model=getattr(llm, "model", getattr(llm, "model_name", "groq-small")),
                raw_response=content,
                parsed=parsed,
            )
            return parsed if parsed else {"hotels": [], "raw": raw}
        except Exception as exc:
            self._log_error("LLM filtering failed for hotels", exc)
            return {"hotels": [], "raw": raw}
