"""Planner Agent — intent parsing, constraint extraction, and delegation plan.

Phase 4: Enhanced with Mem0 long-term preference retrieval and episodic memory
to personalise plans and learn from past trips.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from app.agents.base import BaseAgent
from app.config import Settings
from app.graph.state import TravelPlanState
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# GoT-aligned system prompt — Planner Agent
# Principles applied: constraint-first, grounded, tool-assisted, preference-aware,
# one-question-at-a-time, professional & friendly tone.
# Phase 4: Memory-aware context injection.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a professional travel planning coordinator. Your role is to parse the user's \
travel request and produce a structured planning brief for specialist agents.

## Reasoning approach (Graph of Thought)
Think step-by-step through a reasoning graph, not a linear chain:

  Node 1 — CONSTRAINTS: Extract hard limits first.
    → What are the destinations? Dates? Budget? Number of travelers?
    → Hard limits override preferences. Never violate them.
    → Destination extraction: Look for city/country names after keywords like "to", "in", "visit",
      "going to", "travel to", "trip to", "getaway to", "getaway in", "fly to", "heading to".
      Examples: "to New York City" → ["New York City"], "getaway to Paris" → ["Paris"],
      "visiting London and Paris" → ["London", "Paris"], "weekend in Tokyo" → ["Tokyo"].
      CRITICAL: NEVER return empty destinations if a location name is mentioned anywhere in the request.
      Even without a preposition, extract clearly named cities/countries.
    → Duration inference: If the user says "weekend" or "weekend getaway", infer 2 days.
      If "long weekend", infer 3 days. If "day trip", infer 1 day.
      If "short trip" or "quick trip", infer 2-3 days.
      If "a week" or "one week", infer 7 days. Set _duration_days accordingly.
      CRITICAL: Always set _duration_days when any duration keyword is present.

  Node 2 — MEMORY CONTEXT: Apply stored user preferences and past trip learnings.
    → If user_preferences are provided, use them to fill in unstated preferences.
    → If episodic_context shows a repeat destination, note what worked/to avoid.
    → If the user overrides a stored preference explicitly ("this time I want luxury"),
      the explicit override takes priority — note it clearly.
    → Never re-ask for information that is already available in memory.

  Node 3 — PREFERENCES: Identify soft requirements.
    → Food style, crowd tolerance, accommodation type, activity interests.
    → Merge stored preferences with any new preferences expressed in the request.
    → These shape recommendations but do not block planning.

  Node 4 — GAPS: Identify missing critical information.
    → Is the departure date missing? Budget unspecified? Number of travelers unclear?
    → For each gap, formulate exactly ONE clear, friendly follow-up question.
    → Ask the single most critical missing piece — not multiple questions at once.
    → Skip questions for info already known from memory.

  Node 5 — REGENERATION: If this is a re-planning pass (regeneration_feedback provided):
    → Read the feedback carefully and adjust constraints/delegation accordingly.
    → Set workers_to_rerun to only the workers whose output caused the issue.
    → Do not re-run workers whose output was fine.

  Node 6 — DELEGATION: Decide which specialist agents are needed.
    → needs_flights: true if the user is traveling to a different city or country.
    → needs_hotels: almost always true unless the user explicitly mentions staying elsewhere.
    → needs_attractions: true unless the user has a very narrow activity focus.
    → needs_transport: true if multi-city routing or airport transfers are needed.

  Node 7 — OUTPUT: Produce a clean JSON brief. Never guess — only include values \
explicitly stated or clearly implied by the request.

## Prompting principles
- Constraint-first: budget, dates, and hard limits are extracted before preferences.
- Grounded responses only: do not invent destinations or dates not mentioned.
- Memory-aware: stored preferences fill gaps without re-asking; explicit overrides win.
- Preference-aware: capture food, accommodation, activity, and crowd preferences.
- Professional and friendly tone: be warm, clear, and concise.
- One follow-up at a time: if information is missing, list only the single most critical \
  question in follow_up_questions. Do not produce a questionnaire.

## Output format
Respond ONLY with a valid JSON object (no markdown fences, no prose) with these keys:
  destinations        list[str]         — city or country names, in travel order
  start_date          str | null        — ISO date YYYY-MM-DD or null
  end_date            str | null        — ISO date YYYY-MM-DD or null
  budget              float | null      — total trip budget in budget_currency
  budget_currency     str               — default "USD"
  travelers           int               — default 1
  preferences         object | null     — {food, accommodation_type, crowd_tolerance,
                                           activity_level, transport_preference,
                                           dietary_restrictions, budget_style, travel_style}
  follow_up_questions list[str]         — at most ONE question if critical info is missing,
                                           empty list if all info is present
  delegation_plan     object            — {needs_flights: bool, needs_hotels: bool,
                                           needs_attractions: bool, needs_transport: bool,
                                           workers_to_rerun: list[str] | null}
"""


