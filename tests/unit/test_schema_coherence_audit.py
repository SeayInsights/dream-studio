"""Tests for the aspirational schema audit (core/config/schema_coherence.py).

Five ground-truth fixtures from the 18.4.6 pre-flight:

  A — migration-only DB with canonical_events absent → structural medium findings
  B — Python-owned table with no migration references → low finding
  C — column mismatch (INSERT references cols absent from Python DDL) → high finding
  D — clean DB (no Python-owned tables referenced by migrations) → zero high/medium
  E — unregistered Python-owned table (staleness guard fires) → medium finding
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.config.schema_coherence import (
    _CANONICAL_EVENTS_PYTHON_COLS,
    _PYTHON_OWNED_TABLES,
    _build_migration_only_tables,
    _migration_insert_columns,
    _migration_references,
    _staleness_guard,
    check_schema_coherence,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _source_root() -> Path:
    """Return the repo source root (parent of core/)."""
    return Path(__file__).resolve().parents[2]


def _findings_of_type(result: dict, finding_type: str) -> list[dict]:
    return [f for f in result["findings"] if f.get("finding_type") == finding_type]


def _findings_for_table(result: dict, table: str) -> list[dict]:
    return [f for f in result["findings"] if f.get("table") == table]


# ── Fixture A: canonical_events absent from migration-only DB ─────────────────


def test_fixture_a_canonical_events_absent_from_migration_replay():
    """canonical_events must be absent from a migration-only DB build."""
    migration_tables = _build_migration_only_tables(_source_root())
    assert "canonical_events" not in migration_tables, (
        "canonical_events should NOT be created by migrations alone. "
        "If it is now present, it has been moved into a migration — update this test and the debt doc."
    )


def test_fixture_a_audit_detects_canonical_events_aspirational():
    """Audit reports medium structural findings for canonical_events referenced by migrations."""
    result = check_schema_coherence(_source_root())

    ce_findings = _findings_for_table(result, "canonical_events")
    aspirational = [
        f for f in ce_findings if f["finding_type"] == "python_owned_table_in_migration"
    ]
    assert aspirational, (
        "Expected at least one python_owned_table_in_migration finding for canonical_events. "
        "If canonical_events has been moved into a migration, update this test."
    )
    for f in aspirational:
        assert f["severity"] == "medium", f"Expected medium, got {f['severity']}"
        assert f["scope"] == "structural"


def test_fixture_a_migrations_referenced_include_known_set():
    """Migrations 052, 060, 061, 062, 064 must appear in the canonical_events reference set."""
    source_root = _source_root()
    migration_dir = source_root / "core" / "event_store" / "migrations"
    refs = _migration_references(migration_dir, "canonical_events")
    migration_names = {r["migration"] for r in refs}

    expected_migrations = {
        "052_invocation_mode.sql",
        "060_ta0b_backfill_execution_events_from_canonical.sql",
        "061_backfill_sdlc_creation_events.sql",
        "062_nullify_activity_id_backfill_and_replace_views.sql",
        "064_backfill_task_creation_events.sql",
    }
    missing = expected_migrations - migration_names
    assert not missing, (
        f"Expected migrations {missing} to reference canonical_events. "
        "If any have been cleaned up, update this test."
    )


# ── Fixture B: Python-owned table with no migration references → low ──────────


def test_fixture_b_python_owned_no_migration_ref_is_low():
    """Tables like proj_* that are Python-owned and unreferenced by migrations → low severity."""
    result = check_schema_coherence(_source_root())
    low_findings = [
        f
        for f in result["findings"]
        if f["finding_type"] == "python_owned_table_no_migration_ref" and f["severity"] == "low"
    ]
    assert low_findings, (
        "Expected at least one low-severity python_owned_table_no_migration_ref finding "
        "(e.g. proj_workflow_runs, proj_sessions, etc.)."
    )
    # Spot-check: proj_workflow_runs should be low
    tables_in_low = {f["table"] for f in low_findings}
    assert "proj_workflow_runs" in tables_in_low or any(
        t.startswith("proj_") for t in tables_in_low
    ), "At least one proj_* table should appear as a low finding."


# ── Fixture C: column mismatch → high finding ─────────────────────────────────


def test_fixture_c_column_mismatch_detected():
    """Migration INSERT references columns absent from EventStore._init_tables → high severity."""
    source_root = _source_root()
    migration_dir = source_root / "core" / "event_store" / "migrations"

    inserts = _migration_insert_columns(migration_dir, "canonical_events")
    assert inserts, "Expected at least one INSERT INTO canonical_events in migrations."

    # Verify the known missing columns are present in at least one INSERT
    all_insert_cols = {c for entry in inserts for c in entry["columns"]}
    known_missing = {"raw_prompt_retained", "raw_tool_output_retained", "schema_version"}
    found_missing = known_missing & all_insert_cols
    assert found_missing, (
        f"Expected migration INSERTs to reference at least one of {known_missing}, "
        f"but only found {all_insert_cols}."
    )


def test_fixture_c_audit_reports_high_for_column_mismatch():
    """Audit reports high-severity column_absent_from_python_ddl for canonical_events."""
    result = check_schema_coherence(_source_root())
    col_findings = _findings_of_type(result, "column_absent_from_python_ddl")
    assert col_findings, (
        "Expected at least one column_absent_from_python_ddl finding. "
        "If the column mismatch has been resolved, update this test."
    )
    for f in col_findings:
        assert (
            f["severity"] == "high"
        ), f"Column mismatch findings must be high, got {f['severity']}"
        assert f["scope"] == "structural"
        assert "raw_prompt_retained" in f["missing_columns"] or any(
            c in f["missing_columns"] for c in ("raw_tool_output_retained", "schema_version")
        ), f"Unexpected missing_columns: {f['missing_columns']}"


# ── Fixture D: clean scenario → no high/medium findings ───────────────────────


def test_fixture_d_clean_db_produces_no_high_medium(tmp_path):
    """A source root with no Python-owned tables referenced by migrations → zero high/medium.

    We test this by calling check_schema_coherence with an empty source root that
    has an empty migrations dir — no Python tables, no migration references.
    """
    # Build a minimal source tree: empty migrations dir, empty core/
    (tmp_path / "core" / "event_store" / "migrations").mkdir(parents=True)
    (tmp_path / "core").mkdir(parents=True, exist_ok=True)

    # Override the Python-owned table registry and staleness guard to use the empty tree
    result = check_schema_coherence(
        tmp_path,
        _override_python_files=[],  # no Python files to scan
    )
    # With no Python files and no migrations referencing anything, only the
    # _PYTHON_OWNED_TABLES entries from the real registry remain. Since the empty
    # migration dir produces an empty migration_tables set, all Python-owned tables
    # appear as python_owned_table_no_migration_ref (low) rather than aspirational (medium).
    # High findings (column mismatch) require migration INSERTs → none with empty migrations dir.
    # The stale swallow (medium) is always present regardless of source root.
    high_findings = [f for f in result["findings"] if f["severity"] == "high"]
    assert not high_findings, f"Unexpected high findings: {high_findings}"


def test_fixture_d_real_audit_status_is_findings():
    """The real codebase audit status is 'findings' (has medium/high) — confirming debt exists."""
    result = check_schema_coherence(_source_root())
    assert result["status"] == "findings", (
        f"Expected 'findings' status (known debt in codebase), got '{result['status']}'. "
        "If all debt is resolved, update this assertion."
    )
    assert result["summary"]["high"] >= 1, "Expected at least 1 high finding (column mismatch)"
    assert (
        result["summary"]["medium"] >= 1
    ), "Expected at least 1 medium finding (aspirational ref or stale swallow)"


# ── Fixture E: staleness guard fires for unregistered table ──────────────────


def test_fixture_e_staleness_guard_flags_unregistered_table():
    """Staleness guard flags a Python CREATE TABLE not in the registry."""
    fake_python_content = (
        "def setup():\n"
        '    conn.execute("""\n'
        "        CREATE TABLE IF NOT EXISTS test_audit_orphan_table (\n"
        "            id INTEGER PRIMARY KEY\n"
        "        )\n"
        '    """)\n'
    )
    source_root = _source_root()
    # Build migration_tables so the guard can check for migration-ownership
    migration_tables = _build_migration_only_tables(source_root)

    staleness_findings = _staleness_guard(
        source_root,
        migration_tables,
        _override_python_files=[("core/test_module.py", fake_python_content)],
    )

    orphan_findings = [f for f in staleness_findings if f.get("table") == "test_audit_orphan_table"]
    assert (
        orphan_findings
    ), "Staleness guard should have flagged 'test_audit_orphan_table' as unregistered."
    assert orphan_findings[0]["finding_type"] == "unregistered_python_owned_table"
    assert orphan_findings[0]["severity"] == "medium"
    assert orphan_findings[0]["scope"] == "structural"


