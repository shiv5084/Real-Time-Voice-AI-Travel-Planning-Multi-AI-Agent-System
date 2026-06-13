#!/usr/bin/env python
"""Live Mem0 integration test — makes REAL API calls to the Mem0 cloud.

No mocks. Run this inside Docker to verify MEM0_API_KEY is valid and the
Mem0 platform is reachable from the container.

Usage (from project root):
    docker compose run --rm backend python scripts/test_mem0_live.py

Exit codes:
    0 — all checks passed, Mem0 is live and working
    1 — one or more checks failed (see output for details)
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


async def main() -> int:
    print("=" * 65)
    print("Mem0 Live Integration Test — Real API calls, no mocks")
    print("=" * 65)

    # ── Pre-flight: check env var is set ──────────────────────────────
    api_key = os.environ.get("MEM0_API_KEY", "")
    if not api_key:
        print("\n✗ MEM0_API_KEY is not set in the environment.")
        print("  Add it to your .env file and rebuild the container.")
        return 1

    print(f"\nMEM0_API_KEY : {'*' * 8}{api_key[-6:]}  (last 6 chars shown)")

    from app.config import get_settings
    settings = get_settings()
    print(f"App env      : {settings.app_env}")
    print(f"Redis URL    : {settings.redis_url}")

    all_passed = True
    # Use a unique user ID per run so tests don't collide across runs
    test_user = f"live_test_{uuid.uuid4().hex[:8]}"
    print(f"\nTest user ID : {test_user}")

    # ── Import the client ─────────────────────────────────────────────
    try:
        from app.memory.mem0_client import Mem0Client
        import app.memory.mem0_client as mem0_module
        # Reset singleton so this test gets a fresh client
        mem0_module._mem0_client = None
        client = Mem0Client()
    except Exception as exc:
        print(f"\n✗ Failed to import Mem0Client: {exc}")
        return 1

    # ─────────────────────────────────────────────────────────────────
    # Test 1: SDK initialisation — must connect to Mem0 cloud
    # ─────────────────────────────────────────────────────────────────
    print("\n[1/5] Initialising Mem0 AsyncMemoryClient...")
    try:
        t0 = time.monotonic()
        await client._ensure_init()
        elapsed = (time.monotonic() - t0) * 1000

        if client._client is not None:
            print(f"   ✓ AsyncMemoryClient initialised via Mem0 cloud ({elapsed:.0f} ms)")
        elif client._redis is not None:
            print(f"   ⚠ Fell back to Redis (MEM0_API_KEY set but SDK init failed)")
            print("     Check the logs above for the init error.")
            all_passed = False
        else:
            print("   ✗ Neither Mem0 cloud nor Redis is available")
            all_passed = False
    except Exception as exc:
        print(f"   ✗ Initialisation raised an exception: {exc}")
        all_passed = False

    # ─────────────────────────────────────────────────────────────────
    # Test 2: store_preferences — writes to Mem0 cloud
    # ─────────────────────────────────────────────────────────────────
    print("\n[2/5] Storing travel preferences via Mem0...")
    prefs_to_store = {
        "food": "Japanese",
        "accommodation_type": "boutique hotel",
        "crowd_tolerance": "low",
        "dietary_restrictions": "vegetarian",
        "travel_style": "cultural",
    }
    try:
        t0 = time.monotonic()
        stored = await client.store_preferences(test_user, prefs_to_store)
        elapsed = (time.monotonic() - t0) * 1000

        if stored:
            print(f"   ✓ Preferences stored successfully ({elapsed:.0f} ms)")
            print(f"     Keys stored: {list(prefs_to_store.keys())}")
        else:
            print("   ✗ store_preferences returned False")
            all_passed = False
    except Exception as exc:
        print(f"   ✗ store_preferences raised: {exc}")
        all_passed = False

    # Give Mem0 a moment to process the memory (async background indexing)
    print("   ⏳ Waiting 3 s for Mem0 to index...")
    await asyncio.sleep(3)

    # ─────────────────────────────────────────────────────────────────
    # Test 3: get_memories — retrieves raw memories from Mem0 cloud
    # ─────────────────────────────────────────────────────────────────
    print("\n[3/5] Retrieving raw memories from Mem0...")
    try:
        t0 = time.monotonic()
        memories = await client.get_memories(
            test_user,
            query="travel preferences food accommodation",
            limit=10,
        )
        elapsed = (time.monotonic() - t0) * 1000

        if isinstance(memories, list):
            print(f"   ✓ get_memories returned {len(memories)} memory entries ({elapsed:.0f} ms)")
            for i, m in enumerate(memories[:3]):
                print(f"     [{i+1}] {m.get('memory', str(m))[:80]}")
            if not memories:
                print("   ⚠ No memories returned yet — Mem0 indexing may still be in progress")
        else:
            print(f"   ✗ Unexpected return type: {type(memories)}")
            all_passed = False
    except Exception as exc:
        print(f"   ✗ get_memories raised: {exc}")
        all_passed = False

    # ─────────────────────────────────────────────────────────────────
    # Test 4: get_preferences — structured preference extraction
    # ─────────────────────────────────────────────────────────────────
    print("\n[4/5] Retrieving structured preferences via get_preferences...")
    try:
        t0 = time.monotonic()
        retrieved = await client.get_preferences(test_user)
        elapsed = (time.monotonic() - t0) * 1000

        print(f"   ✓ get_preferences returned ({elapsed:.0f} ms): {retrieved}")

        if retrieved:
            print("   ✓ Preferences non-empty — Mem0 round-trip confirmed")
        else:
            # Mem0 indexing can lag a few seconds; not a hard failure
            print("   ⚠ Empty dict returned — Mem0 may still be indexing.")
            print("     This is not a failure; re-run in ~10s if you want to verify.")
    except Exception as exc:
        print(f"   ✗ get_preferences raised: {exc}")
        all_passed = False

    # ─────────────────────────────────────────────────────────────────
    # Test 5: delete_user_memories — cleanup (also verifies delete API)
    # ─────────────────────────────────────────────────────────────────
    print("\n[5/5] Deleting test user memories (cleanup)...")
    try:
        t0 = time.monotonic()
        deleted = await client.delete_user_memories(test_user)
        elapsed = (time.monotonic() - t0) * 1000

        if deleted:
            print(f"   ✓ delete_user_memories succeeded ({elapsed:.0f} ms)")
        else:
            print("   ✗ delete_user_memories returned False")
            all_passed = False
    except Exception as exc:
        print(f"   ✗ delete_user_memories raised: {exc}")
        all_passed = False

    # ── Summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    if all_passed:
        print("✓ All Mem0 live checks PASSED — API key is valid and cloud is reachable")
        print("  Check your Mem0 dashboard → you should see API activity for this run.")
    else:
        print("✗ Some Mem0 live checks FAILED — see errors above")
        print("  Common causes:")
        print("  - MEM0_API_KEY is wrong or expired")
        print("  - mem0ai package version mismatch (check requirements.txt)")
        print("  - Network connectivity issue inside the container")
    print("=" * 65)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
