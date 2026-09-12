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

WHAT STANDS IN FOR THE SPOOL, AND WHY IT CALLS PRODUCTION CODE. `spool.writer.write_event`
writes a JSON file that an out-of-process ingestor later denormalizes into
`business_canonical_events`. Running that daemon in a unit test buys nothing, so the
writer is replaced with a recorder — but the recorder does NOT hand-roll the canonical
INSERT. It hands each envelope to the ingestor's own `_write_to_dual_canonical`, so the
denormalization, the routing and the column set are production code.

A FIRST VERSION OF THIS FILE DID HAND-ROLL THAT INSERT AND WAS WRONG IN TWO WAYS the
independent runner caught: it denormalized only `project_id` and `work_order_id` of the
four the ingestor writes, so `milestone_id` came back NULL after a rebuild and a test
failed blaming production; and it wrote synchronously on a second connection while the
caller still held an open write transaction, so every emission after the first hit
`database is locked` and was swallowed. Both were the stand-in diverging from the thing it
stood in for — the same failure as a stub that accepts an envelope object. Ingestion now
runs AFTER the spawn transaction closes, which is also what actually happens in
production, where it is asynchronous.

AND THE RECORDER ENFORCES THE WRITER'S REAL CONTRACT. The production `write_event` takes a
DICT; handing it a `CanonicalEventEnvelope` object raises TypeError from
`_validate_payload_keys`, the caller's `except` swallows it, and the emission reads as
present while never once succeeding. That exact bug shipped in this module, and three
tests stayed green through it because their stubs accepted the envelope OBJECT. This
recorder rejects anything that is not a dict, so that defect fails here instead.
"""

from __future__ import annotations

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
def emitted(monkeypatch):
    """Capture what the spawn path emits, enforcing write_event's real contract.

    Capture only — nothing is written here. Ingestion is a separate step run after the
    caller's transaction closes, because that is when it happens in production and
    because writing on a second connection mid-transaction deadlocks SQLite.
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

    import spool.writer as _spool_writer

    monkeypatch.setattr(_spool_writer, "write_event", _write_event)
    return captured


def _ingest(db_path: Path, envelopes: list[dict[str, Any]]) -> int:
    """Run the REAL ingestor write for each captured envelope.

    Production code does the denormalization and the routing, so this stand-in cannot
    drift from the column set the ingestor actually populates — which is exactly how the
    first version of this file produced a false failure.
    """
    from spool.ingestor import _write_to_dual_canonical

    for envelope in envelopes:
        _write_to_dual_canonical(envelope, db_path)
    return len(envelopes)


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
            # WO 82f608ca: the spawn path now asks admission, exactly as its attach
            # sibling always has, so a fixture filing a criterion-less task is refused.
            # These tests are about REBUILD SURVIVAL, not about admission -- the criterion
            # is what lets the row exist to be rebuilt at all.
            "tasks": [
                {
                    "title": "A spawned task",
                    "description": "do the thing",
                    "acceptance_criteria": "TEST-CHECK: tests/unit/test_verify_gaps.py::test_a_spawned_task_survives_a_projection_rebuild",
                }
            ],
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


def test_a_spawned_work_order_survives_a_projection_rebuild(authority, emitted):
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
    assert _ingest(authority, emitted) >= 2, (
        "precondition: the spawn must have emitted a work_order.created AND a "
        f"task.created; captured {len(emitted)} envelope(s)"
    )

    _rebuild(authority, WorkOrderProjection())

    assert _count(authority, "business_work_orders", work_order_id=new_id) == 1, (
        "the spawned work order did NOT survive the rebuild. pre_rebuild truncated "
        "business_work_orders and no work_order.created event existed to replay it back, "
        "so a recovery rebuild silently deletes every work order a review has spawned."
    )


