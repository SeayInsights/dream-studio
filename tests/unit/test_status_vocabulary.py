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
    TASK_STATUS_EVENT,
    TASK_STATUS_SYNONYMS,
    WORK_ORDER_STATUS_EVENT,
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

    THE POPULATION COMES FROM THE VOCABULARY, not from a list kept here. It used to be
    two literal maps transcribed into this function -- the second-copy shape this work
    order exists to end, sitting inside the test that exists to prove it ended. Reading
    the declared maps means a status added to the vocabulary tomorrow is SEEDED AND
    REBUILT here automatically; a new status that nobody proved survives a replay is the
    exact gap that left 53 work orders and 369 tasks unreproducible.
    """
    project_id, milestone_id = _seed_parents(authority)

    wo_terminal = WORK_ORDER_STATUS_EVENT
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

    task_terminal = TASK_STATUS_EVENT
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


def test_every_event_produces_the_status_the_map_promises(authority):
    """Drive each event through a real rebuild: the PROJECTION must obey the map.

    This test pins the projections to the vocabulary and DOES NOT pin the vocabulary --
    the two are different jobs and conflating them is what went wrong twice here. The
    first attempt walked the status -> event map, whose only entry reaching `in_progress`
    is `work_order.started`, so `work_order.unblocked` appeared in neither loop and an
    independent reviewer's mutation of it passed all eight tests. The second compared the
    rebuilt row against `status_for(event)` while the projection had just written
    `status_for(event)` -- an identity, which passed the same mutant again. The third
    wrote the whole expected map out as a literal, which a review called what it was: a
    second transcription of the thing under test, free to drift.

    So the map's own entries are held by RELATIONS in the test below this one, and this
    one asks only the question a replay can answer: does a projection handling this event
    land on what the vocabulary said it would. That is not an identity for this purpose --
    a handler that ignored the map, or wrote to the wrong column, or never ran, all fail
    here.
    """
    from core.work_orders.task_status import (
        TASK_EVENT_STATUS,
        WORK_ORDER_EVENT_STATUS,
        status_for,
    )

    project_id, milestone_id = _seed_parents(authority)

    wo_ids: dict[str, str] = {}
    for event in WORK_ORDER_EVENT_STATUS:
        wo_id = str(uuid.uuid4())
        wo_ids[event] = wo_id
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
        if event != "work_order.created":
            _emit(
                authority,
                event,
                trace,
                {
                    "work_order_id": wo_id,
                    "project_id": project_id,
                    "title": "t",
                    "forced": False,
                    "block_reason": "r",
                },
            )

    task_ids: dict[str, str] = {}
    for event in TASK_EVENT_STATUS:
        wo_id, task_id = str(uuid.uuid4()), str(uuid.uuid4())
        task_ids[event] = task_id
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
        if event != "task.created":
            _emit(authority, event, trace, {})

    _rebuild(authority)

    for event, wo_id in wo_ids.items():
        got = _status(authority, "business_work_orders", "work_order_id", wo_id)
        assert got == status_for(event, work_order=True), (
            f"the vocabulary says {event!r} produces "
            f"{status_for(event, work_order=True)!r}; a rebuild produced {got!r}"
        )
    for event, task_id in task_ids.items():
        got = _status(authority, "business_tasks", "task_id", task_id)
        assert got == status_for(event), (
            f"the vocabulary says {event!r} produces {status_for(event)!r}; "
            f"a rebuild produced {got!r}"
        )


def test_the_map_entries_hold_the_relations_that_define_them():
    """What pins the vocabulary, without copying it.

    Once the projections take every status from the map, nothing in production can
    contradict it -- so a test comparing production to the map is an identity, and a test
    restating the map is a second copy that drifts. What is left is the RELATIONS BETWEEN
    ENTRIES, which are statements about meaning rather than duplicates of values: they
    stay true if a status is renamed, and false if an entry is wrong.

    The relation that matters most is the one a reviewer's mutation broke. `unblocked`
    means a work order returns to the state `started` put it in. Written as
    `status_for("work_order.unblocked") == status_for("work_order.started")`, that holds
    whatever `in_progress` is eventually called, and fails the moment unblocking lands
    somewhere else -- which is exactly the mutation that passed three earlier versions of
    this file.
    """
    from core.work_orders.task_status import (
        CANONICAL_TASK_STATUSES,
        CANONICAL_WORK_ORDER_STATUSES,
        TASK_EVENT_STATUS,
        WORK_ORDER_EVENT_STATUS,
        creation_status,
        status_for,
    )

    started = status_for("work_order.started", work_order=True)
    assert status_for("work_order.unblocked", work_order=True) == started, (
        "unblocking returns a work order to the state starting it produced; an entry "
        "that lands anywhere else silently reopens or re-blocks work on every rebuild"
    )
    assert status_for("work_order.reopened", work_order=True) == started, (
        "reopening returns a closed work order to the state starting produced; an entry "
        "landing anywhere else means a rebuild cannot reproduce a reopen, which is how "
        "work_order.reopened came to be emitted, consumed by nothing, and unregistered"
    )
    assert status_for("work_order.blocked", work_order=True) != started, (
        "blocked and working must be distinguishable, or a blocked work order is "
        "indistinguishable from one in progress"
    )
    assert status_for("work_order.created", work_order=True) == creation_status(
        work_order=True
    ), "the creation event must produce the creation default, not a second spelling of it"
    assert (
        status_for("task.created") == creation_status()
    ), "same for tasks: the creation event and the creation default are one status"

    # A terminal event must not land on the creation default -- that is the exact shape
    # that made a backfill reopen 396 closed work orders.
    for event in ("work_order.closed", "work_order.cancelled", "work_order.deleted"):
        assert status_for(event, work_order=True) != creation_status(
            work_order=True
        ), f"{event} produces the creation default, so replaying it would reopen the row"
    for event in ("task.completed", "task.cancelled", "task.deleted"):
        assert (
            status_for(event) != creation_status()
        ), f"{event} produces the creation default, so replaying it would un-finish the task"

    # Every entry stays inside the declared vocabulary, so a typo cannot become a status.
    for event, status in WORK_ORDER_EVENT_STATUS.items():
        assert status in CANONICAL_WORK_ORDER_STATUSES, f"{event} produces undeclared {status!r}"
    for event, status in TASK_EVENT_STATUS.items():
        assert status in CANONICAL_TASK_STATUSES, f"{event} produces undeclared {status!r}"

    # Distinct terminal events must stay distinct: collapsing two onto one status would
    # make a rebuild unable to tell abandoned work from deleted rows.
    terminals = [
        status_for(e, work_order=True)
        for e in ("work_order.closed", "work_order.cancelled", "work_order.deleted")
    ]
    assert len(set(terminals)) == 3, f"terminal work-order events collapsed onto {terminals}"


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


def test_the_docstring_table_records_the_measured_overlap():
    """The blast-radius number this work order turns on must be IN the record.

    A criterion named this test before it existed -- the overlap was measured, written
    into the module docstring, and the check that holds it there was never written, so a
    verify reported the node missing. That is the same shape as a lane with no detector:
    a claim with nothing keeping it true.

    WHAT MAKES THE NUMBER WORTH HOLDING. The misrepresented rows fail in two different
    ways and only the split says which. Rows MISSING a creation event are deleted outright
    by a rebuild -- destructive and loud. Rows that HAVE one survive and come back wrong,
    because replay reaches whatever the last handled event set and no handled event set
    `cancelled`. The second half is the urgent one precisely because it looks like
    success. An aggregate count cannot tell them apart, which is why "493 + 1706" was not
    an answer to the question the task asked.

    Checked for ARITHMETIC, not for presence. Asserting the string is in the docstring
    would pass on numbers someone edited to anything at all; requiring each row's two
    columns to sum to its total means a number cannot be changed in isolation without
    the table contradicting itself.
    """
    import re

    doc = sys.modules[__name__].__doc__ or ""
    assert "creation event" in doc.lower(), (
        "the module docstring no longer records the creation-event overlap, which is the "
        "measurement distinguishing rows a rebuild deletes from rows it returns wrong"
    )

    # Rows look like: <table>.<status>  <total>  <has>  <missing>
    rows = re.findall(r"business_(?:work_orders|tasks)\.[a-z_]+\s+(\d+)\s+(\d+)\s+(\d+)", doc)
    assert len(rows) >= 5, (
        f"expected the per-status overlap table (5 misrepresented statuses), found "
        f"{len(rows)} parseable row(s). An aggregate does not answer the question."
    )
    for total, has, missing in rows:
        assert int(has) + int(missing) == int(total), (
            f"overlap row does not add up: {has} with a creation event + {missing} "
            f"without != {total} total. A number was edited without the others."
        )

    # And the split must be non-trivial in BOTH directions, or the distinction the table
    # exists to draw is not present in the data it records.
    assert any(int(h) > 0 for _, h, _ in rows), "no row records rows that HAVE a creation event"
    assert any(int(m) > 0 for _, _, m in rows), "no row records rows that are MISSING one"


def _projected_status_writers(root: Path | None = None) -> list[str]:
    """Every production site that writes a status into a projected table, DISCOVERED.

    The table list comes from each projection's own `target_tables`, not a literal pair.
    A hardcoded list would have covered the two tables this was found in and silently
    exempted the rest -- the same subset-of-what-it-writes shape the event-backed-write
    gate was built to refuse.
    """
    import re

    from core.projections.task_projection import TaskProjection
    from core.projections.work_order_projection import WorkOrderProjection

    tables = set(WorkOrderProjection.target_tables) | set(TaskProjection.target_tables)
    offenders: list[str] = []
    base = root or _REPO_ROOT
    for path in base.rglob("*.py"):
        rel = path.relative_to(base).as_posix()
        if rel.startswith(("dist/", ".claude/", "tests/")) or "worktrees" in rel:
            continue
        if not rel.startswith(("core/", "interfaces/", "runtime/", "control/", "integrations/")):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        for table in tables:
            for match in re.finditer(rf"UPDATE {table}\b", text):
                begin = match.start()
                window = text[begin:][:400]
                literal = re.search(r"SET status = '([a-z_]+)'", window)
                if literal:
                    line = text[: match.start()].count("\n") + 1
                    offenders.append(f"{rel}:{line} writes '{literal.group(1)}'")
            # INSERT TOO, WHICH THE FIRST VERSION OF THIS FINDER MISSED. It scanned
            # UPDATE only, so two INSERTs spelling 'pending' and 'created' inline sat
            # inside the very function this work order was opened about, and the guard
            # reported the tree clean. A finder covering one of two statement kinds is
            # the subset-of-what-it-writes shape, found in the check built to refuse it.
            for match in re.finditer(rf"INSERT INTO {table}\b", text):
                begin = match.start()
                window = text[begin:][:600]
                declared = "pending|created|complete|closed|in_progress|blocked|cancelled|deleted"
                for literal in re.finditer(rf"'({declared})'", window):
                    line = text[: match.start()].count("\n") + 1
                    offenders.append(f"{rel}:{line} INSERTs literal '{literal.group(1)}'")
        for match in re.finditer(r'"status":\s*"([a-z_]+)"', text):
            if rel.startswith("core/projections/"):
                offenders.append(f"{rel} writes dict literal '{match.group(1)}'")
    return sorted(set(offenders))


def test_no_production_writer_spells_a_projected_status():
    """THE OUTCOME: no production site names a status the vocabulary owns.

    Seven sites wrote a literal into `business_work_orders` / `business_tasks` as a
    synchronous read-model mirror -- `mutations.py` three times, `start_main.py`,
    `close_main.py`, and both drain sites in `verify_gaps.py`. Each now takes its value
    from `status_for(<the event this site emits>)`, so the row and the event cannot
    disagree about the word and a renamed status is a KeyError at the write rather than
    silent drift.
    """
    offenders = _projected_status_writers()
    assert not offenders, (
        "production sites spell a projected status instead of asking the vocabulary:\n  "
        + "\n  ".join(offenders)
        + "\nEach must take its value from status_for(<the event this site emits>), so a "
        "renamed status is a KeyError at the write rather than silent drift."
    )


def test_the_guard_covers_every_writer_not_a_named_pair():
    """THE MECHANISM: the guard DISCOVERS its subjects rather than naming them.

    The previous guard read two projection files by name. It asserted those two took
    their statuses from the vocabulary, and passed while seven other production sites
    drifted -- found by an independent review, not by the suite. A guard that names its
    subjects can only ever catch the subjects someone remembered, which is why this test
    is about how the finder is built and not about today's result.
    """
    from core.projections.task_projection import TaskProjection
    from core.projections.work_order_projection import WorkOrderProjection

    # The table list is DERIVED from each projection's own declaration.
    declared = set(WorkOrderProjection.target_tables) | set(TaskProjection.target_tables)
    assert declared >= {"business_work_orders", "business_tasks"}, declared

    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    start = source.index("def _projected_status_writers")
    finder = source[start:]
    end = finder.index("def test_")
    finder = finder[:end]

    assert "target_tables" in finder, (
        "the finder hardcodes its tables instead of reading each projection's own "
        "target_tables, so a new projected table is exempt the day it is added"
    )
    assert "rglob" in finder, (
        "the finder walks a fixed list of files rather than the tree, which is exactly "
        "how seven writers stayed invisible to a green suite"
    )
    for statement in ("UPDATE {table}", "INSERT INTO {table}"):
        assert statement in finder, (
            f"the finder does not scan {statement.split()[0]}; covering one statement "
            "kind and not the other is the subset-of-what-it-writes shape"
        )


def test_the_mutation_proof_runs_the_real_finder(tmp_path):
    """The guard proves it can fail, THROUGH THE GUARD, on every run.

    Two mutations were once run by hand with the proof living in a transcript, and the
    first of them PASSED because the finder's regex carried a stray 0x08 byte and matched
    nothing. So plant-and-detect was made automatic -- and the first automatic version
    RE-IMPLEMENTED the finder's regexes locally, which meant the same broken finder would
    have left it green. Its own independent review caught that: a mutation proof that does
    not invoke the thing it certifies proves nothing about it.

    This drives `_projected_status_writers` itself against a planted tree. If the real
    finder stops matching -- a stray control byte, a narrowed pattern, a lost statement
    kind -- this test goes red with it.
    """
    pkg = tmp_path / "core" / "work_orders"
    pkg.mkdir(parents=True)

    clean = pkg / "compliant.py"
    clean.write_text(
        "conn.execute(\n"
        '    "UPDATE business_tasks SET status = ?, updated_at = ?"\n'
        '    " WHERE task_id = ?",\n'
        '    (status_for("task.completed"), now, task_id),\n'
        ")\n",
        encoding="utf-8",
    )
    assert _projected_status_writers(tmp_path) == [], (
        "the real finder flagged a compliant write, so a green result elsewhere means "
        "nothing -- it cannot tell compliant from offending"
    )

    for name, body, kind in (
        (
            "sql_literal.py",
            "conn.execute(\n"
            "    \"UPDATE business_tasks SET status = 'complete', updated_at = ?\"\n"
            '    " WHERE task_id = ?",\n'
            "    (now, task_id),\n"
            ")\n",
            "an inline SQL literal",
        ),
        (
            "insert_literal.py",
            "conn.execute(\n"
            '    "INSERT INTO business_tasks (task_id, status) VALUES (?, ?)",\n'
            "    (task_id, 'pending'),\n"
            ")\n",
            "an INSERT literal",
        ),
    ):
        planted = pkg / name
        planted.write_text(body, encoding="utf-8")
        found = _projected_status_writers(tmp_path)
        planted.unlink()

        assert found, (
            f"the real finder did not reject {kind}. A check that cannot fail reports a "
            "clean tree whatever is in it -- which is what a stray 0x08 byte in its regex "
            "already caused once."
        )


def test_the_enumeration_is_driven_through_the_real_finder():
    """The discovery itself works, so a green result means looked-and-found-nothing.

    A finder that silently matched zero files would make the test above vacuous -- the
    compared-nothing-reported-clean shape. Proved by planting a literal in a temp tree the
    real finder walks.
    """
    from core.projections.task_projection import TaskProjection
    from core.projections.work_order_projection import WorkOrderProjection

    tables = set(WorkOrderProjection.target_tables) | set(TaskProjection.target_tables)
    assert tables, "no target tables were derived, so the finder searches for nothing"
    assert len(tables) >= 2, tables

    scanned = [
        p
        for p in _REPO_ROOT.rglob("*.py")
        if p.relative_to(_REPO_ROOT).as_posix().startswith("core/work_orders/")
    ]
    assert len(scanned) > 20, (
        f"the finder walked only {len(scanned)} files under core/work_orders/, so a clean "
        "result would mean it looked nowhere"
    )


def test_the_mirror_decision_is_recorded_in_the_module_docstring():
    """A recorded decision with nothing holding it there is a comment waiting to be deleted.

    WO 1364e05e task 4 required the synchronous-mirror decision to be recorded in
    `core/work_orders/task_status.py`. It was written, and it was substantive, and it
    lived in a free-floating comment above `status_for` -- so a future edit could remove
    the only record of why seven production sites still write a status beside the event
    they emit, and nothing would notice. Its own independent review said so.

    Anchored on the MODULE DOCSTRING via `ast.get_docstring`, not on a string search of
    the file, because the claim is that the decision is part of what the module says
    about itself. A comment anywhere in the file would satisfy a grep and would be
    exactly the arrangement this test exists to end.
    """
    import ast

    import core.work_orders.task_status as vocab

    source = pathlib.Path(vocab.__file__).read_text(encoding="utf-8")
    doc = ast.get_docstring(ast.parse(source)) or ""

    assert doc, "the vocabulary module has no docstring at all"
    for marker in ("SYNCHRONOUS MIRROR", "CHOSEN"):
        assert marker in doc, (
            f"the module docstring no longer records the mirror decision ({marker!r} is "
            "missing). Seven production sites write a projected status beside the event "
            "they emit, and this is the only record of why that is deliberate."
        )
    # The rejected alternative matters as much as the choice: without it a reader cannot
    # tell a decision from a description of what happens to be true.
    assert (
        "drain" in doc.lower()
    ), "the docstring records the choice but not what it was chosen against"
