from __future__ import annotations
import json
import sqlite3


def _wo_started_raw(event_id: str, wo_id: str) -> dict:
    """Simulate a raw ds.py work_order.started emit — no schema_version."""
    return {
        "event_id": event_id,
        "event_type": "work_order.started",
        "timestamp": "2026-05-17T00:00:00+00:00",
        "trace": {"work_order_id": wo_id, "project_id": "test-project-01"},
        "severity": "info",
        "payload": {
            "work_order_id": wo_id,
            "title": "Test work order",
            "type": "ui_component",
            "project_id": "test-project-01",
        },
        "source_type": "confirmed",
    }


def _wo_closed_raw(event_id: str, wo_id: str) -> dict:
    """Simulate a raw ds.py work_order.closed emit — no schema_version."""
    return {
        "event_id": event_id,
        "event_type": "work_order.closed",
        "timestamp": "2026-05-17T01:00:00+00:00",
        "trace": {"work_order_id": wo_id, "project_id": "test-project-01"},
        "severity": "info",
        "payload": {
            "work_order_id": wo_id,
            "title": "Test work order",
            "project_id": "test-project-01",
            "forced": False,
        },
        "source_type": "confirmed",
    }


def test_work_order_start_produces_valid_envelope(spool_root):
    """writer auto-injects schema_version; spool file is valid for work_order.started."""
    from spool.writer import write_event
    from spool.states import SpoolState, state_dir

    raw = _wo_started_raw("chain-start-001", "wo-id-chain-abc")
    assert "schema_version" not in raw  # precondition: writer must supply it

    write_event(raw, root=spool_root)

    spool_dir = state_dir(SpoolState.SPOOL, spool_root)
    files = list(spool_dir.glob("*.json"))
    assert len(files) == 1

    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["event_type"] == "work_order.started"
    assert data["event_id"] == "chain-start-001"


def test_work_order_close_produces_valid_envelope(spool_root):
    """writer auto-injects schema_version; spool file is valid for work_order.closed."""
    from spool.writer import write_event
    from spool.states import SpoolState, state_dir

    raw = _wo_closed_raw("chain-close-001", "wo-id-chain-abc")
    assert "schema_version" not in raw

    write_event(raw, root=spool_root)

    spool_dir = state_dir(SpoolState.SPOOL, spool_root)
    files = list(spool_dir.glob("*.json"))
    assert len(files) == 1

    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["event_type"] == "work_order.closed"


def test_ingestor_processes_wo_events_without_failure(spool_root):
    """Both WO events go to processed/ — none end up in failed/."""
    from spool.writer import write_event
    from spool.ingestor import ingest
    from spool.states import SpoolState, state_dir

    db_path = spool_root / "studio.db"
    write_event(_wo_started_raw("chain-ingest-start-001", "wo-id-ingest"), root=spool_root)
    write_event(_wo_closed_raw("chain-ingest-close-001", "wo-id-ingest"), root=spool_root)

    result = ingest(root=spool_root, db_path=db_path)

    assert result.failed == 0
    assert result.processed == 2

    failed_dir = state_dir(SpoolState.FAILED, spool_root)
    assert len(list(failed_dir.glob("*.json"))) == 0

    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)
    assert len(list(processed_dir.glob("*.json"))) == 2


def test_sqlite_has_rows_for_both_event_types(spool_root):
    """After ingest, canonical_events has a row for work_order.started and work_order.closed."""
    from spool.writer import write_event
    from spool.ingestor import ingest

    db_path = spool_root / "studio.db"
    write_event(_wo_started_raw("chain-sql-start-001", "wo-id-sql"), root=spool_root)
    write_event(_wo_closed_raw("chain-sql-close-001", "wo-id-sql"), root=spool_root)
    ingest(root=spool_root, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    started = conn.execute(
        "SELECT event_id FROM canonical_events WHERE event_type = 'work_order.started'"
    ).fetchall()
    closed = conn.execute(
        "SELECT event_id FROM canonical_events WHERE event_type = 'work_order.closed'"
    ).fetchall()
    conn.close()

    assert len(started) == 1
    assert started[0][0] == "chain-sql-start-001"
    assert len(closed) == 1
    assert closed[0][0] == "chain-sql-close-001"