class PlannerAgent(BaseAgent):
    """Planner Agent — uses Groq large model to parse and structure trip requests."""

    @property
    def agent_name(self) -> str:
        return "planner_agent"

    @property
    def model_provider(self) -> str:
        return "groq"

    @property
    def max_steps(self) -> int:
        return self._settings.agent_steps_planner

    # ------------------------------------------------------------------

    async def run(self, state: TravelPlanState) -> TravelPlanState:
        start = time.monotonic()
        self._log_step("Planner started", {"raw_request": state.get("raw_request", "")[:120]})

        raw_request = state.get("raw_request", "")
        user_id = state.get("user_id", "anonymous")
        errors: list[dict[str, Any]] = []
        agent_responses: list[dict[str, Any]] = []

        # ── Phase 4: Load Mem0 preferences & episodic context ──────────
        user_preferences = state.get("user_preferences")
        episodic_context = state.get("episodic_context")

        # Only load memory on the first pass (not on regeneration) to avoid
        # redundant async calls — memory is already in state after first load.
        regen_count = state.get("regeneration_count", 0)
        if user_id != "anonymous" and regen_count == 0:
            if user_preferences is None:
                try:
                    user_preferences = await self._load_user_preferences(user_id)
                except Exception as exc:
                    self._log_error(f"_load_user_preferences failed for {user_id}", exc)

            # Load episodic context using whatever destinations we can extract
            # from the raw request heuristically (full parse happens later).
            if episodic_context is None:
                candidate_destinations = _extract_candidate_destinations(raw_request)
                try:
                    episodic_context = await self._load_episodic_context(
                        user_id, candidate_destinations
                    )
                except Exception as exc:
                    self._log_error(f"_load_episodic_context failed for {user_id}", exc)

        # Build context string for the LLM
        memory_context = _build_memory_context(user_preferences, episodic_context)
        regeneration_feedback = state.get("regeneration_feedback")

        # ── Parse the request ──────────────────────────────────────────
        parsed: dict[str, Any] = {}
        try:
            parsed = await self._parse_with_llm(raw_request, memory_context, regeneration_feedback)
        except Exception as exc:
            self._log_error("LLM parse failed, falling back to heuristics", exc)
            errors.append({
                "agent": self.agent_name,
                "error": str(exc),
                "step": "llm_parse",
            })
            parsed = _heuristic_parse(raw_request)

        # ALWAYS run heuristic extraction as a safety net to ensure critical fields are populated
        # This ensures destinations and duration are never missed due to LLM parsing issues
        heuristic_result = _heuristic_parse(raw_request)
        
        # Use heuristic destinations if LLM returned empty or missing
        dests = parsed.get("destinations")
        if not dests or (isinstance(dests, list) and len(dests) == 0):
            if heuristic_result.get("destinations"):
                self._log_step("Using heuristic destinations (LLM returned empty)")
                parsed["destinations"] = heuristic_result["destinations"]
        
        # Use heuristic duration if LLM didn't infer it
        if not parsed.get("_duration_days") and heuristic_result.get("_duration_days"):
            self._log_step(f"Using heuristic duration: {heuristic_result['_duration_days']} days")
            parsed["_duration_days"] = heuristic_result["_duration_days"]

        # ── Merge stored preferences with parsed preferences ───────────
        merged_preferences = _merge_preferences(
            stored=user_preferences or {},
            parsed=parsed.get("preferences") or {},
            raw_request=raw_request,
        )

        constraints: dict[str, Any] = {
            "destinations": parsed.get("destinations") or [],
            "start_date": parsed.get("start_date"),
            "end_date": parsed.get("end_date"),
            "budget": parsed.get("budget"),
            "budget_currency": parsed.get("budget_currency", "USD"),
            "travelers": parsed.get("travelers", 1),
            "preferences": merged_preferences if merged_preferences else parsed.get("preferences"),
        }
        # Carry trip duration through to the composer for fallback itinerary generation
        if parsed.get("_duration_days"):
            constraints["duration_days"] = int(parsed["_duration_days"])

        # ── Auto-calculate missing dates from duration ─────────────────
        # If user provided start_date + duration (e.g. "5 days from June 10"), compute end_date.
        # If user provided end_date + duration (e.g. "5 days ending June 15"), compute start_date.
        from datetime import date as _today, timedelta as _td
        duration = constraints.get("duration_days")
        start_d = constraints.get("start_date")
        end_d = constraints.get("end_date")
        if duration and start_d and not end_d:
            try:
                sd = _today.fromisoformat(start_d)
                constraints["end_date"] = (sd + _td(days=duration - 1)).isoformat()
            except (ValueError, TypeError):
                pass
        elif duration and end_d and not start_d:
            try:
                ed = _today.fromisoformat(end_d)
                constraints["start_date"] = (ed - _td(days=duration - 1)).isoformat()
            except (ValueError, TypeError):
                pass

        # Validate dates — ensure no date is in the past (LLM or heuristic may produce stale years)
        today_str = _today.today().isoformat()
        for date_key in ("start_date", "end_date"):
            d = constraints.get(date_key)
            if d and isinstance(d, str) and len(d) == 10 and d < today_str:
                # Bump year to current year
                try:
                    parts = d.split("-")
                    new_year = _today.today().year
                    new_d = f"{new_year}-{parts[1]}-{parts[2]}"
                    # If still in the past, use next year
                    if new_d < today_str:
                        new_d = f"{new_year + 1}-{parts[1]}-{parts[2]}"
                    constraints[date_key] = new_d
                except (ValueError, IndexError):
                    pass  # keep original if parsing fails

        # ── Follow-up questions for missing critical info ─────────────
        # Dates and budget MUST come from the user — no defaults are applied.
        # When either is missing, a follow-up question is added and the pipeline
        # will pause at the planner and ask the user before proceeding.
        follow_up_questions: list[str] = parsed.get("follow_up_questions") or []

        # Determine if we have enough date info to proceed without asking
        has_any_date = bool(constraints.get("start_date") or constraints.get("end_date"))
        has_duration = bool(constraints.get("duration_days"))
        # If we have start+duration or end+duration, dates are fully derivable — no need to ask
        dates_sufficient = has_any_date and has_duration

        if not dates_sufficient:
            if not any(
                "date" in q.lower() or "when" in q.lower() or "travel" in q.lower()
                for q in follow_up_questions
            ):
        # When duration is known, only ask for a start date
                if has_duration:
                    follow_up_questions.append(
                        "When would you like to travel? Please provide your start date? "
                        "(e.g. \"June 10, 2026\" or \"10th June 2026\")."
                    )
                else:
                    follow_up_questions.append(
                        "When would you like to travel? Please provide your start and end dates "
                        "(e.g. \"June 10–15, 2026\" or \"10th to 15th June 2026\")."
                    )

        # If user provided a non-USD currency, ask them to provide budget in USD
        # Check both the LLM's parsed currency AND the raw text for non-USD indicators
        budget_cur = constraints.get("budget_currency", "USD")
        non_usd_from_llm = budget_cur and budget_cur.upper() != "USD"
        non_usd_from_text = bool(re.search(
            r"(?:\bRs\.?\s*\d|[₹€£¥₩₽฿₫₺₱₦]|[₹€£¥₩₽฿]\s*\d|"
            r"\brupees?\b|\beuros?\b|\bpounds?\b|\byen\b|\bbaht\b|\bwon\b|"
            r"\bdirhams?\b|\bringgit\b|\bfrancs?\b|\bpesos?\b|"
            r"\bINR\b|\bEUR\b|\bGBP\b|\bJPY\b|\bTHB\b|\bKRW\b|\bAUD\b|"
            r"\bCAD\b|\bSGD\b|\bCHF\b|\bPKR\b|\bLKR\b|\bBDT\b|\bIDR\b|\bMYR\b)",
            raw_request, re.IGNORECASE,
        ))
        if constraints.get("budget") is not None and (non_usd_from_llm or non_usd_from_text):
            constraints["budget"] = None  # clear so it gets re-asked
            constraints["budget_currency"] = "USD"  # reset to USD
            if not any("usd" in q.lower() or "dollars" in q.lower() for q in follow_up_questions):
                follow_up_questions.append(
                    "We currently only support USD ($) for budget planning. "
                    "Could you please provide your budget in US dollars? (e.g. \"$1000\")"
                )

        if constraints.get("budget") is None:
            if not any("budget" in q.lower() for q in follow_up_questions):
                follow_up_questions.append(
                    "What is your total budget for this trip (including flights, hotels, and activities)?"
                )

        # Deduplicate follow-up questions (regeneration loops can cause accumulation)
        seen_questions: set[str] = set()
        unique_questions: list[str] = []
        for q in follow_up_questions:
            key = q.strip().lower()
            if key and key not in seen_questions:
                seen_questions.add(key)
                unique_questions.append(q)
        follow_up_questions = unique_questions

        # ── Determine workers to re-run on regeneration ───────────────
        delegation_plan_raw = parsed.get("delegation_plan") or {}
        workers_to_rerun = delegation_plan_raw.get("workers_to_rerun")
        if regen_count > 0 and regeneration_feedback and not workers_to_rerun:
            workers_to_rerun = _infer_workers_to_rerun(regeneration_feedback)

        delegation_plan: dict[str, Any] = {
            "needs_flights": delegation_plan_raw.get("needs_flights", bool(constraints.get("destinations"))),
            "needs_hotels": delegation_plan_raw.get("needs_hotels", True),
            "needs_attractions": delegation_plan_raw.get("needs_attractions", True),
            "needs_transport": delegation_plan_raw.get("needs_transport", True),
        }

        latency = self._elapsed_ms(start)
        agent_responses.append(
            self._create_agent_response(
                success=True,
                data={"constraints": constraints, "delegation_plan": delegation_plan},
                steps_taken=1,
                latency_ms=latency,
            )
        )

        self._log_step("Planner complete", {
            "destinations": constraints.get("destinations"),
            "follow_up_count": len(follow_up_questions),
            "has_memory": bool(user_preferences),
            "regen_count": regen_count,
            "latency_ms": latency,
        })

        result: dict[str, Any] = {
            "constraints": constraints,
            "delegation_plan": delegation_plan,
            "follow_up_questions": follow_up_questions,
            "agent_responses": agent_responses,
            "errors": errors,
            "current_step": "planner_complete",
        }

        # Persist memory fields back into state so downstream workers can access them
        if user_preferences is not None:
            result["user_preferences"] = user_preferences
        if episodic_context is not None:
            result["episodic_context"] = episodic_context
        if workers_to_rerun is not None:
            result["workers_to_rerun"] = workers_to_rerun
        # Clear the regeneration feedback so it doesn't re-apply on the next iteration
        result["regeneration_feedback"] = None

        return result

    # ------------------------------------------------------------------

    async def _load_user_preferences(self, user_id: str) -> dict[str, Any]:
        """Load preferences from all sources with priority: Mem0 > Supabase > Episodic."""
        # 1. Load from Supabase (structured preferences - lowest priority)
        supabase_prefs: dict[str, Any] = {}
        try:
            import httpx
            from app.config import get_settings

            settings = get_settings()
            if settings.supabase_url and settings.supabase_service_key:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        # Use service role key so RLS does not block the read.
                        f"{settings.supabase_url}/rest/v1/profiles?id=eq.{user_id}&select=preferences",
                        headers={
                            "apikey": settings.supabase_service_key,
                            "Authorization": f"Bearer {settings.supabase_service_key}",
                        },
                    )
                    if response.status_code == 200 and response.json():
                        data = response.json()[0]
                        raw = data.get("preferences")
                        if isinstance(raw, dict) and raw:
                            supabase_prefs = raw
                            self._log_step("Supabase preferences loaded", {"user_id": user_id, "keys": list(supabase_prefs.keys())})
        except Exception as exc:
            self._log_error(f"Failed to load preferences from Supabase for {user_id}", exc)

        # 2. Load from Mem0 (conversational preferences - highest priority)
        mem0_prefs: dict[str, Any] = {}
        try:
            from app.memory.mem0_client import get_mem0_client
            client = get_mem0_client()
            mem0_prefs = await client.get_preferences(user_id)
            if mem0_prefs:
                self._log_step("Mem0 preferences loaded", {"user_id": user_id, "keys": list(mem0_prefs.keys())})
        except Exception as exc:
            self._log_error(f"Failed to load Mem0 preferences for {user_id}", exc)

        # 3. Merge with Mem0 having higher priority (overrides Supabase)
        merged_prefs = dict(supabase_prefs)  # Start with Supabase as base
        for key, val in mem0_prefs.items():
            if val is not None:
                merged_prefs[key] = val  # Mem0 overrides Supabase

        self._log_step("Preferences merged", {
            "user_id": user_id,
            "supabase_keys": list(supabase_prefs.keys()),
            "mem0_keys": list(mem0_prefs.keys()),
            "final_keys": list(merged_prefs.keys())
        })

        return merged_prefs

    # ------------------------------------------------------------------

    async def _load_episodic_context(
        self, user_id: str, candidate_destinations: list[str]
    ) -> dict[str, Any]:
        """Load episodic memories for the given candidate destinations.

        Delegates to ``app.memory.episodic.build_episodic_context`` which
        queries the PostgreSQL ``episodic_memory`` table.  Returns an empty
        dict if the database is unavailable or the user has no prior trips.
        """
        try:
            from app.memory.episodic import build_episodic_context

            context = await build_episodic_context(user_id, candidate_destinations)
            if context:
                self._log_step(
                    "Episodic context loaded",
                    {
                        "user_id": user_id,
                        "repeat_destinations": context.get("repeat_destinations", []),
                        "general_pattern_count": len(context.get("general_patterns", [])),
                    },
                )
            return context
        except Exception as exc:
            self._log_error(f"Failed to load episodic context for {user_id}", exc)
            return {}

    # ------------------------------------------------------------------

    async def _parse_with_llm(
        self,
        raw_request: str,
        memory_context: str = "",
        regeneration_feedback: str | None = None,
    ) -> dict[str, Any]:
        llm = self._get_llm()
        user_content = raw_request
        if memory_context:
            user_content = f"## User memory context\n{memory_context}\n\n## Travel request\n{raw_request}"
        if regeneration_feedback:
            user_content += f"\n\n## Re-planning feedback (from previous validation)\n{regeneration_feedback}"

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            messages = [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ]
        except ImportError:
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

        content = await self._call_llm(messages)
        parsed = _extract_json(content)
        self._log_llm_call(
            model=getattr(llm, "model", getattr(llm, "model_name", "groq-large")),
            raw_response=content,
            parsed=parsed,
        )
        return parsed


