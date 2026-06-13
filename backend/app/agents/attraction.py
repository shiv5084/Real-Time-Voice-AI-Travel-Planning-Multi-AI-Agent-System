"""Attraction Agent — POI discovery via Tavily + geocoding validation via Maps."""

from __future__ import annotations

import time
from typing import Any

from app.agents.base import BaseAgent
from app.graph.state import TravelPlanState
from app.mcp_clients import MapsMCPClient, TavilyMCPClient
from app.utils.errors import ToolError
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# GoT-aligned system prompt — Attraction Agent
# Principles: constraint-first, grounded, preference-aware, geocoding-verified.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a professional destination research specialist. Your task is to curate the \
best attractions and activities for a traveler based on their preferences and verified \
real-world data.

## Reasoning approach (Graph of Thought)

  Node 1 — CONSTRAINTS: Apply hard limits first.
    → Activity budget per person (if specified). Trip dates (to filter seasonal closures).
    → Crowd tolerance: if the traveler dislikes crowds, deprioritize peak-hour landmarks.

  Node 2 — PREFERENCES: Filter by traveler style.
    → Food preferences (e.g., vegetarian — prioritize food markets, not steakhouses).
    → Activity interests (temples, museums, nature, nightlife, shopping, etc.).
    → Activity level (relaxed → short walks and cafes; active → hikes and tours).

  Node 3 — TOOL RESULTS: Use only what Tavily search returned.
    → Do not invent attractions. Every recommendation must appear in the search data.
    → Cross-reference with geocoding results to confirm the location exists on the map.

  Node 4 — SCORING: For each candidate attraction, evaluate:
    → Preference alignment (40%) — matches stated interests?
    → Crowd level vs. tolerance (30%) — avoid overcrowded if traveler dislikes crowds.
    → Cost vs. budget (20%) — prefer free or low-cost if budget is tight.
    → Geocoding confidence (10%) — higher confidence if Maps confirmed the location.

  Node 5 — GEOCODING GUARD: Flag any attraction that could not be geocoded or that \
    Maps returned zero results for. Do not silently include unverified locations.

  Node 6 — OUTPUT: Select the top 8 attractions. Return clean JSON.

## Prompting principles
- Grounded: only recommend places present in search results and verifiable on a map.
- Preference-aware: crowd tolerance and activity style must shape the final list.
- Constraint-first: cost and date limits before aesthetic preferences.
- Professional and friendly: describe each attraction in 1–2 actionable sentences.

## Output format
Return ONLY a valid JSON object (no markdown fences) with key:
  attractions  list of up to 8 objects, each with:
    name, type (museum/park/landmark/restaurant/market/etc.),
    location (neighborhood or address), estimated_duration_hours (float),
    cost_usd (float — 0 if free), rating (float or null),
    description (1–2 sentences), best_time_to_visit (str or null),
    geocoded (bool — true if Maps confirmed the location)
  note         str | null — e.g., "2 attractions could not be geocoded and were excluded"
