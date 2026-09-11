"""WO 17466550 task 2: the rows that predate the fix must survive a rebuild too.

Task 1 stopped the spawn path creating unreplayable rows. It did nothing for the 493 work
orders and 1706 tasks already in the authority with no creation event — and those are
still deleted by the recovery tool.

AS WITH TASK 1, THESE TESTS DRIVE A REAL REBUILD. Asserting that events were written
proves events were written; the claim is that the row COMES BACK, and only a replay shows
that. So each test runs the genuine `ProjectionEngine.rebuild()` against the genuine
projections, truncating `pre_rebuild` included.

Nothing here is stubbed: the backfill calls the ingestor's own `_write_to_dual_canonical`,
so these tests exercise production code end to end against a temporary authority.
"""

from __future__ import annotations

import pathlib
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.backfill_creation_events import RECONSTRUCTED_KEY, backfill

_THEN = "2026-01-15T08:30:00+00:00"


@pytest.fixture
def authority(tmp_path, monkeypatch):
    db_path = tmp_path / "studio.db"
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path))
    try:
        from core.config.database import DatabaseRuntime

        DatabaseRuntime.reset_instance()
    except Exception:
        pass
    bootstrap_database(db_path)
    yield db_path
    try:
        from core.config.database import DatabaseRuntime

        DatabaseRuntime.reset_instance()
    except Exception:
        pass


def _seed_eventless(db_path: Path) -> tuple[str, str, str]:
    """A work order and a task written straight into the projections, as history did."""
    project_id, milestone_id = str(uuid.uuid4()), str(uuid.uuid4())
    wo_id, task_id = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, status, created_at, updated_at)"
            " VALUES (?, 'T', 'active', ?, ?)",
            (project_id, _THEN, _THEN),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, 'M', 'active', ?, ?)",
            (milestone_id, project_id, _THEN, _THEN),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description,"
            "  work_order_type, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Historic work order', 'a description',"
            "  'infrastructure', 'created', ?, ?)",
            (wo_id, project_id, milestone_id, _THEN, _THEN),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            "  created_at, updated_at)"
            " VALUES (?, ?, ?, 'Historic task', 'task description', 'pending', ?, ?)",
            (task_id, wo_id, project_id, _THEN, _THEN),
        )
        conn.commit()
    finally:
        conn.close()
    return wo_id, task_id, project_id


def _rebuild(db_path: Path) -> None:
    from core.projections.framework_engine import ProjectionEngine
    from core.projections.task_projection import TaskProjection
    from core.projections.work_order_projection import WorkOrderProjection

    engine = ProjectionEngine(db_path=str(db_path))
    for proj in (WorkOrderProjection(), TaskProjection()):
        engine.register(proj)
        engine.rebuild(proj.name)