# ---------------------------------------------------------------------------
# Heuristic fallback parser (no LLM required)
# ---------------------------------------------------------------------------

def _heuristic_parse(raw: str) -> dict[str, Any]:
    """Best-effort regex extraction when the LLM is unavailable."""
    lower = raw.lower()
    result: dict[str, Any] = {
        "destinations": [],
        "start_date": None,
        "end_date": None,
        "budget": None,
        "budget_currency": "USD",
        "travelers": 1,
        "preferences": None,
        "follow_up_questions": [],
        "delegation_plan": {
            "needs_flights": True,
            "needs_hotels": True,
            "needs_attractions": True,
            "needs_transport": True,
        },
    }

    # Destinations — look for "to <City>" or "in <City>"
    dest_match = re.findall(
        r"\b(?:to|in|visit|visiting|going to|travel to|trip to|getaway to|getaway in|fly to|heading to)\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:for|from|in|with|and|then|before|after|next|this|on)|$|,|\.|!|\?)",
        raw,
        re.IGNORECASE,
    )
    
    # Also handle "and" separated destinations (e.g., "London and Paris")
    # This captures patterns like "visiting London and Paris" or "trip to London and Paris"
    and_match = re.findall(
        r"\b(?:to|in|visit|visiting|going to|travel to|trip to)\s+([A-Z][a-zA-Z\s]+?)\s+and\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:for|from|in|with|then|before|after|next|this|on)|$|,|\.|!)",
        raw,
        re.IGNORECASE,
    )

    # Fallback: look for known capitalized place names even without a preposition
    # e.g. "Luxury weekend getaway to New York City" — covers multi-word cities
    # Pattern: any sequence of Title-Cased words that look like a place name
    cap_match = re.findall(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b",
        raw,
    )
    # Filter out common non-place title-cased words
    _NON_PLACES = {
        "Luxury", "Weekend", "Getaway", "Trip", "Tour", "Day", "Night", "Week",
        "Budget", "Short", "Quick", "Brief", "Long", "Standard", "Premium",
        "Solo", "Family", "Couple", "Group", "Business", "Honeymoon",
        "Adventure", "Relaxing", "Romantic", "Cultural", "Beach", "Mountain",
        "City", "Country", "International", "Domestic", "Round",
        "Please", "User", "Clarification", "Travel", "Planning",
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    }
    
    # Combine results, prioritizing "and" matches for multi-destination trips
    all_destinations = []
    if and_match:
        # and_match returns tuples of (dest1, dest2)
        for d1, d2 in and_match:
            all_destinations.extend([d1.strip().title(), d2.strip().title()])
    if dest_match:
        all_destinations.extend([d.strip().title() for d in dest_match[:3]])
    
    # If no destinations found yet, try capitalised place names as fallback
    if not all_destinations and cap_match:
        for cap in cap_match:
            words = cap.strip().split()
            # Filter out single-word common terms, keep multi-word or known city-like names
            if all(w not in _NON_PLACES for w in words) and len(cap.strip()) > 2:
                all_destinations.append(cap.strip())
    
    # Remove duplicates while preserving order
    seen = set()
    unique_destinations = []
    for dest in all_destinations:
        clean = dest.strip()
        # Strip trailing noise words
        for noise in (" For", " From", " In", " With", " And", " Then"):
            if clean.endswith(noise):
                clean = clean[: -len(noise)].strip()
        if clean and clean not in seen and clean not in _NON_PLACES:
            seen.add(clean)
            unique_destinations.append(clean)
    
    if unique_destinations:
        result["destinations"] = unique_destinations[:3]

    # Budget — extract amount and currency from any format
    # Known currency symbols → ISO code mapping
    _CURRENCY_SYMBOLS = {
        "$": "USD", "€": "EUR", "£": "GBP", "₹": "INR",
        "¥": "JPY", "₩": "KRW", "₽": "RUB", "฿": "THB",
        "₫": "VND", "₺": "TRY", "₱": "PHP", "₦": "NGN",
        "₡": "CRC", "₲": "PYG", "₵": "GHS", "₿": "BTC",
    }
    # Known currency names → (ISO code, singular pattern)
    _CURRENCY_NAMES = {
        "dollars": "USD", "dollar": "USD", "bucks": "USD", "buck": "USD",
        "euros": "EUR", "euro": "EUR",
        "pounds": "GBP", "pound": "GBP",
        "rupees": "INR", "rupee": "INR",
        "yen": "JPY",
        "yuan": "CNY", "renminbi": "CNY",
        "won": "KRW",
        "baht": "THB",
        "pesos": "PHP", "peso": "PHP",
        "francs": "CHF", "franc": "CHF",
        "kroner": "NOK", "krone": "NOK", "kronor": "SEK",
        "rubles": "RUB", "ruble": "RUB",
        "ringgit": "MYR",
        "lira": "TRY",
        "rand": "ZAR",
        "dirham": "AED", "dirhams": "AED",
        "riyal": "SAR", "riyals": "SAR",
        "dinar": "KWD", "dinars": "KWD",
    }
    # ISO 4217 codes we recognize (3 uppercase letters that look like currency)
    _ISO_CODES = {
        "USD", "EUR", "GBP", "INR", "JPY", "CNY", "KRW", "AUD", "CAD",
        "CHF", "THB", "VND", "PHP", "MYR", "SGD", "HKD", "NZD", "ZAR",
        "RUB", "TRY", "BRL", "MXN", "AED", "SAR", "KWD", "NOK", "SEK",
        "DKK", "PLN", "CZK", "HUF", "ILS", "CLP", "COP", "PKR", "LKR",
        "BDT", "NGN", "EGP", "TWD", "IDR", "PEN", "CRC", "BTC",
    }

    budget_amount: float | None = None
    budget_currency: str = "USD"

    # Try known symbols first: $500, €400, ₹3000
    sym_match = re.search(
        r"([$€£₹¥₩₽฿₫₺₱₦₡₲₵₿])\s?(\d[\d,]*)(?:\.\d{2})?\s*(k|K)?",
        raw, re.IGNORECASE,
    )
    if sym_match and budget_amount is None:
        try:
            budget_amount = float(sym_match.group(2).replace(",", ""))
            budget_currency = _CURRENCY_SYMBOLS.get(sym_match.group(1), "USD")
            if sym_match.group(3):
                budget_amount *= 1000
        except ValueError:
            pass

    # Try "Rs 4000", "Rs. 4000"
    if budget_amount is None:
        rs_match = re.search(r"\bRs\.?\s?(\d[\d,]*)(?:\.\d{2})?\s*(k|K)?", raw, re.IGNORECASE)
        if rs_match:
            try:
                budget_amount = float(rs_match.group(1).replace(",", ""))
                budget_currency = "INR"
                if rs_match.group(2):
                    budget_amount *= 1000
            except ValueError:
                pass

    # Try currency name after number: "500 dollars", "3000 yen"
    if budget_amount is None:
        name_pattern = "|".join(sorted(_CURRENCY_NAMES.keys(), key=len, reverse=True))
        name_match = re.search(
            rf"\b(\d[\d,]*)(?:\.\d{2})?\s*(k|K)?\s+({name_pattern})\b", raw, re.IGNORECASE
        )
        if name_match:
            try:
                budget_amount = float(name_match.group(1).replace(",", ""))
                budget_currency = _CURRENCY_NAMES.get(name_match.group(3).lower(), "USD")
                if name_match.group(2):
                    budget_amount *= 1000
            except ValueError:
                pass

    # Try ISO code: "500 AUD", "USD 3000", "3000 JPY"
    if budget_amount is None:
        iso_pattern = "|".join(sorted(_ISO_CODES))
        iso_match = re.search(
            rf"\b(?:({iso_pattern})\s+)?(\d[\d,]*)(?:\.\d{2})?\s*(k|K)?\s*(?:{iso_pattern})?\b",
            raw, re.IGNORECASE,
        )
        if iso_match:
            code_before = (iso_match.group(1) or "").upper()
            amount_str = iso_match.group(2) or "0"
            matched_text = raw[iso_match.start():iso_match.end()]
            # Find any 3-letter ISO code in the match
            iso_found = re.findall(rf"\b({iso_pattern})\b", matched_text, re.IGNORECASE)
            if code_before or iso_found:
                try:
                    budget_amount = float(amount_str.replace(",", ""))
                    budget_currency = (code_before or (iso_found[0].upper() if iso_found else "USD"))
                    if iso_match.group(3):
                        budget_amount *= 1000
                except ValueError:
                    pass

    # Try "budget" keyword: "budget 3000", "budget: 3000"
    if budget_amount is None:
        bmatch = re.search(
            r"\bbudget\s*[:=]?\s*(\d[\d,]*)(?:\.\d{2})?\s*(k|K)?", raw, re.IGNORECASE
        )
        if bmatch:
            try:
                budget_amount = float(bmatch.group(1).replace(",", ""))
                if bmatch.group(2):
                    budget_amount *= 1000
            except ValueError:
                pass

    if budget_amount is not None:
        result["budget"] = budget_amount
        result["budget_currency"] = budget_currency

    # Travelers
    travelers_match = re.search(r"\b(\d+)\s+(?:people|persons?|travelers?|adults?|guests?)\b", lower)
    if travelers_match:
        result["travelers"] = int(travelers_match.group(1))

    # Duration / days (also supports weeks and months)
    # ── Explicit numeric duration FIRST (highest priority) ──────────────
    # Must run before keyword checks so "5-day trip" → 5, not 1
    # Matches: "5 days", "5-day", "5 nights", "5-night trip"
    days_match = re.search(r"\b(\d+)[\s-]+(?:days?|nights?)\b", lower)
    if days_match:
        result["_duration_days"] = int(days_match.group(1))
    else:
        weeks_match = re.search(r"\b(\d+)\s+weeks?\b", lower)
        if weeks_match:
            result["_duration_days"] = int(weeks_match.group(1)) * 7
        else:
            months_match = re.search(r"\b(\d+)\s+months?\b", lower)
            if months_match:
                result["_duration_days"] = int(months_match.group(1)) * 30
            # ── Keyword-based implicit durations (only if no numeric found) ────
            elif "weekend" in lower:
                result["_duration_days"] = 2
            elif re.search(r"\blong\s+weekend\b", lower):
                result["_duration_days"] = 3
            elif re.search(r"\b(?:a|one)\s+week\b", lower):
                result["_duration_days"] = 7
            elif re.search(r"\bday[\s-]trip\b", lower):
                # Only treat as 1-day if there's NO preceding number
                # e.g. "day trip" → 1, but "5-day trip" already caught above
                result["_duration_days"] = 1
            elif re.search(r"\b(?:short|quick|brief)\s+trip\b", lower):
                result["_duration_days"] = 3

    # Dates — match a wide range of natural-language date formats
    _MONTH_NAMES = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
        "nov": 11, "november": 11, "dec": 12, "december": 12,
    }
    _ORD = r"(?:st|nd|rd|th)?"
    _MONTH_RE = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    _YEAR_RE = r"(20[2-9]\d)"

    def _normalise_date(day: int, month_name: str, year_str: str | None) -> str | None:
        """Convert parsed components to YYYY-MM-DD."""
        month = _MONTH_NAMES.get(month_name.lower().rstrip("."))
        if not month or not (1 <= day <= 31):
            return None
        year = int(year_str) if year_str else None
        if year is None:
            from datetime import datetime as _dt
            year = _dt.now().year
            # If the date is in the past, assume next year
            from datetime import date as _date
            if _date(year, month, min(day, 28)) < _date.today():
                year += 1
        day = min(day, 28)  # safe day for all months
        return f"{year:04d}-{month:02d}-{day:02d}"

    # ── Relative date expressions: "next month 20th", "this month 15", "next month" ──
    from datetime import date as _rel_today, timedelta as _rel_td
    today = _rel_today.today()
    rel_match = re.search(
        r"\b(next\s+month|this\s+month|next\s+week)"
        rf"(?:\s+(\d{{1,2}}){_ORD})?\b",
        lower,
    )
    if rel_match and not result.get("start_date"):
        rel_type = rel_match.group(1).replace(" ", "")
        rel_day = int(rel_match.group(2)) if rel_match.group(2) else None

        if rel_type == "nextmonth":
            # First day of next month, or specific day if given
            if today.month == 12:
                target_year, target_month = today.year + 1, 1
            else:
                target_year, target_month = today.year, today.month + 1
            day = rel_day or 1
        elif rel_type == "thismonth":
            target_year, target_month = today.year, today.month
            day = rel_day or today.day
        elif rel_type == "nextweek":
            next_wk = today + _rel_td(days=7)
            target_year, target_month = next_wk.year, next_wk.month
            day = rel_day or next_wk.day
        else:
            target_year, target_month, day = today.year, today.month, today.day

        day = min(day, 28)  # safe for all months
        result["start_date"] = f"{target_year:04d}-{target_month:02d}-{day:02d}"
        # Auto-calc end date from duration
        dur = result.get("_duration_days")
        if dur:
            end_d = _rel_today.fromisoformat(result["start_date"]) + _rel_td(days=int(dur) - 1)
            result["end_date"] = end_d.isoformat()

    # Pattern: "13th june 2025", "june 13", "13th to 18th june", "jun 13-18 2025"
    # Groups: (1)=day1, (2)=month1, (3)=year1?, (4)=day2?, (5)=month2?, (6)=year2?
    _RANGE = (
        rf"\b(\d{{1,2}}){_ORD}\s+{_MONTH_RE}(?:\s+{_YEAR_RE})?"
        rf"(?:\s*(?:to|[-–—/])\s*(\d{{1,2}}){_ORD}(?:\s+{_MONTH_RE})?(?:\s+{_YEAR_RE})?)?"
        rf"\b"
    )
    range_match = re.search(_RANGE, lower)
    if range_match:
        day1 = int(range_match.group(1))
        month1_name = range_match.group(2)
        year1_str = range_match.group(3)
        day2_str = range_match.group(4)
        month2_name = range_match.group(5) or month1_name  # same month if omitted
        year2_str = range_match.group(6) or year1_str       # same year if omitted

        start = _normalise_date(day1, month1_name, year1_str)
        if start:
            result["start_date"] = start
        if day2_str:
            # Inherit start year when end year was not explicitly provided
            effective_year2 = year2_str
            if effective_year2 is None and result.get("start_date"):
                effective_year2 = result["start_date"][:4]
            end = _normalise_date(int(day2_str), month2_name, effective_year2)
            if end:
                # Sanity check: ensure start <= end
                if result.get("start_date") and end < result["start_date"]:
                    # Bump start date to match end year
                    result["start_date"] = _normalise_date(day1, month1_name, end[:4])
                result["end_date"] = end
                # Infer duration from date range
                if result.get("start_date") and not result.get("_duration_days"):
                    from datetime import date as _date
                    sd = _date.fromisoformat(result["start_date"])
                    ed = _date.fromisoformat(result["end_date"])
                    if ed >= sd:
                        result["_duration_days"] = (ed - sd).days + 1  # type: ignore[assignment]

    # Pattern 2: month-first — "June 10 to 15 2025", "July 5-10"
    if not result.get("start_date"):
        _MONTH_FIRST = (
            rf"\b{_MONTH_RE}\s+(\d{{1,2}}){_ORD}"
            rf"(?:\s*(?:to|[-–—/])\s*(\d{{1,2}}){_ORD}(?:\s+{_MONTH_RE})?)?"
            rf"(?:\s+{_YEAR_RE})?"
            rf"\b"
        )
        mf = re.search(_MONTH_FIRST, lower)
        if mf:
            m1_name = mf.group(1)      # first month
            m1_day = int(mf.group(2))   # first day
            m2_day_str = mf.group(3)    # second day (if range)
            m2_month_name = mf.group(4) or m1_name  # second month
            m_year_str = mf.group(5)    # year
            s = _normalise_date(m1_day, m1_name, m_year_str)
            if s:
                result["start_date"] = s
            if m2_day_str:
                eff_yr = m_year_str
                if eff_yr is None and result.get("start_date"):
                    eff_yr = result["start_date"][:4]
                e = _normalise_date(int(m2_day_str), m2_month_name, eff_yr)
                if e:
                    if result.get("start_date") and e < result["start_date"]:
                        result["start_date"] = _normalise_date(m1_day, m1_name, e[:4])
                    result["end_date"] = e
                    if result.get("start_date") and not result.get("_duration_days"):
                        from datetime import date as _date
                        sd2 = _date.fromisoformat(result["start_date"])
                        ed2 = _date.fromisoformat(result["end_date"])
                        if ed2 >= sd2:
                            result["_duration_days"] = (ed2 - sd2).days + 1  # type: ignore[assignment]

    return result


