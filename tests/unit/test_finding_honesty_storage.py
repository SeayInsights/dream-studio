"""security_events stores a finding's confidence, coverage and limitations (migration 161).

The read model already carried the three honesty fields (test_finding_honesty_fields.py)
but nothing could store them, so every authority-backed finding read as unknown. These
tests pin the storage half: the migration, the writers, and the collector, with the one
rule that matters stated three ways -- NULL is unknown, never high or complete, and a
value the vocabulary does not recognise is stored as NULL, never as a certain one.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database, run_migrations
from core.findings.collect import from_security_events
from core.findings.model import (
    CONFIDENCE_VALUES,
    COVERAGE_VALUES,
    decode_limitations,
    encode_honesty,
)
from core.findings.mutations import record_finding

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "core" / "event_store" / "migrations"
FORWARD = MIGRATIONS / "161_finding_honesty_fields.sql"
REVERSE = MIGRATIONS / "rollback" / "161_finding_honesty_fields.sql"
COLUMNS = ("confidence", "coverage", "limitations")


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(security_events)")}


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"  # where `ds render` looks under a home
    bootstrap_database(path)
    return path


@pytest.fixture(autouse=True)
def _no_real_spool():
    """record_finding emits an observability event; never let a test write a real spool."""
    with patch("emitters.shared.spool_writer.write_envelopes") as write:
        yield write


def _row(db: Path, finding_id: str) -> sqlite3.Row:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM security_events WHERE event_id = ?", (finding_id,)
        ).fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The migration
# ---------------------------------------------------------------------------


def test_the_migration_applies_on_an_empty_database():
    conn = sqlite3.connect(":memory:")
    assert run_migrations(conn) >= 161
    assert set(COLUMNS) <= _columns(conn)
    conn.close()


def test_the_migration_applies_on_a_database_at_the_previous_schema():
    """A database at 160 with an old finding row upgrades; the old row is unknown."""
    conn = sqlite3.connect(":memory:")
    assert run_migrations(conn, target_version=160) == 160
    assert not set(COLUMNS) & _columns(conn)
    conn.execute(
        "INSERT INTO security_events (event_id, event_kind, severity, title)"
        " VALUES ('old', 'finding.recorded', 'high', 'before 161')"
    )
    conn.commit()
    assert run_migrations(conn) >= 161
    assert set(COLUMNS) <= _columns(conn)
    stored = conn.execute(
        "SELECT confidence, coverage, limitations FROM security_events WHERE event_id = 'old'"
    ).fetchone()
    assert tuple(stored) == (None, None, None), "an old row must read unknown, not backfilled"
    conn.close()


def test_the_columns_are_nullable_with_no_default():
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    info = {r[1]: r for r in conn.execute("PRAGMA table_info(security_events)")}
    for name in COLUMNS:
        assert info[name][3] == 0, f"{name} must be nullable"
        assert info[name][4] is None, f"{name} must have no default: a default is a claim"
    conn.close()


def test_the_check_vocabulary_matches_the_read_model():
    """The CHECK mirrors CONFIDENCE_VALUES / COVERAGE_VALUES; the two may not drift."""
    sql = FORWARD.read_text(encoding="utf-8")

    def vocab(column: str) -> tuple[str, ...]:
        match = re.search(rf"{column} IN \(([^)]*)\)", sql)
        assert match, column
        return tuple(re.findall(r"'([^']+)'", match.group(1)))

    assert vocab("confidence") == CONFIDENCE_VALUES
    assert vocab("coverage") == COVERAGE_VALUES


@pytest.mark.parametrize(
    "column,value",
    [("confidence", "certain"), ("coverage", "all"), ("limitations", "not json {")],
)
def test_the_database_refuses_an_off_vocabulary_value(column, value):
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            f"INSERT INTO security_events (event_id, event_kind, {column})"
            " VALUES ('x', 'finding.recorded', ?)",
            (value,),
        )
    conn.close()


def test_the_rollback_drops_exactly_the_three_columns_and_no_row():
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    conn.execute(
        "INSERT INTO security_events (event_id, event_kind, severity, coverage)"
        " VALUES ('keep', 'finding.recorded', 'low', 'partial')"
    )
    before = _columns(conn)
    conn.executescript(REVERSE.read_text(encoding="utf-8"))
    assert _columns(conn) == before - set(COLUMNS)
    assert conn.execute("SELECT COUNT(*) FROM security_events").fetchone()[0] == 1
    # The security summary view selects from the table and must still resolve.
    conn.execute("SELECT * FROM vw_security_summary").fetchall()
    conn.close()


# ---------------------------------------------------------------------------
# Encoding: one vocabulary, the read model's
# ---------------------------------------------------------------------------


def test_encode_stores_recognised_values_and_null_for_the_rest():
    assert encode_honesty("High", "partial", ["a", " ", "b"]) == {
        "confidence": "high",
        "coverage": "partial",
        "limitations": '["a", "b"]',
    }
    unknown = {"confidence": None, "coverage": None, "limitations": None}
    assert encode_honesty() == unknown
    assert encode_honesty("certain", "all", 42) == unknown
    assert encode_honesty("unknown", "unknown", "") == unknown


def test_encode_keeps_none_recorded_distinct_from_not_recorded():
    assert encode_honesty(limitations=[])["limitations"] == "[]"
    assert decode_limitations("[]") == ()
    assert decode_limitations(None) is None


@pytest.mark.parametrize("stored", ["not json", "{}", '"a string"', "3", b"\xff"])
def test_decode_limitations_of_garbage_is_not_recorded(stored):
    assert decode_limitations(stored) is None


# ---------------------------------------------------------------------------
# record_finding -> row -> collector
# ---------------------------------------------------------------------------


def test_record_finding_round_trips_through_the_row_and_the_collector(db: Path):
    fid = record_finding(
        severity="high",
        title="SQL injection",
        confidence="medium",
        coverage="partial",
        limitations=["no taint analysis", "tests dir skipped"],
        db_path=db,
    )
    row = _row(db, fid)
    assert (row["confidence"], row["coverage"]) == ("medium", "partial")
    assert json.loads(row["limitations"]) == ["no taint analysis", "tests dir skipped"]

    (finding,) = from_security_events(db)
    assert finding.confidence == "medium"
    assert finding.coverage == "partial"
    assert finding.limitations == ("no taint analysis", "tests dir skipped")


def test_record_finding_without_the_fields_stores_null_and_reads_unknown(db: Path):
    fid = record_finding(severity="high", title="bare", db_path=db)
    row = _row(db, fid)
    assert (row["confidence"], row["coverage"], row["limitations"]) == (None, None, None)
    (finding,) = from_security_events(db)
    assert (finding.confidence, finding.coverage, finding.limitations) == (
        "unknown",
        "unknown",
        None,
    )


def test_an_empty_limitations_list_is_recorded_as_none_exist(db: Path):
    record_finding(severity="low", title="clean scan", limitations=[], db_path=db)
    (finding,) = from_security_events(db)
    assert finding.limitations == ()


@pytest.mark.parametrize("bad", ["certain", "HIGHEST", "", 3])
def test_invalid_values_are_stored_as_unknown_never_as_certain(db: Path, bad):
    fid = record_finding(
        severity="high", title="junk", confidence=bad, coverage=bad, limitations=bad, db_path=db
    )
    row = _row(db, fid)
    assert row["confidence"] is None and row["coverage"] is None
    (finding,) = from_security_events(db)
    assert (finding.confidence, finding.coverage) == ("unknown", "unknown")
    assert finding.coverage != "complete" and finding.confidence != "high"


def test_the_collector_reads_a_database_without_the_columns(tmp_path: Path):
    """A database that predates 161 (or never applied it) reads unknown, not an error."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE security_events (event_id TEXT, event_kind TEXT, project_id TEXT,"
        " file_path TEXT, line_number INTEGER, severity TEXT, title TEXT, body TEXT,"
        " created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO security_events VALUES ('e','finding.recorded','p','a',1,'high','t','b','t')"
    )
    conn.commit()
    conn.close()
    (f,) = from_security_events(path)
    assert (f.confidence, f.coverage, f.limitations) == ("unknown", "unknown", None)


