"""WO 20796691: every status the authority holds must be reachable by replay.

MEASURED ON THE LIVE AUTHORITY 2026-09-11, which is why this work order exists. Listing
every status each projection could WRITE and diffing it against every status actually
PRESENT found 459 rows the substrate could not express:

    business_work_orders.cancelled   53   no event type produced it
    business_tasks.cancelled        369   no event type produced it
    business_tasks.done              27   no task.completed event on any of them
    business_tasks.open              10   only 1 of 10 had a task.created event

The consequence is broader than the missing-creation-event defect it was found under: a
rebuild misrepresents a `cancelled` row EVEN WHEN its creation event already exists,
because replay reaches whatever the last handled event sets and no handled event set
`cancelled`. Work someone deliberately abandoned came back open.

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

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.projections.task_projection import TaskProjection
from core.projections.work_order_projection import WorkOrderProjection
from core.work_orders.task_status import TASK_ABANDONED_STATUSES, TASK_STATUSES

_NOW = "2026-09-11T00:00:00+00:00"

#: Statuses the tables legitimately hold, against which the producible set is checked.
#: `done` and `open` are absent deliberately — they are drift, and a replay normalises
#: them onto `complete` and `pending`.
_WORK_ORDER_STATUSES = frozenset(
    {"created", "in_progress", "blocked", "closed", "cancelled", "deleted"}
)


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

    expected_tasks = set(TASK_STATUSES)
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
    assert "open" not in TASK_STATUSES, (
        "open is not declared vocabulary — is_open() treats an unknown status as "
        "outstanding, which is what pending already means"
    )
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
