"""Regression tests for issue #718 — task-done must not report a completion it does not hold.

WO b6ca23fa-33a9-442c-bafb-a1b9c33e9895.

``mark_task_done`` wrapped both the ``task.completed`` spool write and the
``sync_tick()`` projection in bare ``except Exception: pass`` and then returned
``ok: True, status: "complete"`` unconditionally.

The casualty that motivated this is subtler than those two swallows, which is why
these tests assert on the AUTHORITY rather than on raised exceptions: event
``d441e451-b96c-42c0-85eb-86b4ce49e894`` (task.completed, 2026-08-28) reached
``business_canonical_events`` — so ``write_event`` succeeded — and then failed a
FOREIGN KEY constraint inside the projection, where ``framework_engine_dispatch``
catches the handler error, dead-letters it, and returns a ``ProjectionResult``
normally. NOTHING THREW, and task ``c1698f88-e304-4ece-84e2-24189af3f718`` has no
row in ``business_tasks`` to this day while its caller was told "complete".

The contract these tests pin distinguishes two cases that look identical from the
read model alone, and must not:

* the projection has not run yet — the event is durable and will materialize on
  the next pass or a rebuild. Pending, not failed; the call still succeeds.
* the projection tried this event and queued or dead-lettered it — it will not
  recover unaided. That is the false-done, and the call must fail.
"""

from __future__ import annotations

import sqlite3

import pytest

# The seeder is shared with the sibling WO-TASKDONE-SYNC regression test; the
# fixture is defined locally rather than imported, because importing a fixture
# whose name is also a test parameter reads as a redefinition to flake8 (F811).
from tests.unit.test_taskdone_sync import _seed_pending_task


@pytest.fixture
def live_like_home(tmp_path, monkeypatch):
    """A bootstrapped studio.db wired as the authority for both the mutation and
    the projection engine, so the mutation's internal sync_tick() reads and writes
    this temp DB rather than the operator's live one.
    """
    from core.config.database import DatabaseRuntime
    from core.config.sqlite_bootstrap import bootstrap_database

    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(tmp_path))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    DatabaseRuntime.reset_instance()
    bootstrap_database(db)
    yield tmp_path, db
    DatabaseRuntime.reset_instance()


def _status_of(db, task_id: str) -> str | None:
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT status FROM business_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _run(home, work_order_id, task_id):
    from core.work_orders.mutations import mark_task_done

    return mark_task_done(
        work_order_id=work_order_id,
        task_id=task_id,
        source_root=home,
        dream_studio_home=home,
    )


def test_happy_path_still_reports_complete(live_like_home):
    """Regression guard: the honest contract must not break the working path."""
    home, db = live_like_home
    work_order_id, task_id = _seed_pending_task(db)

    result = _run(home, work_order_id, task_id)

    assert result["ok"] is True, f"happy path must stay ok:true — got {result}"
    assert result["status"] == "complete"
    assert result.get("all_tasks_complete") is True
    assert _status_of(db, task_id) == "complete"


def test_read_model_lag_is_pending_not_complete(live_like_home, monkeypatch):
    """A projection that has not run yet is lag: reported honestly, still ok."""
    home, db = live_like_home
    work_order_id, task_id = _seed_pending_task(db)

    import core.projections.runner as runner

    monkeypatch.setattr(runner, "sync_tick", lambda *a, **k: None)

    result = _run(home, work_order_id, task_id)

    assert _status_of(db, task_id) != "complete", "fixture precondition"
    assert (
        result["status"] != "complete"
    ), f"task-done claimed complete while business_tasks disagrees — got {result}"
    assert result.get("read_model_pending") is True
    # The event is durable, so this is recoverable and must not fail the call.
    assert result["ok"] is True, f"recoverable lag must not fail the call — got {result}"


def test_stalled_projection_is_reported_as_not_done(live_like_home, monkeypatch):
    """The c1698f88 shape: the projection took the event and could not apply it.

    Simulated by queueing the event for retry without applying it — exactly what
    ``_schedule_retry`` does on a handler failure, and the state the real casualty
    passed through on its way to the dead-letter table.
    """
    home, db = live_like_home
    work_order_id, task_id = _seed_pending_task(db)

    import core.projections.runner as runner
    import spool.writer as spool_writer

    # The event id is only known to the writer, and spool ingestion happens inside
    # sync_tick — so capture it on the way past rather than reading it back.
    captured: dict[str, str] = {}
    real_write = spool_writer.write_event

    def _capture(envelope, *a, **k):
        captured["event_id"] = envelope.get("event_id")
        return real_write(envelope, *a, **k)

    def _stall(*a, **k):
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "INSERT INTO projection_retry_queue"
                " (event_id, event_source, projection_name, next_retry_at, retry_count)"
                " VALUES (?, 'business', 'task_projection', ?, 1)",
                (captured["event_id"], "2099-01-01T00:00:00+00:00"),
            )
            conn.commit()
        finally:
            conn.close()

    monkeypatch.setattr(spool_writer, "write_event", _capture)
    monkeypatch.setattr(runner, "sync_tick", _stall)

    result = _run(home, work_order_id, task_id)

    assert _status_of(db, task_id) != "complete", "fixture precondition"
    assert (
        result["ok"] is False
    ), f"a stalled projection is a false-done and must fail the call — got {result}"
    assert result["status"] != "complete"
    assert "dead-letter" in result.get("error", "")
    assert (
        result.get("all_tasks_complete") is None
    ), "a task that was not recorded must not suggest closing the work order"


def test_event_write_failure_is_surfaced(live_like_home, monkeypatch):
    """A failed task.completed write must reach the caller, not be swallowed."""
    home, db = live_like_home
    work_order_id, task_id = _seed_pending_task(db)

    import spool.writer as spool_writer

    def _boom(*a, **k):
        raise RuntimeError("spool unavailable")

    monkeypatch.setattr(spool_writer, "write_event", _boom)

    result = _run(home, work_order_id, task_id)

    assert (
        result["ok"] is False
    ), f"task-done returned ok:true after the event write raised — got {result}"
    assert "spool unavailable" in str(
        result.get("event_write_error", "")
    ), f"the event-write failure must be reported on the result — got {result}"


def test_projection_exception_is_surfaced(live_like_home, monkeypatch):
    """A raising sync_tick must be reported rather than passed over."""
    home, db = live_like_home
    work_order_id, task_id = _seed_pending_task(db)

    import core.projections.runner as runner

    def _boom(*a, **k):
        raise RuntimeError("projection exploded")

    monkeypatch.setattr(runner, "sync_tick", _boom)

    result = _run(home, work_order_id, task_id)

    assert "projection exploded" in str(
        result.get("projection_error", "")
    ), f"the projection failure must be reported on the result — got {result}"
