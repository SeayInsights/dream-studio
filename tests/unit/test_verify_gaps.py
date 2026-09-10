"""WO 17466550: what the spawn path writes must survive the recovery tool.

`_insert_gap_work_orders` INSERTed into `business_work_orders` and `business_tasks` and
emitted no canonical event at all. Both tables are PROJECTIONS —
`WorkOrderProjection.target_tables == ["business_work_orders"]`,
`TaskProjection.target_tables == ["business_tasks"]` — and neither class overrides
`pre_rebuild`, so both inherit the framework default that runs `DELETE FROM <table>`
before replaying events. A row with no event is therefore deleted by a rebuild and never
comes back. Measured on the live authority when the work order was raised: 493 of 949
work orders and 1706 of 3286 tasks had no creation event.

The bite is that a rebuild is the DISASTER-RECOVERY tool, so this defect is worst exactly
when it is reached for: recovering from corruption would silently delete every
remediation work order any review has ever spawned.

WHY THIS TEST DRIVES A REBUILD INSTEAD OF ASSERTING AN EMISSION. Asserting that
`write_event` was called proves the call; the claim is RECONSTRUCTION, and only a replay
can show that. So these tests run the real `ProjectionEngine.rebuild()` against the real
`WorkOrderProjection` / `TaskProjection` — including the real truncating `pre_rebuild` —
and then look for the row.

WHAT IS SUBSTITUTED, STATED PLAINLY. The spool→canonical ingestion stage is stood in for:
`spool.writer.write_event` is replaced with a recorder that writes the envelope into
`business_canonical_events`, which is what ingestion does. Everything after that point is
production code.

AND THE STAND-IN ENFORCES THE REAL CONTRACT, which is the whole reason it is safe. The
production `write_event` takes a DICT; handing it a `CanonicalEventEnvelope` object raises
TypeError from `_validate_payload_keys`, the caller's `except` swallows it, and the
emission reads as present while never once succeeding. That exact bug shipped in this
module, and three tests stayed green through it because their stubs accepted the envelope
OBJECT. This recorder therefore rejects anything that is not a dict — so that defect fails
here instead of passing.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

_NOW = "2026-09-10T00:00:00+00:00"


class _NotADict(AssertionError):
    """Raised when the emitter hands the writer something write_event would reject."""


@pytest.fixture
def authority(tmp_path, monkeypatch):
    """A bootstrapped authority DB, isolated from the operator's own."""
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


