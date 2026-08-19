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
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# DROP-safety (DATA_LOSS class, WO dbcaa64f): a forward migration that DROPs a table must not
# rest on a prose "it was never released / it's empty" claim (the raw_runtime_state/mig-150
# finding). It must carry, IN THE MIGRATION FILE, one of:
#   - a backup/copy of the data (CREATE TABLE ..._backup AS SELECT / INSERT INTO ... SELECT), or
#   - an explicit reviewed rationale line: "-- DROP-SAFETY: <why this loses no data>".
# The gate scans only CHANGED forward migrations, so released migrations are never re-flagged.
_DROP_TABLE_RE = re.compile(r'(?im)^\s*DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?["`\[]?(?P<name>\w+)')
_DROP_SAFETY_MARKER = "-- DROP-SAFETY:"
# A data-preserving copy: a *_backup table, or an INSERT ... SELECT (optional column list) that
# migrates rows elsewhere before the drop. [^;] keeps the match within the one INSERT statement.
_BACKUP_RE = re.compile(r"(?i)CREATE\s+TABLE\s+\S*_backup|INSERT\s+INTO\b[^;]*\bSELECT\b")


def unguarded_drop_violations(sql_text: str) -> list[str]:
    """Return a violation per DROP TABLE that lacks a backup/copy or a DROP-SAFETY rationale.

    Pure function over migration SQL text so it is unit-testable without git."""
    drops = [m.group("name") for m in _DROP_TABLE_RE.finditer(sql_text)]
    if not drops:
        return []
    if _DROP_SAFETY_MARKER in sql_text or _BACKUP_RE.search(sql_text):
        return []
    return [
        f"DROP TABLE {name}: no rows=0 backup/copy and no '{_DROP_SAFETY_MARKER} <why>' rationale"
        for name in drops
    ]


def _changed_forward_migration_drops(risk_files: list[str]) -> list[str]:
    """Collect DROP-safety violations across changed forward-migration .sql files.

    Excludes rollback/ (reverse migrations legitimately drop what their forward created)."""
    violations: list[str] = []
    for path in risk_files:
        if not path.endswith(".sql"):
            continue
        if "/rollback/" in path or "\\rollback\\" in path:
            continue
        if "core/event_store/migrations/" not in path.replace("\\", "/"):
            continue
        try:
            sql = (REPO_ROOT / path).read_text(encoding="utf-8")
        except OSError:
            continue
        for v in unguarded_drop_violations(sql):
            violations.append(f"{path}: {v}")
    return violations


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
            encoding="utf-8",
            errors="replace",
            cwd=REPO_ROOT,
            timeout=15,
        )
        if result.returncode != 0:
            # Fallback: just diff the index vs HEAD (staged changes)
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
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

    # Rollback-pairing escalation (R3): every forward migration >= the cutover must
    # ship a paired reverse. This is a hard failure — a real reversibility defect,
    # not the matrix-watch reminder — so MIGRATION_RISK_ACKNOWLEDGED does NOT bypass
    # it. Runs here because a migration-touching push is exactly when it matters.
    from core.gates.migration_rollback_pairing import (
        ROLLBACK_ENFORCED_FROM,
        find_unpaired_migrations,
    )

    unpaired = find_unpaired_migrations()
    if unpaired:
        print()
        print("=" * 70)
        print("MIGRATION ROLLBACK PAIRING: unpaired forward migration(s)")
        print("=" * 70)
        print(f"Every forward migration >= {ROLLBACK_ENFORCED_FROM} must ship a paired")
        print("reverse under core/event_store/migrations/rollback/<same NNN_>*.sql")
        print("(reversible authority migrations — see docs/migrations.md).")
        for name in unpaired:
            print(f"  MISSING rollback for: {name}")
        print("=" * 70)
        print()
        return 1

    # DROP-safety escalation (DATA_LOSS class, WO dbcaa64f): a changed forward migration that
    # DROPs a table must carry an in-file backup/copy or a "-- DROP-SAFETY:" rationale — not a
    # hidden prose claim. Hard failure (a real data-loss defect), NOT bypassable by the
    # matrix-watch acknowledgement below.
    drop_violations = _changed_forward_migration_drops(risk_files)
    if drop_violations:
        print()
        print("=" * 70)
        print("MIGRATION DROP-SAFETY: unguarded DROP TABLE in a forward migration")
        print("=" * 70)
        print("A DROP TABLE must not rest on a prose 'never released / empty' claim. Add, in the")
        print("migration file, a backup/copy (CREATE TABLE ..._backup AS SELECT / INSERT INTO")
        print("... SELECT) OR an explicit reviewed rationale line:")
        print("  -- DROP-SAFETY: <why this drops no live data, e.g. rows=0 verified / dead table>")
        for v in drop_violations:
            print(f"  {v}")
        print("=" * 70)
        print()
        return 1

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
    print("(see migrations 081, 082 — both required post-merge hotfixes).")
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
        # WO-BYPASS-TELEMETRY: the acknowledgment still works, but it is recorded —
        # previously this env var left no trace anywhere.
        from core.gates.bypass_event import record_gate_bypass

        record_gate_bypass(
            "migration_risk",
            "MIGRATION_RISK_ACKNOWLEDGED=1 — matrix-watch reminder bypassed at push",
            extra={"risk_files": risk_files},
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
