"""Budget Agent — deterministic cost aggregation + Gemini optimization suggestions."""

from __future__ import annotations

import time
from typing import Any

from app.agents.base import BaseAgent
from app.graph.state import TravelPlanState
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# GoT-aligned system prompt — Budget Agent (Gemini)
# Principles: constraint-first, deterministic aggregation, budget-aware,
# actionable recommendations, professional tone.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a professional travel budget analyst. The trip is currently over budget. \
Your task is to recommend specific, actionable adjustments that bring the total cost \
within the traveler's stated budget while preserving as much of the trip quality as possible.

## Reasoning approach (Graph of Thought)

  Node 1 — BUDGET GAP: Quantify the problem precisely.
    → Total budget: [provided]
    → Estimated cost: [provided]
    → Overage amount and percentage: calculate exactly.

  Node 2 — COST DRIVERS: Identify which categories are causing the overage.
    → Examine the breakdown: flights, hotels, attractions, transport, food.
    → Rank categories by overage contribution (largest first).

  Node 3 — OPTIMIZATION BRANCHES: For each major cost driver, generate one or more \
    specific reduction options:
    → Flights: flexible dates, connecting flights, nearby alternative airports.
    → Hotels: lower-tier accommodation, fewer nights, shared room.
    → Attractions: free alternatives, skip paid attractions, combo tickets.
    → Transport: public transit instead of taxi, walking distances.
    → Food: local markets and street food instead of restaurants.

  Node 4 — FEASIBILITY CHECK: For each suggestion, verify it is realistic.
    → Would it actually close the budget gap?
    → Does it conflict with any hard constraints (dates, travelers, stated preferences)?
    → Discard suggestions that are impractical or that violate hard limits.

  Node 5 — OUTPUT: Present 3–5 specific, ranked recommendations. Most impactful first.

## Prompting principles
- Budget-aware: every suggestion must directly reduce the identified overage.
- Constraint-first: never suggest changes that violate travel dates or traveler count.
- Grounded: base suggestions on the actual cost breakdown provided.
- Actionable: each recommendation must be concrete ("book a connecting flight via X" \
  not "consider cheaper flights").
- Professional and friendly: acknowledge the trade-off clearly and positively.

## Output format
Return ONLY a valid JSON object (no markdown fences) with key:
  recommendations  list[str] — 3 to 5 specific, actionable cost-reduction suggestions,
                               ordered from most to least impactful.
