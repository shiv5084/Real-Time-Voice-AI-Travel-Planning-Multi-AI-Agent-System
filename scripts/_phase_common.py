"""Shared helpers for scripts/run_phase0.py … run_phase7.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent


def check_files(paths: list[str], optional: list[str] | None = None) -> list[str]:
    """Return list of missing required paths (relative to ROOT)."""
    optional = optional or []
    missing: list[str] = []
    for rel in paths:
        if rel in optional and not (ROOT / rel).exists():
            continue
        if not (ROOT / rel).exists():
            missing.append(rel)
    return missing


def run_pytest(paths: list[str], markers: str | None = None) -> bool:
    """Run pytest on given paths; return True if all pass or no tests yet."""
    args = [sys.executable, "-m", "pytest", "-q", *paths]
    if markers:
        args.extend(["-m", markers])
    existing = [p for p in paths if (ROOT / p).exists()]
    if not existing:
        return True
    result = subprocess.run(args, cwd=ROOT, capture_output=False)
    return result.returncode == 0


def run_npm_script(script: str, cwd: str = "frontend") -> bool:
    """Run npm script in frontend; skip if package.json missing."""
    pkg = ROOT / cwd / "package.json"
    if not pkg.exists():
        return True
    result = subprocess.run(
        ["npm", "run", script],
        cwd=ROOT / cwd,
        shell=sys.platform == "win32",
    )
    return result.returncode == 0


def env_keys_documented(keys: list[str]) -> list[str]:
    """Return env keys missing from .env.example."""
    example = ROOT / ".env.example"
    if not example.exists():
        return keys
    text = example.read_text(encoding="utf-8")
    return [k for k in keys if k not in text]


def run_phase(
    phase: int,
    title: str,
    file_checks: list[str],
    optional_files: list[str] | None = None,
    pytest_paths: list[str] | None = None,
    extra_checks: list[Callable[[], tuple[bool, str]]] | None = None,
) -> int:
    """Execute phase verification; return exit code 0 or 1."""
    print(f"\n{'=' * 60}")
    print(f"Phase {phase}: {title}")
    print(f"{'=' * 60}\n")

    failed = False

    missing = check_files(file_checks, optional=optional_files)
    if missing:
        print("FAIL — Missing required files:")
        for m in missing:
            print(f"  - {m}")
        failed = True
    else:
        print(f"OK — All {len(file_checks)} required paths exist")

    if pytest_paths:
        print("\nRunning pytest …")
        if run_pytest(pytest_paths):
            print("OK — pytest passed (or no tests collected)")
        else:
            print("FAIL — pytest failed")
            failed = True

    if extra_checks:
        for fn in extra_checks:
            ok, msg = fn()
            if ok:
                print(f"OK — {msg}")
            else:
                print(f"FAIL — {msg}")
                failed = True

    if failed:
        print(f"\nPhase {phase} verification: FAILED\n")
        return 1
    print(f"\nPhase {phase} verification: PASSED\n")
    return 0
