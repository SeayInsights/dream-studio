from __future__ import annotations
import json
import sqlite3
from pathlib import Path

import pytest


def _make_envelope(
    event_id: str = "evt-001", event_type: str = "prompt.lifecycle.submitted"
) -> dict:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "timestamp": "2026-05-15T00:00:00+00:00",
        "schema_version": 1,
        "payload": {"prompt_hash": "abc123", "raw_retained": False},
        "raw_prompt_retained": False,
        "raw_tool_output_retained": False,
    }


def test_spool_to_processing_transition(spool_root):
    from spool.states import SpoolState, state_dir
    from spool.writer import write_event
    from spool.ingestor import ingest

    db_path = spool_root / "test.db"
    envelope = _make_envelope("evt-transition-001")
    write_event(envelope, root=spool_root)

    assert (state_dir(SpoolState.SPOOL, spool_root) / "evt-transition-001.json").exists()

    result = ingest(root=spool_root, db_path=db_path)

    assert not (state_dir(SpoolState.SPOOL, spool_root) / "evt-transition-001.json").exists()
    assert result.processed == 1
    assert result.failed == 0


def test_file_moves_to_processed_on_success(spool_root):
    from spool.states import SpoolState, state_dir
    from spool.writer import write_event
    from spool.ingestor import ingest

    db_path = spool_root / "test.db"
    envelope = _make_envelope("evt-processed-001")
    write_event(envelope, root=spool_root)
    ingest(root=spool_root, db_path=db_path)

    assert (state_dir(SpoolState.PROCESSED, spool_root) / "evt-processed-001.json").exists()


def test_file_moves_to_failed_on_schema_error(spool_root):
    from spool.states import SpoolState, state_dir
    from spool.ingestor import ingest

    spool_dir = state_dir(SpoolState.SPOOL, spool_root)
    spool_dir.mkdir(parents=True, exist_ok=True)
    bad_file = spool_dir / "bad-event.json"
    bad_file.write_text(json.dumps({"no_required_fields": True}), encoding="utf-8")

    db_path = spool_root / "test.db"
    result = ingest(root=spool_root, db_path=db_path)

    assert result.failed == 1
    assert (state_dir(SpoolState.FAILED, spool_root) / "bad-event.json").exists()


def test_sqlite_row_written_on_success(spool_root):
    from spool.writer import write_event
    from spool.ingestor import ingest

    db_path = spool_root / "test.db"
    envelope = _make_envelope("evt-sqlite-001")
    write_event(envelope, root=spool_root)
    ingest(root=spool_root, db_path=db_path)

    # prompt.lifecycle.submitted routes to ai_canonical_events (WO-M: canonical_events retired)
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT event_id, event_type FROM ai_canonical_events WHERE event_id = ?",
        ("evt-sqlite-001",),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "evt-sqlite-001"
    assert row[1] == "prompt.lifecycle.submitted"


# ── reason.json subdirectory tests (WS 9e-1) ──────────────────────────────────


def test_reason_file_written_to_reasons_subdirectory(spool_root):
    from spool.states import SpoolState, state_dir
    from spool.ingestor import ingest

    spool_dir = state_dir(SpoolState.SPOOL, spool_root)
    spool_dir.mkdir(parents=True, exist_ok=True)
    bad_file = spool_dir / "bad-event-reason.json"
    bad_file.write_text(json.dumps({"no_required_fields": True}), encoding="utf-8")

    db_path = spool_root / "test.db"
    ingest(root=spool_root, db_path=db_path)

    failed_dir = state_dir(SpoolState.FAILED, spool_root)
    reasons_dir = failed_dir / "reasons"
    # Reason file must be in failed/reasons/, NOT in failed/ root
    assert (reasons_dir / "bad-event-reason.reason.json").is_file()
    assert not (failed_dir / "bad-event-reason.reason.json").is_file()


def test_doctor_count_excludes_reasons_subdirectory(spool_root, tmp_path):
    from spool.states import SpoolState, state_dir
    from spool.ingestor import ingest
    from interfaces.cli.commands.system import _check_failed_events

    spool_dir = state_dir(SpoolState.SPOOL, spool_root)
    spool_dir.mkdir(parents=True, exist_ok=True)

    # Write one bad event so it lands in failed/ root
    bad_file = spool_dir / "bad-count-event.json"
    bad_file.write_text(json.dumps({"no_required_fields": True}), encoding="utf-8")

    db_path = spool_root / "test.db"
    ingest(root=spool_root, db_path=db_path)

    failed_dir = state_dir(SpoolState.FAILED, spool_root)
    reasons_dir = failed_dir / "reasons"

    # Sanity: one event in failed root, one reason in reasons/
    assert (failed_dir / "bad-count-event.json").is_file()
    assert reasons_dir.is_dir()

    # Doctor count uses dream_studio_home = spool_root.parent (events/ is one level down)
    # _check_failed_events receives the parent of "events/"
    dream_studio_home = spool_root.parent
    info = _check_failed_events(dream_studio_home)
    # Only the event file in failed/ root should be counted, not reason files in reasons/
    assert info["count"] == 1


def test_second_rejection_does_not_accumulate_suffixes(spool_root):
    from spool.states import SpoolState, state_dir
    from spool.ingestor import ingest

    spool_dir = state_dir(SpoolState.SPOOL, spool_root)
    spool_dir.mkdir(parents=True, exist_ok=True)

    # First rejection
    bad_file = spool_dir / "repeated-fail.json"
    bad_file.write_text(json.dumps({"no_required_fields": True}), encoding="utf-8")
    db_path = spool_root / "test.db"
    ingest(root=spool_root, db_path=db_path)

    failed_dir = state_dir(SpoolState.FAILED, spool_root)
    reasons_dir = failed_dir / "reasons"
    assert (reasons_dir / "repeated-fail.reason.json").is_file()

    # Simulate requeue: move back to spool
    import os as _os

    _os.replace(
        str(failed_dir / "repeated-fail.json"),
        str(spool_dir / "repeated-fail.json"),
    )

    # Second rejection
    ingest(root=spool_root, db_path=db_path)

    # Reason file must still be <id>.reason.json — no .reason.reason.json accumulation
    assert (reasons_dir / "repeated-fail.reason.json").is_file()
    assert not (reasons_dir / "repeated-fail.reason.reason.json").is_file()