"""

# Budget warning threshold: 85% of budget used triggers a WARNING
_WARNING_THRESHOLD = 0.85


class BudgetAgent(BaseAgent):
    """Budget Agent — Gemini model for optimization; deterministic aggregation."""

    @property
    def agent_name(self) -> str:
        return "budget_agent"

    @property
    def model_provider(self) -> str:
        return "gemini"

    @property
    def max_steps(self) -> int:
        return self._settings.agent_steps_budget

    # ------------------------------------------------------------------

    async def run(self, state: TravelPlanState) -> TravelPlanState:
        start = time.monotonic()
        self._log_step("Budget agent started")

        constraints = state.get("constraints") or {}
        flight_results = state.get("flight_results") or {}
        hotel_results = state.get("hotel_results") or {}
        attraction_results = state.get("attraction_results") or {}
        transport_results = state.get("transport_results") or {}
        errors: list[dict[str, Any]] = []
        agent_responses: list[dict[str, Any]] = []

        total_budget = constraints.get("budget")
        travelers = constraints.get("travelers", 1) or 1

        # Aggregate costs deterministically
        categories = _aggregate_costs(
            flight_results, hotel_results, attraction_results, transport_results, travelers,
            constraints
        )
        total_cost = sum(c["amount"] for c in categories)

        # Determine compliance
        if total_budget is None:
            compliance = "within_budget"
            variance_pct = None
        else:
            ratio = total_cost / total_budget if total_budget > 0 else float("inf")
            if ratio > 1.0:
                compliance = "over_budget"
            elif ratio >= _WARNING_THRESHOLD:
                compliance = "warning"
            else:
                compliance = "within_budget"
            variance_pct = round((total_cost - total_budget) / total_budget * 100, 2) if total_budget > 0 else None

        # Gemini optimization suggestions if over budget
        recommendations: list[str] = []
        if compliance == "over_budget" and total_budget:
            recommendations = await self._get_recommendations(
                total_budget, total_cost, categories, constraints
            )

        budget_breakdown: dict[str, Any] = {
            "total_budget": total_budget or 0.0,
            "total_estimated_cost": round(total_cost, 2),
            "currency": constraints.get("budget_currency", "USD"),
            "compliance": compliance,
            "categories": categories,
            "variance_percentage": variance_pct,
            "recommendations": recommendations,
        }

        latency = self._elapsed_ms(start)
        agent_responses.append(
            self._create_agent_response(
                success=True,
                data={"budget_breakdown": budget_breakdown},
                steps_taken=2,
                latency_ms=latency,
            )
        )

        self._log_step("Budget agent complete", {
            "compliance": compliance,
            "total_cost": total_cost,
            "latency_ms": latency,
        })

        return {
            "budget_breakdown": budget_breakdown,
            "agent_responses": agent_responses,
            "errors": errors,
        }

    # ------------------------------------------------------------------

    async def _get_recommendations(
        self,
        total_budget: float,
        total_cost: float,
        categories: list[dict[str, Any]],
        constraints: dict[str, Any],
    ) -> list[str]:
        llm = self._get_llm()
        overage = total_cost - total_budget
        overage_pct = (overage / total_budget * 100) if total_budget > 0 else 0

        # Sort categories by amount descending to highlight the biggest cost drivers
        sorted_cats = sorted(categories, key=lambda c: c.get("amount", 0), reverse=True)
        cats_summary = "\n".join(
            f"  - {c['category']}: ${c['amount']:.0f}" for c in sorted_cats
        )

        prompt = (
            f"## Budget situation\n"
            f"Total budget:        ${total_budget:.0f} {constraints.get('budget_currency', 'USD')}\n"
            f"Estimated cost:      ${total_cost:.0f}\n"
            f"Over budget by:      ${overage:.0f} ({overage_pct:.1f}%)\n\n"
            f"## Cost breakdown (highest to lowest)\n{cats_summary}\n\n"
            f"## Trip constraints\n"
            f"Destinations: {constraints.get('destinations', [])}\n"
            f"Dates: {constraints.get('start_date')} to {constraints.get('end_date')}\n"
            f"Travelers: {constraints.get('travelers', 1)}\n"
            f"Preferences: {constraints.get('preferences') or 'none stated'}\n\n"
            "Apply the Graph of Thought optimization process from your system prompt. "
            "Work through all 5 nodes (budget gap → cost drivers → optimization branches → "
            "feasibility check → output) and return your top 3–5 recommendations."
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
                model=getattr(llm, "model", getattr(llm, "model_name", "gemini")),
                raw_response=content,
                parsed=parsed,
            )
            recs = parsed.get("recommendations") if parsed else []
            if isinstance(recs, list):
                return [str(r) for r in recs]
        except Exception as exc:
            self._log_error("Gemini recommendation failed", exc)
        return [
            "Book connecting flights to reduce airfare costs",
            "Switch to a mid-range hotel or consider a hostel for solo travelers",
            "Replace paid attractions with free alternatives (parks, markets, viewpoints)",
        ]


# ---------------------------------------------------------------------------
# Deterministic cost aggregation helpers
# ---------------------------------------------------------------------------

def _aggregate_costs(
    flights: dict[str, Any],
    hotels: dict[str, Any],
    attractions: dict[str, Any],
    transport: dict[str, Any],
    travelers: int,
    constraints: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Extract costs from worker results and return a list of CostCategory dicts."""
    categories: list[dict[str, Any]] = []

    # Flights
    flight_cost = _extract_flight_cost(flights, travelers)
    categories.append({"category": "flights", "amount": flight_cost, "currency": "USD", "items": None})

    # Hotels
    hotel_cost = _extract_hotel_cost(hotels, travelers)
    categories.append({"category": "hotels", "amount": hotel_cost, "currency": "USD", "items": None})

    # Attractions
    attraction_cost = _extract_attraction_cost(attractions, travelers)
    categories.append({"category": "attractions", "amount": attraction_cost, "currency": "USD", "items": None})

    # Transport
    transport_cost = _extract_transport_cost(transport, travelers)
    categories.append({"category": "transport", "amount": transport_cost, "currency": "USD", "items": None})

    # Food estimate: $50/person/day — use duration_days from constraints if available
    duration_days = (constraints or {}).get("duration_days", 5)
    food_estimate = 50.0 * travelers * duration_days
    categories.append({"category": "food", "amount": food_estimate, "currency": "USD", "items": None})

    return categories


def _extract_flight_cost(flights: dict[str, Any], travelers: int) -> float:
    flight_list = flights.get("flights") or []
    if flight_list and isinstance(flight_list, list):
        prices = []
        for f in flight_list:
            if isinstance(f, dict):
                price = f.get("price_usd") or f.get("price") or 0
                try:
                    prices.append(float(price))
                except (TypeError, ValueError):
                    pass
        if prices:
            return min(prices) * travelers
    return 500.0 * travelers  # default estimate


def _extract_hotel_cost(hotels: dict[str, Any], travelers: int) -> float:
    hotel_list = hotels.get("hotels") or []
    if hotel_list and isinstance(hotel_list, list):
        costs = []
        for h in hotel_list:
            if isinstance(h, dict):
                total = h.get("total_cost_usd") or h.get("price_per_night_usd") or 0
                try:
                    costs.append(float(total))
                except (TypeError, ValueError):
                    pass
        if costs:
            return min(costs)
    return 150.0 * 5  # default: $150/night × 5 nights


def _extract_attraction_cost(attractions: dict[str, Any], travelers: int) -> float:
    attraction_list = attractions.get("attractions") or []
    total = 0.0
    for a in attraction_list:
        if isinstance(a, dict):
            cost = a.get("cost_usd") or 0
            try:
                total += float(cost) * travelers
            except (TypeError, ValueError):
                pass
    return total if total > 0 else 100.0 * travelers  # default


def _extract_transport_cost(transport: dict[str, Any], travelers: int) -> float:
    opts = transport.get("transport_options") or []
    if opts and isinstance(opts, list):
        costs = []
        for t in opts:
            if isinstance(t, dict):
                cost = t.get("estimated_cost_usd") or 0
                try:
                    costs.append(float(cost))
                except (TypeError, ValueError):
                    pass
        if costs:
            return sum(costs) * travelers
    return 80.0 * travelers  # default
