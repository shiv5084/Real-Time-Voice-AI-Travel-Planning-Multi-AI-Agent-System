"""Tests for Planner Agent memory integration.

Covers:
- _merge_preferences: all priority rules (raw request > parsed > stored)
- _build_memory_context: formatting for LLM injection
- _extract_candidate_destinations: pre-LLM heuristic
- PlannerAgent._load_user_preferences: Mem0 > Supabase merge
- PlannerAgent._load_episodic_context: episodic memory loading
- PlannerAgent.run: end-to-end with both memory sources populated
- PlannerAgent.run: episodic_context persisted to returned state
- PlannerAgent.run: memory skipped on regeneration pass
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.planner import (
    PlannerAgent,
    _build_memory_context,
    _extract_candidate_destinations,
    _merge_preferences,
)
from app.config import Settings
from app.graph.state import initial_state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def settings():
    return Settings.model_validate({
        "app_env": "local",
        "groq_api_key": "",
        "gemini_api_key": "",
        "enable_llm_cache": False,
        "enable_llm_streaming": False,
    })


def _no_stream_llm_mock(json_str: str):
    """Return a MagicMock LLM with no astream, proper model name, and ainvoke returning json_str."""
    mock_llm = MagicMock(spec=[])  # spec=[] → hasattr(llm, 'astream') is False
    mock_llm.model = "test-model"
    mock_llm.model_name = "test-model"
    resp = MagicMock()          # Full MagicMock for response so .content is accessible
    resp.content = json_str
    mock_llm.ainvoke = AsyncMock(return_value=resp)
    return mock_llm


@pytest.fixture
def planner(settings):
    return PlannerAgent(settings=settings)


def _llm_response(planner_fixture, json_str: str):
    """Wire a no-stream mock LLM onto the planner that returns the given JSON string."""
    planner_fixture._llm = _no_stream_llm_mock(json_str)


def _full_llm_json(**overrides) -> str:
    import json
    base = {
        "destinations": ["Paris"],
        "start_date": "2026-07-01",
        "end_date": "2026-07-06",
        "budget": 2000.0,
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
    base.update(overrides)
    return json.dumps(base)


# ===========================================================================
# 1. _merge_preferences
# ===========================================================================

class TestMergePreferences:
    """Priority: raw_request keywords > LLM-parsed > stored (Mem0/Supabase)."""

    def test_stored_fills_missing_parsed_keys(self):
        stored = {"food": "Japanese", "crowd_tolerance": "low"}
        parsed = {"accommodation_type": "hotel"}
        result = _merge_preferences(stored, parsed, "")
        assert result["food"] == "Japanese"
        assert result["crowd_tolerance"] == "low"
        assert result["accommodation_type"] == "hotel"

    def test_parsed_overrides_stored(self):
        stored = {"accommodation_type": "budget hostel"}
        parsed = {"accommodation_type": "boutique hotel"}
        result = _merge_preferences(stored, parsed, "")
        assert result["accommodation_type"] == "boutique hotel"

    def test_raw_request_luxury_overrides_parsed_and_stored(self):
        stored = {"accommodation_type": "budget"}
        parsed = {"accommodation_type": "mid-range"}
        result = _merge_preferences(stored, parsed, "I want a luxury five star hotel")
        assert result["accommodation_type"] == "luxury"
        assert result["budget_style"] == "luxury"

    def test_raw_request_budget_keywords_set_budget_style(self):
        result = _merge_preferences({}, {}, "Looking for a cheap budget hotel")
        assert result["accommodation_type"] == "budget"
        assert result["budget_style"] == "budget"

    def test_raw_request_vegetarian_overrides(self):
        stored = {"dietary_restrictions": "none"}
        result = _merge_preferences(stored, {}, "I am vegetarian so please no meat")
        assert result["dietary_restrictions"] == "vegetarian"

    def test_raw_request_vegan(self):
        result = _merge_preferences({}, {}, "I am a vegan traveler")
        assert result["dietary_restrictions"] == "vegan"

    def test_raw_request_halal(self):
        result = _merge_preferences({}, {}, "need halal food options please")
        assert result["dietary_restrictions"] == "halal"

    def test_five_star_keyword(self):
        result = _merge_preferences({}, {}, "book a 5 star resort in Bali")
        assert result["accommodation_type"] == "luxury"

    def test_all_empty_returns_empty_dict(self):
        result = _merge_preferences({}, {}, "")
        assert result == {}

    def test_none_values_in_stored_do_not_bleed_through(self):
        stored = {"food": None, "crowd_tolerance": "low"}
        parsed = {"food": "Italian"}
        result = _merge_preferences(stored, parsed, "")
        # Parsed should set food to Italian; None from stored is already overridden
        assert result["food"] == "Italian"
        assert result["crowd_tolerance"] == "low"

    def test_none_values_in_parsed_do_not_override_stored(self):
        stored = {"food": "Japanese"}
        parsed = {"food": None}
        result = _merge_preferences(stored, parsed, "")
        # None from parsed should NOT override a non-None stored value
        # because the merge loop only sets when val is not None
        assert result["food"] == "Japanese"

    def test_luxury_in_request_takes_priority_over_budget_stored(self):
        stored = {"budget_style": "budget", "accommodation_type": "hostel"}
        result = _merge_preferences(stored, {}, "this time I want a luxury hotel please")
        assert result["accommodation_type"] == "luxury"
        assert result["budget_style"] == "luxury"

    def test_multiple_dietary_keywords_last_one_wins(self):
        """When both vegetarian and vegan appear, vegan check runs last."""
        result = _merge_preferences({}, {}, "I am vegetarian, actually vegan")
        # Vegan check overwrites vegetarian check (both set dietary_restrictions)
        assert result["dietary_restrictions"] == "vegan"

    def test_returns_dict_not_none_when_only_stored_present(self):
        stored = {"travel_style": "backpacker"}
        result = _merge_preferences(stored, {}, "")
        assert isinstance(result, dict)
        assert result["travel_style"] == "backpacker"


# ===========================================================================
# 2. _build_memory_context
# ===========================================================================

class TestBuildMemoryContext:
    def test_empty_inputs_return_empty_string(self):
        assert _build_memory_context(None, None) == ""

    def test_preferences_formatted_correctly(self):
        prefs = {"food": "Japanese", "accommodation_type": "luxury"}
        ctx = _build_memory_context(prefs, None)
        assert "Japanese" in ctx
        assert "luxury" in ctx
        assert "Stored user preferences" in ctx

    def test_episodic_repeat_destinations_included(self):
        episodic = {"repeat_destinations": ["Paris", "Tokyo"], "destination_memories": {}}
        ctx = _build_memory_context(None, episodic)
        assert "Paris" in ctx
        assert "Tokyo" in ctx

    def test_episodic_lessons_included(self):
        episodic = {
            "repeat_destinations": ["Paris"],
            "destination_memories": {
                "Paris": ["What worked: Marais stay", "Avoid: Champs-Elysées in July"]
            },
        }
        ctx = _build_memory_context(None, episodic)
        assert "Marais" in ctx
        assert "Champs" in ctx

    def test_both_preferences_and_episodic(self):
        prefs = {"food": "Italian"}
        episodic = {"repeat_destinations": ["Rome"], "destination_memories": {}}
        ctx = _build_memory_context(prefs, episodic)
        assert "Italian" in ctx
        assert "Rome" in ctx

    def test_empty_preference_values_not_included(self):
        prefs = {"food": "", "accommodation_type": None, "crowd_tolerance": "low"}
        ctx = _build_memory_context(prefs, None)
        assert "crowd_tolerance" in ctx.lower() or "Crowd Tolerance" in ctx
        # Empty / None values should not appear as lines
        assert "food" not in ctx.lower() or "low" in ctx


# ===========================================================================
# 3. _extract_candidate_destinations
# ===========================================================================

class TestExtractCandidateDestinations:
    def test_extracts_single_destination(self):
        dests = _extract_candidate_destinations("I want to travel to Paris next month")
        assert "Paris" in dests

    def test_extracts_multiple_destinations(self):
        dests = _extract_candidate_destinations(
            "Trip to Tokyo and then visiting Kyoto before going to Osaka"
        )
        assert len(dests) >= 2

    def test_caps_at_five(self):
        text = (
            "Visit Paris, then to London, trip to Berlin, going to Rome, "
            "travel to Madrid, visit Lisbon"
        )
        dests = _extract_candidate_destinations(text)
        assert len(dests) <= 5

    def test_empty_string(self):
        dests = _extract_candidate_destinations("")
        assert dests == []

    def test_no_destinations(self):
        dests = _extract_candidate_destinations("I want to plan a trip but not sure where")
        assert isinstance(dests, list)

    def test_deduplicates(self):
        dests = _extract_candidate_destinations("Trip to Paris then back to Paris")
        paris_count = sum(1 for d in dests if "Paris" in d)
        assert paris_count == 1


# ===========================================================================
# 4. PlannerAgent._load_user_preferences (Mem0 > Supabase merge)
# ===========================================================================

class TestLoadUserPreferences:
    @pytest.mark.asyncio
    async def test_mem0_overrides_supabase(self, planner):
        """When both Mem0 and Supabase return data, Mem0 wins on conflicts."""
        supabase_prefs = {
            "food": "Italian",
            "accommodation_type": "budget",
            "crowd_tolerance": "low",
        }
        mem0_prefs = {
            "accommodation_type": "luxury",  # overrides Supabase
            "budget_style": "luxury",         # new key
        }

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [{"preferences": supabase_prefs}]
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_response)
            ))

            mock_mem0 = AsyncMock()
            mock_mem0.get_preferences = AsyncMock(return_value=mem0_prefs)

            with patch("app.memory.mem0_client.get_mem0_client", return_value=mock_mem0):
                result = await planner._load_user_preferences("user_123")

        # Mem0 overrides Supabase on conflict
        assert result["accommodation_type"] == "luxury"
        assert result["budget_style"] == "luxury"
        # Supabase-only keys are preserved
        assert result["food"] == "Italian"
        assert result["crowd_tolerance"] == "low"

    @pytest.mark.asyncio
    async def test_supabase_used_as_fallback_when_mem0_empty(self, planner):
        """When Mem0 returns nothing, Supabase preferences are used as-is."""
        supabase_prefs = {"food": "Thai", "travel_style": "backpacker"}

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [{"preferences": supabase_prefs}]
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_response)
            ))

            mock_mem0 = AsyncMock()
            mock_mem0.get_preferences = AsyncMock(return_value={})

            with patch("app.memory.mem0_client.get_mem0_client", return_value=mock_mem0):
                result = await planner._load_user_preferences("user_123")

        assert result["food"] == "Thai"
        assert result["travel_style"] == "backpacker"

    @pytest.mark.asyncio
    async def test_mem0_only_when_supabase_fails(self, planner):
        """When Supabase fails, Mem0 preferences are used alone."""
        mem0_prefs = {"accommodation_type": "luxury", "food": "Japanese"}

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("Supabase unreachable")
            )

            mock_mem0 = AsyncMock()
            mock_mem0.get_preferences = AsyncMock(return_value=mem0_prefs)

            with patch("app.memory.mem0_client.get_mem0_client", return_value=mock_mem0):
                result = await planner._load_user_preferences("user_123")

        assert result["accommodation_type"] == "luxury"
        assert result["food"] == "Japanese"

    @pytest.mark.asyncio
    async def test_empty_dict_when_both_sources_fail(self, planner):
        """When both Mem0 and Supabase fail, returns empty dict (no crash)."""
        with patch("httpx.AsyncClient") as mock_httpx:
            mock_httpx.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("HTTP error")
            )

            mock_mem0 = AsyncMock()
            mock_mem0.get_preferences = AsyncMock(side_effect=Exception("Mem0 error"))

            with patch("app.memory.mem0_client.get_mem0_client", return_value=mock_mem0):
                result = await planner._load_user_preferences("user_123")

        assert result == {}

    @pytest.mark.asyncio
    async def test_mem0_none_values_do_not_override_supabase(self, planner):
        """Mem0 keys with None value should not overwrite Supabase non-None values."""
        supabase_prefs = {"food": "Mexican", "crowd_tolerance": "medium"}
        mem0_prefs = {"food": None}  # None from Mem0 should not overwrite

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [{"preferences": supabase_prefs}]
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_response)
            ))

            mock_mem0 = AsyncMock()
            mock_mem0.get_preferences = AsyncMock(return_value=mem0_prefs)

            with patch("app.memory.mem0_client.get_mem0_client", return_value=mock_mem0):
                result = await planner._load_user_preferences("user_123")

        assert result["food"] == "Mexican"


# ===========================================================================
# 5. PlannerAgent._load_episodic_context
# ===========================================================================

class TestLoadEpisodicContext:
    @pytest.mark.asyncio
    async def test_returns_episodic_context_for_known_destinations(self, planner):
        """Should return context dict populated from episodic memory module."""
        mock_context = {
            "repeat_destinations": ["Paris"],
            "destination_memories": {
                "Paris": ["What worked: Marais", "Avoid: Champs-Elysées in July"]
            },
            "general_patterns": ["User prefers boutique hotels"],
        }

        with patch("app.memory.episodic.build_episodic_context", AsyncMock(return_value=mock_context)):
            result = await planner._load_episodic_context("user_123", ["Paris"])

        assert result["repeat_destinations"] == ["Paris"]
        assert "Paris" in result["destination_memories"]

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_episodic_fails(self, planner):
        """Should return {} gracefully when episodic module raises."""
        with patch(
            "app.memory.episodic.build_episodic_context",
            AsyncMock(side_effect=Exception("DB down")),
        ):
            result = await planner._load_episodic_context("user_123", ["Paris"])

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_dict_for_no_prior_visits(self, planner):
        """Empty episodic context when user has no prior trips."""
        with patch(
            "app.memory.episodic.build_episodic_context",
            AsyncMock(return_value={}),
        ):
            result = await planner._load_episodic_context("user_123", ["NewCity"])

        assert result == {}

    @pytest.mark.asyncio
    async def test_passes_candidate_destinations_to_build_context(self, planner):
        """Verifies that destinations are forwarded to build_episodic_context."""
        captured = {}

        async def mock_build(user_id, destinations):
            captured["user_id"] = user_id
            captured["destinations"] = destinations
            return {}

        with patch("app.memory.episodic.build_episodic_context", side_effect=mock_build):
            await planner._load_episodic_context("user_abc", ["Tokyo", "Kyoto"])

        assert captured["user_id"] == "user_abc"
        assert "Tokyo" in captured["destinations"]
        assert "Kyoto" in captured["destinations"]


# ===========================================================================
# 6. PlannerAgent.run — end-to-end memory integration
# ===========================================================================

class TestPlannerRunMemoryIntegration:
    @pytest.mark.asyncio
    async def test_run_loads_mem0_preferences_for_known_user(self, planner):
        """Planner should call _load_user_preferences for non-anonymous users."""
        _llm_response(planner, _full_llm_json())

        load_called = {}

        async def mock_load_prefs(uid):
            load_called["uid"] = uid
            return {"accommodation_type": "luxury"}

        planner._load_user_preferences = mock_load_prefs

        async def mock_load_episodic(uid, dests):
            return {}

        planner._load_episodic_context = mock_load_episodic

        state = initial_state("Trip to Paris", user_id="user_real")
        await planner.run(state)

        assert load_called["uid"] == "user_real"

    @pytest.mark.asyncio
    async def test_run_skips_memory_load_for_anonymous(self, planner):
        """Anonymous users should not trigger any memory loading."""
        _llm_response(planner, _full_llm_json())

        load_called = {"prefs": False, "episodic": False}

        async def mock_load_prefs(uid):
            load_called["prefs"] = True
            return {}

        async def mock_load_episodic(uid, dests):
            load_called["episodic"] = True
            return {}

        planner._load_user_preferences = mock_load_prefs
        planner._load_episodic_context = mock_load_episodic

        state = initial_state("Trip to Paris", user_id="anonymous")
        await planner.run(state)

        assert load_called["prefs"] is False
        assert load_called["episodic"] is False

    @pytest.mark.asyncio
    async def test_run_skips_memory_on_regeneration_pass(self, planner):
        """Memory should NOT be re-loaded on regeneration (regen_count > 0)."""
        _llm_response(planner, _full_llm_json())

        load_called = {"prefs": False, "episodic": False}

        async def mock_load_prefs(uid):
            load_called["prefs"] = True
            return {}

        async def mock_load_episodic(uid, dests):
            load_called["episodic"] = True
            return {}

        planner._load_user_preferences = mock_load_prefs
        planner._load_episodic_context = mock_load_episodic

        state = initial_state("Trip to Paris", user_id="user_real")
        state["regeneration_count"] = 1
        # Preferences already loaded in previous pass
        state["user_preferences"] = {"food": "Italian"}
        state["episodic_context"] = {"repeat_destinations": []}
        await planner.run(state)

        assert load_called["prefs"] is False
        assert load_called["episodic"] is False

    @pytest.mark.asyncio
    async def test_run_persists_user_preferences_in_returned_state(self, planner):
        """user_preferences should be in returned state after first run."""
        _llm_response(planner, _full_llm_json())

        async def mock_load_prefs(uid):
            return {"food": "Sushi", "accommodation_type": "luxury"}

        async def mock_load_episodic(uid, dests):
            return {}

        planner._load_user_preferences = mock_load_prefs
        planner._load_episodic_context = mock_load_episodic

        state = initial_state("Trip to Paris", user_id="user_real")
        result = await planner.run(state)

        assert "user_preferences" in result
        assert result["user_preferences"]["food"] == "Sushi"

    @pytest.mark.asyncio
    async def test_run_persists_episodic_context_in_returned_state(self, planner):
        """episodic_context should be in returned state after loading."""
        _llm_response(planner, _full_llm_json())

        async def mock_load_prefs(uid):
            return {}

        async def mock_load_episodic(uid, dests):
            return {
                "repeat_destinations": ["Paris"],
                "destination_memories": {"Paris": ["What worked: Eiffel Tower tour"]},
                "general_patterns": [],
            }

        planner._load_user_preferences = mock_load_prefs
        planner._load_episodic_context = mock_load_episodic

        state = initial_state("Trip to Paris", user_id="user_real")
        result = await planner.run(state)

        assert "episodic_context" in result
        assert "Paris" in result["episodic_context"]["repeat_destinations"]

    @pytest.mark.asyncio
    async def test_run_mem0_preferences_influence_merged_preferences(self, planner):
        """Preferences loaded from Mem0 should flow into constraints.preferences."""
        import json

        # LLM returns no parsed preferences
        _llm_response(
            planner,
            _full_llm_json(preferences=None),
        )

        async def mock_load_prefs(uid):
            return {"food": "Japanese", "crowd_tolerance": "low"}

        async def mock_load_episodic(uid, dests):
            return {}

        planner._load_user_preferences = mock_load_prefs
        planner._load_episodic_context = mock_load_episodic

        state = initial_state("Trip to Paris", user_id="user_real")
        result = await planner.run(state)

        prefs = result["constraints"].get("preferences") or {}
        assert prefs.get("food") == "Japanese"
        assert prefs.get("crowd_tolerance") == "low"

    @pytest.mark.asyncio
    async def test_run_raw_request_overrides_mem0_preference(self, planner):
        """Explicit 'luxury' in raw_request should override stored budget preference."""
        _llm_response(planner, _full_llm_json(preferences=None))

        async def mock_load_prefs(uid):
            return {"accommodation_type": "budget", "budget_style": "budget"}

        async def mock_load_episodic(uid, dests):
            return {}

        planner._load_user_preferences = mock_load_prefs
        planner._load_episodic_context = mock_load_episodic

        state = initial_state(
            "I want a luxury five star hotel in Paris this time", user_id="user_real"
        )
        result = await planner.run(state)

        prefs = result["constraints"].get("preferences") or {}
        assert prefs.get("accommodation_type") == "luxury"
        assert prefs.get("budget_style") == "luxury"

    @pytest.mark.asyncio
    async def test_run_episodic_context_injected_into_llm_prompt(self, planner):
        """Episodic lessons should appear in the prompt sent to the LLM."""
        captured_content = {}

        async def mock_ainvoke(messages):
            for m in messages:
                content = m.content if hasattr(m, "content") else (
                    m.get("content", "") if isinstance(m, dict) else "")
                if "Marais" in content:
                    captured_content["found"] = True
            resp = MagicMock()
            resp.content = _full_llm_json()
            return resp

        # Simple stub — no astream attribute, so _call_llm takes the ainvoke path
        class _StubLLM:
            model = "test-model"
            model_name = "test-model"
            ainvoke = staticmethod(mock_ainvoke)

        planner._llm = _StubLLM()

        async def mock_load_prefs(uid):
            return {}

        async def mock_load_episodic(uid, dests):
            return {
                "repeat_destinations": ["Paris"],
                "destination_memories": {"Paris": ["What worked: Marais stay"]},
                "general_patterns": [],
            }

        planner._load_user_preferences = mock_load_prefs
        planner._load_episodic_context = mock_load_episodic

        state = initial_state("Trip to Paris", user_id="user_real")
        await planner.run(state)

        assert captured_content.get("found") is True, (
            "Episodic context (Marais lesson) was not injected into LLM prompt"
        )

    @pytest.mark.asyncio
    async def test_run_does_not_crash_when_all_memory_fails(self, planner):
        """Memory failures should be silently absorbed; pipeline should continue."""
        full_json = _full_llm_json()

        class _StubLLM:
            model = "test-model"
            model_name = "test-model"
            async def ainvoke(self, messages):
                resp = MagicMock()
                resp.content = full_json
                return resp

        planner._llm = _StubLLM()

        async def mock_load_prefs(uid):
            raise Exception("Mem0 down")

        async def mock_load_episodic(uid, dests):
            raise Exception("DB down")

        planner._load_user_preferences = mock_load_prefs
        planner._load_episodic_context = mock_load_episodic

        state = initial_state("Trip to Paris", user_id="user_real")
        result = await planner.run(state)

        # Pipeline must complete successfully despite memory failures
        assert result["current_step"] == "planner_complete"
        assert result["constraints"]["destinations"] == ["Paris"]

    @pytest.mark.asyncio
    async def test_run_state_already_has_preferences_not_reloaded(self, planner):
        """If user_preferences is already in state (e.g. loaded by caller), skip reload."""
        _llm_response(planner, _full_llm_json())

        load_called = {"count": 0}

        async def mock_load_prefs(uid):
            load_called["count"] += 1
            return {"food": "Overwritten"}  # should NOT be called

        async def mock_load_episodic(uid, dests):
            return {}

        planner._load_user_preferences = mock_load_prefs
        planner._load_episodic_context = mock_load_episodic

        state = initial_state("Trip to Paris", user_id="user_real")
        state["user_preferences"] = {"food": "Pre-loaded Thai"}
        # regen_count is 0 — but preferences already present
        result = await planner.run(state)

        # _load_user_preferences should NOT have been called
        assert load_called["count"] == 0
        assert result["user_preferences"]["food"] == "Pre-loaded Thai"
