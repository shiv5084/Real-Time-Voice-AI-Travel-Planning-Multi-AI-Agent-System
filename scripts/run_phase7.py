#!/usr/bin/env python3
"""Verify Phase 7 — E2E, golden dataset, Git, CI, production readiness."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _phase_common import ROOT, run_phase

REQUIRED = [
    "scripts/test_golden_dataset.py",
    "scripts/load_test.py",
    "scripts/migrate_to_managed.py",
    "docker-compose.prod.yml",
    ".env.production.example",
    "backend/tests/e2e/test_golden_dataset_e2e.py",
    "doc/deployment-guide.md",
]

OPTIONAL = [
    ".github/workflows/ci.yml",
    "backend/tests/e2e/test_managed_migration.py",
]


def check_prod_compose_no_local_db() -> tuple[bool, str]:
    compose = ROOT / "docker-compose.prod.yml"
    if not compose.exists():
        return False, "docker-compose.prod.yml missing — create in Phase 7.13"
    text = compose.read_text(encoding="utf-8").lower()
    if "postgres:" in text or "redis:" in text:
        return False, "docker-compose.prod.yml must NOT include postgres/redis (use managed services)"
    return True, "docker-compose.prod.yml has no local postgres/redis services"


def check_migration_script() -> tuple[bool, str]:
    script = ROOT / "scripts/migrate_to_managed.py"
    if not script.exists():
        return False, "scripts/migrate_to_managed.py missing"
    return True, "Managed migration script present"


def check_git_repo() -> tuple[bool, str]:
    if not (ROOT / ".git").exists():
        return False, "Git not initialized (.git missing) — complete Phase 7.15"
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, "git status failed"
    return True, "Git repository initialized"


def check_ci_workflow() -> tuple[bool, str]:
    ci = ROOT / ".github/workflows/ci.yml"
    if not ci.exists():
        return False, "Missing .github/workflows/ci.yml — complete Phase 7.16"
    text = ci.read_text(encoding="utf-8")
    if "pytest" not in text and "npm" not in text:
        return False, "ci.yml should run pytest and npm run build"
    return True, "GitHub Actions CI workflow present"


if __name__ == "__main__":
    sys.exit(
        run_phase(
            7,
            "Integration, Git, CI & Production Readiness",
            REQUIRED,
            optional_files=OPTIONAL,
            pytest_paths=[
                "backend/tests/e2e",
            ],
            extra_checks=[
                check_git_repo,
                check_ci_workflow,
                check_migration_script,
                check_prod_compose_no_local_db,
            ],
        )
    )
