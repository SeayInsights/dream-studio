"""WO-MERGE-BEFORE-VERIFY: consult the work order's own verdict at merge time.

Every red on main on 2026-08-19 was one failing test out of ~5,386, from a work
order whose own verify was failing or had never run when its PR merged. Verify is a
CLOSE gate and merge happens BEFORE close, so the entire verification apparatus
could not influence the decision that puts code on main.

This does not block merges and must not: an urgent hotfix has to be mergeable, and
a red verdict on someone else's WO must never stop unrelated work. It reads the
verdict, reports it, and makes an override recorded rather than unremarked.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.gates.merge_readiness import (
    merge_readiness,
    record_merge_override,
    resolve_work_order,
    verdict_state,
)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(path)
    return path


def _wo(db: Path) -> str:
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-08-20T00:00:00+00:00"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", now, now),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at)"
        " VALUES (?,?,NULL,'WO','d','infrastructure','in_progress',?,?)",
        (wo_id, project_id, now, now),
    )
    conn.commit()
    conn.close()
    return wo_id


def _store_verdict(db: Path, wo_id: str, verdict: dict, *, enveloped: bool = True) -> None:
    from core.work_orders.artifacts import set_wo_artifact

    if enveloped:
        set_wo_artifact(
            wo_id,
            "review_verdict",
            json.dumps(verdict),
            db_path=db,
            generator="ds work-order verify",
            project_root=Path("."),
        )
    else:
        set_wo_artifact(wo_id, "review_verdict", json.dumps(verdict), db_path=db)


# ── Resolution ─────────────────────────────────────────────────────────────────


def test_a_branch_naming_its_work_order_resolves(db):
    wo_id = _wo(db)
    resolved, why = resolve_work_order(branch=f"fix/wo-{wo_id[:8]}-thing", db_path=db)
    assert resolved == wo_id and why is None

    resolved, why = resolve_work_order(branch=f"feat/{wo_id}", db_path=db)
    assert resolved == wo_id and why is None


def test_a_branch_naming_no_work_order_says_so_rather_than_guessing(db):
    """ "This branch has no WO" and "this WO has no verdict" are different facts with
    different remedies. Guessing between them makes the report unactionable."""
    resolved, why = resolve_work_order(branch="chore/tidy-readme", db_path=db)
    assert resolved is None
    assert why and "does not name a work order" in why


def test_an_unknown_id_in_a_branch_is_not_invented(db):
    resolved, why = resolve_work_order(branch="fix/wo-deadbeef-nope", db_path=db)
    assert resolved is None
    assert why and "no work order matches" in why


# ── Verdict classification ─────────────────────────────────────────────────────


def test_a_passing_verdict_is_ready(db):
    wo_id = _wo(db)
    _store_verdict(db, wo_id, {"passed": True, "summary": "all tasks substantiated"})
    out = merge_readiness(work_order_id=wo_id, db_path=db)
    assert out["ready"] is True and out["state"] == "passed"


def test_a_failing_verdict_is_not_ready_and_names_the_reason(db):
    """The 9a9e23da case: a verdict on record as FAILED, naming two gaps, whose PR
    merged anyway."""
    wo_id = _wo(db)
    _store_verdict(
        db, wo_id, {"passed": False, "summary": "two gaps remain: HEAD comparison, skill text"}
    )
    out = merge_readiness(work_order_id=wo_id, db_path=db)
    assert out["ready"] is False
    assert out["state"] == "failed"
    assert "two gaps remain" in out["reason"]
    assert "2026-08-19" in out["advice"], "the advice should say why this rule exists"


def test_an_absent_verdict_is_distinct_from_a_failing_one(db):
    """Most of the 2026-08-19 merges were this: verify had never run at all."""
    wo_id = _wo(db)
    out = merge_readiness(work_order_id=wo_id, db_path=db)
    assert out["ready"] is False
    assert out["state"] == "absent"
    assert "never" in (out["reason"] or "") or "not run" in (out["reason"] or "")
    assert "work-order verify" in out["advice"], "the remedy is to run it, not to retry"


def test_unreviewable_is_not_treated_as_approval(db):
    """ "We could not tell" is not "it is fine" — the distinction the grader-outage
    path depends on."""
    wo_id = _wo(db)
    _store_verdict(
        db, wo_id, {"passed": False, "summary": "independent review unreviewable: grader timed out"}
    )
    out = merge_readiness(work_order_id=wo_id, db_path=db)
    assert out["ready"] is False
    assert out["state"] == "unreviewable"
    assert "re-run verify" in out["advice"]


def test_a_summaryless_failure_is_unreviewable_not_failed(db):
    """WO-VERDICT-PARTIAL-WRITE's lesson applied here too: an empty record is not a
    judgement, so it must not be reported as one."""
    wo_id = _wo(db)
    _store_verdict(db, wo_id, {"passed": False})
    out = merge_readiness(work_order_id=wo_id, db_path=db)
    assert out["state"] == "unreviewable"


def test_an_envelopeless_verdict_does_not_count_as_a_review(db):
    """Same rule the independent_review gate applies — a hand-written verdict is
    not a certified review, and this check must not be the softer door."""
    wo_id = _wo(db)
    _store_verdict(db, wo_id, {"passed": True, "summary": "trust me"}, enveloped=False)
    out = merge_readiness(work_order_id=wo_id, db_path=db)
    assert out["ready"] is False
    assert out["state"] == "absent"
    assert "provenance" in (out["reason"] or "")


def test_an_unparseable_verdict_is_unreadable_not_passed(db):
    from core.work_orders.artifacts import set_wo_artifact

    wo_id = _wo(db)
    set_wo_artifact(
        wo_id,
        "review_verdict",
        "not json at all",
        db_path=db,
        generator="ds work-order verify",
        project_root=Path("."),
    )
    out = merge_readiness(work_order_id=wo_id, db_path=db)
    assert out["ready"] is False and out["state"] == "unreadable"


# ── It reports; it does not block ──────────────────────────────────────────────


def test_a_change_with_no_work_order_is_ready_with_a_note(db):
    """A docs typo or a revert has no WO. Refusing those would make this check
    something people route around, and a check people route around is worse than
    no check."""
    out = merge_readiness(branch="chore/fix-typo", db_path=db)
    assert out["ready"] is True
    assert out["state"] == "no_work_order"
    assert out["reason"], "the absence is still explained"


def test_nothing_here_raises_on_a_missing_database(tmp_path):
    """A merge check that explodes gets removed from the workflow."""
    out = merge_readiness(branch="fix/wo-abcdef12-x", db_path=tmp_path / "absent.db")
    assert out["ready"] is True and out["state"] == "no_work_order"


# ── The override is recorded ───────────────────────────────────────────────────


def test_an_override_is_recorded_as_a_queryable_bypass(db, tmp_path, monkeypatch):
    """Merging past a red verdict stays possible — an urgent hotfix must be
    mergeable. It just stops being unremarked."""
    events: list[dict] = []

    def _capture(gate, reason, extra=None):
        events.append({"gate": gate, "reason": reason, **(extra or {})})

    monkeypatch.setattr("core.gates.bypass_event.record_gate_bypass", _capture)
    record_merge_override(
        work_order_id="abc123",
        state="failed",
        reason="urgent hotfix; verdict gaps tracked as WO xyz",
        pull_request=999,
        merge_commit="deadbeef",
    )
    assert len(events) == 1
    assert events[0]["gate"] == "merge_before_verify"
    assert events[0]["verdict_state"] == "failed"
    assert events[0]["pull_request"] == 999
    assert events[0]["work_order_id"] == "abc123"


def test_the_override_uses_the_existing_bypass_family(db):
    """Reusing gate.bypassed means ds doctor's bypass audit and bypass_report
    already aggregate it. A new event type nobody reads would be this same
    invisibility wearing a different name."""
    import inspect

    from core.gates import merge_readiness as mod

    src = inspect.getsource(mod.record_merge_override)
    assert "record_gate_bypass" in src
    assert 'gate="merge_before_verify"' in src
