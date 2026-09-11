"""WO 20796691: every status the authority holds must be reachable by replay.

MEASURED ON THE LIVE AUTHORITY 2026-09-11, which is why this work order exists. Listing
every status each projection could WRITE and diffing it against every status actually
PRESENT found 459 rows the substrate could not express:

    business_work_orders.cancelled   53   no event type produced it
    business_tasks.cancelled        369   no event type produced it
    business_tasks.done              27   no task.completed event on any of them
    business_tasks.open              10   only 1 of 10 had a task.created event

THE CREATION-EVENT OVERLAP IS THE NUMBER THAT SEPARATES URGENT FROM LATENT, and the first
pass of this work order did not compute it -- an independent review asked for it by status
rather than in aggregate. Measured on the live authority 2026-09-11:

    status                          rows   has creation event   missing it
    business_work_orders.cancelled    53                    8           45
    business_work_orders.deleted      16                    1           15
    business_tasks.cancelled         369                   95          274
    business_tasks.done               27                    1           26
    business_tasks.open               10                    1            9

The two columns fail DIFFERENTLY, which is why the split matters. The 369 rows MISSING a
creation event are deleted outright by a rebuild -- destructive, and loud. The 106 that
HAVE one survive and come back WRONG: replay reaches whatever the last handled event set,
and no handled event set `cancelled`, so work someone deliberately abandoned returns as
open. That half is the urgent one precisely because it looks like success -- a rebuild
reports rows restored, and 95 abandoned tasks are back on the board.

THE PRODUCIBLE SET IS DERIVED BY DRIVING A REBUILD, NOT BY READING THE HANDLERS. A test
that greps handler source for status literals is a transcription of someone else's code
and goes stale the moment a handler changes shape. These tests emit one event of each
consumed type, run the genuine `ProjectionEngine.rebuild()` — truncating `pre_rebuild`
included — and read the status back, so the answer is the projection's actual behaviour.

WHAT WAS DECIDED, AND ON WHAT EVIDENCE. `cancelled` is a real state: it is declared in
`TASK_ABANDONED_STATUSES`, and `verify_gaps.py`'s gap drain writes it deliberately. It
got event types. `done` and `open` are drift — `done` is already treated as a synonym of
`complete` by `TASK_DONE_STATUSES`, and `open` is not in the declared vocabulary at all
while `is_open()` treats an unknown status as outstanding, which is `pending`. They get
no new event types; replaying their real lifecycle events normalises them.
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.projections.task_projection import TaskProjection
from core.projections.work_order_projection import WorkOrderProjection
from core.work_orders.task_status import (
    CANONICAL_TASK_STATUSES,
    CANONICAL_WORK_ORDER_STATUSES,
    TASK_ABANDONED_STATUSES,
    TASK_STATUS_SYNONYMS,
)

_NOW = "2026-09-11T00:00:00+00:00"

#: Located from the production module this test reads, not from this file, so moving the
#: test does not silently repoint the paths it asserts about.
_REPO_ROOT = Path(sys.modules[WorkOrderProjection.__module__].__file__).resolve().parents[2]

#: Read from production, not redeclared here. A vocabulary a writer cannot import is a
#: note, not a closed set -- this constant lived only in this test file until WO 20796691
#: moved it beside TASK_STATUSES in the module whose docstring calls itself the one
#: definition.
_WORK_ORDER_STATUSES = frozenset(CANONICAL_WORK_ORDER_STATUSES)


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


def _seed_parents(db_path: Path) -> tuple[str, str]:
    project_id, milestone_id = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, status, created_at, updated_at)"
            " VALUES (?, 'T', 'active', ?, ?)",
            (project_id, _NOW, _NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, 'M', 'active', ?, ?)",
            (milestone_id, project_id, _NOW, _NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id, milestone_id


def _emit(db_path: Path, event_type: str, trace: dict, payload: dict | None = None) -> None:
    from canonical.events.envelope import CanonicalEventEnvelope
    from spool.ingestor import _write_to_dual_canonical

    _write_to_dual_canonical(
        CanonicalEventEnvelope(
            event_type=event_type,
            session_id=None,
            payload=payload or {},
            timestamp=datetime.now(UTC).isoformat(),
            severity="info",
            trace={"domain": "sdlc", "attribution_status": "fully_attributed", **trace},
        ).to_dict(),
        db_path,
    )


def _rebuild(db_path: Path) -> None:
    from core.projections.framework_engine import ProjectionEngine

    engine = ProjectionEngine(db_path=str(db_path))
    for proj in (WorkOrderProjection(), TaskProjection()):
        engine.register(proj)
        engine.rebuild(proj.name)


def _status(db_path: Path, table: str, column: str, value: str) -> str | None:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(f"SELECT status FROM {table} WHERE {column} = ?", (value,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _producible_work_order_statuses(db_path: Path, project_id: str, milestone_id: str) -> set:
    """Drive one work order per consumed event type and read back what replay produces."""
    produced: set[str] = set()
    for event_type in WorkOrderProjection.consumed_event_types:
        wo_id = str(uuid.uuid4())
        trace = {
            "project_id": project_id,
            "milestone_id": milestone_id,
            "work_order_id": wo_id,
        }
        _emit(
            db_path,
            "work_order.created",
            trace,
            {
                "title": "t",
                "status": "created",
                "type": "infrastructure",
                "work_order_id": wo_id,
                "project_id": project_id,
            },
        )
        if event_type != "work_order.created":
            _emit(
                db_path,
                event_type,
                trace,
                {"work_order_id": wo_id, "project_id": project_id, "title": "t", "forced": False},
            )
        _rebuild(db_path)
        status = _status(db_path, "business_work_orders", "work_order_id", wo_id)
        if status:
            produced.add(status)
    return produced


def _producible_task_statuses(db_path: Path, project_id: str) -> set:
    produced: set[str] = set()
    for event_type in TaskProjection.consumed_event_types:
        wo_id, task_id = str(uuid.uuid4()), str(uuid.uuid4())
        # The parent MUST exist: business_tasks.work_order_id is NOT NULL REFERENCES
        # business_work_orders. Without this every task insert failed the foreign key,
        # every status came back None, and the task half of this test measured nothing
        # while still going red for an unrelated reason.
        _emit(
            db_path,
            "work_order.created",
            {"project_id": project_id, "work_order_id": wo_id},
            {
                "title": "parent",
                "status": "created",
                "type": "infrastructure",
                "work_order_id": wo_id,
                "project_id": project_id,
            },
        )
        trace = {"project_id": project_id, "work_order_id": wo_id, "task_id": task_id}
        _emit(
            db_path, "task.created", trace, {"title": "t", "description": "d", "status": "created"}
        )
        if event_type != "task.created":
            _emit(db_path, event_type, trace, {})
        _rebuild(db_path)
        status = _status(db_path, "business_tasks", "task_id", task_id)
        if status:
            produced.add(status)
    return produced


def test_every_live_status_is_producible_by_some_consumed_event(authority):
    """The defect, stated as a rule: the substrate must be able to express the data.

    Derived by rebuilding rather than by reading the handlers, so it measures behaviour
    and cannot go stale against a refactor.
    """
    project_id, milestone_id = _seed_parents(authority)

    wo_produced = _producible_work_order_statuses(authority, project_id, milestone_id)
    task_produced = _producible_task_statuses(authority, project_id)

    missing_wo = _WORK_ORDER_STATUSES - wo_produced
    assert not missing_wo, (
        f"no consumed event produces work order status(es) {sorted(missing_wo)} — "
        "a row holding one cannot be reconstructed by any replay"
    )

    expected_tasks = set(CANONICAL_TASK_STATUSES)
    missing_tasks = expected_tasks - task_produced
    assert not missing_tasks, (
        f"no consumed event produces task status(es) {sorted(missing_tasks)}; "
        f"replay can only produce {sorted(task_produced)}"
    )


def test_the_decision_is_recorded_and_the_vocabulary_is_closed(authority):
    """`cancelled` is a real state; `done` and `open` are drift.

    Pinned so the decision survives as a check rather than as a paragraph someone has to
    find. If a future writer introduces a new status string, the producible set will not
    contain it and the test above fails — which is the point of closing the vocabulary.
    """
    assert (
        "cancelled" in TASK_ABANDONED_STATUSES
    ), "cancelled is a declared abandoned state, which is why it earned event types"
    assert "done" not in _WORK_ORDER_STATUSES
    assert TASK_STATUS_SYNONYMS == {"done": "complete", "open": "pending"}, (
        "done is a second spelling of complete and open is not declared vocabulary at "
        "all; both are normalised by a replay rather than given event types of their own"
    )
    assert "done" not in CANONICAL_TASK_STATUSES
    assert "open" not in CANONICAL_TASK_STATUSES
    # The two event types this work order added, named so their removal breaks a test
    # rather than silently reopening 422 rows on the next rebuild.
    assert "work_order.cancelled" in WorkOrderProjection.consumed_event_types
    assert "task.cancelled" in TaskProjection.consumed_event_types


def test_a_row_of_every_live_status_survives_a_rebuild_unchanged(authority):
    """Seed one row at each status, rebuild, and require it to come back the same.

    This is the claim the work order makes, and only a replay can show it. Asserting an
    event type is registered proves it is registered.
    """
    project_id, milestone_id = _seed_parents(authority)

    wo_terminal = {
        "created": None,
        "in_progress": "work_order.started",
        "blocked": "work_order.blocked",
        "closed": "work_order.closed",
        "cancelled": "work_order.cancelled",
        "deleted": "work_order.deleted",
    }
    ids: dict[str, str] = {}
    for status, terminal in wo_terminal.items():
        wo_id = str(uuid.uuid4())
        ids[status] = wo_id
        trace = {"project_id": project_id, "milestone_id": milestone_id, "work_order_id": wo_id}
        _emit(
            authority,
            "work_order.created",
            trace,
            {
                "title": "t",
                "status": "created",
                "type": "infrastructure",
                "work_order_id": wo_id,
                "project_id": project_id,
            },
        )
        if terminal:
            _emit(
                authority,
                terminal,
                trace,
                {
                    "work_order_id": wo_id,
                    "project_id": project_id,
                    "title": "t",
                    "forced": False,
                    "block_reason": "r",
                },
            )

    task_terminal = {
        "pending": None,
        "complete": "task.completed",
        "cancelled": "task.cancelled",
        "deleted": "task.deleted",
    }
    task_ids: dict[str, str] = {}
    for status, terminal in task_terminal.items():
        wo_id, task_id = str(uuid.uuid4()), str(uuid.uuid4())
        task_ids[status] = task_id
        _emit(
            authority,
            "work_order.created",
            {"project_id": project_id, "work_order_id": wo_id},
            {
                "title": "parent",
                "status": "created",
                "type": "infrastructure",
                "work_order_id": wo_id,
                "project_id": project_id,
            },
        )
        trace = {"project_id": project_id, "work_order_id": wo_id, "task_id": task_id}
        _emit(
            authority,
            "task.created",
            trace,
            {"title": "t", "description": "d", "status": "created"},
        )
        if terminal:
            _emit(authority, terminal, trace, {})

    _rebuild(authority)

    for status, wo_id in ids.items():
        got = _status(authority, "business_work_orders", "work_order_id", wo_id)
        assert got == status, f"work order seeded {status!r} came back {got!r}"
    for status, task_id in task_ids.items():
        got = _status(authority, "business_tasks", "task_id", task_id)
        assert got == status, f"task seeded {status!r} came back {got!r}"


def test_the_work_order_vocabulary_is_declared_in_production():
    """A vocabulary a writer cannot import is a note, not a closed set.

    The task side was closed against `core/work_orders/task_status.py`, which readers
    import. The work-order side had no equivalent: its constant was authored in this test
    file and existed nowhere else, so a writer introducing a new status was refused by
    nothing and the test would only complain after the value was already in the authority.
    """
    import core.work_orders.task_status as vocab

    assert vocab.CANONICAL_WORK_ORDER_STATUSES, "the work-order vocabulary must be declared"
    assert vocab.CANONICAL_TASK_STATUSES

    # And the map that makes each one reachable by replay is declared beside it, so a
    # status added without an event that produces it is visible at the declaration.
    assert set(vocab.WORK_ORDER_STATUS_EVENT) == set(vocab.CANONICAL_WORK_ORDER_STATUSES), (
        "every work-order status must name the event that produces it, or None where the "
        "creation event alone lands on it"
    )
    assert set(vocab.TASK_STATUS_EVENT) == set(vocab.CANONICAL_TASK_STATUSES)

    # Read from production by this test rather than redeclared in it -- the property the
    # work order is about.
    source = pathlib.Path(vocab.__file__).read_text(encoding="utf-8")
    assert "CANONICAL_WORK_ORDER_STATUSES" in source


def test_the_projections_read_the_declared_vocabulary():
    """A vocabulary nothing reads refuses nothing.

    THE FIRST VERSION OF THIS TEST DID NOT CHECK ITS OWN NAME. It asserted that each
    projection CONSUMES the event types the vocabulary names -- event-type coverage, which
    was already true and stayed true while both projections went on writing
    `SET status = 'complete'` as inline SQL literals. An independent review caught the
    gap: the test was named for the import-and-membership property and asserted something
    adjacent to it, so the task it certified was marked done while the projections read
    nothing.

    The property is that a projection CANNOT NAME A STATUS ITSELF. Every status it writes
    comes back from `status_for` or `creation_status`, so a status the vocabulary does not
    declare is unreachable from a projection rather than merely discouraged.

    THIS TEST READS SOURCE, WHICH THIS MODULE'S DOCSTRING OTHERWISE FORBIDS, and the
    distinction is real: the rebuild tests answer WHICH STATUSES ARE PRODUCIBLE and must
    drive the engine to do it, because the handlers' behaviour is the answer. This one
    answers WHERE THE STRING CAME FROM, which is a property of the source text and cannot
    be observed from the outside -- a projection writing 'complete' inline and one asking
    the vocabulary for it produce identical rows.
    """
    import re

    for module in (
        "core/projections/work_order_projection.py",
        "core/projections/task_projection.py",
    ):
        text = (_REPO_ROOT / module).read_text(encoding="utf-8")
        assert "from core.work_orders.task_status import" in text, (
            f"{module} does not import the status vocabulary, so nothing stops it "
            "writing a status no event can produce"
        )
        # A status written as a literal into the status column, in either dialect the two
        # projections use: a dict payload for safe_upsert, or inline SQL.
        literals = re.findall(r'"status":\s*"([a-z_]+)"', text)
        literals += re.findall(r"SET status = '([a-z_]+)'", text)
        assert not literals, (
            f"{module} still writes the status literal(s) {sorted(set(literals))} itself. "
            "Every status must come from status_for()/creation_status(), or the "
            "vocabulary and the write are two sites agreeing only by inspection"
        )


def test_every_consumed_event_either_produces_a_status_or_declares_it_does_not():
    """The vocabulary must answer for every event a projection actually handles.

    Coverage in the other direction from the map: `status_for` raising for an event a
    projection consumes would be a crash at replay time, not a caught mistake.
    `task.ac_repointed` is the one consumed event that legitimately produces no status --
    it edits a criterion -- and it is named here so that a future event added without a
    status is a failure rather than an omission.
    """
    from core.projections.task_projection import TaskProjection
    from core.projections.work_order_projection import WorkOrderProjection
    from core.work_orders.task_status import status_for

    produces_no_status = {"task.ac_repointed"}
    for projection, is_wo in ((WorkOrderProjection, True), (TaskProjection, False)):
        for event in projection().consumed_event_types:
            if event in produces_no_status:
                continue
            status = status_for(event, work_order=is_wo)
            assert status, f"{event} produced an empty status"


def test_the_two_status_maps_agree_where_they_overlap():
    """Two maps decide what status goes with what event, in opposite directions.

    They are NOT inverses: `work_order.started` and `work_order.unblocked` both produce
    `in_progress`, so inverting either loses information. That is precisely why they can
    drift -- the Gate-integrity lane's own signature, two sites deciding one question with
    one consulting a subset. Every (status -> event) pair must round-trip back to that
    status through the event -> status map.
    """
    from core.work_orders import task_status as vocab

    for forward, backward, kind in (
        (vocab.WORK_ORDER_STATUS_EVENT, vocab.WORK_ORDER_EVENT_STATUS, "work order"),
        (vocab.TASK_STATUS_EVENT, vocab.TASK_EVENT_STATUS, "task"),
    ):
        for status, event in forward.items():
            if event is None:
                continue
            assert backward.get(event) == status, (
                f"{kind} vocabulary disagrees with itself: {status!r} names {event!r} as "
                f"its event, but that event produces {backward.get(event)!r}"
            )
        # And nothing in the projection-facing map is a status the vocabulary disowns.
        declared = set(forward)
        for event, status in backward.items():
            assert status in declared, (
                f"{kind} event {event!r} produces {status!r}, which is not a declared " "status"
            )


def test_canonical_status_has_a_production_reader():
    """A helper only its own test calls is dead, whatever its docstring says.

    `canonical_status` resolves a row's status to the one a replay lands on, and exists to
    be used by the repair that emits terminal lifecycle events. If the only caller were
    this file, it would be test-only code in a production module -- which this repo
    deletes rather than keeps.
    """
    import pathlib
    import subprocess

    import core.work_orders.task_status as vocab

    root = pathlib.Path(vocab.__file__).resolve().parents[2]
    proc = subprocess.run(
        ["git", "grep", "-l", "canonical_status", "--", "core", "interfaces", "runtime"],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    readers = {
        line.strip().replace("\\", "/")
        for line in (proc.stdout or "").splitlines()
        if line.strip() and "task_status.py" not in line
    }
    assert readers, (
        "canonical_status is defined in production and called from nowhere in core/, "
        "interfaces/ or runtime/ -- production-located code reachable only from tests is "
        "dead, and this repo deletes dead code rather than keeping it"
    )