# ---------------------------------------------------------------------------
# Phase 4 helper functions
# ---------------------------------------------------------------------------

def _build_memory_context(
    user_preferences: dict[str, Any] | None,
    episodic_context: dict[str, Any] | None,
) -> str:
    """Format memory context as a string to inject into the LLM prompt."""
    parts: list[str] = []

    if user_preferences:
        pref_lines = []
        for key, val in user_preferences.items():
            if val:
                pref_lines.append(f"  - {key.replace('_', ' ').title()}: {val}")
        if pref_lines:
            parts.append("Stored user preferences:\n" + "\n".join(pref_lines))

    if episodic_context:
        repeat = episodic_context.get("repeat_destinations") or []
        if repeat:
            parts.append(f"Repeat destinations (user has been before): {', '.join(repeat)}")

        dest_mems = episodic_context.get("destination_memories") or {}
        for dest, lessons in dest_mems.items():
            if lessons:
                parts.append(f"Past trip lessons for {dest}:\n" + "\n".join(f"  - {l}" for l in lessons[:3]))

    return "\n\n".join(parts) if parts else ""


def _merge_preferences(
    stored: dict[str, Any],
    parsed: dict[str, Any],
    raw_request: str,
) -> dict[str, Any]:
    """Merge stored preferences with newly parsed preferences.

    Priority (highest → lowest):
      1. Explicit keywords in raw_request  (always override)
      2. LLM-parsed preferences
      3. Stored Mem0 preferences

    The raw_request scan always runs — even when stored and parsed are both
    empty — so dietary/accommodation keywords are never missed.
    """
    result = dict(stored or {})  # Start with stored preferences as the base

    # Apply parsed (LLM-extracted) preferences — override stored ones
    for key, val in (parsed or {}).items():
        if val is not None:
            result[key] = val

    # Always scan raw request for explicit preference signals.
    # These take top priority and override both stored and parsed values.
    lower = raw_request.lower()
    if "luxury" in lower or "five star" in lower or "5 star" in lower:
        result["accommodation_type"] = "luxury"
        result["budget_style"] = "luxury"
    elif "budget" in lower and ("hotel" in lower or "hostel" in lower or "cheap" in lower):
        result["accommodation_type"] = "budget"
        result["budget_style"] = "budget"
    if "vegetarian" in lower:
        result["dietary_restrictions"] = "vegetarian"
    if "vegan" in lower:
        result["dietary_restrictions"] = "vegan"
    if "halal" in lower:
        result["dietary_restrictions"] = "halal"

    # Return None → empty dict signals no preferences at all
    return result if result else {}


