"""Validator / Critic Agent — quality checks, conflict detection, factual grounding."""

from __future__ import annotations

import time
from typing import Any

from app.agents.base import BaseAgent
from app.graph.state import TravelPlanState
from app.mcp_clients import MapsMCPClient
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# GoT-aligned system prompt — Validator / Critic Agent (Gemini)
# Principles: constraint-first, grounded, validation-before-output,
# structured issue reporting, professional & constructive tone.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a professional travel plan quality reviewer. Your task is to rigorously \
validate a composed itinerary before it is presented to the traveler. You are the \
final quality gate — no plan reaches the user without passing your review.

## Reasoning approach (Graph of Thought)

  Node 1 — HARD CONSTRAINTS (critical failures — must reject if violated):
    → Budget: does the total estimated cost exceed the stated budget?
    → Dates: are all activities within the trip's start and end dates?
    → Traveler count: are costs correctly scaled for the number of travelers?
    → Geographic feasibility: is there enough travel time between cities on the same day?
      (e.g., Tokyo and Kyoto cannot both be full-day activities on the same day)
    → Flight anchors: does Day 1 assume pre-arrival activities? Does the last day \
      schedule activities after the departure flight?
    → If ANY of the above are violated → severity: "critical" → approved: false.

  Node 2 — LOGICAL CONSISTENCY (major issues — flag but may not require rejection):
    → Time sequence: do activities on each day flow in chronological order?
    → Buffer violations: are there gaps of less than 30 minutes between activities?
    → Overlap: do any two activities share overlapping time windows?
    → Hotel check-in: is check-in scheduled before the hotel's stated check-in time?
    → Meal gaps: are any days missing all meal slots (breakfast, lunch, dinner)?
    → If found → severity: "major".

  Node 3 — PREFERENCE ALIGNMENT (minor issues — informational):
    → Crowd tolerance: are any high-crowd venues scheduled for a crowd-averse traveler?
    → Food preferences: are meals consistent with stated dietary requirements?
    → Activity level: does the daily pace match the stated activity preference?
    → If found → severity: "minor".

  Node 4 — FACTUAL GROUNDING:
    → Cross-check destinations in the itinerary against geocoding results.
    → Any location that failed geocoding or returned zero results should be flagged.
    → Flag activities at venues that cannot be verified on a map.
    → Severity: "major" for core destinations, "minor" for specific venues.

  Node 5 — OVERALL ASSESSMENT:
    → If no critical issues → approved: true (proceed to delivery).
    → If critical issues exist AND regeneration attempts < 3 → approved: false \
      (request re-planning with specific feedback).
    → If critical issues exist AND regeneration attempts = 3 → approved: true with \
      prominent warnings (deliver with caveats rather than loop indefinitely).
    → Write a concise, constructive overall_assessment paragraph: acknowledge strengths, \
      describe issues clearly, and state the outcome (approved / rejected / approved with warnings).

## Prompting principles
- Constraint-first: hard limits (budget, dates, feasibility) checked before preferences.
- Grounded: location validation backed by geocoding data, not assumption.
- Validation before output: no plan is delivered without this check completing.
- Constructive tone: issues are described specifically and actionably, not vaguely.
- Professional and friendly: the assessment is written as if briefing a colleague \
  — clear, respectful, and solution-oriented.

## Output format
Return ONLY a valid JSON object (no markdown fences) with keys:
  issues             list of objects, each with:
    severity         str — "critical" | "major" | "minor"
    description      str — specific, actionable description of the issue
    affected_day     int | null — day number if issue is day-specific
  overall_assessment str — one concise paragraph summarizing quality and outcome
  approved           bool — true only if no critical issues remain (or max regen reached)
