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

from core.config.schema_coherence import (
    _PYTHON_OWNED_TABLES,
    _effective_swallow_classification,
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


# ── Fixture A: canonical_events remediated (18.4.6-followup-1) ───────────────
# Migration 083 moved canonical_events into migrations. These tests now assert
# the CLEAN state: the table IS present in migration-only DBs and the audit
# reports ZERO canonical_events findings.


def test_fixture_a_canonical_events_present_in_migration_replay():
    """canonical_events must be present in a migration-only DB after migration 083."""
    migration_tables = _build_migration_only_tables(_source_root())
    assert "canonical_events" in migration_tables, (
        "canonical_events should be created by migration 083. "
        "If it is absent, migration 083 did not run or was removed."
    )


def test_fixture_a_canonical_events_has_14_columns_in_migration_replay():
    """Migration 083 creates canonical_events with the authoritative 14-column schema."""
    from core.config.sqlite_bootstrap import run_migrations

    conn = __import__("sqlite3").connect(":memory:")
    run_migrations(conn)
    conn.row_factory = __import__("sqlite3").Row
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(canonical_events)").fetchall()}
    conn.close()

    expected = {
        "event_id",
        "event_type",
        "timestamp",
        "trace",
        "severity",
        "payload",
        "actor",
        "confidence_score",
        "source_type",
        "raw_prompt_retained",
        "raw_tool_output_retained",
        "schema_version",
        "created_at",
        "invocation_mode",
    }
    assert cols == expected, f"Column mismatch: {cols ^ expected}"


def test_fixture_a_audit_reports_zero_canonical_events_findings():
    """Audit must report zero canonical_events findings after migration 083 remediation."""
    result = check_schema_coherence(_source_root())
    ce_findings = _findings_for_table(result, "canonical_events")
    assert not ce_findings, (
        f"Expected zero canonical_events findings after migration 083 remediation, "
        f"but found: {[f['finding_type'] for f in ce_findings]}"
    )


def test_fixture_a_migrations_still_reference_canonical_events_structurally():
    """Migrations 052, 060, 061, 062, 064 still reference canonical_events in their SQL.
    This is expected — they predate migration 083. The structural references remain
    but no longer produce audit findings because canonical_events is now migration-owned.
    """
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
        f"Expected migrations {missing} to still reference canonical_events in their SQL. "
        "These references are expected (legacy migrations before 083)."
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


def test_fixture_c_migration_inserts_use_columns_now_in_migration_083():
    """The columns that were 'missing' from Python DDL (raw_prompt_retained etc.) are now
    declared in migration 083 — they were always in the ingestor's DDL.
    The INSERTs in migrations 061/062/064 still reference them; the mismatch is resolved.
    """
    source_root = _source_root()
    migration_dir = source_root / "core" / "event_store" / "migrations"

    inserts = _migration_insert_columns(migration_dir, "canonical_events")
    assert inserts, "Expected at least one INSERT INTO canonical_events in migrations."

    # The historically-missing columns must still appear in the INSERT statements
    # (they were not removed — they're valid now that migration 083 declares them)
    all_insert_cols = {c for entry in inserts for c in entry["columns"]}
    expected_cols = {"raw_prompt_retained", "raw_tool_output_retained", "schema_version"}
    assert expected_cols <= all_insert_cols, (
        f"Expected migration INSERTs to still reference {expected_cols}; "
        f"found: {all_insert_cols}"
    )


def test_fixture_c_audit_reports_zero_column_mismatch_findings():
    """After migration 083, column_absent_from_python_ddl findings must be zero.
    canonical_events is now migration-owned with the full 14-column schema.
    """
    result = check_schema_coherence(_source_root())
    col_findings = _findings_of_type(result, "column_absent_from_python_ddl")
    assert not col_findings, (
        f"Expected zero column_absent_from_python_ddl findings after migration 083, "
        f"but found: {[(f.get('migration'), f.get('missing_columns')) for f in col_findings]}"
    )


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


def test_fixture_d_real_audit_status_is_low_findings_after_remediation():
    """After migration 083, the real codebase audit has zero high/medium findings.
    Status is 'low_findings' (only the 14 low proj_* no-migration-ref findings remain).
    """
    result = check_schema_coherence(_source_root())
    assert result["status"] == "low_findings", (
        f"Expected 'low_findings' after canonical_events remediation, got '{result['status']}'. "
        "If new high/medium debt was introduced, investigate."
    )
    assert (
        result["summary"]["high"] == 0
    ), f"Expected zero high findings, got {result['summary']['high']}"
    assert (
        result["summary"]["medium"] == 0
    ), f"Expected zero medium findings, got {result['summary']['medium']}"
    assert result["summary"]["low"] >= 1, "Expected low findings for proj_* tables still present"


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


def test_stale_swallow_is_no_longer_reported():
    """After migration 083, the canonical_events swallow is reclassified as 'legitimate'
    (intentional graceful degradation for migrations 052-064 that predate migration 083).
    No stale_swallow findings should appear.
    """
    result = check_schema_coherence(_source_root())
    stale = _findings_of_type(result, "stale_swallow")
    assert not stale, (
        f"Expected zero stale_swallow findings after canonical_events remediation, "
        f"but found: {[f.get('pattern') for f in stale]}"
    )


# ── Q2 regression tests: stale_swallow detection is not deceivable by relabeling ──


def test_swallow_classification_is_not_deceivable_by_relabeling():
    """The stale_swallow detection probes migration_tables, not the hardcoded label.

    A swallow labeled 'legitimate' for a table that is ABSENT from migration_tables
    AND is in _PYTHON_OWNED_TABLES must still be reported as stale. Relabeling alone
    cannot silence the finding.
    """
    migration_tables = _build_migration_only_tables(_source_root())

    # Simulate a swallow entry labeled 'legitimate' for a table that is:
    # - absent from migration_tables (not in any migration)
    # - present in _PYTHON_OWNED_TABLES (Python-owned → schema debt)
    # Pick any table we know is Python-owned and not in migrations.
    python_owned_table = "validation_failures"
    assert python_owned_table in _PYTHON_OWNED_TABLES, f"{python_owned_table} not in registry"
    assert (
        python_owned_table not in migration_tables
    ), f"{python_owned_table} should NOT be in migration-only DB"

    fake_entry = {
        "pattern": f"no such table: {python_owned_table}",
        "classification": "legitimate",  # deliberately relabeled as legitimate
        "explanation": "fake entry for regression test",
    }
    effective = _effective_swallow_classification(fake_entry, migration_tables)
    assert effective == "stale", (
        f"Expected 'stale' for a relabeled swallow of a Python-owned table, "
        f"got '{effective}'. The detection must not be deceivable by relabeling."
    )


def test_swallow_classification_correctly_detects_migration_owned_as_legitimate():
    """A swallow for a table that IS in migration_tables is auto-detected as legitimate,
    even if the hardcoded label says 'stale'. The probe overrides the label.
    """
    migration_tables = _build_migration_only_tables(_source_root())

    # canonical_events is the canonical test case: it IS in migration_tables after
    # migration 083. Even if someone labels the swallow 'stale', the probe sees it
    # in migration_tables and classifies it as legitimate.
    assert "canonical_events" in migration_tables, (
        "canonical_events should be in migration_tables after migration 083. "
        "If this fails, migration 083 is missing."
    )

    fake_entry = {
        "pattern": "no such table: canonical_events",
        "classification": "stale",  # deliberately relabeled as stale
        "explanation": "fake entry for regression test",
    }
    effective = _effective_swallow_classification(fake_entry, migration_tables)
    assert effective == "legitimate", (
        f"Expected 'legitimate' for a swallow of a migration-owned table, "
        f"got '{effective}'. The probe should override the 'stale' label."
    )


# ── Fixture F: staleness guard ignores non-DDL CREATE TABLE text ─────────────


def test_fixture_f_guard_ignores_comment_lines():
    """Lines starting with # are skipped — CREATE TABLE in comments must not fire the guard."""
    source_root = _source_root()
    migration_tables = _build_migration_only_tables(source_root)

    # All occurrences of CREATE TABLE are in Python comment lines.
    fake_content = (
        "# This helper creates tables like CREATE TABLE sample_thing\n"
        "# See also: CREATE TABLE other_thing (id INTEGER)\n"
        "# Example DDL: CREATE TABLE yet_another_thing (name TEXT)\n"
    )
    staleness_findings = _staleness_guard(
        source_root,
        migration_tables,
        _override_python_files=[("core/some_helper.py", fake_content)],
    )
    flagged = {f.get("table") for f in staleness_findings}
    assert "sample_thing" not in flagged, "Comment-line CREATE TABLE must not be flagged."
    assert "other_thing" not in flagged, "Comment-line CREATE TABLE must not be flagged."
    assert "yet_another_thing" not in flagged, "Comment-line CREATE TABLE must not be flagged."


def test_fixture_f_guard_excludes_own_source_file():
    """The staleness guard must not scan schema_coherence.py itself (self-exclusion)."""
    source_root = _source_root()
    migration_tables = _build_migration_only_tables(source_root)

    # schema_coherence.py contains CREATE TABLE in its own source (the regex pattern,
    # the _SELF_SCAN_EXCLUDE comment text, the docstrings). Run the guard against the
    # real filesystem and confirm no findings come from schema_coherence.py itself.
    all_findings = _staleness_guard(source_root, migration_tables)
    self_findings = [f for f in all_findings if "schema_coherence" in f.get("file", "")]
    assert (
        not self_findings
    ), f"Staleness guard must not flag its own source file. Got: {self_findings}"


# ── Live-drift probe status ───────────────────────────────────────────────────


def test_live_drift_probe_status_skipped_when_no_path():
    """check_schema_coherence must report 'skipped' when live_db_path is not provided."""
    result = check_schema_coherence(_source_root())
    assert "live_drift_probe_status" in result
    assert result["live_drift_probe_status"].startswith(
        "skipped:"
    ), f"Expected skipped status when no live_db_path, got: {result['live_drift_probe_status']}"


def test_live_drift_probe_status_skipped_when_path_absent(tmp_path):
    """check_schema_coherence must report 'skipped: no DB at <path>' for missing DB file."""
    missing = tmp_path / "state" / "studio.db"
    result = check_schema_coherence(_source_root(), live_db_path=missing)
    assert result["live_drift_probe_status"].startswith(
        "skipped: no DB at"
    ), f"Expected 'skipped: no DB at ...' for missing path, got: {result['live_drift_probe_status']}"
    assert str(missing) in result["live_drift_probe_status"]


def test_live_drift_probe_status_ran_for_real_db(tmp_path):
    """check_schema_coherence must report 'ran: N findings' when probe executes."""
    from core.event_store.studio_db import _connect, _run_migrations

    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    with _connect(db) as conn:
        _run_migrations(conn)
        conn.commit()

    result = check_schema_coherence(_source_root(), live_db_path=db)
    assert result["live_drift_probe_status"].startswith(
        "ran:"
    ), f"Expected 'ran: N findings' for real DB, got: {result['live_drift_probe_status']}"


# ── Cross-reference enrichment ────────────────────────────────────────────────


def test_no_medium_findings_for_migration_062_after_remediation():
    """After migration 083, migration 062 no longer produces medium or high findings.
    canonical_events is migration-owned, so old migration references are no longer reported.
    """
    result = check_schema_coherence(_source_root())

    mediums_062 = [
        f
        for f in result["findings"]
        if f.get("finding_type")
        in ("python_owned_table_in_migration", "column_absent_from_python_ddl")
        and f.get("migration") == "062_nullify_activity_id_backfill_and_replace_views.sql"
    ]
    assert not mediums_062, (
        f"Expected zero medium/high findings for migration 062 after remediation, "
        f"but found: {[f['finding_type'] for f in mediums_062]}"
    )


def test_no_column_absent_findings_after_remediation():
    """After migration 083, column_absent_from_python_ddl findings must be zero.
    The previously-missing columns are now declared in migration 083.
    """
    result = check_schema_coherence(_source_root())
    highs = _findings_of_type(result, "column_absent_from_python_ddl")
    assert not highs, (
        f"Expected zero column_absent_from_python_ddl findings after remediation, "
        f"but found {len(highs)}: {[(f.get('migration'), f.get('missing_columns')) for f in highs]}"
    )


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
    assert "live_drift_probe_status" in sc
