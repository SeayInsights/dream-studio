"""emit_security_finding says whether a row was written, and why not when it was not.

record_security_finding used to swallow a failing INSERT, so emit_security_finding returned
emitted=True with no security_events row: a CHECK or trigger violation, a string over
SQLite's length limit, a lock timeout or a full disk all told the caller the finding was
recorded. These tests pin the opposite: a failed write is reported (emitted False, failed
True, a reason), logged by exception class only, leaves no row and no orphan execution
event, does not reach the spool, and is distinguishable from a disabled emitter and from a
duplicate, which are skips, not failures.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.telemetry import emitters_shared
from core.telemetry.emitters import emit_security_finding
from core.telemetry.emitters_shared import MODE_STRICT, TELEMETRY_DISABLED_ENV
from core.telemetry.execution_spine import record_security_finding

POISON = "poisoned-title"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "studio.db"
    bootstrap_database(path)
    conn = sqlite3.connect(path)
    # Any constraint failure takes the same path as a CHECK violation: the INSERT raises.
    conn.execute(
        "CREATE TRIGGER poison BEFORE INSERT ON security_events WHEN NEW.title = '"
        + POISON
        + "' BEGIN SELECT RAISE(ABORT, 'rejected by constraint'); END"
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture(autouse=True)
def _no_spool():
    with patch("spool.writer.write_event") as write_event:
        yield write_event


def _emit(db: Path, description: str = "ordinary", rule_id: str = "CWE-1", **kw):
    return emit_security_finding(
        severity="high",
        description=description,
        rule_id=rule_id,
        context={"project_id": "proj"},
        db_path=db,
        **kw,
    )


def _count(db: Path, sql: str) -> int:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


ROWS = "SELECT COUNT(*) FROM security_events WHERE event_kind = 'finding.recorded'"
EVENTS = "SELECT COUNT(*) FROM execution_events WHERE event_type = 'security.finding_recorded'"


def test_a_normal_emit_is_emitted_and_leaves_a_row(db: Path, _no_spool):
    result = _emit(db)
    assert result.emitted is True and result.failed is False and result.error is None
    assert _count(db, ROWS) == 1 and _count(db, EVENTS) == 1
    assert _no_spool.called


def test_a_constraint_violation_is_reported_not_swallowed(db: Path, caplog, _no_spool):
    with caplog.at_level(logging.WARNING):
        result = _emit(db, description=POISON)
    assert result.emitted is False
    assert result.failed is True
    assert result.error and "write failed" in result.error
    assert result.record_id, "the caller can still see which finding it was"
    assert _count(db, ROWS) == 0, "no row"
    assert _count(db, EVENTS) == 0, "and no orphan execution event for a finding never stored"
    assert not _no_spool.called, "a finding that was not stored is not announced"
    logged = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("IntegrityError" in m for m in logged), logged


def test_an_oversize_value_is_reported_not_swallowed(db: Path, caplog):
    real = emitters_shared._connect

    def limited(path):
        conn = real(path)
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 100_000)
        return conn

    with patch.object(emitters_shared, "_connect", limited), caplog.at_level(logging.WARNING):
        result = _emit(db, description="x" * 200_000)
    assert result.emitted is False and result.failed is True
    assert "write failed" in (result.error or "")
    assert _count(db, ROWS) == 0
    assert any("DataError" in r.getMessage() for r in caplog.records)


def test_the_log_names_the_class_and_never_the_data(db: Path, caplog):
    secret = "api-key-AKIA0123456789"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TRIGGER leak BEFORE INSERT ON security_events WHEN NEW.title LIKE '%AKIA%' "
        "BEGIN SELECT RAISE(ABORT, 'rejected value ' || NEW.title); END"
    )
    conn.commit()
    conn.close()
    with caplog.at_level(logging.DEBUG):
        result = _emit(db, description=secret)
    assert result.failed
    everything = " ".join(r.getMessage() for r in caplog.records) + (result.error or "")
    assert secret not in everything and "AKIA" not in everything


def test_a_disabled_emitter_reports_disabled_not_failed(db: Path, monkeypatch):
    monkeypatch.setenv(TELEMETRY_DISABLED_ENV, "1")
    result = _emit(db)
    assert result.emitted is False
    assert result.failed is False, "disabled is a choice, not a failure"
    assert result.error == "telemetry disabled"
    assert _count(db, ROWS) == 0


def test_a_duplicate_is_a_skip_not_a_failure(db: Path):
    assert _emit(db).emitted is True
    again = _emit(db)
    assert again.emitted is False and again.failed is False
    assert "duplicate" in (again.error or "")
    assert _count(db, ROWS) == 1


def test_a_missing_table_is_a_failure_not_a_skip(tmp_path: Path):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    result = _emit(path)
    assert result.emitted is False and result.failed is True


def test_strict_mode_raises_on_a_failed_write(db: Path):
    with pytest.raises(RuntimeError, match="write failed"):
        _emit(db, description=POISON, mode=MODE_STRICT)
    assert _count(db, ROWS) == 0


def test_record_security_finding_returns_the_reason_and_none_on_success(db: Path, caplog):
    conn = sqlite3.connect(db)
    try:
        ok = record_security_finding(conn, finding_id="f-ok", severity="low", description="fine")
        assert ok is None
        with caplog.at_level(logging.WARNING):
            bad = record_security_finding(
                conn, finding_id="f-bad", severity="low", description=POISON
            )
        assert bad and "IntegrityError" in bad
        dup = record_security_finding(conn, finding_id="f-ok", severity="low", description="fine")
        assert dup and "duplicate" in dup
    finally:
        conn.close()
