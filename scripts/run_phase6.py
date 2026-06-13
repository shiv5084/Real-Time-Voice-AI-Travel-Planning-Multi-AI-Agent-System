#!/usr/bin/env python3
"""
Verify Phase 6 — Frontend & Output Generation.

Checks:
  - All Next.js page routes exist
  - All React components exist
  - All lib utilities exist
  - Design system & layout configuration
  - Config files (next.config.ts, .env.local.example)
  - package.json dependencies (recharts, @supabase/supabase-js)
  - Backend services (pdf.py, email.py, itineraries.py)
  - requirements.txt has reportlab
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _check(label: str, condition: bool, detail: str = "") -> tuple[bool, str]:
    msg = label
    if detail:
        msg += f"  →  {detail}"
    return condition, msg


def check_file_exists(path: str) -> tuple[bool, str]:
    p = ROOT / path
    return _check(path, p.exists(), "" if p.exists() else f"missing {path}")


def check_file_contains(path: str, needle: str, label: str | None = None) -> tuple[bool, str]:
    p = ROOT / path
    if not p.exists():
        return False, f"{label or path}  →  file missing"
    text = p.read_text(encoding="utf-8", errors="ignore")
    found = needle in text
    desc = label or f"{path} contains '{needle}'"
    return _check(desc, found, "" if found else f"{path} missing '{needle}'")


def run_all() -> int:
    results: list[tuple[bool, str]] = []

    # ── Frontend pages ────────────────────────────────────────────────────
    print("\n[ Frontend pages ]")
    pages = [
        ("Landing page",           "frontend/src/app/page.tsx"),
        ("Login page",             "frontend/src/app/(auth)/login/page.tsx"),
        ("Register page",          "frontend/src/app/(auth)/register/page.tsx"),
        ("Dashboard page",         "frontend/src/app/dashboard/page.tsx"),
        ("Planner page",           "frontend/src/app/planner/page.tsx"),
        ("Itinerary detail page",  "frontend/src/app/itinerary/[id]/page.tsx"),
        ("Profile page",           "frontend/src/app/profile/page.tsx"),
    ]
    for label, path in pages:
        ok, msg = check_file_exists(path)
        results.append((ok, f"{label}  →  {'OK' if ok else f'missing {path}'}"))
        print(f"{'PASS' if ok else 'FAIL'}  {label}  →  {'OK' if ok else f'missing {path}'}")

    # ── Components ────────────────────────────────────────────────────────
    print("\n[ Components ]")
    components = [
        "VoiceInput", "ChatInterface", "PlanStatus",
        "ItineraryCard", "BudgetChart", "TripCard",
    ]
    for c in components:
        path = f"frontend/src/components/{c}.tsx"
        ok, _ = check_file_exists(path)
        results.append((ok, f"{c} component  →  {'OK' if ok else f'missing {path}'}"))
        print(f"{'PASS' if ok else 'FAIL'}  {c} component  →  {'OK' if ok else f'missing {path}'}")

    # ── Lib utilities ─────────────────────────────────────────────────────
    print("\n[ Lib utilities ]")
    for lib in ["api.ts", "auth.ts", "sse.ts", "voice.ts"]:
        path = f"frontend/src/lib/{lib}"
        ok, _ = check_file_exists(path)
        results.append((ok, f"{lib}  →  {'OK' if ok else f'missing {path}'}"))
        print(f"{'PASS' if ok else 'FAIL'}  {lib}  →  {'OK' if ok else f'missing {path}'}")

    # ── Design system & layout ────────────────────────────────────────────
    print("\n[ Design system & layout ]")
    ok1, _ = check_file_contains(
        "frontend/src/app/globals.css", "--bg-base", "globals.css has dark palette variables"
    )
    results.append((ok1, f"globals.css has dark palette variables  →  {'OK' if ok1 else 'FAIL'}"))
    print(f"{'PASS' if ok1 else 'FAIL'}  globals.css has dark palette variables")

    ok2, _ = check_file_contains(
        "frontend/src/app/layout.tsx", "dark", "layout.tsx applies dark class"
    )
    results.append((ok2, f"layout.tsx applies dark class  →  {'OK' if ok2 else 'FAIL'}"))
    print(f"{'PASS' if ok2 else 'FAIL'}  layout.tsx applies dark class")

    # ── Config files ──────────────────────────────────────────────────────
    print("\n[ Config files ]")
    ok3, _ = check_file_exists("frontend/next.config.ts")
    results.append((ok3, f"next.config.ts exists  →  {'OK' if ok3 else 'FAIL'}"))
    print(f"{'PASS' if ok3 else 'FAIL'}  next.config.ts exists")

    ok4, _ = check_file_contains("frontend/next.config.ts", "rewrites", "next.config.ts has API rewrite")
    results.append((ok4, f"next.config.ts has API rewrite  →  {'OK' if ok4 else 'FAIL'}"))
    print(f"{'PASS' if ok4 else 'FAIL'}  next.config.ts has API rewrite")

    ok5, _ = check_file_exists("frontend/.env.local.example")
    results.append((ok5, f".env.local.example exists  →  {'OK' if ok5 else 'FAIL'}"))
    print(f"{'PASS' if ok5 else 'FAIL'}  .env.local.example exists")

    ok6, _ = check_file_contains("frontend/.env.local.example", "NEXT_PUBLIC_API_URL")
    results.append((ok6, f".env.local.example documents NEXT_PUBLIC_API_URL  →  {'OK' if ok6 else 'FAIL'}"))
    print(f"{'PASS' if ok6 else 'FAIL'}  .env.local.example documents NEXT_PUBLIC_API_URL")

    ok7, _ = check_file_contains("frontend/.env.local.example", "NEXT_PUBLIC_SUPABASE_URL")
    results.append((ok7, f".env.local.example documents NEXT_PUBLIC_SUPABASE_URL  →  {'OK' if ok7 else 'FAIL'}"))
    print(f"{'PASS' if ok7 else 'FAIL'}  .env.local.example documents NEXT_PUBLIC_SUPABASE_URL")

    # package.json dependencies
    pkg_path = ROOT / "frontend/package.json"
    if pkg_path.exists():
        pkg = json.loads(pkg_path.read_text())
        all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        for dep in ["recharts", "@supabase/supabase-js"]:
            ok = dep in all_deps
            results.append((ok, f"package.json has {dep}  →  {'OK' if ok else 'MISSING'}"))
            print(f"{'PASS' if ok else 'FAIL'}  package.json has {dep}")
    else:
        results.append((False, "frontend/package.json missing"))
        print("FAIL  frontend/package.json missing")

    # ── Backend services ──────────────────────────────────────────────────
    print("\n[ Backend services ]")
    ok_pdf, _ = check_file_exists("backend/app/services/pdf.py")
    results.append((ok_pdf, f"pdf.py exists  →  {'OK' if ok_pdf else 'FAIL'}"))
    print(f"{'PASS' if ok_pdf else 'FAIL'}  pdf.py exists")

    ok_pdf2, _ = check_file_contains("backend/app/services/pdf.py", "reportlab", "pdf.py uses ReportLab")
    results.append((ok_pdf2, f"pdf.py uses ReportLab  →  {'OK' if ok_pdf2 else 'FAIL'}"))
    print(f"{'PASS' if ok_pdf2 else 'FAIL'}  pdf.py uses ReportLab")

    ok_email, _ = check_file_exists("backend/app/services/email.py")
    results.append((ok_email, f"email.py exists  →  {'OK' if ok_email else 'FAIL'}"))
    print(f"{'PASS' if ok_email else 'FAIL'}  email.py exists")

    ok_email2, _ = check_file_contains("backend/app/services/email.py", "GmailMCPClient", "email.py uses GmailMCPClient")
    results.append((ok_email2, f"email.py uses GmailMCPClient  →  {'OK' if ok_email2 else 'FAIL'}"))
    print(f"{'PASS' if ok_email2 else 'FAIL'}  email.py uses GmailMCPClient")

    # ── Backend router ────────────────────────────────────────────────────
    print("\n[ Backend router ]")
    itin_path = "backend/app/routers/itineraries.py"
    ok_it, _ = check_file_exists(itin_path)
    results.append((ok_it, f"itineraries.py exists  →  {'OK' if ok_it else 'FAIL'}"))
    print(f"{'PASS' if ok_it else 'FAIL'}  itineraries.py exists")

    for needle, label in [
        ("/itineraries/{",  "itineraries.py has GET detail endpoint"),
        ("/pdf",             "itineraries.py has PDF endpoint"),
        ("/email",           "itineraries.py has email endpoint"),
        ("Depends",          "itineraries.py requires JWT auth"),
    ]:
        ok, _ = check_file_contains(itin_path, needle, label)
        results.append((ok, f"{label}  →  {'OK' if ok else 'FAIL'}"))
        print(f"{'PASS' if ok else 'FAIL'}  {label}")

    ok_init, _ = check_file_contains(
        "backend/app/routers/__init__.py", "itineraries_router",
        "routers/__init__.py exports itineraries_router"
    )
    results.append((ok_init, f"routers/__init__.py exports itineraries_router  →  {'OK' if ok_init else 'FAIL'}"))
    print(f"{'PASS' if ok_init else 'FAIL'}  routers/__init__.py exports itineraries_router")

    ok_main, _ = check_file_contains(
        "backend/app/main.py", "itineraries_router",
        "main.py includes itineraries_router"
    )
    results.append((ok_main, f"main.py includes itineraries_router  →  {'OK' if ok_main else 'FAIL'}"))
    print(f"{'PASS' if ok_main else 'FAIL'}  main.py includes itineraries_router")

    # ── Dependencies ──────────────────────────────────────────────────────
    print("\n[ Dependencies ]")
    ok_rl, _ = check_file_contains("backend/requirements.txt", "reportlab")
    results.append((ok_rl, f"requirements.txt has reportlab  →  {'OK' if ok_rl else 'FAIL'}"))
    print(f"{'PASS' if ok_rl else 'FAIL'}  requirements.txt has reportlab")

    # ── Summary ───────────────────────────────────────────────────────────
    passed = sum(1 for ok, _ in results if ok)
    total  = len(results)
    issues = [(msg) for ok, msg in results if not ok]

    print(f"\n{'-'*64}")
    print(f"Results: {passed}/{total} checks passed")

    if issues:
        print(f"Phase 6 verification: FAILED  ({len(issues)} issue(s))")
        for iss in issues:
            print(f"  ✗ {iss}")
        return 1

    print("Phase 6 verification: PASSED ✓")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
