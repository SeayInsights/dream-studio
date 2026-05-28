from __future__ import annotations
import json
import os
from pathlib import Path

import pytest


def test_atomic_write_success(spool_root):
    from spool.writer import write_event

    envelope = {
        "event_id": "test-uuid-001",
        "event_type": "prompt.lifecycle.submitted",
        "timestamp": "2026-05-15T00:00:00+00:00",
        "schema_version": 1,
        "payload": {},
    }
    dest = write_event(envelope, root=spool_root)
    assert dest.exists()
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["event_id"] == "test-uuid-001"


def test_no_temp_file_left_on_success(spool_root):
    from spool.writer import write_event

    envelope = {
        "event_id": "test-uuid-002",
        "event_type": "prompt.lifecycle.submitted",
        "timestamp": "2026-05-15T00:00:00+00:00",
        "schema_version": 1,
        "payload": {},
    }
    write_event(envelope, root=spool_root)
    spool_dir = spool_root / "spool"
    tmp_files = list(spool_dir.glob("*.tmp"))
    assert len(tmp_files) == 0


def test_write_event_auto_adds_schema_version(spool_root):
    from spool.writer import write_event

    envelope = {
        "event_id": "test-auto-schema-001",
        "event_type": "prompt.lifecycle.submitted",
        "timestamp": "2026-05-17T00:00:00+00:00",
        "payload": {},
    }
    dest = write_event(envelope, root=spool_root)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1


def test_write_event_preserves_schema_version_when_present(spool_root):
    from spool.writer import write_event

    envelope = {
        "event_id": "test-schema-preserve-001",
        "event_type": "prompt.lifecycle.submitted",
        "timestamp": "2026-05-17T00:00:00+00:00",
        "schema_version": 2,
        "payload": {},
    }
    dest = write_event(envelope, root=spool_root)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2


def test_write_event_auto_adds_event_id(spool_root):
    from spool.writer import write_event
    import uuid as _uuid

    envelope = {
        "event_type": "prompt.lifecycle.submitted",
        "timestamp": "2026-05-17T00:00:00+00:00",
        "payload": {},
    }
    dest = write_event(envelope, root=spool_root)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert "event_id" in data
    _uuid.UUID(data["event_id"])  # raises ValueError if not a valid UUID


def test_write_event_preserves_event_id_when_present(spool_root):
    from spool.writer import write_event

    envelope = {
        "event_id": "my-custom-id-preserve-001",
        "event_type": "prompt.lifecycle.submitted",
        "timestamp": "2026-05-17T00:00:00+00:00",
        "payload": {},
    }
    dest = write_event(envelope, root=spool_root)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["event_id"] == "my-custom-id-preserve-001"


def test_directory_auto_creation(tmp_path, monkeypatch):
    new_root = tmp_path / "new_spool_root"
    monkeypatch.setenv("DS_SPOOL_ROOT", str(new_root))
    from spool.writer import write_event
    from spool import config
    import importlib

    importlib.reload(config)
    envelope = {
        "event_id": "test-uuid-003",
        "event_type": "prompt.lifecycle.submitted",
        "timestamp": "2026-05-15T00:00:00+00:00",
        "schema_version": 1,
        "payload": {},
    }
    write_event(envelope, root=new_root)
    assert (new_root / "spool" / "test-uuid-003.json").exists()
