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


def test_a_refused_spawn_task_comes_back_instead_of_vanishing(authority):
    """A refusal is a report, and a report nobody receives is a drop.

    The spawn path was gated by admission and its refusals were accumulated into a list
    that NOTHING RETURNED -- built, appended to, read by nowhere. So a finding refused for
    lacking a criterion was discarded in silence, which is the outcome the task called
    strictly worse than a visible stub, shipped inside the fix for it.

    The first correction then appended to the caller's `unfiled_findings` ABOVE the line
    that assigns it -- an UnboundLocalError on the first real spawn, invisible to a suite
    that never reaches that path. The channel already existed and simply was not being
    filled; this drives it.
    """
    db_path = authority
    project_id, milestone_id, reviewed_id = _seed_project(db_path)

    gaps = [
        {
            "title": "A gap with one checkable task and one not",
            "description": "raised by review",
            "category": "durability",
            "type": "infrastructure",
            "tasks": [
                {
                    "title": "checkable",
                    "description": "has a criterion",
                    "acceptance_criteria": "TEST-CHECK: tests/unit/test_verify_gaps.py::test_a_refused_spawn_task_comes_back_instead_of_vanishing",
                },
                {"title": "unverifiable claim", "description": "no criterion at all"},
            ],
        }
    ]
    conn = sqlite3.connect(str(db_path))
    try:
        from core.work_orders.verify_gaps import _insert_gap_work_orders

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

    assert spawned, "nothing was spawned at all, so the fixture is wrong"

    refused = [f for record in spawned for f in (record.get("unfiled_findings") or [])]
    titles = {f.get("title") for f in refused}
    assert "unverifiable claim" in titles, (
        "the refused task did not come back from the spawn path, so a finding raised by a "
        f"review was discarded in silence. Returned: {refused}"
    )

    # The field name matters: verify_main harvests exactly this key across spawned records.
    assert all("unfiled_findings" in record for record in spawned), (
        "a spawned record omits the key the caller harvests, so its refusals never reach "
        "the verdict even though they were returned"
    )

    # And the checkable one was still filed -- a gate that refuses everything is not a fix.
    conn = sqlite3.connect(str(db_path))
    try:
        filed = conn.execute(
            "SELECT title FROM business_tasks WHERE title IN ('checkable', 'unverifiable claim')"
        ).fetchall()
    finally:
        conn.close()
    assert [r[0] for r in filed] == ["checkable"], filed


def test_a_gap_run_leaves_the_uncheckable_count_unmoved(authority):
    """Measured across a real gap run, not asserted about admit_task in isolation.

    THE SUBSTITUTION THIS ENDS. The property is that RUNNING A REVIEW does not raise the
    blocking uncheckable count -- that is what refused a push at 1776 against a ceiling of
    1767. Two earlier attempts asserted that `admit_task` refuses a criterion-less task
    and that `compose_declared_reason` produces a marker. Both are true, both are units,
    and neither can see a gap path that files rows without asking either one. The review
    named the substitution twice before this was written.

    So this measures `task_criteria_baseline.measure()` before and after driving both gap
    paths with every task shape a reviewer can supply: a criterion, a declared reason, and
    neither.
    """
    from core.gates.task_criteria_baseline import measure
    from core.work_orders.verify_gaps import _attach_gap_tasks, _insert_gap_work_orders

    db_path = authority
    project_id, milestone_id, reviewed_id = _seed_project(db_path)

    before = measure(db_path)["uncheckable"]

    shapes = [
        {
            "title": "has a criterion",
            "description": "checkable",
            "acceptance_criteria": "TEST-CHECK: tests/unit/test_verify_gaps.py::test_a_gap_run_leaves_the_uncheckable_count_unmoved",
        },
        {
            "title": "has a declared reason",
            "description": "judgment",
            "why": "no check settles an architecture decision; the deliverable is the record",
        },
        {"title": "has neither", "description": "a stub by any other name"},
    ]

    conn = sqlite3.connect(str(db_path))
    try:
        _insert_gap_work_orders(
            conn,
            gaps=[
                {
                    "title": "spawned gap",
                    "description": "raised by review",
                    "category": "durability",
                    "type": "infrastructure",
                    "tasks": [dict(t) for t in shapes],
                }
            ],
            project_id=project_id,
            milestone_id=milestone_id,
            reviewed_work_order_id=reviewed_id,
            reviewed_wo_title="Reviewed",
            reviewed_wo_sequence=1,
        )
        _attach_gap_tasks(
            conn,
            work_order_id=reviewed_id,
            project_id=project_id,
            tasks=[dict(t) for t in shapes],
            now=_NOW,
            gap_key="k",
        )
        conn.commit()
    finally:
        conn.close()

    after = measure(db_path)["uncheckable"]

    assert after == before, (
        f"a review run raised the uncheckable count from {before} to {after}. That count "
        "is a blocking ceiling, so a reviewer filing findings can refuse an author's push "
        "for work the author never chose to do."
    )


