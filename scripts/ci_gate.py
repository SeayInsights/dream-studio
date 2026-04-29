#!/usr/bin/env python3
"""CI gate — run all quality checks and report pass/fail as JSON.

Exit 0 if all checks pass, exit 1 if any fail.
If ANTHROPIC_API_KEY is set, appends a non-blocking advisory review step.

Usage:
    py scripts/ci_gate.py
    make ci-gate
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

CHECKS = [
    ("test", ["make", "test"]),
    ("lint", ["make", "lint"]),
    ("fmt", ["make", "fmt"]),
    ("security", ["make", "security"]),
]


def run_check(name: str, cmd: list[str]) -> dict:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        passed = result.returncode == 0
        output = (result.stdout + result.stderr).strip()
    except FileNotFoundError as e:
        passed = False
        output = f"command not found: {e}"
    return {"name": name, "passed": passed, "output": output}


def run_advisory() -> dict | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        result = subprocess.run(
            ["claude", "--print", "review: check PR for regressions"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "name": "advisory_review",
            "passed": True,
            "output": (result.stdout + result.stderr).strip(),
        }
    except Exception as e:
        return {"name": "advisory_review", "passed": True, "output": f"skipped: {e}"}


def main() -> None:
    results = [run_check(name, cmd) for name, cmd in CHECKS]

    advisory = run_advisory()
    if advisory:
        results.append(advisory)

    overall = all(r["passed"] for r in results if r["name"] != "advisory_review")
    output = {
        "status": "pass" if overall else "fail",
        "checks": results,
    }
    print(json.dumps(output, indent=2))
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
