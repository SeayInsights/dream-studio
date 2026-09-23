"""A work order moves through its phases in order.

Operator, 2026-09-23: created -> in_progress -> in_review -> pushed -> ci_issues -> closed,
and ci_issues is the only phase that may be skipped, because a push may meet no CI issue.
Closed comes after pushed, and --force does not change that.

Before one table decided this, each writer checked what it happened to think of: start
checked nothing, advance refused only terminal statuses, close refused nothing its
--force could not wave through. A work order went created -> closed in two commands.
Unblock sent everything to in_progress, so a work order blocked while waiting for CI came
back with its review and its push erased.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.projections.work_order_projection import WorkOrderProjection
from core.work_orders.task_status import (
    BLOCKABLE_WORK_ORDER_STATUSES,
    CANONICAL_WORK_ORDER_STATUSES,
    WORK_ORDER_TRANSITIONS,
    transition_refusal,
)

PROJECT_ID = "abababab-abab-abab-abab-abababababab"
WO_ID = "cdcdcdcd-cdcd-cdcd-cdcd-cdcdcdcdcdcd"
NOW = "2026-09-23T00:00:00+00:00"
CHAIN = ("created", "in_progress", "in_review", "pushed", "ci_issues", "closed")


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    db = home / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, project_path,"
        " created_at, updated_at) VALUES (?, 'P', 'd', 'active', ?, ?, ?)",
        (PROJECT_ID, str(tmp_path), NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id, title,"
        " description, status, work_order_type, created_at, updated_at)"
        " VALUES (?, ?, NULL, 'WO-ORDER', 'd', 'created', 'infrastructure', ?, ?)",
        (WO_ID, PROJECT_ID, NOW, NOW),
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(home / "events"))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    return home


def _set_status(home: Path, status: str) -> None:
    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    conn.execute(
        "UPDATE business_work_orders SET status = ? WHERE work_order_id = ?", (status, WO_ID)
    )
    conn.commit()
    conn.close()


def _status(home: Path) -> str:
    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    try:
        return conn.execute(
            "SELECT status FROM business_work_orders WHERE work_order_id = ?", (WO_ID,)
        ).fetchone()[0]
    finally:
        conn.close()


def _events(home: Path, event_type: str) -> list[dict]:
    found = []
    for path in (home / "events").rglob("*.json"):
        event = json.loads(path.read_text(encoding="utf-8"))
        if event.get("event_type") == event_type:
            found.append(event)
    return found


# ── the table ────────────────────────────────────────────────────────────────


def test_the_table_is_the_chain_with_only_ci_issues_skippable():
    """Every open phase goes to the next one, and nowhere else -- except that pushed may
    go straight to closed. That one skip is the whole of the exception."""
    for here, nxt in zip(CHAIN, CHAIN[1:]):
        expected = {nxt, "closed"} if here == "pushed" else {nxt}
        assert set(WORK_ORDER_TRANSITIONS[here]) == expected, here


def test_every_status_is_in_the_table():
    """A status the table does not name would be refused everything, silently."""
    assert set(WORK_ORDER_TRANSITIONS) == set(CANONICAL_WORK_ORDER_STATUSES)


@pytest.mark.parametrize(
    "current,target",
    [
        ("created", "in_review"),
        ("created", "closed"),
        ("in_progress", "pushed"),
        ("in_progress", "closed"),
        ("in_review", "closed"),
        ("in_review", "in_progress"),
        ("ci_issues", "in_progress"),
        ("pushed", "in_review"),
    ],
)
def test_a_skip_or_a_step_back_is_refused_and_says_what_is_next(current, target):
    refusal = transition_refusal(WO_ID, current, target)
    assert refusal and "the next is" in refusal, refusal


# ── the writers ask it ───────────────────────────────────────────────────────


def test_advance_refuses_to_skip_review(home):
    """in_progress -> pushed would skip the review lanes entirely."""
    from core.work_orders.mutations import advance_work_order

    _set_status(home, "in_progress")
    result = advance_work_order(work_order_id=WO_ID, to="pushed", source_root=home)
    assert result["ok"] is False and "the next is in_review" in result["error"]
    assert _status(home) == "in_progress"


def test_advance_takes_the_next_step(home):
    from core.work_orders.mutations import advance_work_order

    _set_status(home, "in_progress")
    result = advance_work_order(work_order_id=WO_ID, to="in_review", source_root=home)
    assert result["ok"] is True and _status(home) == "in_review"


def test_close_refuses_from_in_progress_even_forced(home, monkeypatch):
    """Force waives gates, which are judgments. The phase is a fact about where the work
    is, and a refused close must leave nothing behind: no status change, no event -- and
    no bookkeeping, because the refusal comes before the boundary is pinned (the write at
    the end refuses too, but only after everything before it has run)."""
    from core.work_orders import delivery_boundary
    from core.work_orders.close import close_work_order

    pinned = []
    monkeypatch.setattr(
        delivery_boundary, "record_delivery_boundary_end", lambda *a, **k: pinned.append(a)
    )
    _set_status(home, "in_progress")
    result = close_work_order(work_order_id=WO_ID, force=True, source_root=home)
    assert pinned == [], "the close did work before refusing the phase"
    assert result["ok"] is False and result.get("phase_refused") is True
    assert _status(home) == "in_progress"
    assert _events(home, "work_order.closed") == []


@pytest.mark.parametrize("phase", ["pushed", "ci_issues"])
def test_close_is_not_phase_refused_from_the_two_phases_it_closes_from(home, phase):
    from core.work_orders.close import close_work_order

    _set_status(home, phase)
    result = close_work_order(work_order_id=WO_ID, force=True, source_root=home)
    assert not result.get("phase_refused"), result
    assert result["ok"] is True and _status(home) == "closed"


def test_the_close_preview_names_the_phase(home):
    """A preview that omits a blocking check tells the author they are ready when they
    are not."""
    from core.work_orders.close import check_close_gates

    _set_status(home, "in_review")
    preview = check_close_gates(work_order_id=WO_ID, source_root=home)
    assert preview["gates_pass"] is False
    assert any("cannot move to closed" in f for f in preview["gate_failures"])


def test_start_refuses_a_work_order_past_in_progress(home):
    """Starting a pushed work order again would silently erase its review and push."""
    from core.work_orders.start import start_work_order

    _set_status(home, "pushed")
    result = start_work_order(
        work_order_id=WO_ID, source_root=home, planning_root=home / "planning"
    )
    assert result["ok"] is False and "cannot move to in_progress" in result["error"]
    assert _status(home) == "pushed"


def test_reopen_refuses_what_is_not_closed(home):
    from core.work_orders.mutations import reopen_work_order

    _set_status(home, "in_review")
    result = reopen_work_order(work_order_id=WO_ID, source_root=home)
    assert result["ok"] is False and _status(home) == "in_review"


# ── unblock returns to the phase it came from ────────────────────────────────


@pytest.mark.parametrize("phase", BLOCKABLE_WORK_ORDER_STATUSES)
def test_unblock_returns_to_the_phase_it_was_blocked_from(home, phase):
    from core.work_orders.mutations import block_work_order, unblock_work_order

    _set_status(home, phase)
    assert block_work_order(work_order_id=WO_ID, reason="waiting", source_root=home)["ok"]
    assert _status(home) == "blocked"
    result = unblock_work_order(work_order_id=WO_ID, source_root=home)
    assert result["ok"] is True and result["status"] == phase
    assert _status(home) == phase


def test_the_phase_travels_on_both_events(home):
    """So a replay rebuilds it without the row."""
    from core.work_orders.mutations import block_work_order, unblock_work_order

    _set_status(home, "pushed")
    block_work_order(work_order_id=WO_ID, reason="waiting", source_root=home)
    unblock_work_order(work_order_id=WO_ID, source_root=home)
    assert [e["payload"]["from_status"] for e in _events(home, "work_order.blocked")] == ["pushed"]
    assert [e["payload"]["to_status"] for e in _events(home, "work_order.unblocked")] == ["pushed"]


def test_a_terminal_work_order_cannot_be_blocked(home):
    from core.work_orders.mutations import block_work_order

    _set_status(home, "closed")
    result = block_work_order(work_order_id=WO_ID, reason="x", source_root=home)
    assert result["ok"] is False and _status(home) == "closed"


def test_without_migration_158_unblock_returns_to_in_progress(home):
    """Unreleased migrations do not reach a live authority, so the code must run without
    the column: unblock does what it always did instead of failing."""
    from core.work_orders.mutations import block_work_order, unblock_work_order

    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    conn.execute("ALTER TABLE business_work_orders DROP COLUMN blocked_from_status")
    conn.commit()
    conn.close()
    _set_status(home, "pushed")
    assert block_work_order(work_order_id=WO_ID, reason="x", source_root=home)["ok"]
    assert unblock_work_order(work_order_id=WO_ID, source_root=home)["status"] == "in_progress"


# ── a replay lands where the writer did ──────────────────────────────────────


def _replay(conn, event_type: str, payload: dict, n: int) -> None:
    WorkOrderProjection().handle(
        {
            "event_id": f"e-{n}",
            "event_type": event_type,
            "event_timestamp": f"2026-09-23T00:00:0{n}+00:00",
            "work_order_id": WO_ID,
            "project_id": PROJECT_ID,
            "payload": {"title": "t", "type": "infrastructure", **payload},
        },
        conn,
    )


@pytest.mark.parametrize(
    "blocked,unblocked,lands",
    [
        ({"from_status": "pushed"}, {"to_status": "pushed"}, "pushed"),
        # The unblock's own word wins: here the blocked event recorded nothing, so only
        # `to_status` can land it on pushed.
        ({}, {"to_status": "pushed"}, "pushed"),
        # An unblock written before `to_status` existed: the blocked event's phase.
        ({"from_status": "in_review"}, {}, "in_review"),
        # History from before either key: what unblock always did.
        ({}, {}, "in_progress"),
    ],
)
def test_a_replayed_unblock_lands_on_the_recorded_phase(home, blocked, unblocked, lands):
    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    try:
        _replay(conn, "work_order.blocked", {"reason": "x", **blocked}, 1)
        _replay(conn, "work_order.unblocked", unblocked, 2)
        row = conn.execute(
            "SELECT status, blocked_from_status FROM business_work_orders"
            " WHERE work_order_id = ?",
            (WO_ID,),
        ).fetchone()
    finally:
        conn.close()
    assert row == (lands, None)


# ── the watcher closes from ci_issues and never re-files a failure ───────────


def test_the_watcher_sees_ci_issues_work(home):
    from core.health.main_ci_watch import work_orders_awaiting_ci

    _set_status(home, "ci_issues")
    awaiting = work_orders_awaiting_ci(home / "state" / "studio.db")
    assert [(w["work_order_id"], w["status"]) for w in awaiting] == [(WO_ID, "ci_issues")]


def test_a_red_run_files_nothing_new_on_a_ci_issues_work_order():
    """Its failure is already a task; a copy on every red poll buries it."""
    from interfaces.cli.commands.ci import _act

    def remediation(*a, **k):
        raise AssertionError("a second remediation task was built")

    action = _act(
        {"work_order_id": WO_ID, "project_id": PROJECT_ID, "status": "ci_issues"},
        status="failure",
        verdict={},
        nodes=[],
        unrunnable=[],
        source_root=Path("."),
        dream_studio_home=None,
        dry_run=False,
        remediation=remediation,
    )
    assert action["ok"] is True and action["did"].startswith("nothing")


# ── round-one findings ───────────────────────────────────────────────────────


def test_a_block_that_lands_while_closing_is_not_overwritten(home, monkeypatch):
    """Close checks the phase at the top and writes `closed` minutes later; a block landing
    in between was silently overwritten (receiver's-view lane). The write now carries the
    condition, so the close is refused and nothing announces a close that did not land."""
    from core.work_orders import delivery_boundary
    from core.work_orders.close import close_work_order

    _set_status(home, "pushed")

    def block_meanwhile(*args, **kwargs):
        _set_status(home, "blocked")

    monkeypatch.setattr(delivery_boundary, "record_delivery_boundary_end", block_meanwhile)
    result = close_work_order(work_order_id=WO_ID, force=True, source_root=home)
    assert result["ok"] is False and result.get("phase_refused") is True, result
    assert _status(home) == "blocked"
    assert _events(home, "work_order.closed") == []
    # The per-gate bypass records follow the write too. (Skipping the review itself is
    # recorded earlier, and truly: it was skipped whether or not the close lands.)
    per_gate = [
        e
        for e in _events(home, "gate.bypassed")
        if "proceeded without independent review" not in json.dumps(e)
    ]
    assert per_gate == [], per_gate


def _task(home: Path, criterion: str) -> None:
    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    conn.execute(
        "INSERT INTO business_tasks (task_id, work_order_id, project_id, title, description,"
        " acceptance_criteria, status, created_at, updated_at)"
        " VALUES ('t-open', ?, ?, 'Fix main', 'd', ?, 'pending', ?, ?)",
        (WO_ID, PROJECT_ID, criterion, NOW, NOW),
    )
    conn.commit()
    conn.close()


def _task_criteria(home: Path) -> list[str]:
    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    try:
        return [
            r[0]
            for r in conn.execute(
                "SELECT coalesce(acceptance_criteria, '') FROM business_tasks"
                " WHERE work_order_id = ? ORDER BY created_at",
                (WO_ID,),
            )
        ]
    finally:
        conn.close()


_OLD = "tests/unit/test_work_order_phases_run_in_order.py::test_every_status_is_in_the_table"
_NEW = "tests/unit/test_work_order_phases_run_in_order.py::test_advance_takes_the_next_step"


def test_a_red_run_files_a_new_failure_on_a_ci_issues_work_order(home):
    """ "Already recorded" was true of the old failure and false of a new one, and the new
    one was dropped (receiver's-view lane). Only what no open task names is filed."""
    from core.health.main_ci_watch import remediation_task
    from interfaces.cli.commands.ci import _act

    repo = Path(__file__).resolve().parents[2]
    conn = sqlite3.connect(str(home / "state" / "studio.db"))
    conn.execute("UPDATE business_projects SET project_path = ?", (str(repo),))
    conn.commit()
    conn.close()
    _set_status(home, "ci_issues")
    _task(home, f"TEST-CHECK: {_OLD}")
    wo = {"work_order_id": WO_ID, "project_id": PROJECT_ID, "status": "ci_issues"}
    kwargs = dict(
        status="failure",
        verdict={},
        unrunnable=[],
        source_root=repo,
        dream_studio_home=home,
        dry_run=False,
        remediation=remediation_task,
    )

    same = _act(wo, nodes=[_OLD], **kwargs)
    assert same["did"].startswith("nothing") and len(_task_criteria(home)) == 1

    more = _act(wo, nodes=[_OLD, _NEW], **kwargs)
    assert more["ok"] is True and more["new_failures"] == [_NEW], more
    filed = _task_criteria(home)[-1]
    assert _NEW in filed and _OLD not in filed, filed
    assert _status(home) == "ci_issues"


def test_migration_158_allows_exactly_the_open_phases():
    """SQL cannot import the vocabulary, so the CHECK spells it out; this holds the two
    together, the way the phases themselves are held to the table."""
    import re

    sql = (
        Path(__file__).resolve().parents[2]
        / "core/event_store/migrations/158_work_order_blocked_from_status.sql"
    ).read_text(encoding="utf-8")
    listed = re.search(r"blocked_from_status IN \(([^)]*)\)", sql).group(1)
    assert set(re.findall(r"'([a-z_]+)'", listed)) == set(BLOCKABLE_WORK_ORDER_STATUSES)


def test_the_writer_and_the_projection_ask_one_column_check():
    """Two copies of "has migration 158 landed" would be two answers to one question."""
    from core.projections import work_order_projection
    from core.work_orders import mutations, task_status

    assert mutations.remembers_block_phase is task_status.remembers_block_phase
    assert work_order_projection.remembers_block_phase is task_status.remembers_block_phase
