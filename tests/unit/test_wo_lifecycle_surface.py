"""WO-WO-LIFECYCLE-SURFACE: fan out, because a straight line is not always right.

Operator: "why can't we utilize a fan out approach across milestones or work orders that
are separate. walking down a straight line does not always make sense."

MEASURED 2026-08-26, and the straight line was IMPOSED rather than derived. The dependency
graph was already correct and already honoured — 88 edges, checked by
``NOT EXISTS (... dep_wo.status != 'closed')``. Two other things sat on top of it and
overrode it:

  1. WRITE SIDE, a hard refusal. ``start_work_order`` rejected any work order while ANY
     earlier milestone had open work. It refused to let THIS work order start:
     "Cannot start this work order — 17 work order(s) in earlier milestones are
     incomplete." The change that removes the constraint could not begin under it.

  2. READ SIDE, invisibility. ``get_next_work_order`` filtered to
     ``m.order_index = (SELECT MIN(...))`` and took ``LIMIT 1``, so only the lowest
     numbered milestone with open work was ever offered — 45 open milestones, one answer.

Neither consulted independence. Both are gone: a declared dependency blocks, milestone
order informs. Measured after the change on the live authority: the ready set returns 43
work orders across 6 milestones, 3 of them already in progress, where one was visible
before.

AND IT REPORTS WHAT IT DOES NOT KNOW. All 43 have no declared dependencies, so each says
"independence NOT verified" rather than presenting itself as safe to parallelise — the
absent-is-not-clean rule this milestone keeps relearning.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.projects.queries import ready_work_orders

_NOW = "2026-08-26T00:00:00+00:00"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(path)
    return path


def _project(conn: sqlite3.Connection) -> str:
    pid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, "P", "", "active", _NOW, _NOW),
    )
    return pid


def _milestone(conn: sqlite3.Connection, pid: str, title: str, order_index: int) -> str:
    mid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, description, status, order_index,"
        "  created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (mid, pid, title, "", "active", order_index, _NOW, _NOW),
    )
    return mid


def _wo(
    conn: sqlite3.Connection,
    pid: str,
    mid: str | None,
    title: str,
    *,
    status: str = "created",
    description: str = "d",
    seq: int | None = 1,
) -> str:
    wid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at, sequence_order)"
        " VALUES (?,?,?,?,?,'infrastructure',?,?,?,?)",
        (wid, pid, mid, title, description, status, _NOW, _NOW, seq),
    )
    return wid


def _depend(conn: sqlite3.Connection, wo: str, on: str) -> None:
    conn.execute(
        "INSERT INTO work_order_dependencies (work_order_id, depends_on_id, created_at)"
        " VALUES (?,?,?)",
        (wo, on, _NOW),
    )


# ── The ready set spans milestones ────────────────────────────────────────────


def test_the_ready_set_spans_every_open_milestone(db):
    """THE STRAIGHT LINE, GONE. Before, only the lowest-numbered milestone with open work
    was ever offered — so a work order in milestone 90 was invisible while anything in
    milestone 1 remained open, regardless of whether they had anything to do with each
    other."""
    conn = sqlite3.connect(str(db))
    pid = _project(conn)
    first = _milestone(conn, pid, "first", 1)
    later = _milestone(conn, pid, "much later", 90)
    early_wo = _wo(conn, pid, first, "early work")
    late_wo = _wo(conn, pid, later, "independent later work")
    conn.commit()

    ready = ready_work_orders(conn, pid)
    ids = {r["work_order_id"] for r in ready}

    assert early_wo in ids
    assert late_wo in ids, "an independent later milestone must be reachable"
    assert len({r["milestone_id"] for r in ready}) == 2, "the set spans milestones"
    conn.close()


def test_a_dependency_still_blocks_a_work_order(db):
    """The constraint that IS real. Removing milestone ordering must not remove
    dependency enforcement — that would trade a false constraint for no constraint."""
    conn = sqlite3.connect(str(db))
    pid = _project(conn)
    mid = _milestone(conn, pid, "m", 1)
    blocker = _wo(conn, pid, mid, "must finish first")
    blocked = _wo(conn, pid, mid, "waits for the blocker")
    _depend(conn, blocked, blocker)
    conn.commit()

    ids = {r["work_order_id"] for r in ready_work_orders(conn, pid)}
    assert blocker in ids
    assert blocked not in ids, "a declared, unclosed dependency still blocks"

    conn.execute(
        "UPDATE business_work_orders SET status='closed' WHERE work_order_id=?", (blocker,)
    )
    conn.commit()
    ids = {r["work_order_id"] for r in ready_work_orders(conn, pid)}
    assert blocked in ids, "and releases once the dependency closes"
    conn.close()


def test_in_progress_work_orders_appear_marked(db):
    """Switching work orders is the point, so the ones already underway have to be
    visible as such — 8 were in_progress on the live authority while the surface showed
    one."""
    conn = sqlite3.connect(str(db))
    pid = _project(conn)
    mid = _milestone(conn, pid, "m", 1)
    working = _wo(conn, pid, mid, "already underway", status="in_progress")
    waiting = _wo(conn, pid, mid, "not started")
    conn.commit()

    ready = {r["work_order_id"]: r for r in ready_work_orders(conn, pid)}
    assert ready[working]["status"] == "in_progress"
    assert ready[waiting]["status"] == "created"
    conn.close()


def test_an_in_progress_work_order_appears_even_when_its_dependency_is_open(db):
    """Work already underway is a fact, not a recommendation. Hiding it because a
    dependency is open would make an in-flight work order vanish from the surface an
    operator uses to find it."""
    conn = sqlite3.connect(str(db))
    pid = _project(conn)
    mid = _milestone(conn, pid, "m", 1)
    blocker = _wo(conn, pid, mid, "open blocker")
    underway = _wo(conn, pid, mid, "started anyway", status="in_progress")
    _depend(conn, underway, blocker)
    conn.commit()

    ids = {r["work_order_id"] for r in ready_work_orders(conn, pid)}
    assert underway in ids
    conn.close()


def test_a_milestoneless_work_order_is_not_dropped(db):
    """Two open work orders have no milestone on the live authority. A LEFT JOIN keeps
    them; an INNER JOIN would silently lose work."""
    conn = sqlite3.connect(str(db))
    pid = _project(conn)
    orphan = _wo(conn, pid, None, "no milestone")
    conn.commit()
    assert orphan in {r["work_order_id"] for r in ready_work_orders(conn, pid)}
    conn.close()


# ── What the set does NOT know ────────────────────────────────────────────────


def test_no_declared_dependencies_is_reported_not_implied_safe(db):
    """88 edges across 481 sequenced work orders means most declare none. A work order
    with no recorded dependency looks independent to the selector whether or not it is,
    so the set must SAY that rather than presenting it as verified parallel-safe."""
    conn = sqlite3.connect(str(db))
    pid = _project(conn)
    mid = _milestone(conn, pid, "m", 1)
    bare = _wo(conn, pid, mid, "declares nothing")
    conn.commit()

    entry = next(r for r in ready_work_orders(conn, pid) if r["work_order_id"] == bare)
    assert entry["declared_dependencies"] == 0
    assert "NOT verified" in entry["independence"], entry["independence"]
    conn.close()


def test_a_closed_dependency_is_reported_as_actually_checked(db):
    """The converse: where a dependency WAS declared and is closed, the set may say so —
    that one really was verified."""
    conn = sqlite3.connect(str(db))
    pid = _project(conn)
    mid = _milestone(conn, pid, "m", 1)
    done = _wo(conn, pid, mid, "finished", status="created")
    dependent = _wo(conn, pid, mid, "depends on it")
    _depend(conn, dependent, done)
    conn.execute("UPDATE business_work_orders SET status='closed' WHERE work_order_id=?", (done,))
    conn.commit()

    entry = next(r for r in ready_work_orders(conn, pid) if r["work_order_id"] == dependent)
    assert entry["declared_dependencies"] == 1
    assert "all closed" in entry["independence"]
    assert "NOT verified" not in entry["independence"]
    conn.close()


def test_overlapping_module_boundaries_are_flagged_in_the_ready_set(db):
    """Independent in the dependency graph can still mean the same files, and fan-out
    makes that likely rather than theoretical.

    THERE IS NO module_boundary COLUMN — I assumed one and the query raised
    `no such column: wo.module_boundary`. The boundary is declared in the description as
    "Module boundary: a, b." and parsed by runtime.lib.enforcement.boundary_globs, the
    same parser the on-edit hook and verify use. Reusing it is why those consumers cannot
    disagree about what a work order owns.
    """
    conn = sqlite3.connect(str(db))
    pid = _project(conn)
    mid = _milestone(conn, pid, "m", 1)
    a = _wo(conn, pid, mid, "touches gaps", description="Module boundary: core/work_orders/x.py.")
    b = _wo(
        conn, pid, mid, "also touches gaps", description="Module boundary: core/work_orders/x.py."
    )
    c = _wo(conn, pid, mid, "elsewhere", description="Module boundary: interfaces/cli/y.py.")
    conn.commit()

    ready = {r["work_order_id"]: r for r in ready_work_orders(conn, pid)}
    assert ready[a].get("boundary_overlap"), "the collision must be surfaced"
    assert b[:8] in ready[a]["boundary_overlap"]
    assert "core/work_orders/x.py" in ready[a]["boundary_overlap"]
    assert not ready[c].get("boundary_overlap"), "a disjoint boundary is not a collision"
    conn.close()


def test_a_work_order_declaring_no_boundary_is_not_reported_as_colliding(db):
    """No declared boundary means nothing to compare — which is not the same as verified
    no-collision, and must not read as either a clash or an all-clear."""
    conn = sqlite3.connect(str(db))
    pid = _project(conn)
    mid = _milestone(conn, pid, "m", 1)
    bare = _wo(conn, pid, mid, "declares no boundary", description="no boundary clause here")
    conn.commit()

    entry = next(r for r in ready_work_orders(conn, pid) if r["work_order_id"] == bare)
    assert entry["module_boundary"] == []
    assert "boundary_overlap" not in entry
    conn.close()


def test_the_internal_description_does_not_leak_into_the_payload(db):
    """The description is read to parse the boundary; it is not part of the surface. A
    full description per entry would bloat every project-state response."""
    conn = sqlite3.connect(str(db))
    pid = _project(conn)
    mid = _milestone(conn, pid, "m", 1)
    _wo(conn, pid, mid, "w", description="Module boundary: core/x.py. " + "long prose " * 50)
    conn.commit()

    for entry in ready_work_orders(conn, pid):
        assert "_description" not in entry
        assert "description" not in entry
    conn.close()


# -- WO-LOOP-TEXT-STALE: prose about an engine is a second implementation of it -


def _next_iteration_command() -> str:
    """The autonomous loop's selector instructions, as an agent reads them."""
    import yaml

    data = yaml.safe_load(
        Path("canonical/workflows/execute-work-orders.yaml").read_text(encoding="utf-8")
    )
    node = next(n for n in data["nodes"] if n["id"] == "next-iteration")
    return node["command"]