@pytest.fixture
def ingest(authority, monkeypatch):
    """Stand in for spool ingestion: emitted envelopes land in business_canonical_events.

    Enforces write_event's real contract — a dict — so an envelope object fails loudly
    rather than being silently accepted by a more permissive stub than production.
    """
    captured: list[dict[str, Any]] = []

    def _write_event(envelope, *args, **kwargs):
        if not isinstance(envelope, dict):
            raise _NotADict(
                "write_event takes a dict; got "
                f"{type(envelope).__name__}. Production would raise TypeError here and "
                "the caller's handler would swallow it, so the emission would read as "
                "present and never land. Add .to_dict()."
            )
        captured.append(envelope)
        trace = envelope.get("trace") or {}
        conn = sqlite3.connect(str(authority))
        try:
            conn.execute(
                "INSERT INTO business_canonical_events"
                " (event_id, event_type, event_timestamp, trace, payload,"
                "  work_order_id, project_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    envelope.get("event_id") or str(uuid.uuid4()),
                    envelope["event_type"],
                    envelope.get("timestamp") or _NOW,
                    json.dumps(trace),
                    json.dumps(envelope.get("payload") or {}),
                    trace.get("work_order_id"),
                    trace.get("project_id"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    import spool.writer as _spool_writer

    monkeypatch.setattr(_spool_writer, "write_event", _write_event)
    return captured


def _seed_project(db_path: Path) -> tuple[str, str, str]:
    """A project, a milestone, and the reviewed work order the gaps hang off."""
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    reviewed_id = str(uuid.uuid4())
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
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description,"
            "  work_order_type, status, sequence_order, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Reviewed', '', 'infrastructure', 'in_progress', 1, ?, ?)",
            (reviewed_id, project_id, milestone_id, _NOW, _NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id, milestone_id, reviewed_id


def _spawn(db_path: Path, project_id: str, milestone_id: str, reviewed_id: str) -> list[dict]:
    from core.work_orders.verify_gaps import _insert_gap_work_orders

    gaps = [
        {
            "title": "A spawned remediation work order",
            "description": "raised by review",
            "category": "durability",
            "type": "infrastructure",
            "tasks": [{"title": "A spawned task", "description": "do the thing"}],
        }
    ]
    conn = sqlite3.connect(str(db_path))
    try:
        spawned = _insert_gap_work_orders(
            conn,
            gaps=gaps,
            project_id=project_id,
            milestone_id=milestone_id,
            reviewed_work_order_id=reviewed_id,
            reviewed_wo_title="Reviewed",
            reviewed_wo_sequence=1,
        )
        conn.commit()
    finally:
        conn.close()
    return spawned


def _rebuild(db_path: Path, *projections) -> None:
    """Run the REAL rebuild — truncating pre_rebuild included — for each projection."""
    from core.projections.framework_engine import ProjectionEngine

    engine = ProjectionEngine(db_path=str(db_path))
    for proj in projections:
        engine.register(proj)
    for proj in projections:
        engine.rebuild(proj.name)


def _count(db_path: Path, table: str, **where) -> int:
    clause = " AND ".join(f"{k} = ?" for k in where)
    conn = sqlite3.connect(str(db_path))
    try:
        sql = f"SELECT COUNT(*) FROM {table}" + (f" WHERE {clause}" if where else "")
        return conn.execute(sql, tuple(where.values())).fetchone()[0]
    finally:
        conn.close()


def test_a_spawned_work_order_survives_a_projection_rebuild(authority, ingest):
    """The defect, stated as a test: spawn, rebuild, and the work order is still there."""
    from core.projections.work_order_projection import WorkOrderProjection

    project_id, milestone_id, reviewed_id = _seed_project(authority)
    spawned = _spawn(authority, project_id, milestone_id, reviewed_id)
    assert len(spawned) == 1, spawned
    new_id = spawned[0]["work_order_id"]

    assert _count(authority, "business_work_orders", work_order_id=new_id) == 1, (
        "precondition: the spawn writes the row directly, so it must be present "
        "BEFORE the rebuild — otherwise this test proves nothing about the rebuild"
    )

    _rebuild(authority, WorkOrderProjection())

    assert _count(authority, "business_work_orders", work_order_id=new_id) == 1, (
        "the spawned work order did NOT survive the rebuild. pre_rebuild truncated "
        "business_work_orders and no work_order.created event existed to replay it back, "
        "so a recovery rebuild silently deletes every work order a review has spawned."
    )


def test_a_spawned_task_survives_a_projection_rebuild(authority, ingest):
    """Same claim for the child rows, which live in a different projection."""
    from core.projections.task_projection import TaskProjection

    project_id, milestone_id, reviewed_id = _seed_project(authority)
    spawned = _spawn(authority, project_id, milestone_id, reviewed_id)
    new_id = spawned[0]["work_order_id"]

    assert _count(authority, "business_tasks", work_order_id=new_id) == 1

    _rebuild(authority, TaskProjection())

    assert _count(authority, "business_tasks", work_order_id=new_id) == 1, (
        "the spawned task did NOT survive the rebuild — business_tasks was truncated "
        "and no task.created event existed to replay it back."
    )


def test_the_reconstructed_row_keeps_the_fields_the_event_carries(authority, ingest):
    """Surviving is not enough if it comes back as a different row.

    Scoped to the fields `work_order.created` actually carries. `sequence_order` is
    deliberately NOT asserted here: no event carries it and no handler reads it, so it is
    lost on rebuild for every work order in the authority, not just spawned ones. That is
    a separate defect, registered as WO 5e7221ee, and asserting it here would make this
    test fail for a reason this work order does not own.
    """
    from core.projections.work_order_projection import WorkOrderProjection

    project_id, milestone_id, reviewed_id = _seed_project(authority)
    new_id = _spawn(authority, project_id, milestone_id, reviewed_id)[0]["work_order_id"]

    conn = sqlite3.connect(str(authority))
    conn.row_factory = sqlite3.Row
    before = dict(
        conn.execute(
            "SELECT * FROM business_work_orders WHERE work_order_id = ?", (new_id,)
        ).fetchone()
    )
    conn.close()

    _rebuild(authority, WorkOrderProjection())

    conn = sqlite3.connect(str(authority))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM business_work_orders WHERE work_order_id = ?", (new_id,)
    ).fetchone()
    conn.close()
    assert row is not None, "row did not survive the rebuild"
    after = dict(row)

    for field in ("title", "project_id", "milestone_id", "work_order_type", "description"):
        assert after[field] == before[field], (
            f"{field} changed across the rebuild: {before[field]!r} -> {after[field]!r}. "
            "The row was reconstructed but not faithfully, which reads as success."
        )


def test_the_writer_contract_is_enforced_so_an_envelope_object_would_fail(authority, ingest):
    """Guard the guard: prove this suite rejects the bug that slipped past three tests.

    An emission that hands `write_event` a CanonicalEventEnvelope raises in production and
    the caller swallows it. If this fixture accepted the object, every test above would
    pass against code whose emission never lands. This asserts the fixture is stricter
    than that — a test that cannot fail is worth nothing, so here is it failing.
    """
    import spool.writer as _spool_writer

    class _Envelope:
        pass

    with pytest.raises(_NotADict):
        _spool_writer.write_event(_Envelope())


def test_both_writing_functions_route_through_one_emitter(authority):
    """The class, not the instance: no second copy of the emission block.

    Two siblings in this module disagreed about whether creation goes through the event
    substrate, and the fix note on one NAMED the other as the shape it wrongly copied.
    A third copy would rebuild that condition, so both call `_emit_creation` and the raw
    writer appears exactly once in the module.
    """
    import ast
    import inspect

    import core.work_orders.verify_gaps as mod

    src = inspect.getsource(mod)
    tree = ast.parse(src)
    lines = src.splitlines()

    raw_sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Named indices, not an expression inside the slice: black formats
            # `lines[a - 1 : b]` with spaces around the colon and flake8 reports that as
            # E203, and the two tools cannot both be satisfied inline. Same workaround as
            # `_attached_gap_keys` in the module under test.
            begin = node.lineno - 1
            end = node.end_lineno
            seg = "\n".join(lines[begin:end])
            if "_spool_writer.write_event" in seg:
                raw_sites.append(node.name)

    assert raw_sites == ["_emit_creation"], (
        "the raw writer must appear in exactly one function; found it in "
        f"{raw_sites}. Every additional site is one more place a future fix can land "
        "in one lane and miss its sibling — which is how this defect was created."
    )
