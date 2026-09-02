"""A False from ``set_wo_artifact`` means ONE thing: the table is not there yet.

WO-ARTIFACT-LOCK-FALLBACK / fd981a32. Measured on the live authority 2026-09-02: of
August's review verdicts, 154 landed on disk and 23 in the authority. The cause was not
the disk fallback -- that is deliberate, for an authority whose artifact migration is
still unreleased. The cause was that ``set_wo_artifact`` returned False for EVERY
``sqlite3.OperationalError``, and all five artifact writes in verify run inside an
already-open ``with _connect(db_path)``. A second connection to that file got "database
is locked", returned False, and the caller read that as "the artifact table does not
exist" and wrote to disk. ``ds project state`` reads only the authority, so those
verdicts were invisible to every gate and surface that consults it.

These tests pin the properties that make that failure impossible to repeat silently:

  1. A LOCK RAISES. It is a fault, not a schema state, and a caller must be able to tell.
  2. A MISSING TABLE STILL RETURNS FALSE, because the transition fallback depends on it.
  3. A BORROWED CONNECTION WRITES THROUGH the caller's open transaction, and does not
     commit or close it -- which is what lets a write nested inside verify land at all
     without ending a transaction still in use around it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.work_orders.artifacts import get_wo_artifact, set_wo_artifact

REPO_ROOT = Path(__file__).resolve().parents[2]
_MIG_DIR = REPO_ROOT / "core" / "event_store" / "migrations"

_PASSED = '{"passed": true}'
_INSERT = (
    "INSERT INTO business_work_order_artifacts"
    " (work_order_id, kind, instance_key, content, created_at, updated_at)"
    " VALUES (?, ?, ?, ?, 'now', 'now')"
)


def _db_with_table(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript((_MIG_DIR / "144_wo_artifacts.sql").read_text(encoding="utf-8"))
    conn.executescript((_MIG_DIR / "152_wo_artifacts_instance_key.sql").read_text(encoding="utf-8"))
    conn.close()
    return db


def test_lock_raises_instead_of_reporting_a_missing_table(tmp_path):
    """The exact August failure: an exclusive writer elsewhere on the same file.

    Before the fix this returned False and the caller wrote to disk believing the
    artifact table did not exist. It must now raise -- "someone else holds the write
    lock" and "this schema has no artifact table" are different facts, and a caller
    that cannot tell them apart will mis-handle one of them.
    """
    db = _db_with_table(tmp_path)
    holder = sqlite3.connect(str(db), timeout=0.1)
    holder.execute("BEGIN EXCLUSIVE")
    holder.execute(_INSERT, ("other", "report", "", "x"))
    try:
        with pytest.raises(sqlite3.OperationalError) as exc:
            set_wo_artifact("wo-lock", "review_verdict", _PASSED, db_path=db)
        message = str(exc.value).lower()
        assert "lock" in message or "busy" in message
    finally:
        holder.rollback()
        holder.close()
    # Nothing was stored, so the raise is not hiding a partial write.
    assert get_wo_artifact("wo-lock", "review_verdict", db_path=db) is None


def test_missing_table_still_returns_false(tmp_path):
    """The transition fallback is load-bearing and must keep working.

    Migration 144 stays unreleased on a live authority until ``ds migrate activate``,
    and every caller's disk fallback keys off this False. Narrowing the lock case must
    not narrow this one away with it.
    """
    db = tmp_path / "studio.db"
    sqlite3.connect(str(db)).close()
    assert set_wo_artifact("wo-2", "review_verdict", "{}", db_path=db) is False


def test_an_unopenable_database_raises_rather_than_reading_as_a_stale_schema(tmp_path):
    """The last False that was not a schema state, and it is a fault now.

    ``sqlite3.connect`` failing returned False for any error, so a missing parent
    directory or a typo'd ``db_path`` read as "the artifact table does not exist yet" and
    routed every artifact to disk with a fallback reason saying "authority write no-op".
    An independent review measured it (WO b302834b task 1633f16e).

    This function also does NOT create the authority on the way past. A ``mkdir`` here
    would make a typo quietly produce a new empty database at the wrong location -- an
    artifact write is never what should bring an authority into being.
    """
    import pytest as _pytest

    with _pytest.raises(sqlite3.OperationalError):
        set_wo_artifact("wo-3", "review_verdict", "{}", db_path=tmp_path / "nope" / "studio.db")

    directory = tmp_path / "not-a-db"
    directory.mkdir()
    with _pytest.raises(sqlite3.OperationalError):
        set_wo_artifact("wo-3", "review_verdict", "{}", db_path=directory)

    # And nothing was created where the typo pointed.
    assert not (tmp_path / "nope").exists(), "a bad db_path created an authority"


def test_a_column_missing_for_a_reason_no_migration_explains_is_a_fault(tmp_path):
    """Only a column a MIGRATION adds counts as an older schema.

    Accepting any missing column meant a table whose shape is wrong for some other reason
    -- hand-edited, half-restored from a backup, a foreign table of the same name -- was
    indistinguishable from 144-without-152 and degraded forever. Measured by dropping
    ``updated_at``, which no migration adds (WO b302834b task 1633f16e).
    """
    import pytest as _pytest

    db = _db_with_table(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.execute("ALTER TABLE business_work_order_artifacts DROP COLUMN updated_at")
    conn.commit()
    conn.close()

    with _pytest.raises(sqlite3.OperationalError):
        set_wo_artifact("wo-9", "review_verdict", _PASSED, db_path=db)


def test_borrowed_connection_writes_inside_the_callers_transaction(tmp_path):
    """The fix itself: pass the connection you already hold.

    This is the shape of every nested call site in verify. With ``conn`` the write joins
    the open transaction, so there is no second writer to lose to -- and it is visible on
    that connection before any commit, which is what proves it joined rather than opening
    its own.
    """
    db = _db_with_table(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("BEGIN")
        conn.execute(_INSERT, ("wo-4", "context", "", "ctx"))
        # Without conn= this call would block on the write lock held above and raise.
        assert set_wo_artifact("wo-4", "review_verdict", _PASSED, db_path=db, conn=conn) is True
        row = conn.execute(
            "SELECT content FROM business_work_order_artifacts"
            " WHERE work_order_id='wo-4' AND kind='review_verdict'"
        ).fetchone()
        assert row is not None and row[0] == _PASSED
        conn.commit()
    finally:
        conn.close()
    assert get_wo_artifact("wo-4", "review_verdict", db_path=db) == _PASSED


def test_borrowed_connection_is_not_committed_by_the_write(tmp_path):
    """A borrowed transaction belongs to the caller.

    Verify holds one transaction across a whole run and commits once at the end.
    Committing from inside would end a transaction still in use around it -- turning a
    fix for a silent no-op into a silent partial commit, which is worse. The rollback
    below is the caller's decision and must actually undo the write.
    """
    db = _db_with_table(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("BEGIN")
        set_wo_artifact("wo-5", "review_verdict", _PASSED, db_path=db, conn=conn)
        conn.rollback()
    finally:
        conn.close()
    assert get_wo_artifact("wo-5", "review_verdict", db_path=db) is None


def test_borrowed_connection_is_left_open_for_the_caller(tmp_path):
    """``set_wo_artifact`` must not close a connection it did not open.

    Verify writes the ledger and then the verdict on the same connection. Closing it
    after the first would break the second with "cannot operate on a closed database" --
    a crash rather than a fallback, but caused by the same confusion over who owns the
    handle.
    """
    db = _db_with_table(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        set_wo_artifact("wo-6", "report", "first", instance_key="a", db_path=db, conn=conn)
        set_wo_artifact("wo-6", "review_verdict", _PASSED, db_path=db, conn=conn)
        conn.commit()
    finally:
        conn.close()
    assert get_wo_artifact("wo-6", "report", instance_key="a", db_path=db) == "first"
    assert get_wo_artifact("wo-6", "review_verdict", db_path=db) == _PASSED


def test_a_schema_older_than_the_write_degrades_rather_than_raising(tmp_path):
    """TWO STALE-SCHEMA SHAPES, ONE FACT, AND I BROKE THE SECOND ONE.

    Narrowing the OperationalError to "no such table" alone looked right and was wrong:
    migration 144 released with 152 unreleased is a real intermediate state on a live
    authority, and there the insert fails with "no such column: instance_key". Raising
    there turns a database that merely needs ``ds migrate activate`` into a crash
    mid-verify. Caught by this test, on the 144-only DDL rather than a hand-built table.
    """
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.executescript((_MIG_DIR / "144_wo_artifacts.sql").read_text(encoding="utf-8"))
    conn.close()
    assert set_wo_artifact("wo-7", "review_verdict", _PASSED, db_path=db) is False


def test_a_kind_the_schemas_check_rejects_degrades(tmp_path):
    """The IntegrityError twin, in its real form.

    Migration 152's CHECK does not list ``impact_affirmation``; 154 adds it. So a
    152-without-154 authority is exactly the documented no-op: the table is present and
    usable, and one kind is not accepted yet. Asserted against the real DDL, because a
    hand-built table would be testing my idea of the constraint rather than the
    constraint.
    """
    db = _db_with_table(tmp_path)  # 144 + 152, deliberately not 154
    assert set_wo_artifact("wo-8", "impact_affirmation", "affirmed", db_path=db) is False
    # The table is fine -- an accepted kind still writes, so the False above is about the
    # CHECK and not about an unusable store.
    assert set_wo_artifact("wo-8", "review_verdict", _PASSED, db_path=db) is True


def test_unknown_kind_is_a_programming_error_not_a_no_op(tmp_path):
    """A kind outside VALID_KINDS raises. It is a typo in the caller, not schema state."""
    db = _db_with_table(tmp_path)
    with pytest.raises(ValueError, match="unknown artifact kind"):
        set_wo_artifact("wo-8", "not_a_kind", "x", db_path=db)


def test_locked_db_write_lands_in_authority(tmp_path):
    """THE ACCEPTANCE CRITERION for task f282ad9c, stated as the outcome that matters.

    Not "the fallback is announced" -- "the write reaches the authority anyway". This is
    the whole shape of the August failure reproduced end to end: a caller holding an open
    write transaction on the authority (which is what verify does for the length of a
    run) writes an artifact through it. Before the fix that second connection lost the
    lock, returned False, and the verdict went to ``.planning`` where no gate reads.

    The assertion is made on a SEPARATE connection after commit, because a read on the
    writing connection would pass even if the row never left that transaction.
    """
    db = _db_with_table(tmp_path)
    holder = sqlite3.connect(str(db))
    try:
        holder.execute("BEGIN IMMEDIATE")  # the write lock verify's transaction holds
        holder.execute(_INSERT, ("wo-verify", "context", "", "packet"))
        assert (
            set_wo_artifact("wo-verify", "review_verdict", _PASSED, db_path=db, conn=holder) is True
        )
        holder.commit()
    finally:
        holder.close()
    assert get_wo_artifact("wo-verify", "review_verdict", db_path=db) == _PASSED


def test_a_disk_fallback_is_counted_rather_than_silent(tmp_path, monkeypatch):
    """The other half of task f282ad9c: a fallback that fires must be countable.

    The fallback is legitimate on an authority whose artifact migration is unreleased.
    What was not legitimate is that it fired 154 times leaving no trace, so nobody could
    answer "are verdicts reaching the authority?" without comparing a directory listing
    to a table by hand. ``observations_report`` groups these by rule, which is the count
    that question needs.

    THIS TEST ONLY PROVES THE CALL, and that is not the same as proving the count. It is
    deliberately paired with
    ``tests/integration/test_enforcement_tiers.py::test_an_artifact_disk_fallback_reaches_the_observations_report``,
    which runs the real spool -> sync_tick -> report path. Do not read this one as
    coverage of the landing: written alone it passed while the observation was going to
    the WRONG authority, because db_path was not being threaded.
    """
    from core.work_orders.artifacts import FALLBACK_RULE
    from core.work_orders.verify_persist import _persist_review_verdict

    seen: list[dict] = []
    monkeypatch.setattr(
        "runtime.lib.enforcement.record_observation",
        lambda **kw: seen.append(kw),
    )
    db = tmp_path / "studio.db"
    sqlite3.connect(str(db)).close()  # no artifact table -> the fallback fires
    planning = tmp_path / "planning"

    path = _persist_review_verdict(
        "wo-fell-back", {"passed": True}, planning_root=planning, db_path=db
    )
    assert path is not None and path.is_file(), "the verdict must still be stored somewhere"
    assert len(seen) == 1, f"the fallback was not counted: {seen}"
    assert seen[0]["rule"] == FALLBACK_RULE
    # The record must name the consequence and the recovery, not just the event.
    assert "invisible" in seen[0]["reason"]
    assert "backfill-artifacts" in seen[0]["reason"]


def test_counting_a_fallback_never_costs_the_stored_artifact(tmp_path, monkeypatch):
    """Telemetry is best-effort. An artifact that reached disk is stored, and failing the
    write because its counter failed would trade a countable degradation for a real loss."""
    from core.work_orders.verify_persist import _persist_review_verdict

    def _explode(**_kw):
        raise RuntimeError("telemetry is down")

    monkeypatch.setattr("runtime.lib.enforcement.record_observation", _explode)
    db = tmp_path / "studio.db"
    sqlite3.connect(str(db)).close()
    path = _persist_review_verdict(
        "wo-telemetry-down", {"passed": True}, planning_root=tmp_path / "planning", db_path=db
    )
    assert path is not None and path.is_file()


def test_a_borrowed_ledger_write_does_not_delete_its_disk_copy_before_commit(tmp_path):
    """A VERDICT FAILURE MUST NOT TAKE THE RESIDUAL-RISK LEDGER WITH IT.

    `verify_work_order` wraps its run in `with _connect(db_path) as conn`, which is
    sqlite3's TRANSACTION context manager -- it rolls back on any exception.
    `_persist_unverified_ledger` writes through that connection, returns None meaning
    "stored in the authority", and then unlinked any stale disk copy. The verdict write
    that follows it can now RAISE, so one raise rolled back the ledger while its disk copy
    was already gone: the ledger destroyed by an unrelated failure.

    An independent review found the coupling (WO `b302834b` task `6705ded4`). The disk
    copy now survives until the caller commits, and it is shadowed by the authority on
    read, so keeping it costs nothing.
    """
    from core.work_orders.verify_persist import (
        _UNVERIFIED_LEDGER_FILENAME,
        _persist_unverified_ledger,
    )

    db = _db_with_table(tmp_path)
    planning = tmp_path / "planning"
    ledger = planning / "work-orders" / "wo-led" / _UNVERIFIED_LEDGER_FILENAME
    ledger.parent.mkdir(parents=True)
    ledger.write_text('{"stale": true}', encoding="utf-8")

    conn = sqlite3.connect(str(db))
    try:
        conn.execute("BEGIN")
        result = _persist_unverified_ledger(
            "wo-led", [{"scenario": "x"}], planning_root=planning, db_path=db, conn=conn
        )
        assert result is None, "the authority write should have landed"
        assert ledger.is_file(), (
            "the disk copy was removed while the write was still uncommitted; a later "
            "raise would roll back the row and leave no ledger anywhere"
        )
        conn.rollback()
    finally:
        conn.close()

    # After the rollback the authority has nothing -- and the ledger still exists.
    assert get_wo_artifact("wo-led", "report", instance_key="unverified_risks", db_path=db) is None
    assert ledger.is_file(), "the rollback lost the ledger from both stores"


def test_the_backfill_reports_a_partial_recovery_instead_of_aborting(tmp_path, monkeypatch):
    """The command built for a degraded authority was its least protected caller.

    `backfill_wo_artifacts` looped ~171 `set_wo_artifact` calls with no `try`, so once
    that function learned to RAISE on a lock, any busy moment aborted the loop mid-way and
    discarded the running count -- the operator running the repair learned neither how far
    it got nor why (WO `b302834b` task `f9b6e787`).

    "170 recovered, 1 locked" is a better outcome than nothing recovered, and it has to be
    reported as partial or it is the same silence this command exists to end.
    """
    from core.work_orders import artifacts as artifacts_module

    db = _db_with_table(tmp_path)
    planning = tmp_path / "planning"
    for name in ("wo-a", "wo-b", "wo-c"):
        directory = planning / "work-orders" / name
        directory.mkdir(parents=True)
        (directory / "review-verdict.json").write_text('{"passed": true}', encoding="utf-8")

    real = artifacts_module.set_wo_artifact
    calls = {"n": 0}

    def _flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise sqlite3.OperationalError("database is locked")
        return real(*args, **kwargs)

    monkeypatch.setattr(artifacts_module, "set_wo_artifact", _flaky)
    written, failures = artifacts_module.backfill_wo_artifacts(planning, db_path=db)

    assert written == 2, f"the loop stopped early instead of continuing: {written}"
    assert len(failures) == 1, failures
    # The failure names the artifact and the reason, so the re-run has intent.
    assert "review_verdict" in failures[0] or "wo-" in failures[0], failures[0]
    assert "locked" in failures[0].lower(), failures[0]
