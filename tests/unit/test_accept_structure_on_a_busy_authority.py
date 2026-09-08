"""`--accept-structure` on a BUSY authority must refuse in the shape its callers handle.

THE GAP THIS FILLS, named by WO b302834b's third independent review. ``record_exception``
converts every storage failure to ``ValueError`` because that is what both callers
(``start_main.start_work_order`` and the close CLI) already ``except``. The conversion was
added when ``set_wo_artifact`` learned to RAISE on a lock instead of silently returning
``False`` -- before which a busy authority turned ``--accept-structure`` into an unhandled
``sqlite3.OperationalError`` traceback at both sites.

That fix shipped untested. The acceptance criterion pointed at a test that DROPs the
artifact table, which exercises the table-absent branch -- the one that already returned
``False`` before the change -- so the exact regression the task was written for was
unguarded. The review's own rule is that a test which cannot fail for its stated reason is
a defect, and it applied that rule to the change set that wrote it.

WHY A REAL LOCK RATHER THAN A PATCHED RAISE. Patching ``set_wo_artifact`` to raise would
assert that ``record_exception`` catches ``sqlite3.Error``, which is visible in the source
already. It would NOT show that a busy authority actually produces that error through this
path -- and "a second connection to a file with an open transaction blocks on the write
lock" is precisely the behaviour that was mis-diagnosed as a missing table for a month. So
the lock here is genuine: another connection holds ``BEGIN EXCLUSIVE`` while the call runs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.structural_invariants import record_exception

_REASON = "Correctly sized: this work order owns a single indivisible migration."


@pytest.fixture
def authority(tmp_path: Path) -> Path:
    """A real authority, built by the real migration chain."""
    db_path = tmp_path / "studio.db"
    bootstrap_database(db_path)
    return db_path


def _hold_write_lock(db_path: Path) -> sqlite3.Connection:
    """Another connection holding an exclusive transaction, as a busy authority does."""
    blocker = sqlite3.connect(str(db_path), timeout=0.1)
    blocker.execute("BEGIN EXCLUSIVE")
    return blocker


def test_a_busy_authority_raises_valueerror_not_a_sqlite_traceback(authority):
    """The regression the task was written for, driven end to end.

    Before the conversion this raised ``sqlite3.OperationalError`` straight through
    ``record_exception``, and both callers catch only ``ValueError`` -- so the operator got
    a traceback from ``--accept-structure`` on a busy authority.
    """
    blocker = _hold_write_lock(authority)
    try:
        with pytest.raises(ValueError) as caught:
            record_exception("wo-busy-0001", _REASON, db_path=authority)
    finally:
        blocker.rollback()
        blocker.close()

    # Not an OperationalError that merely inherits from something a caller might catch:
    # the type must be exactly what the callers handle.
    assert type(caught.value) is ValueError
    assert not isinstance(caught.value, sqlite3.Error)


def test_the_refusal_names_the_cause_and_what_to_do(authority):
    """A refusal the operator can act on, not just a type.

    The whole reason the silent ``False`` was wrong is that ``--accept-structure`` printed
    success and stored nothing, so the next close refused with the identical message. A
    raise that says nothing useful repeats that failure in a new costume.
    """
    blocker = _hold_write_lock(authority)
    try:
        with pytest.raises(ValueError) as caught:
            record_exception("wo-busy-0002", _REASON, db_path=authority)
    finally:
        blocker.rollback()
        blocker.close()

    message = str(caught.value)
    assert "could not be recorded" in message
    assert "OperationalError" in message, "the underlying cause must survive the conversion"
    assert "re-run" in message, "the operator needs the remedy, not just the diagnosis"


def test_the_underlying_error_is_chained_not_discarded(authority):
    """`raise ... from exc`, so the original is still reachable for a report."""
    blocker = _hold_write_lock(authority)
    try:
        with pytest.raises(ValueError) as caught:
            record_exception("wo-busy-0003", _REASON, db_path=authority)
    finally:
        blocker.rollback()
        blocker.close()

    assert isinstance(caught.value.__cause__, sqlite3.Error)


def test_nothing_is_recorded_when_the_write_could_not_land(authority):
    """The refusal has to be truthful: no artifact row from a failed write.

    A raise that left a partial row would be worse than the silent False, because the close
    gate would then pass on a record nobody meant to make.
    """
    blocker = _hold_write_lock(authority)
    try:
        with pytest.raises(ValueError):
            record_exception("wo-busy-0004", _REASON, db_path=authority)
    finally:
        blocker.rollback()
        blocker.close()

    conn = sqlite3.connect(str(authority))
    try:
        rows = conn.execute(
            "SELECT COUNT(*) FROM business_work_order_artifacts WHERE work_order_id = ?",
            ("wo-busy-0004",),
        ).fetchone()[0]
    finally:
        conn.close()
    assert rows == 0


def test_the_same_call_succeeds_once_the_authority_is_writable(authority):
    """The control. Without this, every assertion above would also pass against a
    ``record_exception`` that raised unconditionally -- which is the test-that-cannot-pass
    counterpart of the test-that-cannot-fail this file exists to correct."""
    assert record_exception("wo-busy-0005", _REASON, db_path=authority) is True

    conn = sqlite3.connect(str(authority))
    try:
        stored = conn.execute(
            "SELECT content FROM business_work_order_artifacts WHERE work_order_id = ?",
            ("wo-busy-0005",),
        ).fetchone()
    finally:
        conn.close()
    assert stored is not None and _REASON in stored[0]


def test_a_thin_reason_is_still_refused_before_any_write(authority):
    """The pre-existing contract, pinned alongside: an empty reason never reaches storage."""
    with pytest.raises(ValueError, match="reason"):
        record_exception("wo-busy-0006", "n/a", db_path=authority)


# --------------------------------------------------------------------------------------
# BOTH CALLERS. `start_work_order` and the close CLI each catch ValueError, and they were
# hardened in one commit -- but fixed-in-one-branch-not-its-sibling is the shape this repo
# has found five times, so each is driven separately rather than trusted by symmetry.
# --------------------------------------------------------------------------------------

_PROJECT = "11111111-1111-1111-1111-111111111111"
_MILESTONE = "22222222-2222-2222-2222-222222222222"
_WO = "33333333-3333-3333-3333-333333333333"
_NOW = "2026-09-07T00:00:00+00:00"


@pytest.fixture
def seeded(tmp_path: Path) -> Path:
    """A real authority holding one project, milestone and work order."""
    db_path = tmp_path / "studio.db"
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status,"
            " created_at, updated_at) VALUES (?, 'Busy', '', 'active', ?, ?)",
            (_PROJECT, _NOW, _NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones (milestone_id, project_id, title, description,"
            " status, order_index, created_at, updated_at)"
            " VALUES (?, ?, 'M1', '', 'pending', 0, ?, ?)",
            (_MILESTONE, _PROJECT, _NOW, _NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id,"
            " title, description, status, work_order_type, sequence_order, created_at,"
            " updated_at) VALUES (?, ?, ?, 'Solo', '', 'created', 'documentation', 10, ?, ?)",
            (_WO, _PROJECT, _MILESTONE, _NOW, _NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_the_start_caller_reports_the_refusal_instead_of_raising(seeded, monkeypatch):
    """`start_work_order` must return its own failure shape, not propagate."""
    from core.work_orders import start_main, start_shared

    # start_main imports _require_db lazily from start_shared, with a comment saying that
    # is deliberate so this patch target keeps working. Patch the definition, not the
    # importer.
    monkeypatch.setattr(start_shared, "_require_db", lambda *a, **k: seeded)

    blocker = _hold_write_lock(seeded)
    try:
        result = start_main.start_work_order(
            work_order_id=_WO,
            source_root=Path.cwd(),
            accept_structure=_REASON,
        )
    finally:
        blocker.rollback()
        blocker.close()

    assert result["ok"] is False, "a lock must not read as a successful start"
    assert "could not be recorded" in result["error"]
    assert result["work_order_id"] == _WO


def test_the_close_caller_reports_the_refusal_instead_of_raising(seeded, monkeypatch, capsys):
    """The close CLI must exit 1 with JSON, not a traceback.

    This is the site that mattered: `--accept-structure` is passed to a CLOSE far more often
    than to a start, so the likely caller was the one that crashed.
    """
    from interfaces.cli.commands import work_order_lifecycle

    class _Paths:
        sqlite_path = seeded

    monkeypatch.setattr(
        "core.installed_runtime.resolve_installed_runtime_paths", lambda **k: _Paths()
    )

    blocker = _hold_write_lock(seeded)
    try:
        exit_code = work_order_lifecycle._work_order_close(
            work_order_id=_WO,
            force=False,
            source_root=Path.cwd(),
            dream_studio_home=None,
            accept_structure=_REASON,
        )
    finally:
        blocker.rollback()
        blocker.close()

    assert exit_code == 1
    payload = capsys.readouterr().out
    assert '"ok": false' in payload
    assert "could not be recorded" in payload
