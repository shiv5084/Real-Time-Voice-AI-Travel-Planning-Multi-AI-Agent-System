#!/usr/bin/env python3
"""Verify Phase 1 — Data layer, Supabase schema, auth, Redis sessions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _phase_common import run_phase

REQUIRED = [
    "backend/app/models/user.py",
    "backend/app/models/trip.py",
    "backend/app/models/itinerary.py",
    "backend/app/models/budget.py",
    "backend/app/models/agent.py",
    "backend/app/routers/auth.py",
    "backend/app/routers/health.py",
    "backend/app/services/auth.py",
    "backend/app/memory/session.py",
    "backend/app/middleware/auth.py",
    "backend/supabase/migrations/001_initial_schema.sql",
    "scripts/seed_db.py",
]

if __name__ == "__main__":
    sys.exit(
        run_phase(
            1,
            "Data Layer & Authentication",
            REQUIRED,
            pytest_paths=[
                "backend/tests/unit/test_models.py",
                "backend/tests/integration/test_auth.py",
            ],
        )
    )
