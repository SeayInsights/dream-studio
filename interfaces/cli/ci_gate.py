#!/usr/bin/env python3
"""CI gate — run all quality checks and report pass/fail as JSON.

Exit 0 if all checks pass, exit 1 if any fail.
If ANTHROPIC_API_KEY is set, appends a non-blocking advisory review step.

Usage:
    py interfaces/cli/ci_gate.py
    make ci-gate
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_PYTHON = sys.executable

CHECKS = [
    ("test", [_PYTHON, "-m", "pytest", "tests/", "-q"]),
    ("format", [_PYTHON, "-m", "black", "--check", "."]),
    ("lint-baseline", [_PYTHON, "interfaces/cli/lint_baseline.py", "check"]),
    (
        "contract-docs-drift",
        [_PYTHON, "interfaces/cli/contract_docs_drift_gate.py"],
    ),
    (
        "contract-atlas-lifecycle",
        [_PYTHON, "interfaces/cli/contract_atlas_lifecycle_gate.py"],
    ),
    (
        "security",
        [_PYTHON, "-m", "pip_audit", "-r", "requirements-dev.txt", "-r", "requirements.txt"],
    ),
]


def _isolated_check_env() -> dict[str, str]:
    env = os.environ.copy()
    isolated_home = Path(tempfile.mkdtemp(prefix="dream-studio-ci-home-"))
    dream_studio_home = isolated_home / ".dream-studio"
    state_dir = dream_studio_home / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    env["DREAM_STUDIO_HOME"] = str(dream_studio_home)
    env["DREAM_STUDIO_DB_PATH"] = str(state_dir / "studio.db")
    env["GITHUB_ACTIONS"] = env.get("GITHUB_ACTIONS", "true")
    env["HOME"] = str(isolated_home)
    env["USERPROFILE"] = str(isolated_home)
    return env


def _isolated_test_env() -> dict[str, str]:
    env = os.environ.copy()
    isolated_home = Path(tempfile.mkdtemp(prefix="dream-studio-ci-home-"))
    # Use a separate temp dir for the DB. conftest.guard_real_homedir checks
    # whether DREAM_STUDIO_DB_PATH differs from Path.home()/".dream-studio"/...
    # If HOME and DREAM_STUDIO_DB_PATH share the same base, the guard's
    # _db_redirected flag is False and it fires on every DB write.
    db_tmp = Path(tempfile.mkdtemp(prefix="dream-studio-ci-db-"))
    state_dir = db_tmp / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    env.pop("DREAM_STUDIO_HOME", None)
    env["DREAM_STUDIO_DB_PATH"] = str(state_dir / "studio.db")
    env["GITHUB_ACTIONS"] = env.get("GITHUB_ACTIONS", "true")
    env["HOME"] = str(isolated_home)
    env["USERPROFILE"] = str(isolated_home)
    return env


def run_check(name: str, cmd: list[str]) -> dict:
    env = _isolated_test_env() if name == "test" else _isolated_check_env()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env=env,
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

    # Print failures to stderr BEFORE the JSON so they're visible even if the
    # full JSON output is truncated in CI logs (the output field can be megabytes).
    if not overall:
        for r in results:
            if not r["passed"] and r["name"] != "advisory_review":
                tail = (r["output"] or "")[-3000:]
                print(f"\n--- FAILED: {r['name']} ---\n{tail}", file=sys.stderr)

    output = {
        "status": "pass" if overall else "fail",
        "checks": [{**r, "output": (r["output"] or "")[-2000:]} for r in results],
    }
    print(json.dumps(output, indent=2))
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