"""


class ValidatorAgent(BaseAgent):
    """Validator/Critic Agent — Gemini model + Nominatim for location validation."""

    @property
    def agent_name(self) -> str:
        return "validator_agent"

    @property
    def model_provider(self) -> str:
        return "gemini"

    @property
    def max_steps(self) -> int:
        return self._settings.agent_steps_validator

    # ------------------------------------------------------------------

    async def run(self, state: TravelPlanState) -> TravelPlanState:
        start = time.monotonic()
        self._log_step("Validator agent started")

        constraints = state.get("constraints") or {}
        itinerary = state.get("itinerary") or {}
        budget_breakdown = state.get("budget_breakdown") or {}
        regen_count = state.get("regeneration_count", 0) or 0
        errors: list[dict[str, Any]] = []
        agent_responses: list[dict[str, Any]] = []

        tool_results: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []

        # Step 1: Validate key locations exist via Maps
        destinations = constraints.get("destinations", [])
        for dest in destinations[:3]:  # Check up to 3 locations to save quota
            geo_start = time.monotonic()
            try:
                client = MapsMCPClient()
                result = await client.call(
                    "google_maps_geocode",
                    {"address": dest},
                    agent=self.agent_name,
                )
                results_list = result.get("results") or (result.get("data") or {}).get("results") or []
                if not results_list:
                    issues.append({
                        "severity": "major",
                        "description": f"Location '{dest}' could not be geocoded — may not exist or name is incorrect",
                        "affected_day": None,
                    })
                tool_results.append(
                    self._create_tool_result(
                        f"google_maps_geocode_{dest}",
                        success=True,
                        data=result,
                        latency_ms=self._elapsed_ms(geo_start),
                    )
                )
            except Exception as exc:
                self._log_error(f"Geocoding validation failed for {dest}", exc)
                tool_results.append(
                    self._create_tool_result(
                        f"geocode_{dest}",
                        success=False,
                        error=str(exc),
                        latency_ms=self._elapsed_ms(geo_start),
                    )
                )

        # Step 2: Structural validation (deterministic checks)
        structural_issues = _structural_validation(itinerary, budget_breakdown, constraints)
        issues.extend(structural_issues)

        # Step 3: LLM quality check (Gemini)
        llm_issues = await self._llm_validation(itinerary, budget_breakdown, constraints, regen_count)
        issues.extend(llm_issues)

        # Determine validation status
        critical_count = sum(1 for i in issues if i.get("severity") == "critical")
        major_count = sum(1 for i in issues if i.get("severity") == "major")

        # Increment regeneration counter first so graceful degradation threshold is correct
        new_regen_count = regen_count + 1 if critical_count > 0 else regen_count

        # Graceful degradation: on the 3rd rejection (new_regen_count == 3) stop looping
        # and deliver with warnings so the pipeline terminates rather than cycling forever.
        max_regen_reached = new_regen_count >= 3 and critical_count > 0

        if max_regen_reached:
            validation_status = "warnings"
            for issue in issues:
                if issue.get("severity") == "critical":
                    issue["description"] = "[MAX REGEN REACHED] " + issue["description"]
            # Don't increment further — keep at 3
            new_regen_count = 3
        elif critical_count > 0:
            validation_status = "rejected"
        elif major_count > 0:
            validation_status = "warnings"
        else:
            validation_status = "approved"

        # Build specific regeneration feedback for the Planner on rejection
        regeneration_feedback: str | None = None
        if validation_status == "rejected":
            critical_issues = [i["description"] for i in issues if i.get("severity") == "critical"]
            regeneration_feedback = (
                f"Validation attempt {new_regen_count} of 3 failed. Critical issues found:\n"
                + "\n".join(f"- {d}" for d in critical_issues[:5])
                + "\nPlease re-plan to address these specific issues."
            )

        latency = self._elapsed_ms(start)
        agent_responses.append(
            self._create_agent_response(
                success=True,
                data={"validation_status": validation_status, "issues": issues},
                tool_results=tool_results,
                steps_taken=2,
                latency_ms=latency,
            )
        )

        self._log_step("Validator agent complete", {
            "status": validation_status,
            "critical": critical_count,
            "major": major_count,
            "regen_count": new_regen_count,
            "latency_ms": latency,
        })

        result: dict[str, Any] = {
            "validation_status": validation_status,
            "validation_issues": issues,
            "regeneration_count": new_regen_count,
            "agent_responses": agent_responses,
            "errors": errors,
        }
        if regeneration_feedback is not None:
            result["regeneration_feedback"] = regeneration_feedback

        return result

    # ------------------------------------------------------------------

    async def _llm_validation(
        self,
        itinerary: dict[str, Any],
        budget: dict[str, Any],
        constraints: dict[str, Any],
        regen_count: int = 0,
    ) -> list[dict[str, Any]]:
        llm = self._get_llm()

        total_budget = constraints.get("budget", "unspecified")
        total_cost = budget.get("total_estimated_cost", "unknown")
        compliance = budget.get("compliance", "unknown")
        destinations = constraints.get("destinations", [])
        travelers = constraints.get("travelers", 1)
        start_date = constraints.get("start_date", "unspecified")
        end_date = constraints.get("end_date", "unspecified")
        preferences = constraints.get("preferences") or {}

        regen_note = (
            f"This is validation attempt {regen_count + 1} of 3. "
            "If this is the final attempt (attempt 3), set approved: true even if issues exist."
            if regen_count >= 2
            else f"This is validation attempt {regen_count + 1} of 3."
        )

        prompt = (
            f"## Trip context\n"
            f"Destinations: {destinations}\n"
            f"Dates: {start_date} to {end_date}\n"
            f"Travelers: {travelers}\n"
            f"Budget: {total_budget} {constraints.get('budget_currency', 'USD')}\n"
            f"Estimated cost: {total_cost} (compliance: {compliance})\n"
            f"Preferences: {preferences}\n\n"
            f"## Regeneration note\n{regen_note}\n\n"
            f"## Itinerary to validate\n{str(itinerary)[:4000]}\n\n"
            f"## Budget breakdown\n{budget}\n\n"
            "Apply the Graph of Thought validation process described in your system prompt. "
            "Check all 5 nodes (hard constraints, logical consistency, preference alignment, "
            "factual grounding, overall assessment) and return your findings."
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
            if parsed:
                raw_issues = parsed.get("issues") or []
                if isinstance(raw_issues, list):
                    return [
                        {
                            "severity": i.get("severity", "minor"),
                            "description": i.get("description", str(i)),
                            "affected_day": i.get("affected_day"),
                        }
                        for i in raw_issues
                        if isinstance(i, dict)
                    ]
        except Exception as exc:
            self._log_error("LLM validation failed", exc)
        return []


# ---------------------------------------------------------------------------
# Deterministic structural validation
# ---------------------------------------------------------------------------

def _structural_validation(
    itinerary: dict[str, Any],
    budget: dict[str, Any],
    constraints: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    days = itinerary.get("days") or []

    if not days:
        issues.append({
            "severity": "critical",
            "description": "Itinerary has no days — generation may have failed",
            "affected_day": None,
        })
        return issues

    # Check day ordering
    for i, day in enumerate(days):
        expected_day = i + 1
        actual_day = day.get("day")
        if actual_day != expected_day:
            issues.append({
                "severity": "major",
                "description": f"Day numbering error: expected day {expected_day}, got {actual_day}",
                "affected_day": actual_day,
            })

        # Check activity time order and buffers
        activities = day.get("activities") or []
        prev_end: str | None = None
        for act in activities:
            start_t = act.get("start_time")
            end_t = act.get("end_time")
            if prev_end and start_t:
                gap = _time_diff_minutes(prev_end, start_t)
                if gap is not None and gap < 30:
                    issues.append({
                        "severity": "minor",
                        "description": f"Day {day.get('day')}: Less than 30-minute buffer before '{act.get('name', 'activity')}'",
                        "affected_day": day.get("day"),
                    })
            if end_t:
                prev_end = end_t

    # Budget compliance check
    total_cost = budget.get("total_estimated_cost", 0)
    total_budget = budget.get("total_budget", 0)
    if total_budget and total_budget > 0:
        compliance = budget.get("compliance", "within_budget")
        if compliance == "over_budget":
            issues.append({
                "severity": "major",
                "description": f"Trip is over budget: estimated ${total_cost:.0f} vs budget ${total_budget:.0f}",
                "affected_day": None,
            })

    return issues


def _time_diff_minutes(end: str, start: str) -> int | None:
    """Return minutes between two HH:MM times. Returns None if invalid."""
    try:
        e_h, e_m = map(int, end.split(":"))
        s_h, s_m = map(int, start.split(":"))
        return (s_h * 60 + s_m) - (e_h * 60 + e_m)
    except Exception:
        return None