def _live_bullets(command: str) -> list[str]:
    """Bullets are live claims. The correction note quotes the old text as history, so a
    substring search over the whole block cannot tell an assertion from a citation -- the
    same quotation problem the evidence-backed-output gate had to solve."""
    return [ln.strip() for ln in command.splitlines() if ln.strip().startswith("- ")]


def test_the_loop_text_matches_the_selector():
    """MEASURED 2026-08-28. The node told an agent the selector was "scoped to the
    milestone with the lowest order_index that has open WOs" and that "WOs without a valid
    milestone are excluded (never surfaced)", then added "Trust the selector output
    exactly".

    PR #681 removed the `m.order_index = (SELECT MIN(...))` filter and changed the
    milestone join to a LEFT JOIN, making both false. An agent following the old text
    faithfully would have worked AGAINST the fan-out -- and the stale copy is the one an
    agent reads.
    """
    command = _next_iteration_command()
    bullets = " ".join(_live_bullets(command))

    assert "lowest order_index" not in bullets, (
        "a live bullet still claims milestone-scoped selection, which the engine no " "longer does"
    )
    assert "never surfaced" not in bullets, (
        "a live bullet still claims milestone-less work orders are excluded; the join is "
        "a LEFT JOIN and two such work orders exist on the live authority"
    )
    assert "EVERY open milestone" in command
    assert "LEFT JOIN" in command


def test_the_engine_still_matches_what_the_text_now_claims():
    """THE OTHER DIRECTION, which is what makes this a pin rather than a one-off edit.
    If someone reinstates milestone scoping in the query, this fails and points at the
    prose that would then be lying."""
    source = Path("core/projects/queries.py").read_text(encoding="utf-8")

    body = source.split("def get_next_work_order", 1)[1].split("def ", 1)[0]
    assert "order_index = (SELECT MIN" not in body, (
        "get_next_work_order scopes to one milestone again -- the loop text now says every "
        "open milestone is reachable, so one of the two is wrong"
    )
    assert "LEFT JOIN business_milestones" in body, (
        "the milestone join is no longer a LEFT JOIN -- milestone-less work orders would "
        "be dropped, which the loop text says does not happen"
    )


def test_the_correction_records_what_changed_and_why():
    """A silent edit leaves the next reader unable to tell which of two contradictory
    descriptions was ever true. The note names the PR and states the old text was false."""
    command = _next_iteration_command()
    assert "previously said" in command
    assert "#681" in command
    assert "making both statements false" in command


def _one(db: Path, sql: str, params: tuple) -> str | None:
    """First column of the first row, or None."""
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(sql, params).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


# -- Task 1: the authoring door --------------------------------------------------


def _run(argv: list[str], home: Path) -> tuple[int, str]:
    """Drive the REAL parser and dispatcher, not the handler functions.

    Calling the handlers directly would prove they work while leaving the thing the task
    is about -- that a person can type this -- unproven. A wrong `dest=`, a parser never
    registered, or a dispatch branch that was never added would all pass a handler-level
    test and fail a user.

    THE ENV OVERRIDES ARE LOAD-BEARING. ``create_*`` accepts ``dream_studio_home`` but its
    event path ignores it: ``write_event`` resolves ``get_spool_root()`` and ``sync_tick()``
    builds a ``ProjectionRunner()`` with no path, so both follow process-wide environment
    rather than the argument. conftest's autouse ``guard_real_homedir`` already keeps that
    off the operator's authority -- measured, the live orphan count did not move across
    these runs -- but its guard DB is a different temp file from the ``db`` fixture, so
    without this the row materialises somewhere the test never looks. The underlying defect
    is registered as ff7c6ccc, "A temp-database mutation must not emit to the live spool".
    """
    import argparse
    import io
    import os
    from contextlib import redirect_stdout

    from interfaces.cli.commands import milestone as milestone_cmd
    from interfaces.cli.commands import work_order_dispatch as wo_cmd

    parser = argparse.ArgumentParser(prog="ds")
    sub = parser.add_subparsers(dest="command", required=True)
    milestone_cmd.register(sub)
    wo_cmd.register(sub)

    args = parser.parse_args(argv)
    module = milestone_cmd if args.command == "milestone" else wo_cmd

    keys = ("DREAM_STUDIO_HOME", "DS_SPOOL_ROOT", "DREAM_STUDIO_DB_PATH")
    prior = {k: os.environ.get(k) for k in keys}
    os.environ["DREAM_STUDIO_HOME"] = str(home)
    os.environ["DS_SPOOL_ROOT"] = str(home / "events")
    os.environ["DREAM_STUDIO_DB_PATH"] = str(home / "state" / "studio.db")
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            code = module.dispatch(args, source_root=home, dream_studio_home=home)
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return code, buf.getvalue()


def test_a_milestone_work_order_and_task_can_be_created_from_the_cli(db, tmp_path):
    """THE REASON THIS TASK EXISTS.

    ``create_milestone``, ``create_work_order`` and ``create_task`` all existed and all
    emitted canonical events. What did not exist was any way to reach them from the CLI:
    ``ds milestone`` offered only close/list/status, and ``ds work-order`` offered
    start/close/task-done but no create and no add-task.

    So every authoring action was raw SQL by an adapter. That is a rule violation on its
    own -- ``rule3-cli-business-state-writer`` says the CLI owns business-state writes --
    and it is also why no structural invariant could be enforced: with no single door,
    there was nowhere to put a check. Measured on the live authority 2026-08-28: 49 of 128
    open work orders carry one task or none, and 29 of 45 open milestones carry one open
    work order or none. Nothing could have refused those.
    """
    import sqlite3
    import uuid

    pid = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, "P", "", "active", _NOW, _NOW),
    )
    conn.commit()
    conn.close()

    code, out = _run(
        ["milestone", "create", pid, "--title", "Ship the authoring door", "--order", "1"],
        tmp_path,
    )
    assert code == 0, out
    mid = _one(db, "SELECT milestone_id FROM business_milestones WHERE project_id = ?", (pid,))
    assert mid, "the milestone event did not reach the projection"

    code, out = _run(
        [
            "work-order",
            "create",
            pid,
            "--milestone",
            mid,
            "--title",
            "Wire the CLI",
            "--type",
            "infrastructure",
        ],
        tmp_path,
    )
    assert code == 0, out
    wid = _one(db, "SELECT work_order_id FROM business_work_orders WHERE milestone_id = ?", (mid,))
    assert wid, "the work order event did not reach the projection"

    code, out = _run(
        [
            "work-order",
            "add-task",
            wid,
            "--title",
            "Add the parser",
            "--acceptance",
            "TEST-CHECK: tests/unit/test_wo_lifecycle_surface.py",
        ],
        tmp_path,
    )
    assert code == 0, out
    tid = _one(db, "SELECT task_id FROM business_tasks WHERE work_order_id = ?", (wid,))
    assert tid, "the task event did not reach the projection"


