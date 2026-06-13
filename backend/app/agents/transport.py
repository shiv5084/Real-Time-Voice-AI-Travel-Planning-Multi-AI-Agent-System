"""Transport Agent — local routes via Maps MCP Client (geocoding + routing)."""

from __future__ import annotations

import time
from typing import Any

from app.agents.base import BaseAgent
from app.graph.state import TravelPlanState
from app.mcp_clients import MapsMCPClient
from app.utils.errors import ToolError
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# GoT-aligned system prompt — Transport Agent
# Principles: constraint-first, grounded, preference-aware, tool-assisted.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a professional local transport advisor. Your task is to recommend the most \
practical transport options between key trip locations, using verified routing data.

## Reasoning approach (Graph of Thought)

  Node 1 — CONSTRAINTS: Apply hard limits first.
    → Transport budget (if specified). Travel dates.
    → Traveler mobility requirements (e.g., wheelchair accessible, child stroller).

  Node 2 — PREFERENCES: Apply transport preferences.
    → Transport preference: public transit, rental car, taxi, or walking.
    → If no preference stated, prioritize public transit for cost, taxi for convenience.

  Node 3 — TOOL RESULTS: Use only geocoding and routing data returned by the tools.
    → Maps MCP client provides coordinates and routing data.
    → Do not invent route times or distances. Only use tool-provided values.

  Node 4 — ROUTE NODES: Identify the key journeys to plan:
    → Airport → hotel (arrival transfer)
    → Hotel → key attractions (daily transit)
    → Inter-city routes (if multi-destination trip)
    → Hotel → airport (departure transfer)

  Node 5 — SCORING: For each route option, evaluate:
    → Cost vs. transport budget (40%)
    → Travel time efficiency (35%)
    → Alignment with transport preference (25%)

  Node 6 — OUTPUT: Summarize the recommended transport plan. Return clean JSON.

## Prompting principles
- Grounded: route times and distances must come from Maps data, not estimates.
- Constraint-first: budget and accessibility before comfort preferences.
- Tool-assisted: prefer tool-confirmed routes over general knowledge.
- Professional and friendly: explain each option so a first-time visitor can follow it.

## Output format
Return ONLY a valid JSON object (no markdown fences) with key:
  transport_options  list of objects, each with:
    from_location (str), to_location (str),
    mode (walking / public_transit / taxi / rental_car / ferry),
    duration_minutes (int — from routing tool or estimated),
    distance_km (float or null),
    estimated_cost_usd (float),
    description (1–2 actionable sentences for the traveler)
  note               str | null — e.g., "routing API unavailable; times are estimates"