def test_the_collector_treats_a_corrupt_limitations_cell_as_not_recorded(tmp_path: Path):
    path = tmp_path / "odd.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE security_events (event_id TEXT, event_kind TEXT, severity TEXT,"
        " title TEXT, confidence TEXT, coverage TEXT, limitations TEXT)"
    )
    conn.execute(
        "INSERT INTO security_events VALUES ('e','finding.recorded','high','t','sure','all','{bad')"
    )
    conn.commit()
    conn.close()
    (f,) = from_security_events(path)
    assert (f.confidence, f.coverage, f.limitations) == ("unknown", "unknown", None)


def test_record_finding_on_a_database_without_the_columns_still_records_it(tmp_path: Path):
    """The migration is unreleased, so a live authority may not have it. The finding is
    recorded without the fields, with a warning, and reads unknown."""
    path = tmp_path / "pre161.db"
    conn = sqlite3.connect(path)
    run_migrations(conn, target_version=160)
    conn.commit()
    conn.close()
    with pytest.warns(RuntimeWarning, match="migration 161"):
        fid = record_finding(severity="high", title="t", coverage="partial", db_path=path)
    assert _row(path, fid)["title"] == "t"
    (f,) = from_security_events(path)
    assert f.coverage == "unknown"

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # nothing supplied, nothing to warn about
        record_finding(severity="low", title="plain", db_path=path)


