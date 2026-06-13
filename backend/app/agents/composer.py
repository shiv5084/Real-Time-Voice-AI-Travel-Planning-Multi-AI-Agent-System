"""Itinerary Composer Agent — day-by-day schedule using Groq large model."""

from __future__ import annotations

import time
from typing import Any

from app.agents.base import BaseAgent
from app.graph.state import TravelPlanState
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# GoT-aligned system prompt — Itinerary Composer Agent (Groq large model)
# Principles: constraint-first, grounded synthesis, preference-aware scheduling,
# budget-aware, validation-ready output, professional & friendly tone.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a professional travel itinerary designer. Your task is to compose a detailed, \
day-by-day travel schedule by synthesizing verified flight, hotel, attraction, and \
transport data into a coherent, personalized plan.

## Reasoning approach (Graph of Thought)

  Node 1 — CONSTRAINTS (anchor point — never violate these):
    → Start date, end date, and Duration → you MUST generate exactly N days as specified \
      in the Duration field. Never generate fewer or more days than the Duration specifies.
    → Total budget → the itinerary's cost sum must not exceed it.
    → Number of travelers → all costs must be scaled per person where applicable.
    → Departure and arrival times from the selected flight → Day 1 and last day are fixed \
      around these. Do not schedule activities before the flight lands or after it departs.

  Node 2 — STRUCTURE: Map days to a logical skeleton.
    → Day 1: Arrival → airport transfer → hotel check-in → light activity or rest.
    → Middle days: Full activity days — cluster by neighborhood to minimize transit.
    → Last day: Morning activity (if time permits) → hotel check-out → departure transfer.

  Node 3 — ACTIVITY SCHEDULING: For each day, assign activities from the attraction list.
    → Apply GoT branching: if two attractive options conflict on timing, branch and \
      evaluate each; select the path that better satisfies preferences and geography.
    → Enforce minimum 30-minute buffers between activities.
    → Schedule meals: breakfast 08:00–09:00, lunch 12:30–13:30, dinner 19:00–20:30.
    → Crowd-averse travelers: schedule popular landmarks early morning or late afternoon.
    → Food-focused travelers: include at least one local food market or restaurant per day.

  Node 4 — TRANSPORT INTEGRATION: Insert transport legs between locations.
    → Use provided transport options for airport transfers and inter-city legs.
    → For local movement between attractions, use the most efficient mode \
      (walking if under 20 min, public transit otherwise).

  Node 5 — BUDGET CHECK: Tally costs as you build the schedule.
    → Track running total: flights + hotel + daily activity costs + food estimates.
    → If running total approaches the budget limit, substitute with lower-cost alternatives \
      (free attractions, street food, walking instead of taxi).
    → Backtrack and revise a day if it pushes the total over budget.

  Node 6 — PERSONALIZATION: Apply traveler preferences throughout.
    → Accommodation type preference → use the recommended hotel type.
    → Activity level: relaxed → fewer activities per day with longer durations; \
      active → more activities, tighter schedule.
    → Transport preference → apply stated mode (public transit, rental car, etc.).

  Node 7 — OUTPUT: Produce a complete, self-consistent itinerary. Every activity must \
    have a start time, end time, cost, and location. No gaps longer than 2 hours \
    without an activity, meal, or transport leg during waking hours (08:00–22:00).

## Prompting principles
- Constraint-first: dates, budget, and flight times are inviolable anchors.
- Grounded: only use flights, hotels, and attractions provided in the input data.
- Preference-aware: crowd tolerance, food style, and activity level shape every day.
- Budget-aware: running cost tracked and enforced; substitute if needed.
- Validation-ready: structure the output so the Validator can check every claim.
- Professional and friendly: write activity descriptions as if briefing a traveler \
  — warm, clear, and actionable.