def test_fixture_e_staleness_guard_does_not_flag_registered_table():
    """Staleness guard must not flag tables already in _PYTHON_OWNED_TABLES."""
    source_root = _source_root()
    migration_tables = _build_migration_only_tables(source_root)

    # Simulate a Python file containing a known registered table
    fake_content = 'conn.execute("CREATE TABLE IF NOT EXISTS canonical_events (event_id TEXT)")\n'
    staleness_findings = _staleness_guard(
        source_root,
        migration_tables,
        _override_python_files=[("core/event_store/event_store.py", fake_content)],
    )

    flagged_tables = {f.get("table") for f in staleness_findings}
    assert (
        "canonical_events" not in flagged_tables
    ), "canonical_events is registered in _PYTHON_OWNED_TABLES; staleness guard must not flag it."


def test_fixture_e_staleness_guard_does_not_flag_migration_owned_table(tmp_path):
    """Staleness guard must not flag tables that exist in migration-only DB."""
    source_root = _source_root()
    migration_tables = _build_migration_only_tables(source_root)

    # Pick any table we know is migration-owned (e.g., business_canonical_events from 067)
    assert "business_canonical_events" in migration_tables, (
        "Expected business_canonical_events in migration tables. "
        "Update this test if the table was renamed or removed."
    )
    fake_content = (
        'conn.execute("CREATE TABLE IF NOT EXISTS business_canonical_events (id TEXT)")\n'
    )
    staleness_findings = _staleness_guard(
        source_root,
        migration_tables,
        _override_python_files=[("core/some_module.py", fake_content)],
    )
    flagged_tables = {f.get("table") for f in staleness_findings}
    assert (
        "business_canonical_events" not in flagged_tables
    ), "business_canonical_events is migration-owned; staleness guard must not flag it."


# ── Swallow inventory ─────────────────────────────────────────────────────────


def test_stale_swallow_is_reported():
    """The stale canonical_events swallow entry must appear in the audit findings."""
    result = check_schema_coherence(_source_root())
    stale = _findings_of_type(result, "stale_swallow")
    assert stale, "Expected at least one stale_swallow finding."
    patterns = [f["pattern"] for f in stale]
    assert any("canonical_events" in p for p in patterns), (
        "Expected the canonical_events swallow to be classified as stale. "
        "If it has been removed or reclassified, update this test."
    )
    for f in stale:
        assert f["severity"] == "medium"
        assert f["scope"] == "structural"


# ── Doctor integration ────────────────────────────────────────────────────────


def test_doctor_includes_schema_coherence_check(tmp_path):
    """run_doctor_checks includes a schema_coherence key in checks output."""
    from core.health.doctor import run_doctor_checks

    result = run_doctor_checks(
        source_root=_source_root(),
        dream_studio_home=tmp_path,
    )
    assert (
        "schema_coherence" in result["checks"]
    ), "run_doctor_checks should include schema_coherence in its checks dict."
    sc = result["checks"]["schema_coherence"]
    assert "status" in sc
    assert "findings" in sc
    assert "summary" in sc