# ---------------------------------------------------------------------------
# emit_security_finding (the telemetry path)
# ---------------------------------------------------------------------------


def test_emit_security_finding_stores_the_fields(db: Path):
    from core.telemetry.emitters import emit_security_finding

    with patch("spool.writer.write_event") as write_event:
        result = emit_security_finding(
            severity="high",
            description="d",
            rule_id="CWE-89",
            confidence="low",
            coverage="complete",
            limitations=["generated code excluded"],
            context={"project_id": "proj"},
            db_path=db,
        )
        bare = emit_security_finding(
            severity="high",
            description="d",
            rule_id="CWE-90",
            context={"project_id": "proj"},
            db_path=db,
        )
    assert result.emitted and bare.emitted
    row = _row(db, result.record_id)
    assert (row["confidence"], row["coverage"]) == ("low", "complete")
    assert json.loads(row["limitations"]) == ["generated code excluded"]
    assert (_row(db, bare.record_id)["coverage"]) is None
    logged = write_event.call_args_list[0].args[0]["payload"]
    assert logged["coverage"] == "complete" and logged["limitations"] == ["generated code excluded"]
    assert "coverage" not in write_event.call_args_list[1].args[0]["payload"]


# ---------------------------------------------------------------------------
# `ds render findings --json`
# ---------------------------------------------------------------------------


def test_ds_render_findings_json_shows_what_was_recorded(db: Path, monkeypatch, capsys):
    from interfaces.cli import ds_render

    record_finding(
        severity="high",
        title="recorded",
        coverage="partial",
        limitations=["scanner timed out on 3 files"],
        db_path=db,
    )
    record_finding(severity="high", title="bare", db_path=db)
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(db.parent.parent))
    monkeypatch.delenv("DS_DREAM_STUDIO_HOME", raising=False)

    assert ds_render._cmd_findings(argparse.Namespace(json=True, project_id=None)) == 0
    rows = {f["title"]: f for f in json.loads(capsys.readouterr().out)["findings"]}
    assert rows["recorded"]["coverage"] == "partial"
    assert rows["recorded"]["limitations"] == ["scanner timed out on 3 files"]
    assert rows["recorded"]["confidence"] == "unknown"
    assert rows["bare"]["coverage"] == "unknown"
    assert rows["bare"]["limitations"] is None
