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


@pytest.fixture
def pre161(tmp_path: Path) -> Path:
    """A database at the previous schema: what a live authority is until 161 is released."""
    path = tmp_path / "pre161.db"
    conn = sqlite3.connect(path)
    run_migrations(conn, target_version=160)
    conn.commit()
    conn.close()
    return path


def test_record_finding_on_a_database_without_the_columns_still_records_it(pre161: Path, caplog):
    """The migration is unreleased, so a live authority may not have it. The finding is
    recorded without the fields, the loss is logged, and it reads unknown."""
    with caplog.at_level("WARNING"):
        fid = record_finding(severity="high", title="t", coverage="partial", db_path=pre161)
    assert _row(pre161, fid)["title"] == "t"
    assert any("migration 161" in r.getMessage() for r in caplog.records)
    (f,) = from_security_events(pre161)
    assert f.coverage == "unknown"

    caplog.clear()
    record_finding(severity="low", title="plain", db_path=pre161)
    assert not caplog.records, "nothing supplied, nothing to report"


def test_a_warning_escalated_to_an_error_cannot_lose_a_finding(pre161: Path):
    """-W error / filterwarnings=error must not turn "the columns are missing" into "the
    finding is missing". Both write paths, rows read back by SQL."""
    from core.telemetry.emitters import emit_security_finding

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fid = record_finding(severity="high", title="kept", coverage="partial", db_path=pre161)
        with patch("spool.writer.write_event"):
            result = emit_security_finding(
                severity="high",
                description="kept too",
                rule_id="CWE-1",
                coverage="partial",
                limitations=["x"],
                context={"project_id": "proj"},
                db_path=pre161,
            )
    assert result.emitted
    conn = sqlite3.connect(pre161)
    ids = {r[0] for r in conn.execute("SELECT event_id FROM security_events")}
    conn.close()
    assert {fid, result.record_id} <= ids


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


# ---------------------------------------------------------------------------
# limitations is a JSON array at the SQL level
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ['"a string"', '{"a": 1}', "3", "null", "true"])
def test_the_database_refuses_limitations_that_is_not_a_json_array(value):
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO security_events (event_id, event_kind, limitations)"
            " VALUES ('x', 'finding.recorded', ?)",
            (value,),
        )
    conn.close()


@pytest.mark.parametrize("value", ["[]", '["a"]', '["a", "b"]'])
def test_the_database_accepts_a_json_array_of_limitations(value):
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    conn.execute(
        "INSERT INTO security_events (event_id, event_kind, limitations)"
        " VALUES ('x', 'finding.recorded', ?)",
        (value,),
    )
    conn.close()


def test_items_being_strings_is_not_enforceable_in_sql_so_the_reader_is_tolerant(tmp_path):
    """SQLite forbids a subquery in a CHECK, so json_each cannot check the items. [1, 2]
    therefore passes the CHECK, and the reader coerces rather than fails."""
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    with pytest.raises(sqlite3.OperationalError, match="subqueries prohibited"):
        conn.execute("CREATE TABLE t (x TEXT CHECK (EXISTS (SELECT 1 FROM json_each(x))))")
    conn.execute(
        "INSERT INTO security_events (event_id, event_kind, severity, title, limitations)"
        " VALUES ('x', 'finding.recorded', 'low', 't', '[1, 2]')"
    )
    conn.commit()
    path = tmp_path / "n.db"
    disk = sqlite3.connect(path)
    conn.backup(disk)
    disk.close()
    conn.close()
    (f,) = from_security_events(path)
    assert f.limitations == ("1", "2")


def test_a_pathologically_deep_stored_limitations_cell_is_not_recorded():
    assert decode_limitations("[" * 100000 + "]" * 100000) is None


# ---------------------------------------------------------------------------
# A hostile value never loses the finding
# ---------------------------------------------------------------------------


class _RaisingStr:
    def __str__(self):
        raise RuntimeError("boom")


