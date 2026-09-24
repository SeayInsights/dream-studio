"""A work order reaches `pushed` only when its review no longer holds it.

The lifecycle: created, in progress, in review, pushed, CI issues, closed -- gates at
`in_review` (operator, 2026-09-23). The review records what holds a work order and
`ds review --status` reports it, and the bench's round-one receiver's-view seat found the
catch: nothing was required to read that report, so a work order with an open finding
could move on exactly as if it had none. `advance_work_order(to="pushed")` is now the
place that must read it.

These are also the first tests to call `advance_work_order` directly at all.
"""

from __future__ import annotations

import sqlite3

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.mutations import advance_work_order
from core.work_orders.review_answers import record_answers, record_dispatch

#: Credentials issued by each dispatch in this module, so recording helpers can present
#: the one issued to the reviewer they record for -- as a real reviewer must.
_ISSUED: dict = {}


def _issuing(fn):
    def wrapper(*args, **kwargs):
        doc = fn(*args, **kwargs)
        _ISSUED.update(doc.get("credentials") or {})
        return doc

    return wrapper


record_dispatch = _issuing(record_dispatch)

PROJECT_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
WO_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
NOW = "2026-09-23T00:00:00+00:00"
REVIEWER = "review-gate-and-test-integrity"
HOLDS = {"command": "python -m pytest tests/unit/test_x.py -q", "exit_code": 0}
FAILS = {"command": "python -m pytest /tmp/t.py -q", "exit_code": 1}


def _faithful(image, repro):
    return True, {"exit_code": repro["exit_code"], "output_sha256": "x", "output_tail": ""}, "ok"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An isolated authority, with the process env pointed at it.

    The env overrides are load-bearing: the event write resolves the spool from process
    environment rather than from the argument, so without them the row lands somewhere
    this test never looks (see test_wo_lifecycle_surface._run).
    """
    home = tmp_path / "home"
    db = home / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status,"
            " project_path, created_at, updated_at) VALUES (?, 'P', 'd', 'active', ?, ?, ?)",
            (PROJECT_ID, str(tmp_path), NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id,"
            " title, description, status, work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'WO-PUSH-GATE', 'd', 'in_review', 'infrastructure', ?, ?)",
            (WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(home / "events"))
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db))
    return home


def _db(home):
    return home / "state" / "studio.db"


def _status(home) -> str:
    conn = sqlite3.connect(str(_db(home)))
    try:
        return conn.execute(
            "SELECT status FROM business_work_orders WHERE work_order_id = ?", (WO_ID,)
        ).fetchone()[0]
    finally:
        conn.close()


def _push(home, tmp_path):
    return advance_work_order(
        work_order_id=WO_ID, to="pushed", source_root=tmp_path, dream_studio_home=home
    )


def _dispatch(home, lanes=("lane-one", "lane-two")):
    record_dispatch(
        WO_ID,
        sha="b" * 40,
        image="ds-review:fake",
        change_set=["x.py"],
        assignments=[{"reviewer": REVIEWER, "seat": "Gate", "lanes": list(lanes)}],
        db_path=_db(home),
        ownership={REVIEWER: {"lane-one", "lane-two"}},
    )


def _answer(home, answers):
    return record_answers(
        WO_ID,
        REVIEWER,
        answers,
        db_path=_db(home),
        available=lambda: (True, "fake"),
        verify=_faithful,
        credential=_ISSUED.get(REVIEWER),
    )


def test_a_work_order_never_reviewed_cannot_be_pushed(home, tmp_path):
    result = _push(home, tmp_path)
    assert result["ok"] is False
    assert "no review has been dispatched" in result["error"]
    assert _status(home) == "in_review", "a refused push must not move the work order"


def test_an_open_finding_holds_the_work_order(home, tmp_path):
    _dispatch(home)
    _answer(
        home,
        [
            {"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS},
            {"lane": "lane-two", "verdict": "finding", "evidence": "x.py:1", "reproduction": FAILS},
        ],
    )
    result = _push(home, tmp_path)
    assert result["ok"] is False
    assert result["review"]["open_findings"] == [{"lane": "lane-two", "reviewer": REVIEWER}]
    assert _status(home) == "in_review"


def test_an_unanswered_lane_holds_the_work_order(home, tmp_path):
    _dispatch(home)
    _answer(home, [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}])
    result = _push(home, tmp_path)
    assert result["ok"] is False
    assert result["review"]["unanswered"] == {REVIEWER: ["lane-two"]}


def test_a_clean_review_lets_it_through(home, tmp_path):
    _dispatch(home)
    _answer(
        home,
        [
            {"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS},
            {"lane": "lane-two", "verdict": "cannot-tell", "why": "needs production traffic"},
        ],
    )
    result = _push(home, tmp_path)
    assert result["ok"] is True, result.get("error")
    assert _status(home) == "pushed"


def test_a_finding_resolved_in_a_later_round_lets_it_through(home, tmp_path):
    """The loop the operator described: lanes find, work happens, lanes look again."""
    _dispatch(home)
    _answer(
        home,
        [
            {"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS},
            {"lane": "lane-two", "verdict": "finding", "evidence": "x.py:1", "reproduction": FAILS},
        ],
    )
    assert _push(home, tmp_path)["ok"] is False
    _dispatch(home)  # round 2, after the fix -- the open lane is carried
    _answer(
        home,
        [
            {"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS},
            {"lane": "lane-two", "verdict": "pass", "reproduction": HOLDS},
        ],
    )
    assert _push(home, tmp_path)["ok"] is True
    assert _status(home) == "pushed"


def test_moving_into_review_is_not_gated_on_the_review(home, tmp_path):
    """Only `pushed` reads the review; `in_review` is where the review happens."""
    conn = sqlite3.connect(str(_db(home)))
    try:
        conn.execute(
            "UPDATE business_work_orders SET status = 'in_progress' WHERE work_order_id = ?",
            (WO_ID,),
        )
        conn.commit()
    finally:
        conn.close()
    result = advance_work_order(
        work_order_id=WO_ID, to="in_review", source_root=tmp_path, dream_studio_home=home
    )
    assert result["ok"] is True, result.get("error")
    assert _status(home) == "in_review"
