"""Closing a work order consults the lane review, not only the verify verdict.

Found in round two by two seats independently. The evidence-referee recorded an open lane
finding, wrote a legacy verify verdict, and called the real close gate: PASS. The
receiver's-view seat showed why: the close path reads the verify verdict at instance_key
'' and nothing else, and lane answers live under their own key so they never collide with
it. The push gate had closed one road around the review; this closes the other.
"""

from __future__ import annotations

import sqlite3
import uuid
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.review_answers import (
    lane_review_failure,
    record_answers,
    record_dispatch,
)

REVIEWER = "review-gate-and-test-integrity"
HOLDS = {"command": "true", "exit_code": 0}
FAILS = {"command": "false", "exit_code": 1}
OWNED = {REVIEWER: {"lane-one", "lane-two"}}


def _faithful(image, repro):
    return True, {"exit_code": repro["exit_code"], "output_sha256": "x", "output_tail": ""}, "ok"


@pytest.fixture
def authority(tmp_path):
    db = tmp_path / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-09-23T00:00:00+00:00"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", now, now),
    )
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id, project_id, milestone_id, title,"
        " description, work_order_type, status, created_at, updated_at)"
        " VALUES (?,?,NULL,'WO','d','cleanup','in_review',?,?)",
        (wo_id, project_id, now, now),
    )
    conn.commit()
    conn.close()
    return db, wo_id


def _review(db, wo_id, answers):
    record_dispatch(
        wo_id,
        sha="c" * 40,
        image="ds-review:fake",
        change_set=["x.py"],
        assignments=[{"reviewer": REVIEWER, "seat": "Gate", "lanes": ["lane-one", "lane-two"]}],
        db_path=db,
        ownership=OWNED,
    )
    record_answers(
        wo_id,
        REVIEWER,
        answers,
        db_path=db,
        available=lambda: (True, "fake"),
        verify=_faithful,
    )


def _close(tmp_path, db, wo_id, *, force):
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db
    unknown = {"status": "unknown", "red": False, "reason": "not under test"}
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        with patch("core.health.main_ci.main_ci_status", return_value=unknown):
            from core.work_orders.close import close_work_order

            return close_work_order(
                work_order_id=wo_id,
                force=force,
                skip_verify=True,
                source_root=tmp_path,
                dream_studio_home=tmp_path,
                planning_root=tmp_path / "planning",
            )


def _lane_failures(result) -> list[str]:
    return [f for f in (result.get("failures") or []) if str(f).startswith("lane_review")]


def test_an_open_lane_finding_refuses_the_close(tmp_path, authority):
    db, wo_id = authority
    _review(
        db,
        wo_id,
        [
            {"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS},
            {"lane": "lane-two", "verdict": "finding", "evidence": "x.py:1", "reproduction": FAILS},
        ],
    )
    result = _close(tmp_path, db, wo_id, force=False)
    assert result["ok"] is False
    assert _lane_failures(result), result.get("failures")
    assert "1 open finding(s)" in _lane_failures(result)[0]


def test_an_unanswered_dispatched_lane_refuses_the_close(tmp_path, authority):
    db, wo_id = authority
    _review(db, wo_id, [{"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS}])
    result = _close(tmp_path, db, wo_id, force=False)
    assert result["ok"] is False
    assert "unanswered" in _lane_failures(result)[0]


def test_force_closes_past_it_recorded_not_silently(tmp_path, authority):
    """--force is how an operator overrides any close gate, and every override is
    recorded as gate.bypassed. The lane review is not exempt from being overridable, but
    it is never overridden without a record."""
    db, wo_id = authority
    _review(
        db,
        wo_id,
        [
            {"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS},
            {"lane": "lane-two", "verdict": "finding", "evidence": "x.py:1", "reproduction": FAILS},
        ],
    )
    emitted = []
    with patch("spool.writer.write_event", side_effect=lambda env, **k: emitted.append(env)):
        result = _close(tmp_path, db, wo_id, force=True)
    assert result["ok"] is True, result
    bypassed = [e for e in emitted if e.get("event_type") == "gate.bypassed"]
    assert [
        e["payload"]["gate"] for e in bypassed if e["payload"]["gate"] == "lane_review"
    ], "the forced close did not record the lane review it bypassed"


def test_in_review_but_never_dispatched_fails_the_close(authority):
    """Round three, boundary-semantics: "never reviewed" read as "reviewed clean", on the
    reasoning that the push gate owns it -- but close does not require `pushed`."""
    db, wo_id = authority  # the fixture's work order is in_review
    failure = lane_review_failure(wo_id, db_path=db)
    assert failure and "no review was ever dispatched" in failure


def test_a_legacy_work_order_that_never_entered_review_is_not_failed_for_it(authority):
    db, wo_id = authority
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE business_work_orders SET status='in_progress' WHERE work_order_id=?", (wo_id,)
    )
    conn.commit()
    conn.close()
    assert lane_review_failure(wo_id, db_path=db) is None


def test_a_clean_review_adds_no_lane_failure(authority):
    db, wo_id = authority
    _review(
        db,
        wo_id,
        [
            {"lane": "lane-one", "verdict": "pass", "reproduction": HOLDS},
            {"lane": "lane-two", "verdict": "cannot-tell", "why": "needs prod traffic"},
        ],
    )
    assert lane_review_failure(wo_id, db_path=db) is None


def test_a_forced_close_records_whether_it_was_ever_reviewed(tmp_path, authority):
    """Round three, receiver's view: a forced close of a work order nobody reviewed was
    recorded exactly like one reviewed clean. The state now rides the result and the
    work_order.closed event, blocking or not."""
    db, wo_id = authority
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE business_work_orders SET status='in_progress' WHERE work_order_id=?", (wo_id,)
    )
    conn.commit()
    conn.close()
    emitted = []
    with patch("spool.writer.write_event", side_effect=lambda env, **k: emitted.append(env)):
        result = _close(tmp_path, db, wo_id, force=True)
    assert result["ok"] is True, result
    assert result["lane_review"] == "never_dispatched"
    [closed] = [e for e in emitted if e.get("event_type") == "work_order.closed"]
    assert closed["payload"]["lane_review"] == "never_dispatched"