def test_creating_a_work_order_says_it_needs_more_than_one_task(db, tmp_path):
    """A door is only worth having if it says what good work looks like on the way through.

    49 of 128 open work orders carry one task or none -- not because anyone decided a
    single-task work order was right, but because nothing ever said otherwise at the moment
    of creation. Task 2 turns this into a refusal; the message has to be there first, or
    the refusal arrives with no prior warning.
    """
    import sqlite3
    import uuid

    pid, mid = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, "P", "", "active", _NOW, _NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, description, status, order_index,"
        "  created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (mid, pid, "M", "", "active", 1, _NOW, _NOW),
    )
    conn.commit()
    conn.close()

    code, out = _run(
        ["work-order", "create", pid, "--milestone", mid, "--title", "T"],
        tmp_path,
    )
    assert code == 0, out
    assert "MORE THAN ONE task" in out
    assert "add-task" in out, "and it must name the command that fixes it"


def test_a_task_with_no_executable_criterion_is_told_so(db, tmp_path):
    """Close re-runs a task's acceptance criterion. A task without one cannot be verified
    at close -- it can only be asserted done. Saying so at creation is the cheapest moment;
    by close the author has moved on."""
    import sqlite3
    import uuid

    pid, mid = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, "P", "", "active", _NOW, _NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, description, status, order_index,"
        "  created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (mid, pid, "M", "", "active", 1, _NOW, _NOW),
    )
    conn.commit()
    conn.close()

    _run(["work-order", "create", pid, "--milestone", mid, "--title", "T"], tmp_path)
    wid = _one(db, "SELECT work_order_id FROM business_work_orders WHERE milestone_id = ?", (mid,))

    _, bare = _run(["work-order", "add-task", wid, "--title", "T"], tmp_path)
    assert "No executable acceptance criterion" in bare
    assert "TEST-CHECK" in bare, "the message must name what would satisfy it"

    _, withac = _run(
        ["work-order", "add-task", wid, "--title", "T", "--acceptance", "TEST-CHECK: x::y"],
        tmp_path,
    )
    assert (
        "No executable acceptance criterion" not in withac
    ), "the warning fired on a task that HAS one -- it would be noise and get ignored"


def test_add_task_asks_for_the_project_rather_than_refusing_an_unprojected_work_order(db, tmp_path):
    """``create_task`` deliberately tolerates a work order that was emitted but not yet
    materialised -- the comment in ``mutations.py`` says so. It needs a project id it does
    not derive, so the CLI reads one from the work order row. When the row is absent the
    CLI must ASK, not refuse: refusing would reject exactly the just-created work order the
    mutation goes out of its way to accept.
    """
    import uuid

    code, out = _run(
        ["work-order", "add-task", str(uuid.uuid4()), "--title", "T"],
        tmp_path,
    )
    assert code == 1
    assert "--project" in out, "the error must name the way through, not just the problem"
    assert "not projected yet" in out


# -- Task 2: the two structural invariants ---------------------------------------


def _scaffold(db: Path, *, tasks: int, siblings: int) -> tuple[str, str, str]:
    """A project, a milestone with *siblings* work orders, the first carrying *tasks*."""
    import sqlite3
    import uuid

    pid, mid = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, "P", "", "active", _NOW, _NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, description, status, order_index,"
        "  created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (mid, pid, "M", "", "active", 1, _NOW, _NOW),
    )
    first = ""
    for index in range(siblings):
        wid = str(uuid.uuid4())
        first = first or wid
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            "  work_order_type, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (wid, pid, mid, f"W{index}", "", "created", "infrastructure", _NOW, _NOW),
        )
        # The structural invariants judge only work orders the AUTHORITY created, and
        # `create_work_order` is what emits this event. Without it these rows are raw-SQL
        # inserts -- exactly the hermetic-fixture shape the gate is now scoped to ignore --
        # so the fixture has to look like what it is testing.
        conn.execute(
            "INSERT INTO business_canonical_events"
            " (event_id, received_at, event_type, event_timestamp, schema_version,"
            "  trace, payload, project_id, milestone_id, work_order_id, severity, source)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                _NOW,
                "work_order.created",
                _NOW,
                1,
                json.dumps({"work_order_id": wid, "project_id": pid}),
                json.dumps({"title": f"W{index}", "status": "created"}),
                pid,
                mid,
                wid,
                "info",
                "test-fixture",
            ),
        )
    for index in range(tasks):
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            "  created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), first, pid, f"T{index}", "", "pending", _NOW, _NOW),
        )
    conn.commit()
    conn.close()
    return pid, mid, first


def test_a_single_task_work_order_is_refused(db):
    """OPERATOR RULING: a work order should ALWAYS have multiple tasks.

    Measured on the live authority 2026-08-28: 49 of 128 open work orders carry one task
    or none. A single-task work order is a task wearing the wrong label -- it closes on
    one check and gets almost none of the verification a work order is supposed to attract.

    Judged at START, not at creation. A work order has zero tasks at the moment it is
    created, always, including every correct one; a creation-time check could only refuse
    everything or nothing. Start is where the authority treats the structure as final -- it
    writes the context and hands the task list to whoever executes it -- and it is the last
    point where adding a task is cheap.
    """
    from core.work_orders.structural_invariants import check_structure

    _, _, wid = _scaffold(db, tasks=1, siblings=2)
    violations = check_structure(wid, db_path=db)

    assert [v.scope for v in violations] == [
        "work_order"
    ], f"expected only the task invariant to fire, got {[v.scope for v in violations]}"
    assert violations[0].found == 1
    assert "add-task" in violations[0].message, "a refusal must name the command that fixes it"

    _, _, ok_wid = _scaffold(db, tasks=2, siblings=2)
    assert check_structure(ok_wid, db_path=db) == [], "two tasks satisfies the invariant"


def test_a_single_work_order_milestone_is_refused(db):
    """OPERATOR RULING: a milestone should ALWAYS have more than one work order.

    Measured 2026-08-28: 29 of 45 open milestones carry one open work order or none. A
    one-work-order milestone is a work order with extra ceremony -- it sequences nothing,
    and its close gates grade a single diff twice.
    """
    from core.work_orders.structural_invariants import check_structure

    _, _, wid = _scaffold(db, tasks=3, siblings=1)
    violations = check_structure(wid, db_path=db)

    assert [v.scope for v in violations] == ["milestone"]
    assert violations[0].found == 1
    assert "ds work-order create" in violations[0].message


def test_both_invariants_are_reported_together(db):
    """Reporting one at a time would make the author fix, retry, and be refused again.
    Every violation the check can see is returned in one pass."""
    from core.work_orders.structural_invariants import check_structure

    _, _, wid = _scaffold(db, tasks=0, siblings=1)
    assert {v.scope for v in check_structure(wid, db_path=db)} == {"work_order", "milestone"}


def test_closed_siblings_still_count_toward_the_milestone(db):
    """Counting only OPEN siblings would call a finished milestone malformed: its work
    orders are closed precisely because it went well."""
    import sqlite3

    from core.work_orders.structural_invariants import check_structure

    _, mid, wid = _scaffold(db, tasks=2, siblings=2)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE business_work_orders SET status = 'closed'"
        " WHERE milestone_id = ? AND work_order_id != ?",
        (mid, wid),
    )
    conn.commit()
    conn.close()

    assert check_structure(wid, db_path=db) == []


def test_a_work_order_with_no_milestone_is_not_judged_on_the_milestone_invariant(db):
    """There is nothing to count. Inventing a verdict from missing data is the failure
    this repository keeps finding elsewhere -- absent is not the same as violating."""
    import sqlite3

    from core.work_orders.structural_invariants import check_structure

    _, _, wid = _scaffold(db, tasks=2, siblings=1)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE business_work_orders SET milestone_id = NULL WHERE work_order_id = ?", (wid,)
    )
    conn.commit()
    conn.close()

    assert check_structure(wid, db_path=db) == []


def test_an_unprojected_work_order_is_not_judged(db):
    """A work order created seconds ago may not be materialised yet. Refusing it would
    reject exactly the case the create path goes out of its way to support."""
    import uuid

    from core.work_orders.structural_invariants import check_structure

    assert check_structure(str(uuid.uuid4()), db_path=db) == []