"""


class AttractionAgent(BaseAgent):
    """Attraction Agent — Groq small model + Tavily + Maps MCP Clients."""

    @property
    def agent_name(self) -> str:
        return "attraction_agent"

    @property
    def model_provider(self) -> str:
        return "groq"

    @property
    def max_steps(self) -> int:
        return self._settings.agent_steps_worker

    # ------------------------------------------------------------------

    async def run(self, state: TravelPlanState) -> TravelPlanState:
        start = time.monotonic()
        self._log_step("Attraction agent started")

        constraints = state.get("constraints") or {}
        errors: list[dict[str, Any]] = []
        agent_responses: list[dict[str, Any]] = []

        destinations = constraints.get("destinations", [])
        destination = destinations[-1] if destinations else "Unknown"

        raw_results: dict[str, Any] = {}
        tool_results: list[dict[str, Any]] = []

        # Step 1: Tavily search for attractions
        tool_start = time.monotonic()
        try:
            client = TavilyMCPClient()
            raw_results = await client.call(
                "tavily_search",
                {
                    "query": f"top tourist attractions things to do in {destination}",
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
            self._log_error("Attraction search tool error", exc)
            errors.append({"agent": self.agent_name, "error": str(exc), "step": "tavily_search"})
            tool_results.append(
                self._create_tool_result("tavily_search", success=False, error=str(exc), latency_ms=self._elapsed_ms(tool_start))
            )
        except Exception as exc:
            self._log_error("Attraction search unexpected error", exc)
            errors.append({"agent": self.agent_name, "error": str(exc), "step": "tavily_search"})

        # Step 2: Maps geocoding to validate destination exists
        geo_start = time.monotonic()
        geocoding_summary = ""
        try:
            maps_client = MapsMCPClient()
            geo_result = await maps_client.call(
                "google_maps_geocode",
                {"address": destination},
                agent=self.agent_name,
            )
            results_list = geo_result.get("results") or (geo_result.get("data") or {}).get("results") or []
            if results_list:
                first = results_list[0]
                lat = first.get("geometry", {}).get("location", {}).get("lat")
                lng = first.get("geometry", {}).get("location", {}).get("lng")
                geocoding_summary = (
                    f"'{destination}' geocoded successfully: "
                    f"lat={lat}, lon={lng}"
                )
            else:
                geocoding_summary = f"'{destination}' could not be geocoded — location may be unrecognized."
            tool_results.append(
                self._create_tool_result(
                    "google_maps_geocode",
                    success=True,
                    data=geo_result,
                    latency_ms=self._elapsed_ms(geo_start),
                )
            )
        except Exception as exc:
            self._log_error("Geocoding failed for destination", exc)
            geocoding_summary = f"Geocoding failed for '{destination}': {exc}"
            tool_results.append(
                self._create_tool_result("google_maps_geocode", success=False, error=str(exc), latency_ms=self._elapsed_ms(geo_start))
            )

        attraction_results = await self._filter_with_llm(raw_results, constraints, destination, geocoding_summary)

        latency = self._elapsed_ms(start)
        agent_responses.append(
            self._create_agent_response(
                success=True,
                data={"attraction_results": attraction_results},
                tool_results=tool_results,
                steps_taken=3,
                latency_ms=latency,
            )
        )

        self._log_step("Attraction agent complete", {"latency_ms": latency})

        return {
            "attraction_results": attraction_results,
            "agent_responses": agent_responses,
            "errors": errors,
        }

    # ------------------------------------------------------------------

    async def _filter_with_llm(
        self, raw: dict[str, Any], constraints: dict[str, Any], destination: str,
        geocoding_summary: str = ""
    ) -> dict[str, Any]:
        if not raw:
            return {"attractions": [], "note": "No attraction data returned by the search tool"}

        llm = self._get_llm()
        preferences = constraints.get("preferences") or {}
        crowd_tolerance = preferences.get("crowd_tolerance", "not specified")
        activity_interests = preferences.get("activity_level", "not specified")
        food_pref = preferences.get("food_preferences", "not specified")

        prompt = (
            f"## Trip context\n"
            f"Destination: {destination}\n"
            f"Travelers: {constraints.get('travelers', 1)}\n"
            f"Dates: {constraints.get('start_date', 'unspecified')} to {constraints.get('end_date', 'unspecified')}\n"
            f"Activity budget estimate: {constraints.get('budget', 'unspecified')} "
            f"{constraints.get('budget_currency', 'USD')} total\n\n"
            f"## Traveler preferences\n"
            f"Crowd tolerance: {crowd_tolerance}\n"
            f"Activity interests / level: {activity_interests}\n"
            f"Food preferences: {food_pref}\n\n"
            f"## Geocoding verification summary\n"
            f"{geocoding_summary if geocoding_summary else 'Geocoding results not available'}\n\n"
            f"## Raw attraction search results from Tavily\n{str(raw)[:3000]}\n\n"
            "Apply the Graph of Thought attraction curation process from your system prompt. "
            "Work through all 6 nodes (constraints → preferences → tool results → scoring → "
            "geocoding guard → output) and return your top 8 verified attractions."
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
            return parsed if parsed else {"attractions": [], "raw": raw}
        except Exception as exc:
            self._log_error("LLM filtering failed for attractions", exc)
            return {"attractions": [], "raw": raw}