## Output format
Return ONLY a valid JSON object (no markdown fences) with key:
  days  list of day objects, each with:
    day           int (1-indexed)
    date          str (YYYY-MM-DD) or null
    location      str (city or neighborhood)
    activities    list of:
      name          str
      type          str (flight/hotel/attraction/restaurant/transport/leisure)
      start_time    str (HH:MM, 24-hour)
      end_time      str (HH:MM, 24-hour)
      location      str
      cost_usd      float (per person)
      description   str (1–2 actionable sentences for the traveler)
    total_cost_usd  float (sum of activity costs for the day)
    notes           str | null (day-level tip, e.g., "wear comfortable shoes")
"""


class ComposerAgent(BaseAgent):
    """Itinerary Composer Agent — Groq large model, no external tools."""

    @property
    def agent_name(self) -> str:
        return "composer_agent"

    @property
    def model_provider(self) -> str:
        return "groq"

    @property
    def max_steps(self) -> int:
        return self._settings.agent_steps_composer

    # ------------------------------------------------------------------

    async def run(self, state: TravelPlanState) -> TravelPlanState:
        start = time.monotonic()
        self._log_step("Composer agent started")

        constraints = state.get("constraints") or {}
        flight_results = state.get("flight_results") or {}
        hotel_results = state.get("hotel_results") or {}
        attraction_results = state.get("attraction_results") or {}
        transport_results = state.get("transport_results") or {}
        budget_breakdown = state.get("budget_breakdown") or {}
        errors: list[dict[str, Any]] = []
        agent_responses: list[dict[str, Any]] = []

        itinerary = await self._compose(
            constraints, flight_results, hotel_results, attraction_results,
            transport_results, budget_breakdown
        )

        latency = self._elapsed_ms(start)
        agent_responses.append(
            self._create_agent_response(
                success=True,
                data={"itinerary": itinerary},
                steps_taken=3,
                latency_ms=latency,
            )
        )

        self._log_step("Composer agent complete", {
            "days": len(itinerary.get("days") or []),
            "latency_ms": latency,
        })

        return {
            "itinerary": itinerary,
            "agent_responses": agent_responses,
            "errors": errors,
        }

    # ------------------------------------------------------------------

    async def _compose(
        self,
        constraints: dict[str, Any],
        flights: dict[str, Any],
        hotels: dict[str, Any],
        attractions: dict[str, Any],
        transport: dict[str, Any],
        budget: dict[str, Any],
    ) -> dict[str, Any]:
        llm = self._get_llm()

        destinations = constraints.get("destinations", [])
        destination = ", ".join(destinations) if destinations else "Unknown"
        start_date = constraints.get("start_date") or "TBD"
        end_date = constraints.get("end_date") or "TBD"
        travelers = constraints.get("travelers", 1)
        budget_amount = constraints.get("budget", "unspecified")
        currency = constraints.get("budget_currency", "USD")
        preferences = constraints.get("preferences") or {}
        duration_days = constraints.get("duration_days") or 5  # default to 5-day trip

        # Extract compliance note for budget-aware composition
        compliance = budget.get("compliance", "within_budget")
        total_cost = budget.get("total_estimated_cost", 0)
        budget_note = (
            f"⚠ OVER BUDGET: estimated cost ${total_cost:.0f} exceeds budget ${budget_amount}. "
            "Substitute expensive activities with free alternatives and use public transit."
            if compliance == "over_budget"
            else f"Budget: ${budget_amount} {currency} — estimated cost: ${total_cost:.0f} ({compliance})."
        )

        prompt = (
            f"## Trip brief\n"
            f"Destinations: {destination}\n"
            f"Dates: {start_date} to {end_date}\n"
            f"Duration: {duration_days} days\n"
            f"Travelers: {travelers}\n"
            f"Budget: {budget_amount} {currency}\n"
            f"Preferences: {preferences}\n\n"
            f"## Budget status\n{budget_note}\n\n"
            f"## Available flights\n{str(flights.get('flights', []))[:1500]}\n\n"
            f"## Available hotels\n{str(hotels.get('hotels', []))[:1500]}\n\n"
            f"## Verified attractions\n{str(attractions.get('attractions', []))[:2000]}\n\n"
            f"## Transport options\n{str(transport.get('transport_options', []))[:1000]}\n\n"
            "Apply the Graph of Thought composition process from your system prompt. "
            "Work through all 7 nodes (constraints → structure → activity scheduling → "
            "transport integration → budget check → personalization → output) and "
            "produce a complete day-by-day itinerary."
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
                model=getattr(llm, "model", getattr(llm, "model_name", "groq-large")),
                raw_response=content,
                parsed=parsed,
            )
            if isinstance(parsed, list):
                parsed = {"days": parsed}
            if parsed and "days" in parsed:
                # Always ensure destination is set from constraints (source of truth)
                parsed["destination"] = destination
                # ── Day-count enforcement ─────────────────────────────────────
                # The LLM sometimes ignores the Duration instruction and returns
                # fewer days than requested. Detect and pad deterministically.
                days_returned = len(parsed.get("days") or [])
                if days_returned < duration_days:
                    self._log_step(
                        f"LLM returned {days_returned} days but {duration_days} were requested — padding",
                        {"llm_days": days_returned, "required_days": duration_days},
                    )
                    parsed = _pad_itinerary_to_duration(
                        parsed, duration_days, destination, start_date, end_date
                    )
                return parsed
            return _fallback_itinerary(destination, start_date, end_date, duration_days)
        except Exception as exc:
            self._log_error("LLM composition failed", exc)
            return _fallback_itinerary(destination, start_date, end_date, duration_days)


# ---------------------------------------------------------------------------
# Pad a short LLM itinerary up to the requested duration
# ---------------------------------------------------------------------------

def _pad_itinerary_to_duration(
    itinerary: dict[str, Any],
    target_days: int,
    destination: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Pad an LLM itinerary that has fewer days than requested.

    Strategy:
    - Keep all days the LLM produced (they're the richest content).
    - Append additional themed days until we reach `target_days`.
    - The final day from the LLM becomes a middle day; a new proper
      departure day is appended as the very last entry.
    """
    from datetime import date as _date, timedelta as _td

    existing_days: list[dict[str, Any]] = list(itinerary.get("days") or [])
    current_count = len(existing_days)

    # Day themes to rotate through when padding
    _PAD_THEMES = [
        {
            "name": "Museum & gallery day",
            "activities": [
                {"name": "Breakfast at local café", "type": "restaurant",
                 "start_time": "08:00", "end_time": "09:00", "cost_usd": 15,
                 "description": "Start the day with a fresh croissant and coffee."},
                {"name": "Museum visit", "type": "attraction",
                 "start_time": "09:30", "end_time": "13:00", "cost_usd": 20,
                 "description": "Explore one of the city's world-class museums."},
                {"name": "Lunch", "type": "restaurant",
                 "start_time": "13:00", "end_time": "14:00", "cost_usd": 25,
                 "description": "Enjoy a leisurely lunch at a local brasserie."},
                {"name": "Art gallery afternoon", "type": "attraction",
                 "start_time": "14:30", "end_time": "17:30", "cost_usd": 15,
                 "description": "Browse contemporary art galleries in the neighbourhood."},
                {"name": "Romantic dinner", "type": "restaurant",
                 "start_time": "19:30", "end_time": "21:30", "cost_usd": 60,
                 "description": "Reserve a table at a romantic restaurant — book ahead."},
            ],
            "notes": "Wear comfortable shoes for gallery walking.",
        },
        {
            "name": "Neighbourhood & market day",
            "activities": [
                {"name": "Morning market visit", "type": "attraction",
                 "start_time": "08:30", "end_time": "10:30", "cost_usd": 10,
                 "description": "Wander through a bustling local food market."},
                {"name": "Coffee & pastry", "type": "restaurant",
                 "start_time": "10:30", "end_time": "11:00", "cost_usd": 8,
                 "description": "Grab a coffee and pastry from a neighbourhood café."},
                {"name": "Neighbourhood walk", "type": "leisure",
                 "start_time": "11:00", "end_time": "13:00", "cost_usd": 0,
                 "description": "Stroll through a charming district, away from crowds."},
                {"name": "Lunch", "type": "restaurant",
                 "start_time": "13:00", "end_time": "14:00", "cost_usd": 20,
                 "description": "Try local specialties at a tucked-away bistro."},
                {"name": "Historic landmarks", "type": "attraction",
                 "start_time": "15:00", "end_time": "18:00", "cost_usd": 12,
                 "description": "Visit key landmarks — go early evening to avoid peak crowds."},
                {"name": "Dinner", "type": "restaurant",
                 "start_time": "19:30", "end_time": "21:30", "cost_usd": 50,
                 "description": "Dinner at a restaurant recommended by locals."},
            ],
            "notes": "Book landmark tickets online in advance to skip queues.",
        },
        {
            "name": "Parks & scenic day",
            "activities": [
                {"name": "Breakfast", "type": "restaurant",
                 "start_time": "08:00", "end_time": "09:00", "cost_usd": 12,
                 "description": "Relaxed breakfast before a day outdoors."},
                {"name": "Morning park stroll", "type": "leisure",
                 "start_time": "09:30", "end_time": "12:00", "cost_usd": 0,
                 "description": "Enjoy a peaceful walk through a scenic park."},
                {"name": "Picnic lunch", "type": "restaurant",
                 "start_time": "12:00", "end_time": "13:30", "cost_usd": 20,
                 "description": "Pick up fresh produce for a picnic — a favourite local pastime."},
                {"name": "Cultural site visit", "type": "attraction",
                 "start_time": "14:00", "end_time": "17:00", "cost_usd": 18,
                 "description": "Visit a quieter cultural site or viewpoint."},
                {"name": "Sunset view", "type": "leisure",
                 "start_time": "18:00", "end_time": "19:00", "cost_usd": 0,
                 "description": "Find a scenic spot to watch the sunset."},
                {"name": "Dinner", "type": "restaurant",
                 "start_time": "20:00", "end_time": "22:00", "cost_usd": 55,
                 "description": "End the day with a memorable dinner."},
            ],
            "notes": "Perfect day for slower-paced exploration.",
        },
    ]

    # Try to parse start_date so we can assign real dates to padded days
    base_date: _date | None = None
    try:
        if start_date and start_date != "TBD":
            base_date = _date.fromisoformat(start_date)
    except ValueError:
        base_date = None

    for i in range(current_count + 1, target_days + 1):
        theme = _PAD_THEMES[(i - 2) % len(_PAD_THEMES)]
        day_date: str | None = None
        if base_date:
            day_date = (base_date + _td(days=i - 1)).isoformat()

        # Activities with location field filled in
        activities = []
        for act in theme["activities"]:
            activities.append({**act, "location": destination})

        total_cost = sum(a["cost_usd"] for a in activities)
        existing_days.append({
            "day": i,
            "date": day_date,
            "location": destination,
            "activities": activities,
            "total_cost_usd": total_cost,
            "notes": theme.get("notes"),
        })

    # Renumber all days sequentially (LLM may have started at 0 or repeated numbers)
    for idx, day in enumerate(existing_days):
        day["day"] = idx + 1
        # Assign date if missing but base_date is available
        if base_date and not day.get("date"):
            day["date"] = (base_date + _td(days=idx)).isoformat()
        # Ensure location is set
        if not day.get("location"):
            day["location"] = destination

    return {**itinerary, "days": existing_days, "destination": destination}