def test_the_escape_is_a_recorded_reason_not_a_flag(db):
    """NEVER SILENTLY ALLOW. ``--force`` would be silent allowance under another name: it
    leaves no trace a later reader can weigh. The exception is stored on the work order as
    an operator_decision, so an exception is a thing that exists rather than an absence."""
    import pytest as _pytest

    from core.work_orders.structural_invariants import record_exception, recorded_exception

    _, _, wid = _scaffold(db, tasks=1, siblings=2)
    assert recorded_exception(wid, db_path=db) is None

    with _pytest.raises(ValueError) as exc:
        record_exception(wid, "n/a", db_path=db)
    assert "weigh" in str(exc.value), "an empty reason must be refused, not stored"

    record_exception(wid, "One task because the whole change is one line in one file.", db_path=db)
    assert "one line in one file" in (recorded_exception(wid, db_path=db) or "")


def _complete_all_tasks(db: Path, work_order_id: str) -> None:
    """Satisfy tasks_done so the structural gate is what the close is judged on.

    Without this the close fails on tasks_done and a test asserting "refused" would pass
    for the wrong reason -- the failure this repository keeps finding in its own tests.
    """
    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE business_tasks SET status = 'complete' WHERE work_order_id = ?",
        (work_order_id,),
    )
    conn.commit()
    conn.close()


def test_start_reports_the_invariants_without_blocking(db, tmp_path, monkeypatch):
    """START REPORTS; CLOSE REFUSES. Refusing here looked right and was wrong.

    ds-project decomposes only the first work order of the first milestone; its own
    instructions say the rest "get tasks when they are started (by calling
    start_work_order())". So a work order legitimately arrives at start with zero tasks and
    acquires them a moment later. Refusing here blocked the documented authoring path --
    measured, it broke 18 existing tests whose fixtures seed a work order and no tasks,
    which is exactly the shape start is supposed to accept.

    Silence would be wrong too: the author is about to write tasks, which is the cheapest
    possible moment to hear that one is not enough.
    """
    from core.work_orders.start_main import start_work_order

    _, _, wid = _scaffold(db, tasks=1, siblings=1)
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))

    result = start_work_order(
        work_order_id=wid,
        source_root=tmp_path,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )

    assert result["ok"] is True, result.get("error")
    assert {v["scope"] for v in result["structure_violations"]} == {"work_order", "milestone"}
    assert "does not block the start" in result["structure_warning"]
    assert (
        "block the close" in result["structure_warning"]
    ), "a warning must say what it will cost later, or it reads as optional"


def test_a_well_formed_work_order_starts_without_a_warning(db, tmp_path, monkeypatch):
    """The warning must be silent when the invariants hold, or it is noise and gets
    filtered out along with everything else printed at start."""
    from core.work_orders.start_main import start_work_order

    _, _, wid = _scaffold(db, tasks=2, siblings=2)
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))

    result = start_work_order(
        work_order_id=wid,
        source_root=tmp_path,
        dream_studio_home=tmp_path,
        planning_root=tmp_path / ".planning",
    )
    assert result["ok"] is True, result.get("error")
    assert "structure_warning" not in result


def test_closing_a_malformed_work_order_is_refused_with_the_escape_named(db, tmp_path):
    """THE REFUSAL, at the moment the claim is made.

    Close is where "this work order is done" gets asserted. One task then is not a
    not-yet -- it is a finished unit that was mis-sized, and the count is a fact.

    The message must name the escape. A refusal that only states the problem sends the
    author looking for a way around it, and the way they find is --force, which bypasses
    every gate at once and records no reasoning about this one.
    """
    from core.work_orders.close import close_work_order

    _, _, wid = _scaffold(db, tasks=1, siblings=1)
    _complete_all_tasks(db, wid)

    result = close_work_order(
        work_order_id=wid,
        source_root=tmp_path,
        dream_studio_home=tmp_path,
        skip_verify=True,
    )

    assert result["ok"] is False
    failures = " ".join(result.get("failures", []))
    assert "structural_invariants" in failures, result
    assert "--accept-structure" in failures, "the refusal must name the escape"
    assert "`--force` is not the answer" in failures


def test_a_recorded_reason_lets_the_close_through(db, tmp_path):
    """The escape has to actually work, or it is a wall with a sign on it -- and a wall
    gets routed around by the next person who edits the check."""
    from core.work_orders.close import close_work_order
    from core.work_orders.structural_invariants import record_exception

    _, _, wid = _scaffold(db, tasks=1, siblings=1)
    _complete_all_tasks(db, wid)
    record_exception(wid, "Single task: the change is one constant in one file.", db_path=db)

    result = close_work_order(
        work_order_id=wid,
        source_root=tmp_path,
        dream_studio_home=tmp_path,
        skip_verify=True,
    )
    failures = " ".join(result.get("failures", []))
    assert "structural_invariants" not in failures, failures


def test_a_well_formed_work_order_is_not_refused_at_close(db, tmp_path):
    """The gate has to be satisfiable by doing the right thing, not only by the escape."""
    from core.work_orders.close import close_work_order

    _, _, wid = _scaffold(db, tasks=2, siblings=2)
    _complete_all_tasks(db, wid)

    result = close_work_order(
        work_order_id=wid,
        source_root=tmp_path,
        dream_studio_home=tmp_path,
        skip_verify=True,
    )
    failures = " ".join(result.get("failures", []))
    assert "structural_invariants" not in failures, failures


def test_the_preview_and_the_close_agree_about_the_invariants(db, tmp_path):
    """A preview that omits a blocking gate is worse than no preview: it tells an author
    they are ready to close, and then the close refuses. `check_close_gates` builds its own
    failure list rather than sharing one with `close_work_order`, so every gate has to be
    added in two places -- the enumerate-the-call-sites failure this session already made
    twice, once with a completion prompt formatter and once with a milestone join.
    """
    from core.work_orders.close import check_close_gates, close_work_order

    _, _, wid = _scaffold(db, tasks=1, siblings=1)
    _complete_all_tasks(db, wid)

    preview = check_close_gates(work_order_id=wid, source_root=tmp_path, dream_studio_home=tmp_path)
    closed = close_work_order(
        work_order_id=wid, source_root=tmp_path, dream_studio_home=tmp_path, skip_verify=True
    )

    assert any("structural_invariants" in f for f in preview["gate_failures"]), preview
    assert any("structural_invariants" in f for f in closed.get("failures", [])), closed
    assert preview["gates_pass"] is False


def test_the_refusal_names_the_command_it_can_actually_be_answered_with(db, tmp_path):
    """The refusal happens at CLOSE, so it must name close. The first cut said
    `ds work-order start <id> --accept-structure` -- telling someone trying to close a work
    order to re-start it. A message that names the wrong command sends the reader to the
    thing that IS reachable, which is `--force`.
    """
    from core.work_orders.close import close_work_order

    _, _, wid = _scaffold(db, tasks=1, siblings=1)
    _complete_all_tasks(db, wid)
    result = close_work_order(
        work_order_id=wid, source_root=tmp_path, dream_studio_home=tmp_path, skip_verify=True
    )

    failures = " ".join(result.get("failures", []))
    assert "ds work-order close" in failures
    assert "ds work-order start" not in failures


def test_the_close_cli_records_the_reason_before_it_closes(db, tmp_path, monkeypatch):
    """Recording the exception AFTER attempting the close would need a second close to take
    effect -- which is how an escape hatch becomes a thing people run twice without reading
    what it said the first time."""
    import argparse

    from interfaces.cli.commands import work_order_dispatch as wo_cmd

    _, _, wid = _scaffold(db, tasks=1, siblings=1)
    _complete_all_tasks(db, wid)
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "events"))

    parser = argparse.ArgumentParser(prog="ds")
    sub = parser.add_subparsers(dest="command", required=True)
    wo_cmd.register(sub)
    args = parser.parse_args(
        [
            "work-order",
            "close",
            wid,
            "--skip-verify",
            "--accept-structure",
            "One task: the change is a single constant.",
        ]
    )
    wo_cmd.dispatch(args, source_root=tmp_path, dream_studio_home=tmp_path)

    from core.work_orders.structural_invariants import recorded_exception

    assert "single constant" in (recorded_exception(wid, db_path=db) or "")


# -- Task 6: an edit belongs to the work order whose boundary contains it --------


def _enforcement(db: Path, monkeypatch):
    """The enforcement lib pointed at a temp authority.

    ``AUTHORITY_DB`` is a module constant precisely so tests can patch it -- the module
    docstring says so -- and every read goes through it.
    """
    import importlib

    enforcement = importlib.import_module("runtime.lib.enforcement")
    monkeypatch.setattr(enforcement, "AUTHORITY_DB", db)
    return enforcement


