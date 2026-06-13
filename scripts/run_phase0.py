#!/usr/bin/env python3
"""Verify Phase 0 — Project scaffolding, FastAPI skeleton, Next.js init, utilities."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _phase_common import ROOT, env_keys_documented, run_phase

REQUIRED = [
    "backend/app/main.py",
    "backend/app/config.py",
    "backend/app/utils/logging.py",
    "backend/app/utils/tracing.py",
    "backend/app/utils/errors.py",
    "backend/app/utils/validators.py",
    "backend/requirements.txt",
    "backend/Dockerfile",
    ".env.example",
    "docker-compose.yml",
    "docker/postgres/init.sql",
    "README.md",
    ".gitignore",
    "scripts/_phase_common.py",
]

OPTIONAL = [
    "frontend/package.json",
    "frontend/next.config.ts",
    "frontend/src/app/page.tsx",
]


def check_env_example() -> tuple[bool, str]:
    keys = ["APP_ENV", "DATABASE_URL", "REDIS_URL"]
    missing = env_keys_documented(keys)
    if missing:
        return False, f".env.example missing local dev keys: {', '.join(missing)}"
    return True, ".env.example documents APP_ENV, DATABASE_URL, REDIS_URL (local stack)"


def check_docker_compose_services() -> tuple[bool, str]:
    compose = ROOT / "docker-compose.yml"
    if not compose.exists():
        return False, "docker-compose.yml missing"
    text = compose.read_text(encoding="utf-8").lower()
    for svc in ("postgres", "redis"):
        if svc not in text:
            return False, f"docker-compose.yml must define '{svc}' service for local dev"
    return True, "docker-compose.yml includes postgres and redis services"


if __name__ == "__main__":
    sys.exit(
        run_phase(
            0,
            "Scaffolding & DevOps Foundation",
            REQUIRED,
            optional_files=OPTIONAL,
            pytest_paths=["backend/tests"],
            extra_checks=[check_env_example, check_docker_compose_services],
        )
    )
