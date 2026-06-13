"""Flight Agent — searches and filters flights using Skyscanner MCP Client."""

from __future__ import annotations

import time
from typing import Any

from app.agents.base import BaseAgent
from app.config import Settings
from app.graph.state import TravelPlanState
from app.mcp_clients import SkyscannerMCPClient
from app.utils.errors import ToolError
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# GoT-aligned system prompt — Flight Agent
# Principles: constraint-first, tool-grounded, budget-aware, professional tone.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a professional flight research specialist. Your task is to select the best \
flight options from raw API results for a specific trip.

## Reasoning approach (Graph of Thought)

  Node 1 — CONSTRAINTS: Apply hard limits first.
    → Budget per person for flights (if provided). Departure date. Number of passengers.
    → Never recommend a flight that violates the budget or travel date.

  Node 2 — TOOL RESULTS: Analyze only what the Skyscanner API returned.
    → Do not invent flights. Every recommended flight must appear in the raw data.
    → If no results were returned, report that clearly.

  Node 3 — SCORING: For each candidate flight, evaluate three factors:
    → Price (lower is better, weighted 40%)
    → Total duration including layovers (shorter is better, weighted 35%)
    → Number of layovers (direct preferred, weighted 25%)
    → Apply traveler preference if provided (e.g., prefers direct, prefers economy).

  Node 4 — SELECTION: Pick the top 3 options that best balance cost, time, and comfort.
    → If budget is tight, prioritize lowest price.
    → If only 1 or 2 flights are available, return those without padding.

  Node 5 — OUTPUT: Return a clean JSON object. No speculation.

## Prompting principles
- Grounded responses only: every flight must come from tool data.
- Constraint-first: budget and date limits before comfort preferences.
- Budget-aware: flag if the cheapest available option still exceeds the flight budget.
- Professional and friendly tone: present options clearly and actionably.

## Output format
Return ONLY a valid JSON object (no markdown fences) with key:
  flights   list of up to 3 objects, each with:
    airline, flight_number, origin, destination,
    departure_time (ISO datetime or HH:MM), arrival_time (ISO datetime or HH:MM),
    duration_minutes (int), price_usd (float), layovers (int), cabin_class (str)
  note      str | null  — short human-readable note (e.g., "only 1 flight available",
                          "cheapest option exceeds flight budget")
"""


class FlightAgent(BaseAgent):
    """Flight Agent — Groq small model + AviationStack MCP Client."""

    @property
    def agent_name(self) -> str:
        return "flight_agent"

    @property
    def model_provider(self) -> str:
        return "groq"

    @property
    def max_steps(self) -> int:
        return self._settings.agent_steps_worker

    # ------------------------------------------------------------------

    async def run(self, state: TravelPlanState) -> TravelPlanState:
        start = time.monotonic()
        self._log_step("Flight agent started")

        constraints = state.get("constraints") or {}
        errors: list[dict[str, Any]] = []
        agent_responses: list[dict[str, Any]] = []

        destinations = constraints.get("destinations", [])
        origin = destinations[0] if len(destinations) > 1 else "NYC"
        destination = destinations[-1] if destinations else "Unknown"

        raw_results: dict[str, Any] = {}
        tool_results: list[dict[str, Any]] = []
        tool_start = time.monotonic()

        try:
            client = SkyscannerMCPClient()
            raw_results = await client.call(
                "search_flight",
                {
                    "origin": _to_iata(origin),
                    "destination": _to_iata(destination),
                    "departure_date": constraints.get("start_date") or "2025-07-01",
                    "adults": constraints.get("travelers", 1),
                    "cabin_class": constraints.get("cabin_class") or "economy",
                },
                agent=self.agent_name,
            )
            tool_results.append(
                self._create_tool_result(
                    "search_flight",
                    success=True,
                    data=raw_results,
                    latency_ms=self._elapsed_ms(tool_start),
                )
            )
        except ToolError as exc:
            self._log_error("Flight search tool error", exc)
            errors.append({"agent": self.agent_name, "error": str(exc), "step": "search_flight"})
            tool_results.append(
                self._create_tool_result(
                    "search_flight",
                    success=False,
                    error=str(exc),
                    latency_ms=self._elapsed_ms(tool_start),
                )
            )
            raw_results = {}
        except Exception as exc:
            self._log_error("Flight search unexpected error", exc)
            errors.append({"agent": self.agent_name, "error": str(exc), "step": "search_flight"})
            raw_results = {}

        # Filter/summarise with LLM
        flight_results = await self._filter_with_llm(raw_results, constraints)

        latency = self._elapsed_ms(start)
        agent_responses.append(
            self._create_agent_response(
                success=True,
                data={"flight_results": flight_results},
                tool_results=tool_results,
                steps_taken=2,
                latency_ms=latency,
            )
        )

        self._log_step("Flight agent complete", {"latency_ms": latency})

        return {
            "flight_results": flight_results,
            "agent_responses": agent_responses,
            "errors": errors,
        }

    # ------------------------------------------------------------------

    async def _filter_with_llm(
        self, raw: dict[str, Any], constraints: dict[str, Any]
    ) -> dict[str, Any]:
        if not raw:
            return {"flights": [], "note": "No flight data returned by the search tool"}

        llm = self._get_llm()
        destinations = constraints.get("destinations", [])
        origin = destinations[0] if len(destinations) > 1 else "origin"
        destination = destinations[-1] if destinations else "destination"

        prompt = (
            f"## Trip context\n"
            f"Route: {origin} → {destination}\n"
            f"Departure date: {constraints.get('start_date', 'unspecified')}\n"
            f"Travelers: {constraints.get('travelers', 1)}\n"
            f"Total trip budget: {constraints.get('budget', 'unspecified')} "
            f"{constraints.get('budget_currency', 'USD')}\n"
            f"Preferences: {constraints.get('preferences') or 'none stated'}\n\n"
            f"## Raw flight data from Skyscanner API\n{str(raw)[:3000]}\n\n"
            "Apply the Graph of Thought flight selection process from your system prompt. "
            "Work through all 5 nodes (constraints → tool results → scoring → selection → output) "
            "and return your top 3 flight recommendations."
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
            return parsed if parsed else {"flights": [], "raw": raw}
        except Exception as exc:
            self._log_error("LLM filtering failed for flights", exc)
            return {"flights": [], "raw": raw}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Very small IATA stub — real implementation would use Nominatim/DB lookup
_IATA_MAP = {
    "new york": "JFK", "nyc": "JFK", "los angeles": "LAX", "london": "LHR",
    "paris": "CDG", "tokyo": "NRT", "dubai": "DXB", "singapore": "SIN",
    "sydney": "SYD", "toronto": "YYZ", "chicago": "ORD", "miami": "MIA",
    "amsterdam": "AMS", "rome": "FCO", "barcelona": "BCN", "bangkok": "BKK",
    "hong kong": "HKG", "berlin": "BER", "madrid": "MAD", "istanbul": "IST",
}


def _to_iata(city: str) -> str:
    key = city.lower().strip()
    return _IATA_MAP.get(key, city[:3].upper())