def _wo_with_boundary(db: Path, project_id: str, title: str, boundary: str, started_at: str) -> str:
    import sqlite3
    import uuid

    wid = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, status,"
        "  work_order_type, created_at, updated_at, started_at)"
        " VALUES (?,?,NULL,?,?,'in_progress','infrastructure',?,?,?)",
        (wid, project_id, title, f"Module boundary: {boundary}.", _NOW, _NOW, started_at),
    )
    conn.commit()
    conn.close()
    return wid


def test_an_edit_is_attributed_by_module_boundary_not_recency(db, tmp_path, monkeypatch):
    """FAN-OUT'S FIRST CONSEQUENCE, and it fired on this very work order.

    ``in_progress_work_order`` did ``ORDER BY started_at DESC LIMIT 1`` -- the most
    recently STARTED work order was credited with every source edit. Correct when one work
    order is active; a coin flip once fan-out makes several legitimate, and 3 were in
    progress on the live authority.

    OBSERVED while building this: a session whose authority writes all went to 877af544
    was blocked by the stop hook demanding a write for 1db6de49, because 1db6de49 was
    started later. The hook asked for work to be recorded on a work order the session had
    not advanced. That is a false violation, and false violations are what push an operator
    to DS_ENFORCE=0.
    """
    import sqlite3
    import uuid

    enforcement = _enforcement(db, monkeypatch)
    pid = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, "P", "", "active", _NOW, _NOW),
    )
    conn.commit()
    conn.close()

    owner = _wo_with_boundary(
        db, pid, "owns the lifecycle", "core/work_orders", "2026-08-28T01:00:00Z"
    )
    newer = _wo_with_boundary(db, pid, "started later", "control/execution", "2026-08-28T09:00:00Z")

    edited = tmp_path / "core" / "work_orders" / "structural_invariants.py"
    edited.parent.mkdir(parents=True, exist_ok=True)
    edited.write_text("x", encoding="utf-8")

    picked = enforcement.in_progress_work_order(
        pid, file_path=str(edited), project_path=str(tmp_path)
    )

    assert picked["work_order_id"] == owner, (
        "the edit was credited to the newest-started work order, not the one whose "
        "declared boundary contains the file"
    )
    assert picked["work_order_id"] != newer
    assert picked["attribution"] == "module_boundary"

    # And the reverse, so the test cannot pass by always preferring the older row.
    other = tmp_path / "control" / "execution" / "runner.py"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("x", encoding="utf-8")
    assert (
        enforcement.in_progress_work_order(pid, file_path=str(other), project_path=str(tmp_path))[
            "work_order_id"
        ]
        == newer
    )


def test_an_unmatched_edit_falls_back_and_says_so(db, tmp_path, monkeypatch):
    """A work order with no declared boundary is the common case -- most of the live
    authority's work orders declare none. Refusing to attribute at all would turn a
    mislabel into a block.

    But the result must SAY WHICH, because a match and a guess are different claims and
    reading them as the same one is how "attributed to X" stops meaning anything.
    """
    import sqlite3
    import uuid

    enforcement = _enforcement(db, monkeypatch)
    pid = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, "P", "", "active", _NOW, _NOW),
    )
    conn.commit()
    conn.close()

    newest = _wo_with_boundary(db, pid, "newest", "core/work_orders", "2026-08-28T09:00:00Z")
    _wo_with_boundary(db, pid, "older", "docs", "2026-08-28T01:00:00Z")

    stray = tmp_path / "spool" / "writer.py"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text("x", encoding="utf-8")

    picked = enforcement.in_progress_work_order(
        pid, file_path=str(stray), project_path=str(tmp_path)
    )
    assert picked["work_order_id"] == newest
    assert (
        picked["attribution"] == "most_recently_started"
    ), "a fallback presented as a boundary match is a guess wearing a match's clothes"
    assert "claimants" not in picked, "nothing claimed this path; an empty claim is not a claim"


def test_a_boundaryless_work_order_does_not_claim_every_edit(db, tmp_path, monkeypatch):
    """``path_in_boundary`` returns True when no boundary is declared -- vacuously, since
    there is nothing to fail. Letting that count as a match would hand the first
    boundaryless work order every edit in the project: the recency bug in a new costume."""
    import sqlite3
    import uuid

    enforcement = _enforcement(db, monkeypatch)
    pid = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, "P", "", "active", _NOW, _NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, status,"
        "  work_order_type, created_at, updated_at, started_at)"
        " VALUES (?,?,NULL,'no boundary','just prose','in_progress','infrastructure',?,?,?)",
        (str(uuid.uuid4()), pid, _NOW, _NOW, "2026-08-28T09:00:00Z"),
    )
    conn.commit()
    conn.close()
    owner = _wo_with_boundary(db, pid, "declares one", "core/work_orders", "2026-08-28T01:00:00Z")

    edited = tmp_path / "core" / "work_orders" / "close_main.py"
    edited.parent.mkdir(parents=True, exist_ok=True)
    edited.write_text("x", encoding="utf-8")

    picked = enforcement.in_progress_work_order(
        pid, file_path=str(edited), project_path=str(tmp_path)
    )
    assert picked["work_order_id"] == owner
    assert picked["attribution"] == "module_boundary"


def test_a_write_to_either_claimant_satisfies_an_ambiguous_edit(db, tmp_path, monkeypatch):
    """AMBIGUITY IS NOT RESOLVED BY GUESSING. Where two in-progress work orders both
    declare a boundary over a path, both are legitimately doing this work. Picking a winner
    would manufacture a false violation against whichever one lost.

    So every claimant is carried, and a write to ANY of them satisfies the stop check.
    """
    import importlib
    import sqlite3
    import uuid

    enforcement = _enforcement(db, monkeypatch)
    pid = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, "P", "", "active", _NOW, _NOW),
    )
    conn.commit()
    conn.close()

    first = _wo_with_boundary(db, pid, "one", "core/work_orders", "2026-08-28T01:00:00Z")
    second = _wo_with_boundary(db, pid, "two", "core/work_orders", "2026-08-28T09:00:00Z")

    edited = tmp_path / "core" / "work_orders" / "close_main.py"
    edited.parent.mkdir(parents=True, exist_ok=True)
    edited.write_text("x", encoding="utf-8")

    picked = enforcement.in_progress_work_order(
        pid, file_path=str(edited), project_path=str(tmp_path)
    )
    assert set(picked["claimants"]) == {
        first,
        second,
    }, "both work orders claim this path; carrying only one invents a winner"

    stop = (
        importlib.import_module("runtime.hooks.meta.on_stop_enforce_shim", None) if False else None
    )
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader

    src = Path("runtime/hooks/meta/on-stop-enforce.py").resolve()
    loader = SourceFileLoader("_on_stop_enforce", str(src))
    spec = spec_from_loader(loader.name, loader)
    stop = module_from_spec(spec)
    loader.exec_module(stop)

    session = {
        "started_at": "2026-08-28T00:00:00Z",
        "source_edits": [
            {"path": str(edited), "work_order_id": first, "claimants": [first, second]}
        ],
    }

    # Neither has a write yet: one violation, and it names both.
    class _NoWrites:
        @staticmethod
        def authority_write_since(wo_id, since):
            return False

    violations = stop._authority_violations(_NoWrites, session)
    assert len(violations) == 1
    assert first in violations[0] and second in violations[0]
    assert "ANY ONE" in violations[0], "the message must say a single write is enough"

    # A write to the claimant the hook did NOT name still satisfies it.
    class _SecondWrote:
        @staticmethod
        def authority_write_since(wo_id, since):
            return wo_id == second

    assert stop._authority_violations(_SecondWrote, session) == []


def test_a_session_recorded_before_claimants_existed_still_checks(db, tmp_path):
    """Session state files on disk predate this change and carry only work_order_id.
    Reading them as "no claimants" would silently stop checking those edits -- a migration
    that turns a gate off is worse than one that fails loudly."""
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader

    src = Path("runtime/hooks/meta/on-stop-enforce.py").resolve()
    loader = SourceFileLoader("_on_stop_enforce_legacy", str(src))
    spec = spec_from_loader(loader.name, loader)
    stop = module_from_spec(spec)
    loader.exec_module(stop)

    class _NoWrites:
        @staticmethod
        def authority_write_since(wo_id, since):
            return False

    legacy = {
        "started_at": "2026-08-28T00:00:00Z",
        "source_edits": [{"path": "x.py", "work_order_id": "wo-legacy"}],
    }
    violations = stop._authority_violations(_NoWrites, legacy)
    assert len(violations) == 1
    assert "wo-legacy" in violations[0]


