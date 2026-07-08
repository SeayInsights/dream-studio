"""WO-FILESDB-P2: per-session token accumulator lives in raw_session_token_accumulators.

Covers the authority-backed accumulator API, that token_capture writes it and the
emitter reads it when the table is present, and graceful degradation to the legacy
JSON file when the table is absent (migration 145 unreleased on the live DB).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.telemetry.session_accumulator import db_read_accumulator, db_update_accumulator

REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = (
    REPO_ROOT / "core" / "event_store" / "migrations" / "145_session_token_accumulators.sql"
)


def _db_with_table(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_MIGRATION.read_text(encoding="utf-8"))  # exercises the real DDL
    conn.close()
    return db


def test_db_accumulator_roundtrip_and_sum(tmp_path):
    db = _db_with_table(tmp_path)
    assert db_update_accumulator(
        "s1", {"input_tokens": 100, "output_tokens": 50, "model": "claude-opus-4-8"}, db_path=db
    )
    db_update_accumulator("s1", {"input_tokens": 20, "output_tokens": 5}, db_path=db)
    acc = db_read_accumulator("s1", db_path=db)
    assert acc["input_tokens"] == 120
    assert acc["output_tokens"] == 55
    assert acc["model"] == "claude-opus-4-8"  # a later modelless turn doesn't wipe it


def test_db_accumulator_absent_table(tmp_path):
    db = tmp_path / "studio.db"
    sqlite3.connect(str(db)).close()  # no migration → table absent
    assert db_update_accumulator("s2", {"input_tokens": 1}, db_path=db) is False
    assert db_read_accumulator("s2", db_path=db) is None


def test_token_capture_writes_table_when_present(tmp_path, monkeypatch):
    # _db_with_table creates tmp_path/studio.db (with the table); state_dir -> tmp_path
    # makes token_capture's default db path resolve to that same migrated DB.
    _db_with_table(tmp_path)
    monkeypatch.setattr("core.telemetry.session_accumulator.paths.state_dir", lambda: tmp_path)
    from core.telemetry.token_capture import _update_session_accumulator

    _update_session_accumulator("s3", {"input_tokens": 7, "output_tokens": 3})
    acc = db_read_accumulator("s3", db_path=tmp_path / "studio.db")
    assert acc is not None
    assert acc["input_tokens"] == 7


def test_emitter_reads_table_accumulator(tmp_path, monkeypatch):
    db = _db_with_table(tmp_path)
    db_update_accumulator(
        "s4", {"input_tokens": 300, "output_tokens": 120, "model": "claude-opus-4-8"}, db_path=db
    )
    monkeypatch.setattr("core.telemetry.session_accumulator.paths.state_dir", lambda: tmp_path)
    from emitters.claude_code.emitter import _read_session_accumulator

    acc = _read_session_accumulator("s4")
    assert acc["input_tokens"] == 300
    assert acc["model"] == "claude-opus-4-8"
