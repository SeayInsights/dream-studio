"""emit_security_finding says whether a row was written, and why not when it was not.

record_security_finding used to swallow a failing INSERT, so emit_security_finding returned
emitted=True with no security_events row. These tests pin the opposite, scenario by
scenario: a failed write is reported (emitted False, failed True, a reason with the
exception class and SQLite code), logged without the data, leaves no row and no orphan
execution event, and announces NOTHING on the spool. The spool is inspected on disk (a
spy on a name the code bound at import time would see nothing, which is how an earlier
version of this file claimed a guarantee it never checked). A disabled emitter and a
duplicate are skips, not failures; a trigger's RAISE(IGNORE) is not a duplicate.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.telemetry import emitters_security, emitters_shared
from core.telemetry.emitters import emit_security_finding, emit_security_finding_resolved
from core.telemetry.emitters_shared import MODE_STRICT, TELEMETRY_DISABLED_ENV, _emit
from core.telemetry.execution_spine import (
    FINDING_DUPLICATE,
    FINDING_NOT_FOUND,
    record_security_finding,
    resolve_security_finding_reason,
)

POISON = "poisoned-title"
IGNORED = "ignored-title"
CHECKED = "check-me"
CODE = re.compile(r"\(SQLITE_\w+\)")

ROWS = "SELECT COUNT(*) FROM security_events WHERE event_kind = 'finding.recorded'"
STATUS_ROWS = "SELECT COUNT(*) FROM security_events WHERE event_kind = 'finding.status_changed'"
EVENTS = "SELECT COUNT(*) FROM execution_events WHERE event_type = 'security.finding_recorded'"


@pytest.fixture(autouse=True)
def spool_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "spool-root"
    monkeypatch.setenv("DS_SPOOL_ROOT", str(root))
    return root


def spooled(root: Path) -> list[str]:
    """The event types of every envelope on the spool, read from disk."""
    return sorted(
        json.loads(p.read_text(encoding="utf-8"))["event_type"] for p in root.rglob("*.json")
    )


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "studio.db"
    bootstrap_database(path)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TRIGGER poison BEFORE INSERT ON security_events WHEN NEW.title = '"
        + POISON
        + "' BEGIN SELECT RAISE(ABORT, 'rejected by constraint'); END"
    )
    conn.execute(
        "CREATE TRIGGER ignore_it BEFORE INSERT ON security_events WHEN NEW.title = '"
        + IGNORED
        + "' BEGIN SELECT RAISE(IGNORE); END"
    )
    conn.commit()
    conn.close()
    return path


def rebuild_security_events(path: Path, *, check: str | None = None, body_not_null=False) -> None:
    """Replace security_events with a copy that has a CHECK, or a NOT NULL body."""
    conn = sqlite3.connect(path)
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'security_events'"
    ).fetchone()[0]
    for (view,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'view' AND sql LIKE '%security_events%'"
    ).fetchall():
        conn.execute(f"DROP VIEW {view}")
    for (trigger,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'security_events'"
    ).fetchall():
        conn.execute(f"DROP TRIGGER {trigger}")
    conn.execute("DROP TABLE security_events")
    if body_not_null:
        sql = re.sub(r"\bbody(\s+)TEXT", r"body\1TEXT NOT NULL", sql, count=1)
    if check:
        sql = sql[: sql.rstrip().rfind(")")] + f", CHECK ({check})\n)"
    conn.execute(sql)
    conn.commit()
    conn.close()


def emit(db: Path, description: str = "ordinary", rule_id: str = "CWE-1", **kw):
    return emit_security_finding(
        severity="high",
        description=description,
        rule_id=rule_id,
        recommendation=kw.pop("recommendation", "fix it"),
        context={"project_id": "proj"},
        db_path=db,
        **kw,
    )


def count(db: Path, sql: str) -> int:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


def assert_failed_cleanly(db: Path, root: Path, result, *, rows: int = 0) -> None:
    assert result.emitted is False
    assert result.failed is True
    assert result.error and CODE.search(result.error) or "ignored by a trigger" in result.error
    assert count(db, ROWS) == rows, "no finding row"
    assert count(db, EVENTS) == 0, "and no orphan execution event"
    assert spooled(root) == [], "and nothing announced on the spool"


def test_a_normal_emit_is_emitted_leaves_a_row_and_announces_exactly_two_envelopes(
    db: Path, spool_root: Path
):
    result = emit(db)
    assert result.emitted is True and result.failed is False and result.error is None
    assert count(db, ROWS) == 1 and count(db, EVENTS) == 1
    assert spooled(spool_root) == ["security.finding.logged", "security.finding_recorded"]


def test_an_open_finding_with_a_non_open_status_records_both_rows(db: Path, spool_root: Path):
    result = emit(db, status="fixed")
    assert result.emitted is True
    assert count(db, ROWS) == 1 and count(db, STATUS_ROWS) == 1


# ---------------------------------------------------------------------------
# Failure scenarios: each must report, log a class-only reason, store nothing and announce
# nothing
# ---------------------------------------------------------------------------


def test_a_trigger_abort_is_reported_not_swallowed(db: Path, spool_root: Path, caplog):
    with caplog.at_level(logging.WARNING):
        result = emit(db, description=POISON)
    assert_failed_cleanly(db, spool_root, result)
    assert "write failed" in result.error and "IntegrityError" in result.error
    assert result.record_id, "the caller can still see which finding it was"
    logged = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("IntegrityError" in m for m in logged), logged


def test_a_check_violation_is_reported_not_swallowed(db: Path, spool_root: Path):
    rebuild_security_events(db, check=f"title <> '{CHECKED}'")
    result = emit(db, description=CHECKED)
    assert_failed_cleanly(db, spool_root, result)
    assert "SQLITE_CONSTRAINT_CHECK" in result.error


def test_a_not_null_violation_is_reported_not_swallowed(db: Path, spool_root: Path):
    rebuild_security_events(db, body_not_null=True)
    result = emit(db, recommendation=None)
    assert_failed_cleanly(db, spool_root, result)
    assert "SQLITE_CONSTRAINT_NOTNULL" in result.error


def test_a_trigger_raise_ignore_is_a_failed_write_not_a_duplicate(db: Path, spool_root: Path):
    """RAISE(IGNORE) writes nothing and raises nothing. It used to look like a duplicate
    (rowcount 0), so the caller was told 'duplicate' and strict mode did not raise."""
    result = emit(db, description=IGNORED)
    assert result.emitted is False
    assert result.failed is True, "a finding that was not stored is a failure, not a skip"
    assert "ignored by a trigger" in result.error
    assert "duplicate" not in result.error
    assert count(db, ROWS) == 0 and count(db, EVENTS) == 0
    assert spooled(spool_root) == []


def test_an_oversize_value_is_reported_not_swallowed(db: Path, spool_root: Path, caplog):
    real = emitters_shared._connect

    def limited(path):
        conn = real(path)
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 100_000)
        return conn

    with patch.object(emitters_shared, "_connect", limited), caplog.at_level(logging.WARNING):
        result = emit(db, description="x" * 200_000)
    assert_failed_cleanly(db, spool_root, result)
    assert "DataError" in result.error
    assert any("DataError" in r.getMessage() for r in caplog.records)


def test_a_locked_database_is_reported_not_swallowed(db: Path, spool_root: Path):
    real = emitters_shared._connect

    def impatient(path):
        conn = real(path)
        conn.execute("PRAGMA busy_timeout = 50")
        return conn

    blocker = sqlite3.connect(db, isolation_level=None)
    blocker.execute("BEGIN EXCLUSIVE")
    try:
        with patch.object(emitters_shared, "_connect", impatient):
            result = emit(db)
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    assert result.emitted is False and result.failed is True
    assert count(db, ROWS) == 0
    assert spooled(spool_root) == []


def test_a_read_only_database_is_reported_not_swallowed(db: Path, spool_root: Path):
    real = emitters_shared._connect

    def read_only(path):
        conn = real(path)
        conn.execute("PRAGMA query_only = ON")
        return conn

    with patch.object(emitters_shared, "_connect", read_only):
        result = emit(db)
    assert result.emitted is False and result.failed is True
    assert count(db, ROWS) == 0
    assert spooled(spool_root) == []


def test_a_failed_status_event_is_reported_and_rolls_the_finding_back(db: Path, spool_root: Path):
    """The finding row stores, the status event does not: the finding would read 'open'
    while the caller said 'fixed'. All or nothing."""
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TRIGGER no_status BEFORE INSERT ON security_events"
        " WHEN NEW.event_kind = 'finding.status_changed'"
        " BEGIN SELECT RAISE(ABORT, 'no status events'); END"
    )
    conn.commit()
    conn.close()
    result = emit(db, status="fixed")
    assert result.emitted is False and result.failed is True
    assert CODE.search(result.error), "the SQLite code is part of the reason"
    assert count(db, ROWS) == 0 and count(db, STATUS_ROWS) == 0 and count(db, EVENTS) == 0
    assert spooled(spool_root) == []


def test_a_status_event_ignored_by_a_trigger_is_reported(db: Path, spool_root: Path):
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TRIGGER ignore_status BEFORE INSERT ON security_events"
        " WHEN NEW.event_kind = 'finding.status_changed' BEGIN SELECT RAISE(IGNORE); END"
    )
    conn.commit()
    conn.close()
    result = emit(db, status="fixed")
    assert result.emitted is False and result.failed is True
    assert "ignored by a trigger" in result.error
    assert count(db, ROWS) == 0
    assert spooled(spool_root) == []


def test_a_failed_insert_with_a_non_open_status_reports_the_insert_not_the_status(
    db: Path, spool_root: Path, caplog
):
    """The status event is only attempted for a finding that was stored."""
    with caplog.at_level(logging.WARNING):
        result = emit(db, description=POISON, status="fixed")
    assert result.failed and "IntegrityError" in result.error
    assert "status" not in result.error
    assert not any("status" in r.getMessage() for r in caplog.records)
    assert count(db, STATUS_ROWS) == 0


def test_the_log_names_the_class_and_never_the_data(db: Path, caplog):
    secret = "customer-record-7731-do-not-log"
    conn = sqlite3.connect(db)
    # RAISE() takes only a string literal on every SQLite build (some reject an
    # expression), so the secret is written into the message itself.
    conn.execute(
        "CREATE TRIGGER leak BEFORE INSERT ON security_events WHEN NEW.title LIKE '%7731%' "
        f"BEGIN SELECT RAISE(ABORT, 'rejected value {secret}'); END"
    )
    conn.commit()
    conn.close()
    with caplog.at_level(logging.DEBUG):
        result = emit(db, description=secret)
    assert result.failed
    everything = " ".join(r.getMessage() for r in caplog.records) + (result.error or "")
    assert secret not in everything and "7731" not in everything


def test_the_generic_failure_path_reports_the_class_only_too():
    def writer(conn):
        raise ValueError("customer-record-7731-do-not-log")

    result = _emit(writer, db_path=":memory:", mode="best_effort", required_tables=())
    assert result.failed is True
    assert result.error == "ValueError"
    assert "7731" not in result.error


class _CommitFails(sqlite3.Connection):
    """Every statement succeeds and the COMMIT does not: a full disk, a lock timeout."""

    def commit(self):
        raise sqlite3.OperationalError("disk I/O error")


def _commit_fails(path):
    conn = sqlite3.connect(str(path), timeout=1.0, factory=_CommitFails)
    conn.row_factory = sqlite3.Row
    return conn


def test_a_failed_commit_announces_nothing_for_a_finding(db: Path, spool_root: Path):
    """The rows were written in the transaction; the commit did not land. Announcing at
    that point would announce a finding that is not stored."""
    with patch.object(emitters_shared, "_connect", _commit_fails):
        result = emit(db)
    assert result.emitted is False and result.failed is True
    assert count(db, ROWS) == 0 and count(db, EVENTS) == 0
    assert spooled(spool_root) == []


def test_a_failed_commit_announces_nothing_for_a_resolution(db: Path, spool_root: Path):
    finding_id = _recorded(db)
    before = spooled(spool_root)
    with patch.object(emitters_shared, "_connect", _commit_fails):
        result = emit_security_finding_resolved(finding_id=finding_id, db_path=db)
    assert result.emitted is False and result.failed is True
    assert count(db, STATUS_ROWS) == 0
    assert spooled(spool_root) == before


# ---------------------------------------------------------------------------
# Skips are not failures
# ---------------------------------------------------------------------------


def test_a_disabled_emitter_reports_disabled_not_failed(db: Path, monkeypatch, spool_root: Path):
    monkeypatch.setenv(TELEMETRY_DISABLED_ENV, "1")
    result = emit(db)
    assert result.emitted is False
    assert result.failed is False, "disabled is a choice, not a failure"
    assert result.error == "telemetry disabled"
    assert count(db, ROWS) == 0 and spooled(spool_root) == []


def test_a_duplicate_is_a_skip_not_a_failure(db: Path, spool_root: Path):
    assert emit(db).emitted is True
    first_spool = spooled(spool_root)
    again = emit(db)
    assert again.emitted is False and again.failed is False
    assert "duplicate" in (again.error or "")
    assert count(db, ROWS) == 1
    assert spooled(spool_root) == first_spool, "a skip announces nothing further"


def _lose_a_race(db: Path, monkeypatch) -> str:
    """Another writer stores the same finding id after emit's duplicate pre-check and
    before its INSERT. The id is deterministic, so a first emit into a scratch database
    tells us what it will be."""
    scratch = db.parent / "scratch.db"
    bootstrap_database(scratch)
    finding_id = emit(scratch).record_id
    real = emitters_security.record_execution_event

    def racing(conn, **values):
        other = sqlite3.connect(db)
        other.execute(
            "INSERT INTO security_events (event_id, event_kind, severity, title)"
            " VALUES (?, 'finding.recorded', 'high', 'the racer')",
            (finding_id,),
        )
        other.commit()
        other.close()
        real(conn, **values)

    monkeypatch.setattr(emitters_security, "record_execution_event", racing)
    return finding_id


def test_losing_a_race_for_the_same_id_is_a_skip_and_rolls_back(
    db: Path, spool_root: Path, monkeypatch
):
    finding_id = _lose_a_race(db, monkeypatch)
    for leftover in spool_root.rglob("*.json"):  # the scratch emit's envelopes
        leftover.unlink()
    result = emit(db)
    assert result.emitted is False
    assert result.failed is False, "someone else stored it: a skip, not a failure"
    assert "duplicate" in result.error
    assert result.record_id == finding_id
    assert count(db, ROWS) == 1, "the racer's row, once"
    assert count(db, EVENTS) == 0, "our execution event was rolled back"
    assert spooled(spool_root) == []


def test_losing_a_race_does_not_raise_in_strict_mode(db: Path, monkeypatch):
    _lose_a_race(db, monkeypatch)
    assert emit(db, mode=MODE_STRICT).failed is False


@pytest.mark.parametrize("description", [POISON, IGNORED])
def test_strict_mode_raises_on_a_failed_write(db: Path, description):
    with pytest.raises(RuntimeError, match="write failed"):
        emit(db, description=description, mode=MODE_STRICT)
    assert count(db, ROWS) == 0 and count(db, EVENTS) == 0


def test_a_missing_table_is_a_failure_not_a_skip(tmp_path: Path):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    result = emit(path)
    assert result.emitted is False and result.failed is True


# ---------------------------------------------------------------------------
# record_security_finding itself
# ---------------------------------------------------------------------------


def test_record_security_finding_returns_the_reason_and_none_on_success(db: Path):
    conn = sqlite3.connect(db)
    try:
        assert (
            record_security_finding(conn, finding_id="f-ok", severity="low", description="a")
            is None
        )
        bad = record_security_finding(conn, finding_id="f-bad", severity="low", description=POISON)
        assert bad and "IntegrityError" in bad and CODE.search(bad)
        dup = record_security_finding(conn, finding_id="f-ok", severity="low", description="a")
        assert dup == FINDING_DUPLICATE
        ignored = record_security_finding(
            conn, finding_id="f-ign", severity="low", description=IGNORED
        )
        assert ignored and "ignored by a trigger" in ignored
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# emit_security_finding_resolved
# ---------------------------------------------------------------------------


def _recorded(db: Path) -> str:
    result = emit(db)
    assert result.emitted
    return result.record_id


def test_resolving_announces_exactly_one_more_envelope(db: Path, spool_root: Path):
    finding_id = _recorded(db)
    before = spooled(spool_root)
    result = emit_security_finding_resolved(
        finding_id=finding_id, resolution="mitigated", db_path=db
    )
    assert result.emitted is True and result.failed is False
    assert count(db, STATUS_ROWS) == 1
    after = spooled(spool_root)
    assert after == sorted([*before, "security.finding.resolved"])


def test_resolving_an_unknown_finding_is_not_found_and_not_a_failure(db: Path, spool_root: Path):
    result = emit_security_finding_resolved(finding_id="nope", db_path=db)
    assert result.emitted is False and result.failed is False
    assert "not found" in result.error
    assert spooled(spool_root) == []


def test_a_resolve_that_raises_is_a_failure_distinct_from_not_found(
    db: Path, spool_root: Path, caplog
):
    finding_id = _recorded(db)
    before = spooled(spool_root)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TRIGGER no_status BEFORE INSERT ON security_events"
        " WHEN NEW.event_kind = 'finding.status_changed'"
        " BEGIN SELECT RAISE(ABORT, 'no status events'); END"
    )
    conn.commit()
    conn.close()
    with caplog.at_level(logging.WARNING):
        result = emit_security_finding_resolved(finding_id=finding_id, db_path=db)
    assert result.emitted is False
    assert result.failed is True
    assert "not found" not in result.error and "resolve failed" in result.error
    assert CODE.search(result.error)
    assert count(db, STATUS_ROWS) == 0
    assert spooled(spool_root) == before, "a failed resolution is not announced"
    assert any("IntegrityError" in r.getMessage() for r in caplog.records)
    with pytest.raises(RuntimeError, match="resolve failed"):
        emit_security_finding_resolved(finding_id=finding_id, db_path=db, mode=MODE_STRICT)


def test_resolve_reason_distinguishes_not_found_ignored_and_failed(db: Path):
    finding_id = _recorded(db)
    conn = sqlite3.connect(db)
    try:
        assert resolve_security_finding_reason(conn, finding_id="nope") == FINDING_NOT_FOUND
        conn.execute(
            "CREATE TRIGGER ignore_status BEFORE INSERT ON security_events"
            " WHEN NEW.event_kind = 'finding.status_changed' BEGIN SELECT RAISE(IGNORE); END"
        )
        reason = resolve_security_finding_reason(conn, finding_id=finding_id)
        assert reason and "ignored by a trigger" in reason
    finally:
        conn.close()