# -- Task 5: one write path for a generated file ---------------------------------


def test_the_installer_writes_through_the_guarded_path():
    """ALREADY BUILT WHEN THIS TASK CAME UP, and this pins the part that could still rot.

    Operator: "the installer should not be bypassing this, and we should use CLI commands
    where necessary so it cannot happen again." The bypass itself is gone — the installer
    calls merge_claude_md at plan time, and eleven behavioural tests in
    test_claude_md_projection.py cover the outcome (hand-written content survives, a file
    without sentinels is refused, a fresh install writes whole).

    What those cannot catch is the risk generate_routing's own comment names: "two splice
    implementations that can still drift apart". Both writers target the SAME operator
    files, so if one tightened its refusal and the other did not, ~/.claude/CLAUDE.md
    would be safe from one path and clobbered by the other — the original defect back
    through the side door. A behavioural test on one path passes happily while the other
    rots.

    So this asserts the structural property instead: ONE implementation, and every writer
    delegates to it.
    """
    import inspect

    from integrations.compiler import claude_code
    from integrations.installer import claude_code_installer
    from interfaces.cli import generate_routing

    # The splice lives in exactly one place.
    assert hasattr(claude_code, "merge_claude_md")

    for module, name in (
        (generate_routing, "generate_routing"),
        (claude_code_installer, "claude_code_installer"),
    ):
        src = inspect.getsource(module)
        assert "merge_claude_md(" in src, (
            f"{name} writes CLAUDE.md without going through the shared splice — "
            f"a second implementation is how the clobber comes back"
        )

    # And neither reimplements the marker arithmetic itself.
    from integrations.compiler.claude_code import _ROUTING_BEGIN

    splice_src = inspect.getsource(claude_code.merge_claude_md)
    assert _ROUTING_BEGIN in splice_src or "_ROUTING_BEGIN" in splice_src

    for module, name in (
        (generate_routing, "generate_routing"),
        (claude_code_installer, "claude_code_installer"),
    ):
        src = inspect.getsource(module)
        assert (
            ".index(" not in src or "merge_claude_md(" in src
        ), f"{name} appears to locate the markers itself rather than delegating"


def test_a_wholly_generated_file_may_be_written_whole():
    """AGENTS.md is NOT a second instance of the same defect, and treating it as one would
    be wrong. It carries no sentinels at all — it is a projection with no hand-written
    region by design, and its own header says so. Splicing a file that has no protected
    span would refuse every write.

    Pinned because "the installer overwrites a file in ~/.claude" looks identical to the
    CLAUDE.md defect from the outside, and the difference is whether the file has a region
    worth protecting.
    """
    from integrations.compiler.claude_code import _ROUTING_BEGIN

    agents = Path(__file__).resolve().parents[2] / "AGENTS.md"
    assert agents.is_file()
    assert _ROUTING_BEGIN not in agents.read_text(encoding="utf-8"), (
        "AGENTS.md grew sentinels — it now has a protected region and the installer's "
        "whole-file write must be routed through the splice like CLAUDE.md's"
    )


# -- Task 4: status that drifts makes every other count untrustworthy -------------


def test_completable_work_orders_and_milestones_are_surfaced(db):
    """WHY THIS MATTERS MORE THAN IT LOOKS. Measured on the live authority 2026-08-28: 13
    open work orders have every task complete, 25 open milestones have no open work order,
    and 4 have been in_progress since May.

    "49 of 128 open work orders carry one task or none" is only a fact if "open" means
    something. If a tenth of the open set is actually finished, every ratio quoted from it
    is quietly wrong — including the ones the structural invariants in this very work order
    were sized against. Drift does not just lose track of work; it corrupts the
    measurements the gates are built on.
    """
    import sqlite3

    from core.work_orders.reconcile import find_drift

    pid, mid, wid = _scaffold(db, tasks=2, siblings=2)
    _complete_all_tasks(db, wid)

    # A second milestone whose only work order is already closed.
    conn = sqlite3.connect(str(db))
    empty_ms = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, description, status, order_index,"
        "  created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (empty_ms, pid, "finished milestone", "", "active", 2, _NOW, _NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, status,"
        "  work_order_type, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), pid, empty_ms, "done", "", "closed", "infrastructure", _NOW, _NOW),
    )
    conn.commit()
    conn.close()

    drift = find_drift(db_path=db, project_id=pid)

    assert wid in {
        r["work_order_id"] for r in drift.completable_work_orders
    }, "a work order whose every task is complete is not reported as closable"
    assert empty_ms in {r["milestone_id"] for r in drift.completable_milestones}
    assert mid not in {
        r["milestone_id"] for r in drift.completable_milestones
    }, "a milestone with open work is not drift"

    rendered = drift.render()
    assert "ds work-order close" in rendered, "reporting drift without the fix is half an answer"
    assert "ds milestone close" in rendered


def test_a_work_order_with_no_tasks_is_not_reported_as_closable(db):
    """ABSENT IS NOT CLEAN — the error this repository keeps finding. A work order with
    zero tasks is not finished, it is unstarted. Reporting it as closable would turn
    "nobody has written the tasks yet" into "ready to close", and 49 such work orders exist
    on the live authority.
    """
    from core.work_orders.reconcile import find_drift

    pid, _, wid = _scaffold(db, tasks=0, siblings=2)
    assert wid not in {
        r["work_order_id"] for r in find_drift(db_path=db, project_id=pid).completable_work_orders
    }


def test_a_long_running_work_order_is_surfaced_without_being_judged(db):
    """4 work orders have been in_progress since May. That is worth a look, and it is NOT
    evidence of anything: a long-running work order may be genuinely long. It is reported
    separately from the closable ones so the two are never conflated."""
    import sqlite3

    from core.work_orders.reconcile import find_drift

    pid, _, wid = _scaffold(db, tasks=2, siblings=2)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE business_work_orders SET status='in_progress', started_at=? WHERE work_order_id=?",
        ("2026-05-01T00:00:00+00:00", wid),
    )
    conn.commit()
    conn.close()

    drift = find_drift(db_path=db, project_id=pid, now="2026-08-28T00:00:00+00:00")
    assert wid in {r["work_order_id"] for r in drift.stale_in_progress}
    assert wid not in {
        r["work_order_id"] for r in drift.completable_work_orders
    }, "stale and closable are different claims and must not be merged"


def test_reconcile_reports_and_never_closes(db):
    """A reconciler that closed things on the operator's behalf would bypass independent
    review, the executable-AC gate and the structural invariants — for exactly the work
    orders nobody has looked at recently. That is the opposite of what it is for."""
    import sqlite3

    from core.work_orders.reconcile import find_drift

    pid, _, wid = _scaffold(db, tasks=2, siblings=2)
    _complete_all_tasks(db, wid)

    before = _one(db, "SELECT status FROM business_work_orders WHERE work_order_id=?", (wid,))
    rendered = find_drift(db_path=db, project_id=pid).render()
    after = _one(db, "SELECT status FROM business_work_orders WHERE work_order_id=?", (wid,))

    assert before == after == "created", "reconcile mutated a record it was only meant to report"
    assert "Nothing above was changed" in rendered


def test_a_null_title_is_named_rather_than_crashing_or_blanking(db):
    """FOUND BY RUNNING IT, not by imagining inputs. Several work_order rows on the live
    authority carry a NULL title — projection orphans whose project no longer exists. The
    first version crashed on them, which would make the tool unusable exactly where the
    data is worst. Printing an empty string would be worse: it hides the one property that
    identifies them."""
    import sqlite3

    from core.work_orders.reconcile import find_drift

    pid, _, wid = _scaffold(db, tasks=2, siblings=2)
    _complete_all_tasks(db, wid)
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE business_work_orders SET title=NULL WHERE work_order_id=?", (wid,))
    conn.commit()
    conn.close()

    rendered = find_drift(db_path=db, project_id=pid).render()
    assert "projection orphan" in rendered
    assert wid[:8] in rendered


# -- Task 3: honest partial close ------------------------------------------------


def _tasks_of(db: Path, work_order_id: str) -> list[tuple[str, str, str]]:
    import sqlite3

    conn = sqlite3.connect(str(db))
    try:
        return [
            (r[0], r[1], r[2])
            for r in conn.execute(
                "SELECT task_id, title, status FROM business_tasks"
                " WHERE work_order_id = ? ORDER BY created_at",
                (work_order_id,),
            ).fetchall()
        ]
    finally:
        conn.close()


