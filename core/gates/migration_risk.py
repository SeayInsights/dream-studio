"""Migration risk classifier for the pre-push gate.

Detects whether the current branch introduces SQL/migration changes and
prints a visible warning if it does. These changes have historically produced
regressions that only surface on the remote 3-platform matrix (macos, windows)
even when local tests and the pre-push gate pass.

Exit codes:
  0 — no migration-risk files changed, or running in CI (GITHUB_ACTIONS=true)
  1 — migration-risk files changed locally; operator must confirm matrix-watch
      before merging (see WARN output for the exact command)

The gate NEVER blocks CI — GITHUB_ACTIONS skips the check to avoid false
positives inside the matrix itself. It blocks local pushes only, where the
human decision to merge is still pending.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# File patterns that constitute a migration-risk change.
# Any changed path that matches one of these is considered high-risk.
# Scope: the schema-authority set — files that declare or apply schema that the
# migration runner alone cannot reproduce (Python DDL sites), or files that
# control which schema operations are swallowed silently (the bootstrap runner).
# This is deliberately wider than just the .sql files because the canonical_events
# regression class (Phase 18.x) was caused by Python DDL in event_store.py and
# the exception handler in sqlite_bootstrap.py, neither of which are .sql files.
_RISK_PATTERNS = (
    "core/event_store/migrations/",  # SQL migration files
    "core/config/sqlite_bootstrap.py",  # migration runner + swallow handler
    "core/event_store/event_store.py",  # EventStore._init_tables() — Python DDL for canonical_events
    "core/config/schema_coherence",  # aspirational-schema audit — if the detector changes, re-watch
)

_MATRIX_PLATFORMS = "ubuntu-latest, macos-latest, windows-latest"


def _changed_files(base_ref: str = "origin/main") -> list[str]:
    """Return files changed on the current branch vs base_ref."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=15,
        )
        if result.returncode != 0:
            # Fallback: just diff the index vs HEAD (staged changes)
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                timeout=15,
            )
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception:
        return []


def _is_risk_file(path: str) -> bool:
    return any(path.startswith(p) or path == p for p in _RISK_PATTERNS)


def main() -> int:
    # Always pass inside CI — the matrix itself is the check.
    if os.environ.get("GITHUB_ACTIONS"):
        return 0

    base_ref = os.environ.get("DREAM_STUDIO_BASE_REF", "origin/main")
    changed = _changed_files(base_ref)
    risk_files = [f for f in changed if _is_risk_file(f)]

    if not risk_files:
        return 0

    pr_number_hint = os.environ.get("PR_NUMBER", "<PR-NUMBER>")

    print()
    print("=" * 70)
    print("MIGRATION RISK: SQL/migration files changed in this push")
    print("=" * 70)
    for f in risk_files:
        print(f"  {f}")
    print()
    print("This change class has historically produced regressions that pass")
    print("local tests and the pre-push gate but fail on the remote matrix")
    print(f"(see migrations 081, 082 — both required post-merge hotfixes).")
    print()
    print("MATRIX-WATCH IS REQUIRED before you merge this PR.")
    print(f"Platforms: {_MATRIX_PLATFORMS}")
    print()
    print("After pushing, run:")
    print(f"  gh pr checks {pr_number_hint} --watch")
    print()
    print("Do not merge until all three platforms show green.")
    print("=" * 70)
    print()

    # Exit 1 to make the gate visible as FAIL in the pre-push output.
    # Bypass with: MIGRATION_RISK_ACKNOWLEDGED=1 git push
    if os.environ.get("MIGRATION_RISK_ACKNOWLEDGED"):
        print("MIGRATION_RISK_ACKNOWLEDGED set — bypassing block.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
