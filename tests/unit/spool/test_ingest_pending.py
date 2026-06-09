from __future__ import annotations
import json
import pytest


def test_ingest_pending_empty_spool(spool_root):
    from spool.ingestor import ingest_pending

    result = ingest_pending(root=spool_root)
    assert result.processed == 0
    assert result.failed == 0


def test_ingest_pending_processes_valid_event(spool_root):
    from spool.writer import write_event
    from spool.ingestor import ingest_pending
    from spool.states import SpoolState, state_dir

    db = spool_root / "test.db"

    # Write a minimal valid envelope to spool
    envelope = {
        "event_id": "test-evt-001",
        "event_type": "test.event",
        "timestamp": "2026-01-01T00:00:00Z",
        "schema_version": 1,
        "payload": {},
        "trace": {},
        "severity": "info",
        "raw_prompt_retained": False,
        "raw_tool_output_retained": False,
    }
    write_event(envelope, root=spool_root)

    result = ingest_pending(root=spool_root, db_path=db)
    assert result.processed == 1
    assert result.failed == 0

    # Event should now be in processed/
    processed_dir = state_dir(SpoolState.PROCESSED, spool_root)
    assert len(list(processed_dir.glob("*.json"))) == 1


def test_ingest_pending_handles_invalid_event(spool_root):
    from spool.states import SpoolState, state_dir, ensure_dirs
    from spool.ingestor import ingest_pending

    # Ensure all spool subdirectories exist
    ensure_dirs(spool_root)

    # Write a malformed event (missing required fields)
    spool_dir = state_dir(SpoolState.SPOOL, spool_root)
    (spool_dir / "bad-event.json").write_text('{"event_type": "bad"}', encoding="utf-8")

    db = spool_root / "test.db"
    result = ingest_pending(root=spool_root, db_path=db)
    assert result.failed == 1

    # Should be in failed/
    failed_dir = state_dir(SpoolState.FAILED, spool_root)
    assert len(list(failed_dir.glob("*.json"))) >= 1