def test_carry_over_closes_the_original_at_its_true_scope(db, tmp_path, monkeypatch):
    """THE THIRD OPTION THAT DID NOT EXIST.

    A work order turns out to be mis-scoped: some tasks belong to different work. The only
    ways to express that were --force (which records a bypass for something that is not a
    bypass) and cancelling the tasks (a lie -- the work still needs doing). Carry-over
    moves them to a linked work order and lets the original close at what it delivered.

    NARROW BY OPERATOR RULING: this is not for "I want to work on something else". Tasks
    that belong to a work order stay on it and you switch work orders instead.
    """
    from core.work_orders.carry_over import carry_over
    from core.work_orders.close import close_work_order

    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "events"))
    _, _, wid = _scaffold(db, tasks=3, siblings=2)
    tasks = _tasks_of(db, wid)
    carry = [t[0] for t in tasks[1:]]

    result = carry_over(
        work_order_id=wid,
        task_ids=carry,
        reason="These two turned out to belong to the projection work, not this one.",
        title="Projection remainder",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True, result
    new_wo = result["carried_to"]
    assert result["remaining_tasks"] == 1

    # The remainder exists as real work somewhere else -- not cancelled, not lost.
    moved_titles = {t[1] for t in _tasks_of(db, new_wo)}
    assert moved_titles == {"T1", "T2"}
    assert all(
        status == "pending" for _, _, status in _tasks_of(db, new_wo)
    ), "carried work must arrive as work to do, not as already-settled"

    # The original can now close at its true scope, through the gates.
    _complete_all_tasks(db, wid)
    closed = close_work_order(
        work_order_id=wid, source_root=tmp_path, dream_studio_home=tmp_path, skip_verify=True
    )
    failures = " ".join(closed.get("failures", []))
    assert "tasks_done" not in failures, failures


def test_carry_over_is_not_recorded_as_a_gate_bypass(db, tmp_path, monkeypatch):
    """THE WHOLE POINT OF BUILDING THIS RATHER THAN USING --force.

    --force closes past EVERY gate at once and records a gate.bypassed event. Using it for
    a scope change fills the bypass audit with entries that are not bypasses, which makes
    the audit useless for finding the ones that are.

    A carry-over is not a bypass: the tasks did not go unfinished, they went somewhere. So
    the close that follows must be an ordinary close -- no force, no bypassed_gates, and
    tasks_done still running on what remains.
    """
    from core.work_orders.carry_over import carry_over
    from core.work_orders.close import close_work_order

    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "events"))
    _, _, wid = _scaffold(db, tasks=3, siblings=2)
    tasks = _tasks_of(db, wid)

    carry_over(
        work_order_id=wid,
        task_ids=[tasks[2][0]],
        reason="Authored here by mistake; it belongs to the installer work order.",
        title="Installer remainder",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )
    _complete_all_tasks(db, wid)

    closed = close_work_order(
        work_order_id=wid, source_root=tmp_path, dream_studio_home=tmp_path, skip_verify=True
    )

    assert closed.get("forced") is not True, "a carry-over close must not be a forced close"
    assert not closed.get("bypassed_gates"), closed.get("bypassed_gates")
    assert "tasks_done" not in " ".join(closed.get("failures", []))


def test_a_deleted_task_with_no_recorded_split_still_blocks_the_close(db, tmp_path):
    """THE HOLE THIS DESIGN CLOSES.

    The obvious implementation excludes status='deleted' from tasks_done. That would make
    deleting a task a way to close a work order with its work undone -- the lie carry-over
    exists to replace, reachable in one more step.

    So the gate keys on the RECORDED SPLIT, not the status. A task deleted with no carry
    record blocks exactly as before.
    """
    import sqlite3

    from core.work_orders.close import close_work_order

    _, _, wid = _scaffold(db, tasks=2, siblings=2)
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE business_tasks SET status='deleted' WHERE work_order_id=?", (wid,))
    conn.commit()
    conn.close()

    closed = close_work_order(
        work_order_id=wid, source_root=tmp_path, dream_studio_home=tmp_path, skip_verify=True
    )
    assert "tasks_done" in " ".join(
        closed.get("failures", [])
    ), "deleting every task closed the work order -- carry-over became a bypass"


def test_carrying_everything_away_is_refused(db, tmp_path, monkeypatch):
    """A work order that carries away all its tasks was not re-scoped, it was abandoned.
    Closing it afterwards would assert that work happened here when none did. The refusal
    names the honest alternatives so the reader does not go looking for --force."""
    from core.work_orders.carry_over import carry_over

    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "events"))
    _, _, wid = _scaffold(db, tasks=2, siblings=2)

    result = carry_over(
        work_order_id=wid,
        task_ids=[t[0] for t in _tasks_of(db, wid)],
        reason="Everything here belongs to a different work order entirely.",
        title="All of it",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is False
    assert "abandonment" in result["error"]
    assert "ds work-order block" in result["error"]


def test_a_carry_over_without_a_real_reason_is_refused(db, tmp_path, monkeypatch):
    """The reason is the only thing distinguishing a re-scope from moving work you would
    rather do later, and no gate can read intent. An unweighable reason recorded in the
    authority is worse than none -- it looks like a decision was made."""
    from core.work_orders.carry_over import carry_over

    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    _, _, wid = _scaffold(db, tasks=3, siblings=2)

    result = carry_over(
        work_order_id=wid,
        task_ids=[_tasks_of(db, wid)[0][0]],
        reason="later",
        title="Later",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is False
    assert (
        "switch work orders instead" in result["error"]
    ), "the refusal must name what to do instead, or it reads as an obstacle"


def test_the_split_is_recorded_on_both_work_orders(db, tmp_path, monkeypatch):
    """A one-way link is how provenance is lost. The original needs the record because the
    close gate reads it; the new work order needs it because a reader who lands there must
    be able to get back to where the work came from."""
    from core.work_orders.artifacts import get_wo_artifact
    from core.work_orders.carry_over import CARRY_KEY, CARRY_KIND, carry_over

    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "events"))
    _, _, wid = _scaffold(db, tasks=3, siblings=2)

    result = carry_over(
        work_order_id=wid,
        task_ids=[_tasks_of(db, wid)[0][0]],
        reason="Belongs to the reconcile work order, not this one.",
        title="Reconcile remainder",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True

    for side in (wid, result["carried_to"]):
        raw = get_wo_artifact(side, CARRY_KIND, instance_key=CARRY_KEY, db_path=db)
        assert raw, f"no split recorded on {side}"
        assert "Belongs to the reconcile work order" in raw
        assert wid in raw and result["carried_to"] in raw, "the record must name both ends"


# -- WO 17f20d48: a misaddressed criterion can be corrected without --force -------


def _task_with_ac(db: Path, ac: str) -> tuple[str, str]:
    """A project + milestone + work order + one task carrying *ac*. Returns (wo, task)."""
    import sqlite3
    import uuid

    pid, mid, wid, tid = (str(uuid.uuid4()) for _ in range(4))
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (pid, "P", "", "active", _NOW, _NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, description, status, order_index,"
        "  created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (mid, pid, "M", "", "active", 1, _NOW, _NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, status,"
        "  work_order_type, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (wid, pid, mid, "W", "", "in_progress", "infrastructure", _NOW, _NOW),
    )
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, description, status,"
        "  acceptance_criteria, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (tid, wid, pid, "T", "", "complete", ac, _NOW, _NOW),
    )
    conn.commit()
    conn.close()
    return wid, tid


def test_an_acceptance_criterion_can_be_repointed(db, tmp_path, monkeypatch):
    """THE DEFECT, FOUND BY THE GATE REFUSING TO LIE.

    business_tasks.acceptance_criteria is COALESCEd at every write site, so it was
    write-once: a replayed or re-emitted task.created never overwrites it and no update
    mutation existed. WO 1db6de49 named
    `...::test_a_node_without_an_observable_condition_is_not_reported_complete` where the
    test is `..._is_not_reported_completed` — one character. The close gate correctly
    reported MISADDRESSED (pytest exit 4) instead of treating a missing node id as a pass,
    so a work order whose four tasks were done and shipped could not close.

    The only remaining escape was --force, which bypasses EVERY other gate to fix one
    string. That is the trade this removes.
    """
    from core.work_orders.repoint_ac import repoint_acceptance_criteria

    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "events"))
    _, tid = _task_with_ac(db, "SQL-CHECK: SELECT 1 WHERE 0")

    result = repoint_acceptance_criteria(
        task_id=tid,
        acceptance_criteria="SQL-CHECK: SELECT 1",
        reason="The original query had a typo in its predicate.",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True, result

    stored = _one(db, "SELECT acceptance_criteria FROM business_tasks WHERE task_id=?", (tid,))
    assert (
        stored == "SQL-CHECK: SELECT 1"
    ), "the projection still COALESCEd the value — the criterion is still write-once"


def test_a_repointed_criterion_records_what_it_was(db, tmp_path, monkeypatch):
    """AN EDITABLE CRITERION IS A MOVED GOALPOST WAITING TO HAPPEN.

    Nothing can stop someone repointing a failing check at a trivially-passing one. What
    the design CAN do is make it visible: the prior value and a reason ride in the event
    payload, so both criteria are in the stream forever and a later reader can tell a typo
    fix from a weakened target.

    A silent correction would be strictly worse than the write-once column it replaces.
    """
    import json as _json
    import sqlite3

    from core.work_orders.repoint_ac import repoint_acceptance_criteria

    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "events"))
    _, tid = _task_with_ac(db, "SQL-CHECK: SELECT 1 WHERE 0")

    result = repoint_acceptance_criteria(
        task_id=tid,
        acceptance_criteria="SQL-CHECK: SELECT 1",
        reason="The original query had a typo in its predicate.",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )
    assert result["previous"] == "SQL-CHECK: SELECT 1 WHERE 0"

    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT payload FROM business_canonical_events WHERE event_type='task.ac_repointed'"
        ).fetchall()
    finally:
        conn.close()
    assert rows, "no task.ac_repointed event reached the canonical stream"
    payload = _json.loads(rows[-1][0])
    assert payload["previous"] == "SQL-CHECK: SELECT 1 WHERE 0"
    assert payload["acceptance_criteria"] == "SQL-CHECK: SELECT 1"
    assert "typo" in payload["reason"]