def test_a_spawned_task_survives_a_projection_rebuild(authority, emitted):
    """Same claim for the child rows, which live in a different projection."""
    from core.projections.task_projection import TaskProjection

    project_id, milestone_id, reviewed_id = _seed_project(authority)
    spawned = _spawn(authority, project_id, milestone_id, reviewed_id)
    new_id = spawned[0]["work_order_id"]

    assert _count(authority, "business_tasks", work_order_id=new_id) == 1
    _ingest(authority, emitted)

    _rebuild(authority, TaskProjection())

    assert _count(authority, "business_tasks", work_order_id=new_id) == 1, (
        "the spawned task did NOT survive the rebuild — business_tasks was truncated "
        "and no task.created event existed to replay it back."
    )


def test_the_reconstructed_row_keeps_the_fields_the_event_carries(authority, emitted):
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

    _ingest(authority, emitted)
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


def test_the_writer_contract_is_enforced_so_an_envelope_object_would_fail(authority, emitted):
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


def test_no_row_in_the_authority_is_unreconstructable(authority):
    """WO 17466550 task 2, driven end to end: repair, replay, and nothing is lost.

    Task 1 stopped the spawn path CREATING unreplayable rows. This is the other half --
    the rows already there. On the live authority that was 493 work orders and 1706 tasks
    with no creation event, deleted outright by a rebuild, plus 131 that survive and come
    back with the wrong status because no terminal lifecycle event was ever emitted.

    A creation event alone is not enough and the first version of the repair proved it:
    replay lands on the handler's hardcoded default, so backfilling one would have
    reopened 396 closed work orders. The repair emits the terminal event as well, and
    this drives the whole sequence -- seed rows with no events at all, back them up,
    ingest, rebuild, and require every row back with the status it went in with.
    """
    from core.projections.task_projection import TaskProjection
    from core.projections.work_order_projection import WorkOrderProjection
    from core.work_orders.backfill_creation_events import backfill
    from spool.ingestor import ingest

    project_id, milestone_id, _ = _seed_project(authority)
    seeded: dict[str, str] = {}
    conn = sqlite3.connect(str(authority))
    try:
        for status in ("created", "in_progress", "blocked", "closed", "cancelled"):
            wo_id = str(uuid.uuid4())
            seeded[wo_id] = status
            conn.execute(
                "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id,"
                " title, description, work_order_type, status, created_at, updated_at)"
                " VALUES (?, ?, ?, 'Historic', 'd', 'infrastructure', ?, ?, ?)",
                (wo_id, project_id, milestone_id, status, _NOW, _NOW),
            )
        conn.commit()
    finally:
        conn.close()

    before = backfill(db_path=authority, apply=False)
    assert before["would_refuse"] is False, before
    assert before["would_write"]["work_orders"] >= len(seeded), before

    applied = backfill(db_path=authority, apply=True)
    assert applied["ok"], applied
    ingest(db_path=authority)
    _rebuild(authority, WorkOrderProjection(), TaskProjection())

    conn = sqlite3.connect(str(authority))
    try:
        got = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT work_order_id, status FROM business_work_orders"
            ).fetchall()
        }
    finally:
        conn.close()

    missing = [w for w in seeded if w not in got]
    assert (
        not missing
    ), f"{len(missing)} row(s) deleted by the rebuild the repair was meant to survive"
    wrong = {w: (seeded[w], got[w]) for w in seeded if got[w] != seeded[w]}
    assert not wrong, f"rows came back with a status they did not go in with: {wrong}"


def test_every_projection_write_site_emits_its_event(authority):
    """WO 17466550 task 3: the class, checked by the gate rather than by reading.

    The detector derives its target tables from each projection's own `target_tables` --
    the set `pre_rebuild` truncates, so the real blast radius -- and reports every
    production function that INSERTs into one without emitting. This asserts the gate is
    clean against the repository it guards AND that it examined something, because a
    sweep that examined nothing is the failure this gate was written to catch.
    """
    from core.gates.event_backed_write import offenders

    report = offenders()

    assert report["examined"] > 0, (
        "the gate examined zero write sites, which is not a clean sweep -- it is a sweep "
        "that measured nothing and reported compliance"
    )
    assert len(report["target_tables"]) >= 4, report["target_tables"]
    assert report["offenders"] == [], report["offenders"]