"""


class TransportAgent(BaseAgent):
    """Transport Agent — Groq small model + Maps MCP Client."""

    @property
    def agent_name(self) -> str:
        return "transport_agent"

    @property
    def model_provider(self) -> str:
        return "groq"

    @property
    def max_steps(self) -> int:
        return self._settings.agent_steps_worker

    # ------------------------------------------------------------------

    async def run(self, state: TravelPlanState) -> TravelPlanState:
        start = time.monotonic()
        self._log_step("Transport agent started")

        constraints = state.get("constraints") or {}
        errors: list[dict[str, Any]] = []
        agent_responses: list[dict[str, Any]] = []

        destinations = constraints.get("destinations", [])
        destination = destinations[-1] if destinations else "Unknown"

        tool_results: list[dict[str, Any]] = []
        geo_result: dict[str, Any] = {}
        route_result: dict[str, Any] = {}

        # Step 1: Geocode the destination
        geo_start = time.monotonic()
        try:
            maps_client = MapsMCPClient()
            geo_result = await maps_client.call(
                "google_maps_geocode",
                {"address": destination},
                agent=self.agent_name,
            )
            tool_results.append(
                self._create_tool_result(
                    "google_maps_geocode",
                    success=True,
                    data=geo_result,
                    latency_ms=self._elapsed_ms(geo_start),
                )
            )
        except Exception as exc:
            self._log_error("Geocoding failed", exc)
            errors.append({"agent": self.agent_name, "error": str(exc), "step": "google_maps_geocode"})
            tool_results.append(
                self._create_tool_result("google_maps_geocode", success=False, error=str(exc), latency_ms=self._elapsed_ms(geo_start))
            )

        # Step 2: Get routing info from Maps (airport → city center)
        route_start = time.monotonic()
        try:
            maps_client = MapsMCPClient()
            # Use address-based routing
            route_args = {
                "origin": f"airport near {destination}",
                "destination": f"city center {destination}",
                "mode": "driving",
            }

            route_result = await maps_client.call(
                "google_maps_directions",
                route_args,
                agent=self.agent_name,
            )
            tool_results.append(
                self._create_tool_result(
                    "google_maps_directions",
                    success=True,
                    data=route_result,
                    latency_ms=self._elapsed_ms(route_start),
                )
            )
        except ToolError as exc:
            self._log_error("Routing tool error", exc)
            errors.append({"agent": self.agent_name, "error": str(exc), "step": "google_maps_directions"})
            tool_results.append(
                self._create_tool_result("google_maps_directions", success=False, error=str(exc), latency_ms=self._elapsed_ms(route_start))
            )
        except Exception as exc:
            self._log_error("Routing unexpected error", exc)
            errors.append({"agent": self.agent_name, "error": str(exc), "step": "google_maps_directions"})

        transport_results = await self._summarise_with_llm(
            geo_result, route_result, constraints, destination
        )

        latency = self._elapsed_ms(start)
        agent_responses.append(
            self._create_agent_response(
                success=True,
                data={"transport_results": transport_results},
                tool_results=tool_results,
                steps_taken=3,
                latency_ms=latency,
            )
        )

        self._log_step("Transport agent complete", {"latency_ms": latency})

        return {
            "transport_results": transport_results,
            "agent_responses": agent_responses,
            "errors": errors,
        }

    # ------------------------------------------------------------------

    async def _summarise_with_llm(
        self,
        geo: dict[str, Any],
        route: dict[str, Any],
        constraints: dict[str, Any],
        destination: str,
    ) -> dict[str, Any]:
        llm = self._get_llm()
        preferences = constraints.get("preferences") or {}
        transport_pref = preferences.get("transport_preference", "not specified")

        # Extract geocoding confidence — handle both {"results": [...]} and {"data": {"results": [...]}}
        geo_results = geo.get("results") or (geo.get("data") or {}).get("results") or []
        geo_note = (
            f"Geocoded: lat={geo_results[0].get('lat')}, lon={geo_results[0].get('lon')}"
            if geo_results and isinstance(geo_results, list) and isinstance(geo_results[0], dict)
            else "Geocoding returned no results — coordinates unavailable"
        )

        # Extract routing key metrics
        routes = route.get("routes") or (route.get("data") or {}).get("routes") or []
        route_note = "No routing data available"
        if routes:
            r = routes[0]
            dist_meters = r.get("distanceMeters", 0)
            dist_km = round(dist_meters / 1000, 1)
            duration = r.get("duration", "")
            route_note = f"Route: {dist_km} km, {duration} (from Maps)"

        prompt = (
            f"## Trip context\n"
            f"Destination: {destination}\n"
            f"Travelers: {constraints.get('travelers', 1)}\n"
            f"Transport preference: {transport_pref}\n"
            f"Transport budget: part of total {constraints.get('budget', 'unspecified')} "
            f"{constraints.get('budget_currency', 'USD')}\n\n"
            f"## Geocoding result\n{geo_note}\n\n"
            f"## Routing result\n{route_note}\n"
            f"Full route data: {str(route)[:1500]}\n\n"
            "Apply the Graph of Thought transport planning process from your system prompt. "
            "Work through all 6 nodes (constraints → preferences → tool results → route nodes → "
            "scoring → output) and return a practical transport plan for this trip."
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
            return parsed if parsed else {"transport_options": [], "geo": geo, "route": route}
        except Exception as exc:
            self._log_error("LLM summarisation failed for transport", exc)
            return {"transport_options": [], "geo": geo, "route": route}