def test_a_criterion_cannot_be_repointed_at_nothing(db, tmp_path, monkeypatch):
    """THE GUARD THAT MAKES THIS A TYPO-FIXER RATHER THAN AN ESCAPE HATCH.

    Without it, repointing would be a way to aim a check at a node id that does not exist —
    which is precisely the MISADDRESSED state the close gate refuses to treat as a pass. The
    mechanism built to fix that must not be able to recreate it.
    """
    from core.work_orders.repoint_ac import repoint_acceptance_criteria

    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "events"))
    _, tid = _task_with_ac(db, "SQL-CHECK: SELECT 1")

    result = repoint_acceptance_criteria(
        task_id=tid,
        acceptance_criteria="TEST-CHECK: tests/unit/no_such_file.py::test_nothing",
        reason="Pointing it somewhere that does not exist.",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is False
    assert "misaddressed" in result["error"]


def test_repointing_without_a_reason_is_refused(db, tmp_path, monkeypatch):
    """The reason is the only thing that lets a later reader weigh the correction. An
    unweighable one recorded in the authority is worse than none — it looks like a
    decision was made."""
    from core.work_orders.repoint_ac import repoint_acceptance_criteria

    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    _, tid = _task_with_ac(db, "SQL-CHECK: SELECT 1 WHERE 0")

    result = repoint_acceptance_criteria(
        task_id=tid,
        acceptance_criteria="SQL-CHECK: SELECT 1",
        reason="typo",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is False
    assert "moved goalpost" in result["error"]


def test_a_check_that_runs_and_fails_is_still_repointable_to(db, tmp_path, monkeypatch):
    """FAILING IS NOT MISADDRESSED. A check that runs and reports failure is correctly
    aimed — the work simply is not done yet. Refusing it would mean a criterion could only
    ever be repointed at something already passing, which would turn the mechanism into a
    way to guarantee green."""
    from core.work_orders.repoint_ac import repoint_acceptance_criteria

    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "events"))
    _, tid = _task_with_ac(db, "SQL-CHECK: SELECT 1")

    result = repoint_acceptance_criteria(
        task_id=tid,
        acceptance_criteria="SQL-CHECK: SELECT 1 WHERE 0",
        reason="Repointing at a check that runs but does not pass yet.",
        source_root=tmp_path,
        dream_studio_home=tmp_path,
    )
    assert result["ok"] is True, result


def test_a_gate_that_cannot_read_its_data_blocks_rather_than_passing(db, tmp_path):
    """FOUND BY AN INDEPENDENT REVIEW, IN THE MODULE WRITTEN TO ENFORCE THE OPPOSITE.

    check_structure returned [] on sqlite3.Error — no violations, which the close gate
    reads as clean. So a database error silently PASSED the structural gate, on exactly
    the work orders whose data is broken.

    That is absent-is-not-clean, the error this repository keeps finding, committed by the
    gate module itself. A gate that cannot read its data has not found the work order
    clean; it has found nothing.
    """
    from core.work_orders.structural_invariants import check_structure

    missing = tmp_path / "nowhere" / "studio.db"
    violations = check_structure("any-id", db_path=missing)

    assert violations, "an unreadable database reported the work order clean"
    assert violations[0].scope == "unevaluated"
    assert "could not be evaluated" in violations[0].message
    assert (
        "--accept-structure" in violations[0].message
    ), "blocking without naming the escape strands an operator on a legacy database"


def test_only_a_work_order_the_authority_created_is_judged(db):
    """OPERATOR RULING 2026-08-30, after the gate turned main red twice.

    The invariant is about how a human or agent SIZES real work. Applied to every close
    path it also caught hermetic test fixtures, which are one-task by design because they
    are exercising some other gate: 23 tests across 10 files, and repairing them meant
    adding setup unrelated to what each test was about — one such addition then broke four
    more, because a seeded acceptance criterion is not inert.

    `create_work_order` emits `work_order.created`; a raw SQL insert emits nothing. That
    event is the exact recorded line between a work order the authority authored and a row
    someone put in a table — no heuristic, no new column.

    NOT AN EVASION ROUTE: a row with no event is deleted by the next projection rebuild, so
    a raw-SQL work order does not survive to be closed. And measured the day this was
    scoped, the gate keeps almost all its reach: 101 of 132 open work orders are
    event-backed and 45 of those still break an invariant, against 49 before.
    """
    import sqlite3

    from core.work_orders.structural_invariants import check_structure

    # _scaffold emits work_order.created, so this one IS judged.
    _, _, authored = _scaffold(db, tasks=1, siblings=1)
    assert check_structure(
        authored, db_path=db
    ), "a work order the authority created was not judged"

    # The same malformed shape, inserted directly with no event.
    conn = sqlite3.connect(str(db))
    raw = str(uuid.uuid4())
    pid = _one(db, "SELECT project_id FROM business_work_orders WHERE work_order_id=?", (authored,))
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, status,"
        "  work_order_type, created_at, updated_at) VALUES (?,?,NULL,?,?,?,?,?,?)",
        (raw, pid, "raw", "", "created", "infrastructure", _NOW, _NOW),
    )
    conn.commit()
    conn.close()

    assert check_structure(raw, db_path=db) == [], (
        "a row inserted directly was judged — that is the hermetic-fixture case this "
        "scoping exists to exclude"
    )


def test_a_database_with_no_canonical_events_is_not_judged(db, tmp_path):
    """A database with no canonical event table is not a Dream Studio authority at all,
    and a gate about how the authority sizes work has nothing to say about one.

    Distinct from the unreadable-database case, which still BLOCKS: there the gate cannot
    read data it should be able to read; here there is no authority to speak for.
    """
    import sqlite3

    from core.work_orders.structural_invariants import check_structure

    _, _, wid = _scaffold(db, tasks=1, siblings=1)
    conn = sqlite3.connect(str(db))
    conn.execute("DROP TABLE business_canonical_events")
    conn.commit()
    conn.close()

    assert check_structure(wid, db_path=db) == []


def test_the_spool_guard_names_the_test_that_polluted():
    """WO efe2ce9d task 1. The guard aborts the whole session when a test writes to the
    operator's real ~/.dream-studio/events — correctly, that is its job. But it said only
    "Test modified real ~/.dream-studio/events", and a session that ends at test 2,400 of
    5,928 with no identifier leaves the reader to bisect by hand. I nearly did.

    It is an autouse per-test fixture, so its teardown already KNOWS which test polluted;
    the identifier was simply not in the message.

    Asserted against the source rather than by polluting the spool for real: a test that
    proves this by writing to the operator's events directory would be the very thing the
    guard exists to stop. Verified once out-of-band with a throwaway probe, which produced
    'FATAL: tests/unit/test_zz_guard_probe.py::test_this_one_pollutes_the_real_spool
    modified real ~/.dream-studio/events'.
    """
    conftest = Path(__file__).resolve().parents[1] / "conftest.py"
    src = conftest.read_text(encoding="utf-8")

    assert (
        "def guard_real_homedir(tmp_path, monkeypatch, request):" in src
    ), "the guard cannot name the test without the request fixture"
    for surface in ("events", "integrations"):
        marker = f"modified real ~/.dream-studio/{surface}"
        line = next((ln for ln in src.splitlines() if marker in ln), "")
        assert line, f"no guard message for {surface}"
        assert (
            "request.node.nodeid" in line
        ), f"the {surface} guard aborts the session without naming the test that did it"
