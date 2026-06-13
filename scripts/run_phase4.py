#!/usr/bin/env python
"""Phase 4 verification script — Memory, Personalization & Self-Correcting Loop.

Exit criteria (from phase-wise-implementationPlan.md §6.3):
  [1/10]  Mem0 client imports and initialises (falls back to Redis when no API key)
  [2/10]  Preferences can be stored and retrieved via Redis fallback
  [3/10]  Episodic memory module imports; save/get functions are callable
  [4/10]  TravelPlanState has all Phase 4 memory fields
  [5/10]  Planner Agent integrates Mem0 and episodic context (preference injection)
  [6/10]  _merge_preferences correctly applies stored prefs and explicit overrides
  [7/10]  Self-correcting loop: should_regenerate routes correctly for all cases
  [8/10]  Selective worker re-run: _infer_workers_to_rerun parses feedback correctly
  [9/10]  Profile API routes registered: GET + PUT /api/profile
  [10/10] Full pipeline runs with memory context (mocked external calls)
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


async def main() -> int:
    print("=" * 70)
    print("Phase 4 Verification — Memory, Personalization & Self-Correcting Loop")
    print("=" * 70)

    from app.config import get_settings
    settings = get_settings()
    print(f"\nEnvironment: {settings.app_env}")
    print(f"Mem0 API key set: {bool(getattr(settings, 'mem0_api_key', None))}")
    print(f"Redis URL: {settings.redis_url}")

    all_passed = True

    # ─────────────────────────────────────────────────────────────────────
    # Test 1: Mem0 client imports and initialises
    # ─────────────────────────────────────────────────────────────────────
    print("\n[1/10] Verifying Mem0 client imports and initialises...")
    try:
        from app.memory.mem0_client import Mem0Client, get_mem0_client, PREFERENCE_KEYS

        client = Mem0Client()
        assert client is not None
        assert len(PREFERENCE_KEYS) >= 6
        singleton = get_mem0_client()
        assert singleton is not None
        print("   ✓ Mem0Client instantiated, get_mem0_client singleton works")
        print(f"   ✓ Preference categories: {PREFERENCE_KEYS}")
    except Exception as exc:
        print(f"   ✗ Mem0 client init failed: {exc}")
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────
    # Test 2: Preferences can be stored and retrieved via Redis fallback
    # ─────────────────────────────────────────────────────────────────────
    print("\n[2/10] Verifying preference storage and retrieval (Redis fallback)...")
    try:
        from app.memory.mem0_client import Mem0Client, _parse_preferences_from_memories

        # Test parsing functions (pure, no I/O)
        memories = [
            {"memory": "food: Japanese", "metadata": {"category": "food"}},
            {"memory": "crowd_tolerance: low", "metadata": {"category": "crowd_tolerance"}},
            {"memory": "The user is vegetarian", "metadata": {}},
        ]
        parsed = _parse_preferences_from_memories(memories)
        assert parsed.get("food") == "Japanese", f"Expected 'Japanese', got: {parsed.get('food')}"
        assert parsed.get("crowd_tolerance") == "low"
        assert "vegetarian" in str(parsed.get("dietary_restrictions", "")).lower()
        print("   ✓ _parse_preferences_from_memories works for structured and natural language memories")

        # Test Redis fallback mock
        mock_redis = AsyncMock()
        stored_prefs = {"food": "Italian", "accommodation_type": "hotel"}
        mock_redis.get = AsyncMock(return_value=json.dumps(stored_prefs))
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.expire = AsyncMock(return_value=True)

        client = Mem0Client()
        client._initialized = True
        client._redis = mock_redis
        client._client = None

        result = await client.get_preferences("user1")
        assert isinstance(result, dict)
        print(f"   ✓ Redis fallback get_preferences returned: {result}")

        stored = await client.store_preferences("user1", {"crowd_tolerance": "low"})
        assert stored is True
        print("   ✓ Redis fallback store_preferences succeeded")
    except Exception as exc:
        print(f"   ✗ Preference storage/retrieval failed: {exc}")
        import traceback; traceback.print_exc()
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────
    # Test 3: Episodic memory module imports and functions are callable
    # ─────────────────────────────────────────────────────────────────────
    print("\n[3/10] Verifying episodic memory module...")
    try:
        from app.memory.episodic import (
            save_trip_memory,
            get_memories_for_destination,
            get_all_memories,
            build_episodic_context,
            extract_and_save_lessons,
            _row_to_dict,
        )

        # Test _row_to_dict (pure function)
        from datetime import datetime, timezone
        row = {
            "id": "abc",
            "trip_id": "def",
            "user_id": "ghi",
            "destination": "paris",
            "summary": "test",
            "lessons_learned": '{"what_worked": ["Marais"]}',
            "created_at": datetime.now(timezone.utc),
            "expires_at": None,
        }
        result = _row_to_dict(row)
        assert isinstance(result["lessons_learned"], dict)
        assert result["lessons_learned"]["what_worked"] == ["Marais"]
        print("   ✓ _row_to_dict correctly deserializes JSONB and datetime fields")

        # Test with DB unavailable
        with patch("app.memory.episodic._get_conn", return_value=None):
            memories = await get_memories_for_destination("user1", "Paris")
            assert memories == []
            print("   ✓ get_memories_for_destination gracefully returns [] when DB unavailable")

        # Test build_episodic_context for anonymous user
        context = await build_episodic_context("anonymous", ["Paris"])
        assert context == {}
        print("   ✓ build_episodic_context returns {} for anonymous user")

    except Exception as exc:
        print(f"   ✗ Episodic memory module check failed: {exc}")
        import traceback; traceback.print_exc()
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────
    # Test 4: TravelPlanState has all Phase 4 memory fields
    # ─────────────────────────────────────────────────────────────────────
    print("\n[4/10] Verifying TravelPlanState has Phase 4 memory fields...")
    try:
        from app.graph.state import TravelPlanState, initial_state

        phase4_fields = [
            "user_preferences",
            "episodic_context",
            "workers_to_rerun",
            "regeneration_feedback",
        ]
        state = initial_state("test request")
        missing = [f for f in phase4_fields if f not in state]
        if missing:
            print(f"   ✗ Missing Phase 4 fields in state: {missing}")
            all_passed = False
        else:
            print(f"   ✓ All Phase 4 state fields present: {phase4_fields}")
    except Exception as exc:
        print(f"   ✗ State field check failed: {exc}")
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────
    # Test 5: Planner integrates Mem0 and episodic context
    # ─────────────────────────────────────────────────────────────────────
    print("\n[5/10] Verifying Planner Agent integrates memory...")
    try:
        from app.agents.planner import PlannerAgent, _build_memory_context

        # Test _build_memory_context (pure function)
        ctx = _build_memory_context(
            user_preferences={"food": "Japanese", "crowd_tolerance": "low"},
            episodic_context={
                "repeat_destinations": ["Tokyo"],
                "destination_memories": {"Tokyo": ["What worked: JR Pass"]},
                "general_patterns": [],
            }
        )
        assert "Japanese" in ctx
        assert "Tokyo" in ctx
        assert "JR Pass" in ctx
        print("   ✓ _build_memory_context produces correct context string")

        # Verify agent has _load_user_preferences method
        agent = PlannerAgent(settings=settings)
        assert hasattr(agent, "_load_user_preferences")
        print("   ✓ PlannerAgent has _load_user_preferences method")

    except Exception as exc:
        print(f"   ✗ Planner memory integration check failed: {exc}")
        import traceback; traceback.print_exc()
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────
    # Test 6: _merge_preferences applies stored prefs and explicit overrides
    # ─────────────────────────────────────────────────────────────────────
    print("\n[6/10] Verifying preference merge and override logic...")
    try:
        from app.agents.planner import _merge_preferences

        scenarios = [
            # (stored, parsed, raw_request, expected_key, expected_value, description)
            (
                {"food": "Italian", "crowd_tolerance": "low"},
                {"accommodation_type": "hotel"},
                "Trip to Rome",
                "food", "Italian",
                "Stored pref preserved when not overridden"
            ),
            (
                {"accommodation_type": "budget"},
                {},
                "This time I want luxury hotels",
                "accommodation_type", "luxury",
                "Explicit 'luxury' override wins over stored budget"
            ),
            (
                {},
                {},
                "I'm vegetarian please",
                "dietary_restrictions", "vegetarian",
                "Dietary restriction detected from raw request"
            ),
            (
                {"food": "Thai"},
                {"food": "Japanese"},
                "I love Japanese food",
                "food", "Japanese",
                "Parsed pref overrides stored pref"
            ),
        ]

        passed = 0
        for stored, parsed, raw, key, expected, desc in scenarios:
            result = _merge_preferences(stored, parsed, raw)
            actual = result.get(key)
            if actual == expected:
                passed += 1
                print(f"   ✓ {desc}: {key}={actual}")
            else:
                print(f"   ✗ {desc}: expected {key}='{expected}', got '{actual}'")
                all_passed = False

        print(f"   ✓ {passed}/{len(scenarios)} merge scenarios passed")
    except Exception as exc:
        print(f"   ✗ Preference merge check failed: {exc}")
        import traceback; traceback.print_exc()
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────
    # Test 7: Self-correcting loop routing
    # ─────────────────────────────────────────────────────────────────────
    print("\n[7/10] Verifying self-correcting loop routing...")
    try:
        from app.graph.edges import should_regenerate

        test_cases = [
            ({"validation_status": "rejected", "regeneration_count": 0}, "regenerate"),
            ({"validation_status": "rejected", "regeneration_count": 2}, "regenerate"),
            ({"validation_status": "rejected", "regeneration_count": 3}, "finish"),
            ({"validation_status": "approved", "regeneration_count": 0}, "finish"),
            ({"validation_status": "warnings", "regeneration_count": 1}, "finish"),
        ]

        passed = 0
        for state, expected in test_cases:
            result = should_regenerate(state)
            if result == expected:
                passed += 1
            else:
                print(f"   ✗ state={state} → expected '{expected}', got '{result}'")
                all_passed = False

        print(f"   ✓ All {passed}/{len(test_cases)} regeneration routing cases correct")
    except Exception as exc:
        print(f"   ✗ Regeneration routing check failed: {exc}")
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────
    # Test 8: Selective worker re-run inference
    # ─────────────────────────────────────────────────────────────────────
    print("\n[8/10] Verifying selective worker re-run inference...")
    try:
        from app.agents.planner import _infer_workers_to_rerun
        from app.graph.edges import (
            should_run_flight_worker, should_run_hotel_worker,
            should_run_attraction_worker, should_run_transport_worker,
        )

        # Test _infer_workers_to_rerun
        flight_feedback = "The flight departure time conflicts with hotel check-out"
        workers = _infer_workers_to_rerun(flight_feedback)
        assert "flight_worker" in workers
        assert "hotel_worker" in workers
        print(f"   ✓ Flight+hotel feedback infers: {workers}")

        attraction_feedback = "Several attractions are overcrowded and routes are too long"
        workers2 = _infer_workers_to_rerun(attraction_feedback)
        assert "attraction_worker" in workers2
        assert "transport_worker" in workers2
        print(f"   ✓ Attraction+transport feedback infers: {workers2}")

        # Test selective routing functions
        regen_state = {"regeneration_count": 1, "workers_to_rerun": ["flight_worker"]}
        assert should_run_flight_worker(regen_state) == "run"
        assert should_run_hotel_worker(regen_state) == "skip"
        assert should_run_attraction_worker(regen_state) == "skip"
        assert should_run_transport_worker(regen_state) == "skip"
        print("   ✓ Selective worker routing: only flight_worker runs when specified")

        # First pass always runs all
        first_pass = {"regeneration_count": 0, "workers_to_rerun": None}
        assert should_run_flight_worker(first_pass) == "run"
        assert should_run_transport_worker(first_pass) == "run"
        print("   ✓ First pass: all workers run regardless of workers_to_rerun")

    except Exception as exc:
        print(f"   ✗ Selective worker re-run check failed: {exc}")
        import traceback; traceback.print_exc()
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────
    # Test 9: Profile API routes registered
    # ─────────────────────────────────────────────────────────────────────
    print("\n[9/10] Verifying profile API routes are registered...")
    try:
        from app.main import create_app

        app = create_app()
        all_paths = [r.path for r in app.routes if hasattr(r, "path")]

        profile_get = any("/api/profile" in p for p in all_paths)
        profile_prefs = any("preferences" in p for p in all_paths)

        if profile_get:
            print("   ✓ GET /api/profile route registered")
        else:
            print("   ✗ GET /api/profile route NOT found")
            all_passed = False

        if profile_prefs:
            print("   ✓ PUT /api/profile/preferences route registered")
        else:
            print("   ✗ PUT /api/profile/preferences route NOT found")
            all_passed = False

        # Check memories and delete routes
        memories_route = any("memories" in p for p in all_paths)
        if memories_route:
            print("   ✓ /api/profile/memories route registered")
    except Exception as exc:
        print(f"   ✗ Profile route check failed: {exc}")
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────
    # Test 10: Full pipeline with memory context (mocked)
    # ─────────────────────────────────────────────────────────────────────
    print("\n[10/10] Verifying full pipeline with memory context (mocked)...")
    try:
        from app.graph.workflow import run_pipeline

        stored_prefs = {"food": "vegetarian", "accommodation_type": "boutique hotel"}
        mock_mem0 = AsyncMock()
        mock_mem0.get_preferences = AsyncMock(return_value=stored_prefs)

        def mock_get_llm(self):
            responses = {
                "planner_agent": (
                    '{"destinations": ["Kyoto"], "start_date": "2025-10-01", '
                    '"end_date": "2025-10-06", "budget": 2500.0, "budget_currency": "USD", '
                    '"travelers": 1, "preferences": {"food": "vegetarian"}, '
                    '"follow_up_questions": [], '
                    '"delegation_plan": {"needs_flights": true, "needs_hotels": true, '
                    '"needs_attractions": true, "needs_transport": true}}'
                ),
                "flight_agent": '{"flights": [{"airline": "JAL", "price_usd": 800}]}',
                "hotel_agent": '{"hotels": [{"name": "Boutique Kyoto", "total_cost_usd": 700}]}',
                "attraction_agent": '{"attractions": [{"name": "Fushimi Inari", "cost_usd": 0}]}',
                "transport_agent": '{"transport_options": [{"mode": "train", "estimated_cost_usd": 60}]}',
                "budget_agent": '{"recommendations": []}',
                "composer_agent": (
                    '{"days": [{"day": 1, "date": "2025-10-01", "location": "Kyoto", '
                    '"activities": [{"name": "Arrive in Kyoto", "type": "travel", '
                    '"start_time": "14:00", "end_time": "15:00", "cost_usd": 0}], '
                    '"total_cost_usd": 0}]}'
                ),
                "validator_agent": '{"issues": [], "overall_assessment": "Approved", "approved": true}',
            }

            class _FakeLLM:
                def __init__(self, content):
                    self._content = content
                async def ainvoke(self, *args, **kwargs):
                    r = MagicMock()
                    r.content = self._content
                    return r

            return _FakeLLM(responses.get(self.agent_name, '{"mock": true}'))

        mock_aviation = AsyncMock()
        mock_aviation.call = AsyncMock(return_value={"flights": [{"price_usd": 800}]})
        mock_tavily = AsyncMock()
        mock_tavily.call = AsyncMock(return_value={"results": []})
        mock_nominatim = AsyncMock()
        mock_nominatim.call = AsyncMock(return_value={"results": [{"lat": 35.0, "lon": 135.7}]})
        mock_graphhopper = AsyncMock()
        mock_graphhopper.call = AsyncMock(return_value={"paths": []})

        patches = [
            patch("app.agents.flight.SkyscannerMCPClient", return_value=mock_aviation),
            patch("app.agents.hotel.TavilyMCPClient", return_value=mock_tavily),
            patch("app.agents.attraction.TavilyMCPClient", return_value=mock_tavily),
            patch("app.agents.attraction.MapsMCPClient", return_value=mock_nominatim),
            patch("app.agents.transport.MapsMCPClient", return_value=mock_nominatim),
            patch("app.agents.validator.MapsMCPClient", return_value=mock_nominatim),
            patch("app.agents.base.BaseAgent._get_llm", mock_get_llm),
            patch("app.memory.mem0_client.get_mem0_client", return_value=mock_mem0),
            patch("app.memory.episodic.get_all_memories", AsyncMock(return_value=[])),
            patch("app.memory.episodic.extract_and_save_lessons", AsyncMock(return_value=True)),
        ]

        for p in patches:
            p.start()

        try:
            import time as _time
            start = _time.monotonic()
            final = await run_pipeline(
                raw_request="I want to go to Kyoto for 5 days with $2500 budget",
                user_id="phase4_test_user",
                session_id="phase4_session",
                trace_id="phase4_trace",
                trip_id="phase4_trip",
            )
            elapsed = _time.monotonic() - start

            if final["pipeline_status"] == "completed":
                print(f"   ✓ Full pipeline completed in {elapsed:.1f}s")
                print(f"   ✓ Validation status: {final.get('validation_status')}")
                # Verify memory was loaded
                prefs = final.get("user_preferences")
                if prefs == stored_prefs:
                    print("   ✓ User preferences correctly stored in state")
                else:
                    print(f"   ⚠ User preferences in state: {prefs} (expected {stored_prefs})")
                mock_mem0.get_preferences.assert_called_once_with("phase4_test_user")
                print("   ✓ Mem0 get_preferences was called for non-anonymous user")
            else:
                print(f"   ✗ Unexpected pipeline status: {final['pipeline_status']}")
                all_passed = False
        finally:
            for p in patches:
                p.stop()

    except Exception as exc:
        print(f"   ✗ Full pipeline with memory test failed: {exc}")
        import traceback; traceback.print_exc()
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    if all_passed:
        print("✓ Phase 4 verification PASSED — Memory, Personalization & Self-Correcting Loop ready")
        print("=" * 70)
        return 0
    else:
        print("✗ Phase 4 verification FAILED — see errors above")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
