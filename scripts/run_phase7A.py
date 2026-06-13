#!/usr/bin/env python3
"""
Verify Phase 7A — Managed Services Migration (Supabase + Upstash).

Checks:
  - Migration script exists
  - .env.production.example exists with all required variables
  - config.py supports APP_ENV=production/staging
  - session.py supports Upstash Redis
  - E2e test for managed migration exists
  - README updated with production deployment docs
"""

from __future__ import annotations

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

    # ── Migration script ────────────────────────────────────────────────────
    print("\n[ Migration script ]")
    ok1, _ = check_file_exists("scripts/migrate_to_managed.py")
    results.append((ok1, f"migrate_to_managed.py exists  →  {'OK' if ok1 else 'FAIL'}"))
    print(f"{'PASS' if ok1 else 'FAIL'}  migrate_to_managed.py exists")

    ok2, _ = check_file_contains(
        "scripts/migrate_to_managed.py",
        "supabase",
        "migrate_to_managed.py references Supabase"
    )
    results.append((ok2, f"migrate_to_managed.py references Supabase  →  {'OK' if ok2 else 'FAIL'}"))
    print(f"{'PASS' if ok2 else 'FAIL'}  migrate_to_managed.py references Supabase")

    ok3, _ = check_file_contains(
        "scripts/migrate_to_managed.py",
        "upstash",
        "migrate_to_managed.py references Upstash"
    )
    results.append((ok3, f"migrate_to_managed.py references Upstash  →  {'OK' if ok3 else 'FAIL'}"))
    print(f"{'PASS' if ok3 else 'FAIL'}  migrate_to_managed.py references Upstash")

    # ── Production environment example ──────────────────────────────────────
    print("\n[ Production environment example ]")
    ok4, _ = check_file_exists(".env.production.example")
    results.append((ok4, f".env.production.example exists  →  {'OK' if ok4 else 'FAIL'}"))
    print(f"{'PASS' if ok4 else 'FAIL'}  .env.production.example exists")

    for var in [
        "APP_ENV=production",
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_KEY",
        "UPSTASH_REDIS_URL",
        "UPSTASH_REDIS_TOKEN",
    ]:
        ok, _ = check_file_contains(
            ".env.production.example",
            var,
            f".env.production.example has {var}"
        )
        results.append((ok, f".env.production.example has {var}  →  {'OK' if ok else 'FAIL'}"))
        print(f"{'PASS' if ok else 'FAIL'}  .env.production.example has {var}")

    # ── Config.py support for managed services ─────────────────────────────
    print("\n[ Config.py support for managed services ]")
    ok5, _ = check_file_contains(
        "backend/app/config.py",
        "upstash_redis_url",
        "config.py has upstash_redis_url field"
    )
    results.append((ok5, f"config.py has upstash_redis_url field  →  {'OK' if ok5 else 'FAIL'}"))
    print(f"{'PASS' if ok5 else 'FAIL'}  config.py has upstash_redis_url field")

    ok6, _ = check_file_contains(
        "backend/app/config.py",
        "supabase_url",
        "config.py has supabase_url field"
    )
    results.append((ok6, f"config.py has supabase_url field  →  {'OK' if ok6 else 'FAIL'}"))
    print(f"{'PASS' if ok6 else 'FAIL'}  config.py has supabase_url field")

    ok7, _ = check_file_contains(
        "backend/app/config.py",
        "validate_env_profile",
        "config.py has environment validation"
    )
    results.append((ok7, f"config.py has environment validation  →  {'OK' if ok7 else 'FAIL'}"))
    print(f"{'PASS' if ok7 else 'FAIL'}  config.py has environment validation")

    # ── Session.py support for Upstash ───────────────────────────────────────
    print("\n[ Session.py support for Upstash ]")
    ok8, _ = check_file_contains(
        "backend/app/memory/session.py",
        "upstash_redis_url",
        "session.py references upstash_redis_url"
    )
    results.append((ok8, f"session.py references upstash_redis_url  →  {'OK' if ok8 else 'FAIL'}"))
    print(f"{'PASS' if ok8 else 'FAIL'}  session.py references upstash_redis_url")

    ok9, _ = check_file_contains(
        "backend/app/memory/session.py",
        "upstash_redis_token",
        "session.py references upstash_redis_token"
    )
    results.append((ok9, f"session.py references upstash_redis_token  →  {'OK' if ok9 else 'FAIL'}"))
    print(f"{'PASS' if ok9 else 'FAIL'}  session.py references upstash_redis_token")

    ok10, _ = check_file_contains(
        "backend/app/memory/session.py",
        "staging",
        "session.py handles staging environment"
    )
    results.append((ok10, f"session.py handles staging environment  →  {'OK' if ok10 else 'FAIL'}"))
    print(f"{'PASS' if ok10 else 'FAIL'}  session.py handles staging environment")

    # ── E2E test for managed migration ───────────────────────────────────────
    print("\n[ E2E test for managed migration ]")
    ok11, _ = check_file_exists("backend/tests/e2e/test_managed_migration.py")
    results.append((ok11, f"test_managed_migration.py exists  →  {'OK' if ok11 else 'FAIL'}"))
    print(f"{'PASS' if ok11 else 'FAIL'}  test_managed_migration.py exists")

    # ── README documentation ────────────────────────────────────────────────
    print("\n[ README documentation ]")
    ok12, _ = check_file_contains(
        "README.md",
        "Supabase",
        "README.md documents Supabase"
    )
    results.append((ok12, f"README.md documents Supabase  →  {'OK' if ok12 else 'FAIL'}"))
    print(f"{'PASS' if ok12 else 'FAIL'}  README.md documents Supabase")

    ok13, _ = check_file_contains(
        "README.md",
        "Upstash",
        "README.md documents Upstash"
    )
    results.append((ok13, f"README.md documents Upstash  →  {'OK' if ok13 else 'FAIL'}"))
    print(f"{'PASS' if ok13 else 'FAIL'}  README.md documents Upstash")

    ok14, _ = check_file_contains(
        "README.md",
        "production",
        "README.md documents production deployment"
    )
    results.append((ok14, f"README.md documents production deployment  →  {'OK' if ok14 else 'FAIL'}"))
    print(f"{'PASS' if ok14 else 'FAIL'}  README.md documents production deployment")

    # ── Summary ───────────────────────────────────────────────────────────
    passed = sum(1 for ok, _ in results if ok)
    total  = len(results)
    issues = [(msg) for ok, msg in results if not ok]

    print(f"\n{'-'*64}")
    print(f"Results: {passed}/{total} checks passed")

    if issues:
        print(f"Phase 7A verification: FAILED  ({len(issues)} issue(s))")
        for iss in issues:
            print(f"  ✗ {iss}")
        return 1

    print("Phase 7A verification: PASSED")
    print("\nNext steps:")
    print("1. Run: python scripts/migrate_to_managed.py")
    print("2. Set APP_ENV=production in your .env file")
    print("3. Restart your application")
    print("4. Run golden dataset tests to verify migration")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