def test_both_gap_paths_compose_the_declared_reason(authority):
    """The attach path's composition line was executed by no test at all.

    The spawn path was driven and the attach path was not, so half the fix rested on
    reading. Both are driven here, and the marker is checked on the ROW each writes --
    which is the only place `task_criteria_baseline` looks.
    """
    from core.work_orders.admission import DECLARED_PREFIX
    from core.work_orders.verify_gaps import _attach_gap_tasks, _insert_gap_work_orders

    db_path = authority
    project_id, milestone_id, reviewed_id = _seed_project(db_path)
    task = {
        "title": "a judgment call",
        "description": "decide and record it",
        "why": "no check settles an architecture decision; the deliverable is the record",
    }

    conn = sqlite3.connect(str(db_path))
    try:
        _insert_gap_work_orders(
            conn,
            gaps=[
                {
                    "title": "spawned",
                    "description": "raised",
                    "category": "durability",
                    "type": "infrastructure",
                    "tasks": [dict(task)],
                }
            ],
            project_id=project_id,
            milestone_id=milestone_id,
            reviewed_work_order_id=reviewed_id,
            reviewed_wo_title="Reviewed",
            reviewed_wo_sequence=1,
        )
        _attach_gap_tasks(
            conn,
            work_order_id=reviewed_id,
            project_id=project_id,
            tasks=[dict(task)],
            now=_NOW,
            gap_key="k2",
        )
        conn.commit()
        rows = conn.execute(
            "SELECT work_order_id, description FROM business_tasks WHERE title = ?",
            (task["title"],),
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 2, (
        f"expected the task filed by BOTH paths, got {len(rows)} row(s) -- one of the two "
        "paths refused it or never ran"
    )
    for wo_id, description in rows:
        assert DECLARED_PREFIX in description, (
            f"the row filed under {wo_id[:8]} carries no declared-reason marker, so the "
            "ceiling counts it as a stub and the reviewer's reason is unauditable"
        )


# ── The criterion is the identity; the title is a label for it (WO f769de79) ──


_DUP_CRITERION = (
    "TEST-CHECK: tests/unit/test_verify_gaps.py"
    "::test_the_criterion_comparison_is_what_raises_the_question"
)
_OTHER_CRITERION = (
    "TEST-CHECK: tests/unit/test_verify_gaps.py"
    "::test_admission_is_given_the_criteria_not_only_the_titles"
)


def _open_task(db_path: Path, work_order_id: str, project_id: str, title: str, criterion: str):
    """Put one OPEN task carrying `criterion` on the work order."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description,"
            "  acceptance_criteria, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, '', ?, 'pending', ?, ?)",
            (str(uuid.uuid4()), work_order_id, project_id, title, criterion, _NOW, _NOW),
        )
        conn.commit()
    finally:
        conn.close()


def _criteria_on(db_path: Path, work_order_id: str) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return [
            r[0] or ""
            for r in conn.execute(
                "SELECT acceptance_criteria FROM business_tasks WHERE work_order_id = ?",
                (work_order_id,),
            ).fetchall()
        ]
    finally:
        conn.close()


def test_admission_is_given_the_criteria_not_only_the_titles(authority):
    """The decision cannot be made from evidence the decider was never handed.

    `admit_task` was given the candidate's `acceptance_criteria` and the existing TITLES,
    so it could compare a new title against old titles and could not compare a new
    criterion against old criteria. This drives the parameter rather than reading the
    signature: one candidate, two calls, and the only difference is whether the criteria
    set holds its criterion -- so the parameter is what changed the answer.

    The caller half is driven too, through `_attach_gap_tasks`, because a parameter
    accepted by the callee and never populated by the caller is a signature that looks like
    a fact and carries nothing -- the shape this work order's siblings keep finding.
    """
    from core.work_orders.admission import admit_task
    from core.work_orders.verify_gaps import _attach_gap_tasks

    candidate = {
        "title": "a title nothing else on the work order uses",
        "acceptance_criteria": _DUP_CRITERION,
    }

    free = admit_task(**candidate, existing_titles=(), existing_criteria=())
    assert free["admitted"], f"a brand-new task was refused with nothing filed: {free}"
    assert not free["unknowns"], f"nothing is filed, so nothing can be shared: {free}"

    held = admit_task(**candidate, existing_titles=(), existing_criteria=(_DUP_CRITERION,))
    assert held["admitted"], (
        "a shared criterion REFUSED the task. It reports unknown and admits: a restatement "
        "and two changes one check covers are indistinguishable here, and refusing would "
        "drop the second kind"
    )
    assert held["unknowns"], (
        "admit_task was handed a criterion already carried and said nothing, so the "
        "parameter is accepted and not consulted"
    )
    assert any("criterion" in u["reason"] for u in held["unknowns"]), held

    # THE CALLER POPULATES IT. Seed one open task, attach a differently-titled task with
    # the same criterion, and the observation can only have come from the caller building
    # the set -- nothing else in this path carries criteria.
    db_path = authority
    project_id, _milestone_id, reviewed_id = _seed_project(db_path)
    _open_task(db_path, reviewed_id, project_id, "the task that already holds it", _DUP_CRITERION)

    conn = sqlite3.connect(str(db_path))
    try:
        result = _attach_gap_tasks(
            conn,
            work_order_id=reviewed_id,
            project_id=project_id,
            tasks=[dict(candidate, description="a reworded restatement")],
            now=_NOW,
            gap_key="k",
        )
        conn.commit()
    finally:
        conn.close()

    assert result["noted"], (
        "the attach path filed a second task for a criterion already open on the work "
        f"order and observed nothing, so the caller is not passing the criteria: {result}"
    )


def test_a_shared_criterion_is_reported_rather_than_dropped(authority):
    """Admitted is not the end of it. The observation has to reach the verdict.

    Measured on the live authority: 4 groups covering 9 OPEN tasks share a work order and
    an acceptance criterion, and in all 35 same-gap-key duplicate groups the titles DIFFER
    -- so title dedup caught none of them.

    An unknown that stops inside the lane is a lane whose only effect is on a path nobody
    reaches, which is the mechanism-with-no-caller shape three work orders in this
    milestone were opened for. So this asserts BOTH halves: the task IS filed, because
    refusing would drop the legitimate case, AND the observation comes back out.
    """
    from core.work_orders.verify_gaps import _attach_gap_tasks

    db_path = authority
    project_id, _milestone_id, reviewed_id = _seed_project(db_path)
    _open_task(db_path, reviewed_id, project_id, "the original wording", _DUP_CRITERION)

    conn = sqlite3.connect(str(db_path))
    try:
        result = _attach_gap_tasks(
            conn,
            work_order_id=reviewed_id,
            project_id=project_id,
            tasks=[
                {
                    "title": "the same finding, reworded by a later grader",
                    "description": "restatement",
                    "acceptance_criteria": _DUP_CRITERION,
                }
            ],
            now=_NOW,
            gap_key="k",
        )
        conn.commit()
    finally:
        conn.close()

    assert result["added"] == 1, f"the shared criterion refused the task: {result}"
    assert result["noted"], (
        "a second task carrying an open criterion was filed with no observation, so one "
        "check run will mark both done and nothing said so"
    )
    reasons = " ".join(u["reason"] for n in result["noted"] for u in n["unknowns"])
    assert "criterion" in reasons, reasons
    assert "reported rather than decided" in reasons, (
        "the observation does not say it is an observation, so a reader cannot tell a "
        f"question from a verdict: {reasons}"
    )


def test_the_criterion_comparison_is_what_raises_the_question(authority):
    """Which field did the observing -- asserted, not assumed.

    The Herald acts on title OR criterion, so a test that only shows "something was said
    about the second task" is satisfied by the title check that was already there. This
    separates them: both candidates below carry titles that appear nowhere on the work
    order, so the title lane cannot fire, and the ONLY difference between the quiet one and
    the observed one is whether its criterion is already open.

    That is what makes this falsifiable: drop `existing_criteria` from the Herald and the
    observed case goes quiet, turning this red while a title-only test stays green.
    """
    from core.work_orders.verify_gaps import _attach_gap_tasks

    db_path = authority
    project_id, _milestone_id, reviewed_id = _seed_project(db_path)
    _open_task(db_path, reviewed_id, project_id, "already here", _DUP_CRITERION)

    conn = sqlite3.connect(str(db_path))
    try:
        result = _attach_gap_tasks(
            conn,
            work_order_id=reviewed_id,
            project_id=project_id,
            tasks=[
                {
                    "title": "distinct wording, distinct claim",
                    "description": "genuinely new work",
                    "acceptance_criteria": _OTHER_CRITERION,
                },
                {
                    "title": "distinct wording, same claim",
                    "description": "a restatement",
                    "acceptance_criteria": _DUP_CRITERION,
                },
            ],
            now=_NOW,
            gap_key="k",
        )
        conn.commit()
    finally:
        conn.close()

    assert result["added"] == 2, f"both are admitted; only one is remarked on: {result}"
    observed = {n["title"] for n in result["noted"]}
    assert observed == {"distinct wording, same claim"}, (
        "the wrong candidate was flagged, so the comparison is not keyed on the criterion: "
        f"{observed}"
    )

    # AND TWO REWORDINGS IN ONE BATCH. A set built only from what was already in the
    # database says nothing about what this very loop just wrote -- the condition
    # surviving inside its own fix, one iteration apart.
    project_b, _m_b, wo_b = _seed_project(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        batch = _attach_gap_tasks(
            conn,
            work_order_id=wo_b,
            project_id=project_b,
            tasks=[
                {
                    "title": "first wording",
                    "description": "x",
                    "acceptance_criteria": _OTHER_CRITERION,
                },
                {
                    "title": "second wording",
                    "description": "x",
                    "acceptance_criteria": _OTHER_CRITERION,
                },
            ],
            now=_NOW,
            gap_key="k",
        )
        conn.commit()
    finally:
        conn.close()

    assert [n["title"] for n in batch["noted"]] == ["second wording"], (
        "a criterion written by this loop was not compared against, so two rewordings "
        f"filed in one pass with nothing said: {batch}"
    )
    assert len(_criteria_on(db_path, wo_b)) == 2, "both are filed; that is the point"


def test_no_open_task_shares_a_criterion_with_a_sibling(authority):
    """The count of how much of this is already filed.

    The Herald reports on NEW tasks. This is the standing count of what is already in the
    authority, and it belongs beside the other uncheckable count because it is the same
    failure with the opposite cause: a task with no criterion is uncheckable because
    nothing names a check; a task whose criterion is also a sibling's is uncheckable
    because one run marks both done and neither can fail alone.

    Driven on a seeded authority rather than asserted against the operator's live database
    -- a test that reads live state passes or fails on whose machine it runs, and in CI it
    would be skipped or green for no reason. The live number is held by this work order's
    originating symptom, which close re-runs.
    """
    from core.gates.task_criteria_baseline import measure

    db_path = authority
    project_id, _milestone_id, reviewed_id = _seed_project(db_path)

    clean = measure(db_path)
    assert clean["status"] == "computed", clean
    assert clean["shared_criterion"] == 0, clean

    _open_task(db_path, reviewed_id, project_id, "one wording", _DUP_CRITERION)
    _open_task(db_path, reviewed_id, project_id, "another wording", _DUP_CRITERION)

    both = measure(db_path)
    assert both["shared_criterion"] == 2, (
        "two open tasks on one work order carry one criterion and the count did not see "
        f"them, so the condition is unreported: {both}"
    )

    # SCOPED TO ONE WORK ORDER. Two work orders may name the same node without either
    # being a duplicate of the other -- they are different work verified the same way.
    project_b, _m_b, wo_b = _seed_project(db_path)
    _open_task(db_path, wo_b, project_b, "elsewhere entirely", _DUP_CRITERION)
    assert measure(db_path)["shared_criterion"] == 2, (
        "a criterion shared ACROSS work orders was counted, so the number reports "
        "unrelated work orders as duplicating each other"
    )

    # A criterion shared with a task that is DONE is not outstanding duplicate work, and
    # counting it would report a condition nobody can act on.
    project_c, _m_c, wo_c = _seed_project(db_path)
    _open_task(db_path, wo_c, project_c, "still open", _DUP_CRITERION)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description,"
            "  acceptance_criteria, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'finished', '', ?, 'complete', ?, ?)",
            (str(uuid.uuid4()), wo_c, project_c, _DUP_CRITERION, _NOW, _NOW),
        )
        conn.commit()
    finally:
        conn.close()

    assert measure(db_path)["shared_criterion"] == 2, (
        "a criterion shared with a COMPLETE task was counted as a duplicate, so the "
        "number reports finished work as outstanding"
    )


def _gap_carrying(criterion: str, title: str) -> dict:
    return {
        "title": "a class with a tracker",
        "description": "raised by review",
        "category": "durability",
        "type": "infrastructure",
        "tasks": [{"title": title, "description": "x", "acceptance_criteria": criterion}],
    }


def test_the_merge_path_carries_the_observation_too(authority):
    """The sibling call site dropped it, for the fourth time.

    `_attach_gap_tasks` returns `noted`. The attach-onto-the-reviewed-work-order call site
    folds it into the record as `admission_unknowns`; the merge-into-an-existing-work-order
    call site read only `unfiled`, so on that branch a Herald observation was computed and
    silently dropped. Found by the independent review of cc54ab90 -- in the change that
    added the key, directly beneath a comment recording the same lesson from last time.

    Driven through `_insert_gap_work_orders`, not through `_attach_gap_tasks`, because the
    callee returned the value correctly both times. The defect is in which keys a CALL SITE
    reads, and only the real dispatch reaches the branch that chooses between them.
    """
    from core.work_orders.verify_gaps import _insert_gap_work_orders

    db_path = authority
    project_id, milestone_id, reviewed_id = _seed_project(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        # Pass one spawns the sibling tracker and files the criterion on it.
        _insert_gap_work_orders(
            conn,
            gaps=[_gap_carrying(_DUP_CRITERION, "the first wording")],
            project_id=project_id,
            milestone_id=milestone_id,
            reviewed_work_order_id=reviewed_id,
            reviewed_wo_title="Reviewed",
            reviewed_wo_sequence=1,
        )
        # Pass two finds that tracker and MERGES into it -- the branch under test --
        # carrying a differently-titled task whose criterion is already filed there.
        second = _insert_gap_work_orders(
            conn,
            gaps=[_gap_carrying(_DUP_CRITERION, "the second wording")],
            project_id=project_id,
            milestone_id=milestone_id,
            reviewed_work_order_id=reviewed_id,
            reviewed_wo_title="Reviewed",
            reviewed_wo_sequence=1,
        )
        conn.commit()
    finally:
        conn.close()

    merged = [r for r in second if r.get("merged_into_existing")]
    assert merged, f"pass two did not take the merge branch, so this proves nothing: {second}"
    assert any(r.get("admission_unknowns") for r in merged), (
        "the merge call site filed a task carrying a criterion already on that work order "
        "and reported nothing. The callee computed the observation and the caller dropped "
        f"it, which is the whole defect: {merged}"
    )


def test_both_call_sites_report_the_same_keys(authority):
    """Two callers of one function, diverged four times now.

    Twice on event emission, once on the acceptance criterion, once on `noted`. Each was
    found separately, after shipping, by someone reading the diff.

    COMPARED TO EACH OTHER, NOT TO A NAMED LIST -- and the first version of this test did
    not do that, despite saying so. It built both key sets by iterating a hardcoded
    `{"unfiled_findings", "admission_unknowns"}`, so it could only ever see the two keys
    that had already diverged. The independent review of 8a2d68a1 disproved the docstring
    empirically: it added a fifth key to the merge record alone and this test passed. The
    claim "a fifth key is covered without an edit" was false as written.

    WHAT DISTINGUISHES A FINDING KEY, without naming any. Every key that carries a finding
    holds a LIST of them; every other key on these records is a string, a bool or an int
    (`work_order_id`, `gap_key`, `attached_to_reviewed`, `tasks_added`). So the sets are
    built from the records' own items by VALUE SHAPE, and a fifth list-valued key added to
    one call site is caught with no edit here -- which is what the docstring claimed and
    now describes.

    Empty lists fall out on both sides, which matters: `_insert_gap_work_orders` runs
    `record.setdefault("unfiled_findings", [])` over every record, so membership would be
    universally true and prove nothing. Truthiness is what keeps that from masking a real
    divergence.

    Driven rather than read out of the source, because a key read into a branch nothing
    reaches would satisfy a source comparison exactly as well as a live one.
    """
    from core.work_orders.verify_gaps import _insert_gap_work_orders

    def finding_keys(record: dict) -> set[str]:
        """Keys carrying findings: the list-valued ones, by shape and not by name."""
        return {k for k, v in record.items() if isinstance(v, list) and v}

    db_path = authority

    # ATTACH BRANCH: the reviewed work order is open and incomplete, so the gap is its own
    # unfinished work and lands as a task on it. Seed the criterion first so the Herald has
    # something to observe.
    p_a, m_a, wo_a = _seed_project(db_path)
    _open_task(db_path, wo_a, p_a, "already on the reviewed work order", _DUP_CRITERION)
    conn = sqlite3.connect(str(db_path))
    try:
        attached = _insert_gap_work_orders(
            conn,
            gaps=[_gap_carrying(_DUP_CRITERION, "reworded for the attach branch")],
            project_id=p_a,
            milestone_id=m_a,
            reviewed_work_order_id=wo_a,
            reviewed_wo_title="Reviewed",
            reviewed_wo_sequence=1,
            reviewed_wo_incomplete=True,
        )
        conn.commit()
    finally:
        conn.close()

    # MERGE BRANCH: a prior spawn exists, so the second pass merges into it.
    p_b, m_b, wo_b = _seed_project(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        _insert_gap_work_orders(
            conn,
            gaps=[_gap_carrying(_DUP_CRITERION, "the first wording")],
            project_id=p_b,
            milestone_id=m_b,
            reviewed_work_order_id=wo_b,
            reviewed_wo_title="Reviewed",
            reviewed_wo_sequence=1,
        )
        merged_run = _insert_gap_work_orders(
            conn,
            gaps=[_gap_carrying(_DUP_CRITERION, "the second wording")],
            project_id=p_b,
            milestone_id=m_b,
            reviewed_work_order_id=wo_b,
            reviewed_wo_title="Reviewed",
            reviewed_wo_sequence=1,
        )
        conn.commit()
    finally:
        conn.close()

    a_rec = next((r for r in attached if r.get("attached_to_reviewed")), None)
    m_rec = next((r for r in merged_run if r.get("merged_into_existing")), None)
    assert a_rec is not None, f"the attach branch was not reached: {attached}"
    assert m_rec is not None, f"the merge branch was not reached: {merged_run}"

    a_keys = finding_keys(a_rec)
    m_keys = finding_keys(m_rec)
    assert a_keys == m_keys, (
        f"the attach record reports {sorted(a_keys)} and the merge record reports "
        f"{sorted(m_keys)} for the same finding. One caller of _attach_gap_tasks carries "
        "something the other drops, which has now happened four times in this pair"
    )
    assert "admission_unknowns" in a_keys, (
        "neither branch reported the shared criterion, so this test would pass with the "
        f"observation dropped on BOTH sides: attach={a_rec} merge={m_rec}"
    )