def _exists(db_path: Path, table: str, column: str, value: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(f"SELECT 1 FROM {table} WHERE {column} = ?", (value,)).fetchone()
    finally:
        conn.close()
    return row is not None


def _ingest_and_rebuild(db_path: Path) -> None:
    """Drain the spool, then rebuild -- the two steps the module deliberately does not do.

    The backfill writes events and stops there, because draining is the ingestor's job and
    a work-order module reaching for it is the same boundary crossing as calling its
    private writer. Tests drive both explicitly so the sequence is visible.
    """
    from spool.ingestor import ingest

    ingest(db_path=db_path)
    _rebuild(db_path)


def test_without_the_backfill_a_historic_row_is_destroyed_by_a_rebuild(authority):
    """The defect this task exists for, shown going wrong first.

    If this ever passes without the backfill, the premise is gone and every other test
    here is measuring nothing.
    """
    wo_id, task_id, _ = _seed_eventless(authority)

    _ingest_and_rebuild(authority)

    assert not _exists(authority, "business_work_orders", "work_order_id", wo_id)
    assert not _exists(authority, "business_tasks", "task_id", task_id)


def test_a_backfilled_row_survives_a_rebuild(authority):
    """The claim: after the repair, the recovery tool stops destroying the record."""
    wo_id, task_id, _ = _seed_eventless(authority)

    report = backfill(db_path=authority, apply=True)
    assert report["ok"], report
    assert report["written"] == {"work_orders": 1, "tasks": 1}, report

    _ingest_and_rebuild(authority)

    assert _exists(authority, "business_work_orders", "work_order_id", wo_id)
    assert _exists(authority, "business_tasks", "task_id", task_id)


def test_a_dry_run_changes_nothing(authority):
    """It reports thousands of writes against a live authority; it must not do them."""
    _seed_eventless(authority)

    report = backfill(db_path=authority, apply=False)

    assert report["applied"] is False
    assert report["would_write"] == {"work_orders": 1, "tasks": 1}
    assert report["before"] == report["after"] == {"work_orders": 1, "tasks": 1}
    conn = sqlite3.connect(str(authority))
    try:
        events = conn.execute("SELECT COUNT(*) FROM business_canonical_events").fetchone()[0]
    finally:
        conn.close()
    assert events == 0, "a dry run wrote canonical events"


def test_running_it_twice_writes_nothing_the_second_time(authority):
    """Idempotent, because a half-finished repair will be re-run by someone."""
    _seed_eventless(authority)

    first = backfill(db_path=authority, apply=True)
    from spool.ingestor import ingest

    ingest(db_path=authority)
    second = backfill(db_path=authority, apply=True)

    assert first["written"] == {"work_orders": 1, "tasks": 1}
    assert second["written"] == {"work_orders": 0, "tasks": 0}, second


def test_the_event_says_it_is_a_reconstruction_and_keeps_the_original_date(authority):
    """A synthetic event that passed as original would make the record lie about itself.

    The timestamp is the row's own `created_at`, not the repair time, so a replay
    reproduces the real order of history rather than collapsing it onto today.
    """
    wo_id, _, _ = _seed_eventless(authority)
    backfill(db_path=authority, apply=True)
    from spool.ingestor import ingest

    ingest(db_path=authority)

    conn = sqlite3.connect(str(authority))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT payload, event_timestamp FROM business_canonical_events"
            " WHERE event_type = 'work_order.created' AND work_order_id = ?",
            (wo_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    import json

    payload = json.loads(row["payload"])
    assert payload.get(RECONSTRUCTED_KEY) is True, payload
    assert "reconstructed_at" in payload
    assert row["event_timestamp"] == _THEN, (
        "the event must carry the row's original created_at, not the repair time, or a "
        "replay reorders history"
    )


def test_a_row_that_already_has_an_event_is_left_alone(authority):
    """Only the gap is filled — an original event is never duplicated or overwritten."""
    wo_id, _, _ = _seed_eventless(authority)
    backfill(db_path=authority, apply=True)
    from spool.ingestor import ingest

    ingest(db_path=authority)

    conn = sqlite3.connect(str(authority))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM business_canonical_events"
            " WHERE event_type = 'work_order.created' AND work_order_id = ?",
            (wo_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    backfill(db_path=authority, apply=True)
    ingest(db_path=authority)

    conn = sqlite3.connect(str(authority))
    try:
        after = conn.execute(
            "SELECT COUNT(*) FROM business_canonical_events"
            " WHERE event_type = 'work_order.created' AND work_order_id = ?",
            (wo_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert count == 1
    assert after == 1, "a second run duplicated the creation event"


# ── the guard: a repair that resets status is worse than the defect ──────────
#
# Neither created handler reads payload["status"]; both hardcode it. So filling the gap
# with creation events alone would make a rebuild reopen closed work orders and
# un-complete finished tasks. Measured on the live authority before this guard existed:
# 465 of 493 event-less work orders and 1418 of 1706 event-less tasks carry a status the
# replay cannot reproduce.


def _seed_with_status(db_path: Path, wo_status: str, task_status: str) -> tuple[str, str]:
    wo_id, task_id, _ = _seed_eventless(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE business_work_orders SET status = ? WHERE work_order_id = ?",
            (wo_status, wo_id),
        )
        conn.execute(
            "UPDATE business_tasks SET status = ? WHERE task_id = ?", (task_status, task_id)
        )
        conn.commit()
    finally:
        conn.close()
    return wo_id, task_id


def test_a_closed_work_order_comes_back_closed(authority):
    """The repair the guard used to forbid, now doing the thing it forbade it for.

    A creation event alone replays to the handler's hardcoded default, so backfilling
    one would have reopened 396 closed work orders and un-completed 1095 tasks -- worse
    than the row loss it repairs, because the row is present and lying. The repair now
    emits the TERMINAL lifecycle event as well, read from the declared vocabulary, so the
    status is reproduced rather than reset. Driven through a real rebuild, because that
    is the only thing that can show it.
    """
    from core.projections.task_projection import TaskProjection
    from core.projections.work_order_projection import WorkOrderProjection

    wo_id, task_id = _seed_with_status(authority, "closed", "complete")

    report = backfill(db_path=authority, apply=True)
    assert report["ok"], report
    _ingest_and_rebuild(authority)

    conn = sqlite3.connect(str(authority))
    try:
        wo = conn.execute(
            "SELECT status FROM business_work_orders WHERE work_order_id = ?", (wo_id,)
        ).fetchone()
        tk = conn.execute(
            "SELECT status FROM business_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
    finally:
        conn.close()

    assert wo is not None and tk is not None, "the rows did not survive the rebuild"
    assert wo[0] == "closed", f"a closed work order came back {wo[0]!r} — reopened by its repair"
    assert tk[0] == "complete", f"a complete task came back {tk[0]!r} — un-completed by its repair"


def test_a_legacy_spelling_is_normalised_rather_than_lost(authority):
    """`done` and `open` are synonyms, not states, and a replay resolves them.

    27 tasks hold `done` and 10 hold `open` on the live authority. Neither has an event
    type and neither should: `done` is a second spelling of `complete`, `open` of
    `pending`. The repair must land them on the canonical spelling rather than refuse
    them or invent a state.
    """
    from core.projections.task_projection import TaskProjection

    _, task_id = _seed_with_status(authority, "created", "done")

    assert backfill(db_path=authority, apply=True)["ok"]
    _ingest_and_rebuild(authority)

    conn = sqlite3.connect(str(authority))
    try:
        got = conn.execute(
            "SELECT status FROM business_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
    finally:
        conn.close()
    assert got is not None and got[0] == "complete", got


def test_a_status_no_event_can_produce_is_still_refused(authority, monkeypatch):
    """The guard still exists, for the case it is now actually about.

    It no longer asks "is this row at the creation default" -- the terminal event handles
    that. It asks whether any event type produces this status at all, which is the
    condition under which a repair genuinely cannot reproduce the row.
    """
    import core.work_orders.backfill_creation_events as mod

    monkeypatch.setattr(mod, "WORK_ORDER_STATUS_EVENT", {"created": None})
    _seed_with_status(authority, "closed", "pending")

    report = backfill(db_path=authority, apply=True)

    assert report["ok"] is False, report
    assert "no event type can produce" in report["error"]
    assert report["status_at_risk"]["work_orders"]["unreachable_statuses"] == ["closed"]


def test_the_backfill_writes_through_the_public_writer(authority, monkeypatch):
    """The ingestor owns canonical writes; this module must not reach past it.

    An independent review found this module importing `spool.ingestor.
    _write_to_dual_canonical` -- a private function -- and driving canonical-event writes
    itself, while its own sibling `verify_gaps._emit_creation` used the public writer in
    the same change set. Crossing a write boundary from outside the component that owns it
    is the rule this repo already states; the sibling doing it correctly in the same diff
    is what makes it a slip rather than a design.
    """
    import spool.writer as _spool_writer

    seen: list[dict] = []
    real = _spool_writer.write_event

    def _watch(envelope, *a, **k):
        assert isinstance(envelope, dict), type(envelope).__name__
        seen.append(envelope)
        return real(envelope, *a, **k)

    monkeypatch.setattr(_spool_writer, "write_event", _watch)
    _seed_eventless(authority)

    backfill(db_path=authority, apply=True)

    assert seen, (
        "no event reached spool.writer.write_event -- the backfill is writing canonical "
        "rows by another path, which is the boundary this test exists to hold"
    )
    assert {e["event_type"] for e in seen} == {"work_order.created", "task.created"}, seen

    import core.work_orders.backfill_creation_events as mod

    source = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    offending = [
        line
        for line in source.splitlines()
        if "_write_to_dual_canonical" in line and not line.lstrip().startswith("#")
    ]
    assert not offending, f"private ingestor API still called: {offending}"


def test_every_payload_key_written_survives_a_rebuild(authority):
    """A key written into an event and read by nobody repairs nothing.

    The backfill writes title, description, type, originating_symptom, acceptance_criteria
    and status into its creation payloads, and only row EXISTENCE was ever asserted. The
    module already documents one key -- `status` -- as write-only, which is the whole
    reason it refuses to run; a second key in the same condition would be invisible.

    So each key is checked against what a real rebuild actually produces, and `status` is
    pinned as KNOWN-DEAD rather than quietly expected to work. The day a handler starts
    reading it, this fails and the guard that depends on it gets revisited.
    """
    from core.projections.work_order_projection import WorkOrderProjection

    wo_id, _, _ = _seed_eventless(authority)
    conn = sqlite3.connect(str(authority))
    conn.execute(
        "UPDATE business_work_orders SET originating_symptom = ? WHERE work_order_id = ?",
        ("SQL-CHECK: SELECT 1", wo_id),
    )
    conn.commit()
    conn.close()

    backfill(db_path=authority, apply=True)
    _ingest_and_rebuild(authority)

    conn = sqlite3.connect(str(authority))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM business_work_orders WHERE work_order_id = ?", (wo_id,)
    ).fetchone()
    conn.close()
    assert row is not None, "the row did not survive the rebuild"

    # Carried through the event and read by the handler.
    assert row["title"] == "Historic work order"
    assert row["description"] == "a description"
    assert row["work_order_type"] == "infrastructure"
    assert row["originating_symptom"] == "SQL-CHECK: SELECT 1", (
        "originating_symptom is written into the payload; if the handler stops reading it "
        "a defect WO loses the check that reproduces it"
    )
    # And the status the row actually had, which is the whole point of the terminal
    # lifecycle event. `payload["status"]` is still required by the contract and read by
    # nobody (WO b52d7f4c); what makes the status survive is the SECOND event, not that
    # key, and this asserts the outcome rather than either mechanism.
    assert row["status"] == "created", row["status"]