def test_the_spawn_path_admits_its_tasks_like_the_attach_path(authority):
    """These two gap functions have diverged four times; this pins the fourth shut.

    Twice on event emission, once on the acceptance-criteria column, and once on
    admission itself -- `_attach_gap_tasks` has been gated by `admit_task` since the stub
    factory was closed, while `_insert_gap_work_orders` called no seat at all. A review
    could therefore file an uncheckable claim by the spawn route and push the blocking
    task-criteria-baseline ceiling upward, which is how a push came to be refused at 1776
    against 1767.

    DRIVEN, NOT GREPPED. The first version of this test searched the source for
    `admit_task(` in both function bodies. A mutation that kept the call textually while
    neutering its result -- `dict(admitted=True, ...) or admit_task(...)` -- passed it,
    because a grep proves a call exists and not that its answer is honoured. That is the
    grep-standing-in-for-a-drive shape this repo names, written into the check meant to
    close a divergence.
    """
    db_path = authority
    project_id, milestone_id, reviewed_id = _seed_project(db_path)

    gaps = [
        {
            "title": "A gap whose task nobody can check",
            "description": "raised by review",
            "category": "durability",
            "type": "infrastructure",
            "tasks": [{"title": "unverifiable claim", "description": "no criterion at all"}],
        }
    ]
    conn = sqlite3.connect(str(db_path))
    try:
        from core.work_orders.verify_gaps import _insert_gap_work_orders

        _insert_gap_work_orders(
            conn,
            gaps=gaps,
            project_id=project_id,
            milestone_id=milestone_id,
            reviewed_work_order_id=reviewed_id,
            reviewed_wo_title="Reviewed",
            reviewed_wo_sequence=1,
        )
        conn.commit()
        rows = conn.execute(
            "SELECT title, acceptance_criteria FROM business_tasks"
            " WHERE title = 'unverifiable claim'"
        ).fetchall()
    finally:
        conn.close()

    assert rows == [], (
        "the spawn path filed a task with no criterion and no declared reason, so a "
        f"review run raises the blocking uncheckable ceiling by itself: {rows}"
    )


def test_a_declared_reason_is_recorded_on_the_row(authority):
    """A declared reason must reach the row, not be spent on the decision.

    `why` was handed to admit_task and dropped. The ceiling's only notion of "declared"
    is DECLARED_PREFIX appearing in the description, so a task admitted on a reason that
    never got written is counted as a stub -- a bare bypass with a nicer spelling.
    """
    from core.work_orders.admission import DECLARED_PREFIX

    db_path = authority
    project_id, milestone_id, reviewed_id = _seed_project(db_path)

    gaps = [
        {
            "title": "A gap resting on judgment",
            "description": "raised by review",
            "category": "durability",
            "type": "infrastructure",
            "tasks": [
                {
                    "title": "a judgment call",
                    "description": "decide and record it",
                    "why": "no check settles an architecture decision; the deliverable is the record",
                }
            ],
        }
    ]
    conn = sqlite3.connect(str(db_path))
    try:
        from core.work_orders.verify_gaps import _insert_gap_work_orders

        _insert_gap_work_orders(
            conn,
            gaps=gaps,
            project_id=project_id,
            milestone_id=milestone_id,
            reviewed_work_order_id=reviewed_id,
            reviewed_wo_title="Reviewed",
            reviewed_wo_sequence=1,
        )
        conn.commit()
        row = conn.execute(
            "SELECT description FROM business_tasks WHERE title = 'a judgment call'"
        ).fetchone()
    finally:
        conn.close()

    assert row, "a task admitted on a declared reason was not filed at all"
    assert DECLARED_PREFIX in row[0], (
        "the declared reason never reached the row, so the ceiling counts this task as a "
        f"stub and the reviewer's reason is unauditable: {row[0][:160]!r}"
    )