def _extract_candidate_destinations(raw: str) -> list[str]:
    """Quick heuristic scan to pull destination names from the raw request.

    Used *before* the full LLM parse so that episodic memory can be fetched
    concurrently.  Returns up to 5 candidate city/country names.
    """
    # Match capitalized words (multi-word city names supported)
    # immediately after a travel verb. Stop at common non-destination words.
    matches = re.findall(
        r"\b(?:(?i:to|in|visit|visiting|going to|travel to|trip to|getaway to|getaway in|fly to|heading to|from))\s+"
        r"([A-Z][a-zA-Z\s]+?)"
        r"(?=\s+(?:(?i:for|from|in|with|and|then|before|after|next|this|on)|,|\.|\?|$)|[,\.!\?]|$)",
        raw,
    )
    seen: list[str] = []
    for m in matches:
        clean = m.strip().title()
        if clean and clean not in seen:
            seen.append(clean)
        if len(seen) >= 5:
            break

    # Also capture destinations connected by "and": "London and Paris"
    and_matches = re.findall(
        r"\b(?:(?i:to|in|visit|visiting|going to|travel to|trip to))\s+"
        r"([A-Z][a-zA-Z\s]+?)\s+(?i:and)\s+([A-Z][a-zA-Z\s]+?)"
        r"(?=\s+(?:(?i:for|from|in|with|then|before|after|next|this|on)|,|\.|\?|$)|[,\.!\?]|$)",
        raw,
    )
    for d1, d2 in and_matches:
        for name in (d1.strip().title(), d2.strip().title()):
            if name and name not in seen:
                seen.append(name)
        if len(seen) >= 5:
            break

    return seen[:5]


def _infer_workers_to_rerun(feedback: str) -> list[str]:
    """Infer which workers need re-running based on Validator feedback text."""
    feedback_lower = feedback.lower()
    workers: list[str] = []

    if any(w in feedback_lower for w in ("flight", "airline", "departure", "arrival")):
        workers.append("flight_worker")
    if any(w in feedback_lower for w in ("hotel", "accommodation", "check-in", "check in", "lodging")):
        workers.append("hotel_worker")
    if any(w in feedback_lower for w in ("attraction", "activity", "poi", "museum", "restaurant", "sightseeing")):
        workers.append("attraction_worker")
    if any(w in feedback_lower for w in ("transport", "route", "travel time", "transfer", "transit")):
        workers.append("transport_worker")

    # If nothing specific detected or all workers affected — re-run all
    if not workers:
        workers = ["flight_worker", "hotel_worker", "attraction_worker", "transport_worker"]

    return workers


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from LLM output."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("```").strip()

    # Find the first { ... } block
    brace_start = text.find("{")
    if brace_start == -1:
        return {}
    # Find matching closing brace
    depth = 0
    for i, ch in enumerate(text[brace_start:], start=brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[brace_start : i + 1])
                except json.JSONDecodeError:
                    break
    # Last resort
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}
