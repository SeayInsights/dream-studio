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
