"""WO-SQUASH-AUDIT keep/drop gate (tests/unit/test_schema_keep_list.py).

The Schema Truth squash collapses 124 migrations into one lean baseline. Before
that irreversible step, every table in the authority must be classified
KEEP / DROP / RESURFACE with evidence, and no table a live runtime writer depends
on may be dropped.

These tests are the executable acceptance criteria for WO-SQUASH-AUDIT and the
guard for WO-SQUASH-BASELINE:

  test_census_complete       — the classification covers exactly the canonical
                               schema (every bootstrapped table) plus the two
                               runtime-created tables; nothing missing, nothing
                               phantom.
  test_no_live_table_dropped — no DROP-classified table has a live runtime writer
                               in the source tree (tests/, migrations/, and
                               one-time upgrade/backfill tooling excluded).

Both are CI-safe: they bootstrap the canonical schema into a temp DB and grep the
checked-in source tree — neither depends on the operator's live ~/.dream-studio
database or on the gitignored .planning/ audit artifact.
"""

from __future__ import annotations

import re
import sqlite3
import tempfile
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database
from tests.unit.schema_keeplist_data import CLASSIFICATION, RUNTIME_TABLES

REPO_ROOT = Path(__file__).resolve().parents[2]

# Optional quote/backtick wrapper around a table name in SQL text.
_QUOTE = r"[\"'`]?"
_WRITE_VERBS = r"(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|REPLACE\s+INTO|UPDATE)"


def _bootstrapped_tables() -> set[str]:
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "boot.db"
        bootstrap_database(db)
        conn = sqlite3.connect(str(db))
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' " "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        finally:
            conn.close()
    return {r[0] for r in rows}


def _source_files() -> list[Path]:
    """Checked-in .py files that count as live runtime code.

    Excludes tests, the migrations directory (DDL, not a runtime writer), and
    one-time upgrade/backfill/reconcile tooling (operates on the old schema during
    an upgrade, not the live runtime).
    """
    out: list[Path] = []
    for p in REPO_ROOT.rglob("*.py"):
        rel = p.relative_to(REPO_ROOT).as_posix()
        if rel.startswith("tests/") or "/tests/" in f"/{rel}":
            continue
        if "core/event_store/migrations/" in rel:
            continue
        if rel.startswith("core/upgrade/"):
            continue
        if rel.startswith("interfaces/cli/reconcile_") or rel.startswith(
            "interfaces/cli/backfill_"
        ):
            continue
        if "/graphify-out/" in f"/{rel}" or "/.planning/" in f"/{rel}":
            continue
        # Nested/sibling agent worktree copies under .claude/worktrees/ are duplicate
        # source trees — scanning them yields false positives. Exclude them so the
        # scan only sees the canonical checked-in source of this tree.
        if rel.startswith(".claude/worktrees/") or "/.claude/worktrees/" in f"/{rel}":
            continue
        out.append(p)
    return out


def _runtime_writers(table: str, files: list[Path]) -> list[str]:
    pattern = re.compile(
        _WRITE_VERBS + r"\s+" + _QUOTE + re.escape(table) + _QUOTE + r"\b",
        re.IGNORECASE,
    )
    hits: list[str] = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if pattern.search(text):
            hits.append(p.relative_to(REPO_ROOT).as_posix())
    return hits


def test_census_complete():
    """Classification covers the live schema; DROP tables are allowed to be absent.

    Every bootstrapped/runtime table must be classified (nothing unclassified).
    KEEP and RESURFACE tables must exist in the live schema. DROP-classified
    tables are expected to be ABSENT once their dropping migration has run
    (migration 128 dropped 24 of them), so a DROP table missing from the schema
    is not a phantom — only a KEEP/RESURFACE table not in the schema is.
    """
    live = _bootstrapped_tables() | RUNTIME_TABLES
    classified = set(CLASSIFICATION)

    # Every live table must be classified.
    missing = live - classified
    assert not missing, f"tables in schema but not classified: {sorted(missing)}"

    # Only KEEP/RESURFACE classifications must correspond to a live table.
    # DROP classifications may have no live table (the table was dropped).
    expected_present = {t for t, c in CLASSIFICATION.items() if c != "DROP"}
    phantom = expected_present - live
    assert not phantom, f"KEEP/RESURFACE tables not in schema: {sorted(phantom)}"


def test_no_live_table_dropped():
    """No DROP-classified table has a live runtime writer."""
    files = _source_files()
    drops = [t for t, c in CLASSIFICATION.items() if c == "DROP"]
    offenders = {t: _runtime_writers(t, files) for t in drops}
    offenders = {t: w for t, w in offenders.items() if w}
    assert not offenders, (
        "DROP-classified tables have live runtime writers (would lose live data): " f"{offenders}"
    )