class _RaisingEq:
    def __eq__(self, other):
        raise RuntimeError("eq")

    __hash__ = None


class _RaisingHash:
    def __hash__(self):
        raise RuntimeError("hash")


class _BadLen(list):
    def __len__(self):
        raise RuntimeError("len")


class _BadIter(list):
    def __iter__(self):
        raise RuntimeError("iter")


class _OddStr(str):
    """A str subclass that lies: equal to everything, strips to an int."""

    def __eq__(self, other):
        return True

    __hash__ = str.__hash__

    def strip(self, *a):
        return 5

    def lower(self):
        raise RuntimeError("lower")


class _LyingStr(str):
    """Content "bogus", but it hands itself back from str()/strip()/lower() and claims to be
    "high" in a membership test, so a normaliser that trusts `in` would store "bogus"."""

    def __str__(self):
        return self

    def strip(self, *a):
        return self

    def lower(self):
        return self

    def __eq__(self, other):
        return other == "high" or other == "complete"

    __hash__ = str.__hash__


class _IntStripStr(str):
    """Truthy, str-typed, but strips to an int: a non-string would reach the array."""

    def strip(self, *a):
        return 5


class _StrReturnsIntStrip:
    def __str__(self):
        return _IntStripStr("x")


def _recursive():
    items: list = []
    items.append(items)
    return items


def _hostile_values():
    return {
        "raising __str__ item": [_RaisingStr()],
        "raising __str__ bare": _RaisingStr(),
        "raising __eq__ item": [_RaisingEq()],
        "raising __hash__ item": [_RaisingHash()],
        "raising __len__": _BadLen(["a"]),
        "raising __iter__": _BadIter(["a"]),
        "huge list": ["limit"] * 200_000,
        "huge string": "x" * 5_000_000,
        "recursive list": _recursive(),
        "odd str subclass": _OddStr("high"),
        "odd str subclass item": [_OddStr("a")],
        "lying str subclass": _LyingStr("bogus"),
        "item that strips to an int": [_StrReturnsIntStrip()],
    }


def _assert_row_is_well_formed(row) -> None:
    """Whatever came in, the stored cells are NULL or a valid value, never garbage."""
    assert row["confidence"] in (None, *CONFIDENCE_VALUES)
    assert row["coverage"] in (None, *COVERAGE_VALUES)
    if row["limitations"] is not None:
        stored = json.loads(row["limitations"])
        assert isinstance(stored, list) and all(isinstance(i, str) for i in stored)


@pytest.mark.parametrize("name", sorted(_hostile_values()))
def test_a_hostile_value_does_not_lose_the_finding_on_either_write_path(db: Path, name):
    from core.telemetry.emitters import emit_security_finding

    hostile = _hostile_values()[name]
    fid = record_finding(
        severity="high",
        title=name,
        confidence=hostile,
        coverage=hostile,
        limitations=hostile,
        db_path=db,
    )
    with patch("spool.writer.write_event"):
        result = emit_security_finding(
            severity="high",
            description=name,
            rule_id=f"rule-{name}",
            confidence=hostile,
            coverage=hostile,
            limitations=hostile,
            context={"project_id": "proj"},
            db_path=db,
        )
    assert result.emitted, result.error
    for finding_id in (fid, result.record_id):
        row = _row(db, finding_id)
        assert row is not None, f"{name}: the finding was lost"
        _assert_row_is_well_formed(row)


def test_a_failed_encoding_degrades_to_unknown_and_says_so_in_the_log(db: Path, caplog):
    with caplog.at_level("WARNING"):
        fid = record_finding(
            severity="high", title="t", coverage="partial", limitations=[_RaisingStr()], db_path=db
        )
    row = _row(db, fid)
    assert (row["confidence"], row["coverage"], row["limitations"]) == (None, None, None)
    assert any("could not be encoded" in r.getMessage() for r in caplog.records)
    assert not any("boom" in r.getMessage() for r in caplog.records), "the value is not echoed"
