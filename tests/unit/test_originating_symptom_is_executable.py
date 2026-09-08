"""A defect work order's symptom must be a check that can actually fail.

THE DEFECT, measured 2026-09-08. ``_check_originating_symptom`` iterated the symptom's
lines and ``continue``d past anything not starting with ``SQL-CHECK:``, so the ``TEST-CHECK``
form that CLAUDE.md and the ``--originating-symptom`` help text both advertise was silently
skipped and the gate returned None -- a pass. The advertised instrument did nothing.

What that cost: five defect work orders were registered that day and NOT ONE carried a valid
symptom, because a CODE defect usually has no authority data signature and the only working
instrument read the authority. Two (fc2916a4, 3e4ea639) carried SQL that could never return
a truthy value, making them permanently unclosable -- the unachievable-remedy shape. Three
(d33f9f95, 23327260, 376ec1dd) carried SQL that already passed, so the check discriminated
nothing.

The whole point of a symptom is that it FAILS while the defect is present and PASSES once
fixed. A symptom that can never pass blocks forever; one that already passes is ceremony.
Both are asserted here, because a fix that only added TEST-CHECK support would still accept
either.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.work_orders.close_gates import (
    _check_originating_symptom,
    symptom_has_executable_check,
)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "authority.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE widgets (id TEXT, broken INTEGER)")
    conn.execute("INSERT INTO widgets VALUES ('w1', 1)")
    conn.commit()
    conn.close()
    return path


# ── SQL-CHECK, the pre-existing instrument ──────────────────────────────────────


def test_a_satisfied_sql_check_passes(db):
    assert _check_originating_symptom("SQL-CHECK: SELECT COUNT(*) FROM widgets", db) is None


def test_an_unsatisfied_sql_check_blocks(db):
    reason = _check_originating_symptom(
        "SQL-CHECK: SELECT COUNT(*) FROM widgets WHERE id = 'absent'", db
    )
    assert reason is not None
    assert "still failing" in reason


def test_a_broken_sql_check_blocks_rather_than_passing(db):
    """An unrunnable check is not a satisfied one."""
    reason = _check_originating_symptom("SQL-CHECK: SELECT * FROM no_such_table", db)
    assert reason is not None
    assert "SQL-CHECK error" in reason


# ── TEST-CHECK, the advertised instrument that did nothing ──────────────────────


def test_a_test_check_is_evaluated_not_skipped(db):
    """The defect itself. A TEST-CHECK naming a node that cannot run must BLOCK.

    Before the fix this returned None -- the line was skipped as prose and the gate passed,
    so a code defect could carry a symptom that reproduced nothing and close anyway.
    """
    reason = _check_originating_symptom(
        "TEST-CHECK: tests/unit/test_does_not_exist.py::test_nope", db
    )
    assert reason is not None, (
        "a TEST-CHECK naming a nonexistent node passed, so the advertised instrument is"
        " still inert"
    )
    # It must have been RUN and failed -- not refused as an unknown kind. Asserting only
    # `"TEST-CHECK" in reason` could not tell those apart: dropping TEST from the supported
    # kinds makes the line unrecognised, and THAT message also contains "TEST-CHECK", so
    # this test passed under a mutation that removed the very support it exists to prove.
    assert "still failing" in reason, reason
    assert "unrecognised" not in reason, (
        "the line was refused as an unknown kind rather than evaluated, so TEST-CHECK"
        " support is not actually wired"
    )


def test_a_passing_test_check_passes(db):
    """The control: without it, every assertion above would hold against a symptom check
    that blocked unconditionally."""
    reason = _check_originating_symptom(
        "TEST-CHECK: tests/unit/test_originating_symptom_is_executable.py"
        "::test_a_satisfied_sql_check_passes",
        db,
    )
    assert reason is None, reason


# ── unrecognised kinds fail closed ──────────────────────────────────────────────


@pytest.mark.parametrize("kind", ["API", "FOO", "GREP"])
def test_an_unrecognised_check_kind_fails_closed(db, kind):
    """run_executable_checks already refuses an unknown *-CHECK token. This path passed it.

    API-CHECK is real elsewhere and simply not runnable here, which is the case most likely
    to be written by mistake -- so it must refuse rather than silently skip.
    """
    reason = _check_originating_symptom(f"{kind}-CHECK: whatever", db)
    assert reason is not None
    assert "unrecognised check kind" in reason


def test_a_malformed_token_is_read_as_prose(db):
    """Verified by calling it, because an earlier docstring claimed the opposite.

    `SQLCHECK:` and `SQL_CHECK:` do not match the line pattern at all, so they are prose and
    pass. Catching them would need the pattern to guess at intent; a symptom with no
    recognisable check is instead reported as carrying no executable evidence.
    """
    assert _check_originating_symptom("SQLCHECK: SELECT 1", db) is None
    assert _check_originating_symptom("SQL_CHECK: SELECT 1", db) is None
    assert not symptom_has_executable_check("SQLCHECK: SELECT 1")


# ── prose-only symptoms stay closable, and stay visible ─────────────────────────


def test_a_prose_only_symptom_passes(db):
    """A code defect may legitimately have no executable signature, and a fabricated check
    is worse than none -- two work orders were made permanently unclosable by one. So prose
    passes."""
    prose = (
        "NO SQL SYMPTOM: this is a code defect with no authority data signature, and a"
        " fabricated symptom is worse than none."
    )
    assert _check_originating_symptom(prose, db) is None


def test_a_prose_only_symptom_is_reported_as_carrying_no_check(db):
    """...but it must not be indistinguishable from a satisfied one.

    Otherwise "the symptom passed" means both "the root cause is fixed" and "nobody
    checked", which is the silence this whole registry exists to end.
    """
    assert symptom_has_executable_check("NO SQL SYMPTOM: no data signature exists") is False
    assert symptom_has_executable_check("SQL-CHECK: SELECT 1") is True
    assert symptom_has_executable_check("TEST-CHECK: tests/unit/test_x.py::test_y") is True
    assert symptom_has_executable_check("") is False


def test_a_mixed_symptom_evaluates_the_check_and_ignores_the_prose(db):
    symptom = (
        "Context: the widget ledger stopped counting.\n"
        "SQL-CHECK: SELECT COUNT(*) FROM widgets WHERE id = 'absent'\n"
        "Further notes that are not a check."
    )
    reason = _check_originating_symptom(symptom, db)
    assert reason is not None and "still failing" in reason


def test_the_first_failing_check_is_the_one_reported(db):
    """Several checks, and the reason names the one that failed rather than the last line."""
    symptom = (
        "SQL-CHECK: SELECT COUNT(*) FROM widgets\n"
        "SQL-CHECK: SELECT COUNT(*) FROM widgets WHERE id = 'absent'\n"
    )
    reason = _check_originating_symptom(symptom, db)
    assert reason is not None
    assert "absent" in reason
