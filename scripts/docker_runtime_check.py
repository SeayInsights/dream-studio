#!/usr/bin/env python3
"""Clean-room runtime validation entrypoint for the Docker harness."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ISOLATED_HOME = Path(os.environ.get("HOME", "/tmp/dream-studio-user"))
ISOLATED_STUDIO_HOME = Path(os.environ.get("DREAM_STUDIO_HOME", "/tmp/dream-studio-home"))


def _run(label: str, command: list[str]) -> None:
    print(f"\n== {label} ==")
    print(" ".join(command))
    result = subprocess.run(command, cwd=REPO_ROOT, env=os.environ.copy())
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    os.environ["HOME"] = str(ISOLATED_HOME)
    os.environ["DREAM_STUDIO_HOME"] = str(ISOLATED_STUDIO_HOME)
    ISOLATED_HOME.mkdir(parents=True, exist_ok=True)
    ISOLATED_STUDIO_HOME.mkdir(parents=True, exist_ok=True)

    print("Dream Studio Docker clean-room runtime check")
    print(f"repo_root={REPO_ROOT}")
    print(f"HOME={ISOLATED_HOME}")
    print(f"DREAM_STUDIO_HOME={ISOLATED_STUDIO_HOME}")
    print("host_runtime_state_mounted=false")

    commands = [
        (
            "read-only runtime preflight",
            [sys.executable, "interfaces/cli/runtime_preflight.py", "--json"],
        ),
        (
            "read-only recovery dry-run",
            [sys.executable, "interfaces/cli/runtime_recovery.py", "--dry-run", "--json"],
        ),
        (
            "schema migration integration tests",
            [sys.executable, "-m", "pytest", "tests/integration/test_schema_migrations.py", "-q"],
        ),
        (
            "runtime reliability tests",
            [sys.executable, "-m", "pytest", "-m", "runtime_reliability", "-q"],
        ),
    ]

    for label, command in commands:
        _run(label, command)

    print("\nDocker clean-room runtime check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
