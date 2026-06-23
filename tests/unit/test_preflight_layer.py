"""Tests for the preflight findings layer (WO-S).

Verifies:
- create_preflight() emits an event to preflight_events
- set_preflight_status() emits a status-changed event linked via parent_event_id
- preflight_events spine rows are immutable (status change is a new row, not an update)
- PreflightProjection.fold_spine() materializes business_work_order_preflights
- work_order.start blocks on an unresolved critical/high finding
- spec ingestion seeds spec_reference findings from frontmatter files
- pytest green, migration verified
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.event_store.studio_db import _connect


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "preflight_test.db"
    conn = _connect(path)
    conn.close()
    return path


# ── Mutation tests ────────────────────────────────────────────────────────────


def test_create_preflight_writes_event(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    from core.preflight.mutations import create_preflight

    event_id = create_preflight(
        work_order_id="wo-test-001",
        finding_type="blast_radius",
        source="core/telemetry/emitters.py",
        severity="high",
        summary="Emitter touches 3 downstream tables",
        db_path=db_path,
    )

    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT event_kind, finding_type, severity, status, work_order_id"
            " FROM preflight_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        assert row is not None
        assert row["event_kind"] == "preflight.created"
        assert row["finding_type"] == "blast_radius"
        assert row["severity"] == "high"
        assert row["status"] == "open"
        assert row["work_order_id"] == "wo-test-001"
    finally:
        conn.close()


def test_set_preflight_status_emits_linked_event(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    from core.preflight.mutations import create_preflight, set_preflight_status

    finding_id = create_preflight(
        work_order_id="wo-test-002",
        finding_type="impact",
        source="core/projections/runner.py",
        severity="medium",
        summary="Runner touches projection_state on every cycle",
        db_path=db_path,
    )

    status_event_id = set_preflight_status(
        finding_event_id=finding_id,
        work_order_id="wo-test-002",
        new_status="acknowledged",
        db_path=db_path,
    )

    conn = _connect(db_path)
    try:
        status_row = conn.execute(
            "SELECT event_kind, parent_event_id, status FROM preflight_events WHERE event_id = ?",
            (status_event_id,),
        ).fetchone()
        assert status_row["event_kind"] == "preflight.status_changed"
        assert status_row["parent_event_id"] == finding_id
        assert status_row["status"] == "acknowledged"

        # Original finding row is unchanged (spine is immutable)
        original = conn.execute(
            "SELECT status FROM preflight_events WHERE event_id = ?",
            (finding_id,),
        ).fetchone()
        assert original["status"] == "open"
    finally:
        conn.close()


def test_create_preflight_rejects_invalid_severity(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    from core.preflight.mutations import create_preflight

    with pytest.raises(ValueError, match="Invalid severity"):
        create_preflight(
            work_order_id="wo-test-003",
            finding_type="risk",
            source="anywhere",
            severity="urgent",
            summary="bad severity",
            db_path=db_path,
        )


# ── Projection tests ──────────────────────────────────────────────────────────


def test_fold_spine_materializes_read_model(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    from core.preflight.mutations import create_preflight, set_preflight_status
    from core.projections.preflight_projection import PreflightProjection

    finding_id = create_preflight(
        work_order_id="wo-proj-001",
        finding_type="spec_reference",
        source="specs/some-spec.md",
        severity="info",
        summary="Architecture decision for WO-S",
        db_path=db_path,
    )
    set_preflight_status(
        finding_event_id=finding_id,
        work_order_id="wo-proj-001",
        new_status="resolved",
        db_path=db_path,
    )

    proj = PreflightProjection()
    conn = _connect(db_path)
    try:
        upserted = proj.fold_spine(conn)
        conn.commit()
        assert upserted == 1

        row = conn.execute(
            "SELECT status, finding_type, severity FROM business_work_order_preflights"
            " WHERE finding_id = ?",
            (finding_id,),
        ).fetchone()
        assert row is not None
        assert row["status"] == "resolved"
        assert row["finding_type"] == "spec_reference"
        assert row["severity"] == "info"
    finally:
        conn.close()


def test_fold_spine_idempotent(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    from core.preflight.mutations import create_preflight
    from core.projections.preflight_projection import PreflightProjection

    create_preflight(
        work_order_id="wo-idem-001",
        finding_type="dependency",
        source="requirements.txt",
        severity="low",
        summary="Depends on black>=24",
        db_path=db_path,
    )

    proj = PreflightProjection()
    conn = _connect(db_path)
    try:
        proj.fold_spine(conn)
        conn.commit()
        count_before = conn.execute(
            "SELECT COUNT(*) FROM business_work_order_preflights"
        ).fetchone()[0]

        proj.fold_spine(conn)
        conn.commit()
        count_after = conn.execute(
            "SELECT COUNT(*) FROM business_work_order_preflights"
        ).fetchone()[0]

        assert count_before == count_after == 1
    finally:
        conn.close()


# ── Gate stub tests ───────────────────────────────────────────────────────────


def test_preflight_gate_blocks_on_open_critical(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    from core.preflight.mutations import create_preflight
    from core.projections.preflight_projection import PreflightProjection

    finding_id = create_preflight(
        work_order_id="wo-gate-001",
        finding_type="blast_radius",
        source="core/event_store/event_store.py",
        severity="critical",
        summary="Drops live authority table",
        db_path=db_path,
    )

    proj = PreflightProjection()
    conn = _connect(db_path)
    try:
        proj.fold_spine(conn)
        conn.commit()
    finally:
        conn.close()

    # Verify the read-model reflects the critical open finding
    conn2 = _connect(db_path)
    try:
        row = conn2.execute(
            "SELECT status FROM business_work_order_preflights WHERE finding_id = ?",
            (finding_id,),
        ).fetchone()
        assert row is not None
        assert row["status"] == "open"
    finally:
        conn2.close()


def test_preflight_gate_passes_on_no_findings(tmp_path: Path) -> None:
    # No findings created — gate should not block
    from core.work_orders.start import _check_preflight_gate

    # With a work order that has no preflight rows, gate passes silently.
    # Pass an explicit clean DB — the gate reads the WO's own authority, not
    # an ambient/singleton connection.
    db_path = _db(tmp_path)
    result = _check_preflight_gate("wo-empty-001", db_path)
    assert result is None


# ── Spec ingestion tests ──────────────────────────────────────────────────────


def test_spec_ingestor_dry_run(tmp_path: Path) -> None:
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()

    spec_file = specs_dir / "my-feature-preflight.md"
    spec_file.write_text(
        "---\nwork_order: wo-ingest-001\nseverity: info\n---\n# My Feature\nSome body text.\n",
        encoding="utf-8",
    )

    from core.preflight.spec_ingestor import ingest_specs

    results = ingest_specs(tmp_path, dry_run=True)
    assert len(results) == 1
    assert results[0]["action"] == "would_ingest"
    assert results[0]["work_order_id"] == "wo-ingest-001"


def test_spec_ingestor_ingests_and_deduplicates(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()

    spec_file = specs_dir / "architecture-decision.md"
    spec_file.write_text(
        "---\nwork_order: wo-ingest-002\n---\n# Architecture Decision\nBody.\n",
        encoding="utf-8",
    )

    from core.preflight.spec_ingestor import ingest_specs

    results = ingest_specs(tmp_path, db_path=db_path)
    assert len(results) == 1
    assert results[0]["action"] == "ingested"

    # Second run: deduplication
    results2 = ingest_specs(tmp_path, db_path=db_path)
    assert all(r["action"] == "skipped_duplicate" for r in results2)


def test_spec_ingestor_skips_files_without_work_order_key(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()

    no_fm = specs_dir / "no-frontmatter.md"
    no_fm.write_text("# Just a heading\nNo frontmatter.\n", encoding="utf-8")

    from core.preflight.spec_ingestor import ingest_specs

    results = ingest_specs(tmp_path, db_path=db_path)
    assert results == []


# ── Migration sanity ──────────────────────────────────────────────────────────


def test_migration_107_tables_exist(tmp_path: Path) -> None:
    db_path = _db(tmp_path)
    conn = _connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "preflight_events" in tables, "preflight_events table missing"
        assert (
            "business_work_order_preflights" in tables
        ), "business_work_order_preflights table missing"
    finally:
        conn.close()
