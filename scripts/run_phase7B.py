#!/usr/bin/env python3
"""Verify Phase 7B — Integration Testing, Optimization & Production Readiness."""

import subprocess
import sys
from pathlib import Path

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from _phase_common import ROOT, check_files, run_pytest

def check_environment():
    """Verify managed services environment is configured."""
    from app.config import get_settings
    
    try:
        settings = get_settings()
        
        # Check if using managed services
        if settings.app_env not in ("staging", "production"):
            print("WARNING: APP_ENV is not set to 'staging' or 'production'")
            print("Phase 7B tests should run against managed services (Supabase + Upstash)")
            print(f"Current APP_ENV: {settings.app_env}")
            return False, "APP_ENV not set to managed services environment"
        
        # Check managed service credentials
        missing = []
        if not settings.supabase_url:
            missing.append("SUPABASE_URL")
        if not settings.supabase_anon_key:
            missing.append("SUPABASE_ANON_KEY")
        if not settings.upstash_redis_url:
            missing.append("UPSTASH_REDIS_URL")
        
        if missing:
            return False, f"Missing managed service credentials: {', '.join(missing)}"
        
        return True, "Managed services environment configured"
    except Exception as e:
        return False, f"Environment check failed: {e}"

def check_test_scripts_exist():
    """Verify all Phase 7B test scripts exist."""
    required_files = [
        "scripts/test_golden_dataset.py",
        "scripts/load_test.py",
        "backend/tests/e2e/test_golden_dataset_e2e.py",
        "backend/tests/e2e/test_security.py",
        "backend/tests/e2e/test_graceful_degradation.py",
    ]
    
    missing = check_files(required_files)
    if missing:
        return False, f"Missing test scripts: {', '.join(missing)}"
    return True, f"All {len(required_files)} test scripts exist"

def run_e2e_tests():
    """Run Phase 7B E2E tests."""
    test_paths = [
        "backend/tests/e2e/test_golden_dataset_e2e.py",
        "backend/tests/e2e/test_security.py",
        "backend/tests/e2e/test_graceful_degradation.py",
    ]
    
    print("\nRunning E2E tests...")
    if run_pytest(test_paths, markers="e2e"):
        return True, "E2E tests passed"
    return False, "E2E tests failed"

def check_golden_dataset_runner():
    """Verify golden dataset evaluation runner can be executed."""
    script_path = ROOT / "scripts" / "test_golden_dataset.py"
    if not script_path.exists():
        return False, "Golden dataset runner script not found"
    
    # Check if script is syntactically valid
    try:
        with open(script_path, 'r') as f:
            compile(f.read(), script_path, 'exec')
        return True, "Golden dataset runner is valid"
    except SyntaxError as e:
        return False, f"Golden dataset runner has syntax error: {e}"

def check_load_test_runner():
    """Verify load test runner can be executed."""
    script_path = ROOT / "scripts" / "load_test.py"
    if not script_path.exists():
        return False, "Load test runner script not found"
    
    # Check if script is syntactically valid
    try:
        with open(script_path, 'r') as f:
            compile(f.read(), script_path, 'exec')
        return True, "Load test runner is valid"
    except SyntaxError as e:
        return False, f"Load test runner has syntax error: {e}"

def main():
    """Execute Phase 7B verification."""
    print("\n" + "="*60)
    print("Phase 7B: Integration Testing, Optimization & Production Readiness")
    print("="*60 + "\n")
    
    failed = False
    
    # Check environment
    print("1. Checking managed services environment...")
    ok, msg = check_environment()
    if ok:
        print(f"   [OK] {msg}")
    else:
        print(f"   [FAIL] {msg}")
        failed = True
    
    # Check test scripts exist
    print("\n2. Checking test scripts...")
    ok, msg = check_test_scripts_exist()
    if ok:
        print(f"   [OK] {msg}")
    else:
        print(f"   [FAIL] {msg}")
        failed = True
    
    # Check golden dataset runner
    print("\n3. Checking golden dataset evaluation runner...")
    ok, msg = check_golden_dataset_runner()
    if ok:
        print(f"   [OK] {msg}")
    else:
        print(f"   [FAIL] {msg}")
        failed = True
    
    # Check load test runner
    print("\n4. Checking load test runner...")
    ok, msg = check_load_test_runner()
    if ok:
        print(f"   [OK] {msg}")
    else:
        print(f"   [FAIL] {msg}")
        failed = True
    
    # Run E2E tests
    print("\n5. Running E2E tests...")
    ok, msg = run_e2e_tests()
    if ok:
        print(f"   [OK] {msg}")
    else:
        print(f"   [FAIL] {msg}")
        failed = True
    
    # Print summary
    print("\n" + "="*60)
    if failed:
        print("Phase 7B verification: FAILED")
        print("="*60 + "\n")
        print("To fix failures:")
        print("1. Ensure APP_ENV is set to 'staging' or 'production'")
        print("2. Configure SUPABASE_URL, SUPABASE_ANON_KEY, UPSTASH_REDIS_URL")
        print("3. Ensure backend server is running on http://localhost:8000")
        print("4. Run: python scripts/test_golden_dataset.py")
        print("5. Run: python scripts/load_test.py")
        print("6. Run: pytest backend/tests/e2e/ -m e2e")
        return 1
    else:
        print("Phase 7B verification: PASSED")
        print("="*60 + "\n")
        print("Next steps:")
        print("1. Run golden dataset evaluation: python scripts/test_golden_dataset.py")
        print("2. Run load tests: python scripts/load_test.py")
        print("3. Review test results in backend/test_results/")
        print("4. Perform latency and cost optimization")
        print("5. Update eval.md with Phase 7B results")
        return 0

if __name__ == "__main__":
    sys.exit(main())
