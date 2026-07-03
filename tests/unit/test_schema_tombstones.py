"""Dropped tables must never resurface (operator directive, WO-TOMBSTONE-GUARD).

Three guards over the tombstone registry (schema_tombstones_data.py):
1. A fresh fully-migrated studio.db contains no tombstoned table or view —
   catches a future migration (or the squash baseline) recreating a dropped name.
2. No production source file creates a tombstoned table against the authority —
   catches runtime CREATE TABLE resurrection (explicit files.db-scoped
   exceptions carry documented reasons).
3. Registry hygiene: valid identifiers only, self-consistent with the chain.

Complements core/gates/test_fixture_resurrection_guard.py, which covers test
fixtures; this covers migrations and production code. Runs in the pre-push
pin-tests gate.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from tests.unit.schema_tombstones_data import (  # noqa: E402
    TOMBSTONE_CREATOR_EXCEPTIONS,
    TOMBSTONED_TABLES,
)

_IDENT = re.compile(r"^[a-z][a-z0-9_]+$")
_EXCLUDED_PARTS = {
    "tests",
    "migrations",
    "__pycache__",
    ".git",
    ".planning",
    ".claude",
    "node_modules",
    ".venv",
    "graphify-out",
}


def _fresh_schema_names() -> set[str]:
    from core.config.sqlite_bootstrap import run_migrations

    conn = sqlite3.connect(":memory:")
    try:
        run_migrations(conn, apply_unreleased=True)
        return {
            row[0].lower()
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
    finally:
        conn.close()


def test_fresh_chain_contains_no_tombstones():
    resurrected = sorted(_fresh_schema_names() & TOMBSTONED_TABLES)
    assert not resurrected, (
        f"tombstoned tables resurrected by the migration chain: {resurrected} — "
        "dropped tables must never come back; pick a new name or remove the "
        "tombstone with an operator-approved rationale"
    )


def test_no_production_creator_for_tombstones():
    create_res = {
        name: re.compile(
            rf"CREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\[\"']?{name}\b",
            re.IGNORECASE,
        )
        for name in TOMBSTONED_TABLES
        if name not in TOMBSTONE_CREATOR_EXCEPTIONS
    }
    offenders: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if path.suffix not in (".py", ".sql"):
            continue
        if any(part in _EXCLUDED_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name, regex in create_res.items():
            if regex.search(text):
                rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
                offenders.append(f"{rel} creates tombstoned table {name!r}")
    assert not offenders, (
        "production code creates tombstoned tables (dropped tables must never "
        "resurface):\n  " + "\n  ".join(sorted(offenders))
    )


def test_registry_hygiene():
    bad = sorted(n for n in TOMBSTONED_TABLES if not _IDENT.match(n))
    assert not bad, f"tombstone registry contains non-identifier junk: {bad}"
    unknown_exceptions = sorted(set(TOMBSTONE_CREATOR_EXCEPTIONS) - TOMBSTONED_TABLES)
    assert (
        not unknown_exceptions
    ), f"exceptions for names that are not tombstoned: {unknown_exceptions}"
    assert len(TOMBSTONED_TABLES) >= 170, (
        "tombstone registry shrank — removing a tombstone requires an "
        "operator-approved rationale in the commit body"
    )