# ---------------------------------------------------------------------------
# Fallback itinerary when LLM is unavailable
# ---------------------------------------------------------------------------

def _fallback_itinerary(
    destination: str,
    start_date: str,
    end_date: str,
    num_days: int = 5,
) -> dict[str, Any]:
    """Generate a multi-day fallback itinerary with `num_days` days."""
    num_days = max(num_days, 1)  # at least 1 day

    # Themed day templates that rotate for variety
    _DAY_THEMES = [
        {
            "name": "Main sightseeing",
            "type": "attraction",
            "start_time": "09:30",
            "end_time": "17:00",
            "cost_usd": 50,
            "description": "Visit top attractions and landmarks",
            "notes": "Full day of sightseeing",
        },
        {
            "name": "Museums & culture",
            "type": "attraction",
            "start_time": "10:00",
            "end_time": "16:00",
            "cost_usd": 35,
            "description": "Explore museums, galleries, and cultural sites",
            "notes": "Check for combo tickets to save money",
        },
        {
            "name": "Local exploration",
            "type": "attraction",
            "start_time": "09:00",
            "end_time": "17:00",
            "cost_usd": 20,
            "description": "Walk through neighborhoods, markets, and hidden gems",
            "notes": "Wear comfortable shoes — lots of walking",
        },
        {
            "name": "Day trip / excursion",
            "type": "attraction",
            "start_time": "08:00",
            "end_time": "18:00",
            "cost_usd": 60,
            "description": "Visit nearby attractions outside the city center",
            "notes": "Book transport in advance for best prices",
        },
    ]

    days: list[dict[str, Any]] = []

    # Day 1 — arrival
    days.append({
        "day": 1,
        "date": start_date,
        "location": destination,
        "activities": [
            {
                "name": "Arrive & Check-In",
                "type": "hotel",
                "start_time": "14:00",
                "end_time": "15:00",
                "location": destination,
                "cost_usd": 0,
                "description": "Check into hotel and settle in",
            },
            {
                "name": "Explore local area",
                "type": "attraction",
                "start_time": "16:00",
                "end_time": "19:00",
                "location": destination,
                "cost_usd": 0,
                "description": "Light exploration of the neighborhood",
            },
        ],
        "total_cost_usd": 0,
        "notes": "Arrival day — take it easy",
    })

    # Middle days — themed activities
    for i in range(2, num_days):
        theme = _DAY_THEMES[(i - 2) % len(_DAY_THEMES)]
        activities = [
            {
                "name": "Breakfast",
                "type": "restaurant",
                "start_time": "08:00",
                "end_time": "09:00",
                "location": destination,
                "cost_usd": 15,
                "description": "Breakfast at local café",
            },
            {
                "name": theme["name"],
                "type": theme["type"],
                "start_time": theme["start_time"],
                "end_time": theme["end_time"],
                "location": destination,
                "cost_usd": theme["cost_usd"],
                "description": theme["description"],
            },
            {
                "name": "Dinner",
                "type": "restaurant",
                "start_time": "19:00",
                "end_time": "21:00",
                "location": destination,
                "cost_usd": 30,
                "description": "Dinner at a local restaurant",
            },
        ]
        total_cost = sum(a["cost_usd"] for a in activities)
        days.append({
            "day": i,
            "date": None,
            "location": destination,
            "activities": activities,
            "total_cost_usd": total_cost,
            "notes": theme.get("notes"),
        })

    # Last day — departure
    if num_days > 1:
        days.append({
            "day": num_days,
            "date": end_date,
            "location": destination,
            "activities": [
                {
                    "name": "Breakfast & check-out",
                    "type": "hotel",
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "location": destination,
                    "cost_usd": 15,
                    "description": "Final breakfast and check out of hotel",
                },
                {
                    "name": "Last-minute shopping / sightseeing",
                    "type": "attraction",
                    "start_time": "10:30",
                    "end_time": "13:00",
                    "location": destination,
                    "cost_usd": 20,
                    "description": "Pick up souvenirs or visit any missed spots",
                },
            ],
            "total_cost_usd": 35,
            "notes": "Departure day — allow extra time for transit to airport",
        })

    return {
        "days": days,
        "note": "Fallback itinerary — AI unavailable, activities are estimates",
        "destination": destination,
    }
