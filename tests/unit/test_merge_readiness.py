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


# ── Task 4: the pattern is surfaced, not just the instance ─────────────────────


def _emit_bypass(db: Path, when: str, reason: str = "urgent hotfix") -> None:
    """Write a gate.bypassed row directly — the audit reads business_canonical_events,
    and this test is about the READER, not the spool round trip."""
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO business_canonical_events"
            " (event_id, event_type, event_timestamp, payload)"
            " VALUES (?,?,?,?)",
            (
                str(uuid.uuid4()),
                "gate.bypassed",
                when,
                json.dumps({"gate": "merge_before_verify", "reason": reason}),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def test_a_single_override_is_counted_without_being_called_a_pattern(db):
    """One is a judgement call. Labelling it a process gap would train an operator
    to ignore the line."""
    from core.health.doctor_bypass import bypass_audit

    _emit_bypass(db, _now_iso())
    audit = bypass_audit(db)
    summary = audit.get("merge_before_verify")
    assert summary, "a merge override must be surfaced on its own, not only by gate name"
    assert summary["count"] == 1
    assert summary["recurring"] is False
    assert "note" not in summary


def test_repeated_overrides_are_named_as_a_pattern(db):
    """The observation DS should have produced before an operator said "CI keeps
    failing on main" — every red that day was one instance of this."""
    from core.health.doctor_bypass import bypass_audit

    for _ in range(3):
        _emit_bypass(db, _now_iso())
    audit = bypass_audit(db)
    summary = audit["merge_before_verify"]
    assert summary["count"] == 3
    assert summary["recurring"] is True
    assert "process gap" in summary["note"]
    assert "2026-08-19" in summary["note"], "the note should cite the incident it came from"


def test_no_overrides_means_no_merge_section_at_all(db):
    """A section that always renders becomes furniture. Absent when clean."""
    from core.health.doctor_bypass import bypass_audit

    audit = bypass_audit(db)
    assert "merge_before_verify" not in audit
    assert audit["total"] == 0


def test_the_override_still_appears_under_its_gate_name(db):
    """The focused summary is additive — it must not replace the general
    aggregation that bypass_report and the doctor already consume."""
    from core.health.doctor_bypass import bypass_audit

    _emit_bypass(db, _now_iso())
    audit = bypass_audit(db)
    assert "merge_before_verify" in audit["gate_bypasses"]
    assert audit["gate_bypasses"]["merge_before_verify"]["count"] == 1


# ── The REAL verdict shape (not the one I invented) ────────────────────────────

# Copied from an actual stored review-verdict.json, not hand-designed. The first
# version of this module assumed top-level `summary` and `failure_reasons`; real
# verdicts carry NEITHER — the prose is under completion.summary and the findings
# under gaps / spawned_work_orders. Fourteen tests passed against the invented
# shape, which is exactly why they proved nothing.
_REAL_FAILED_VERDICT = {
    "passed": False,
    "work_order_id": "6a4c21d1",
    "certification_basis": "git_diff",
    "scores": {
        "completion_score": 0.75,
        "correctness_score": 1.0,
        "quality_score": 0.59,
        "composite_score": 0.793,
    },
    "completion": {
        "summary": (
            "The verdict reader is complete and careful ... The gap is that none of it is "
            "reachable: merge_readiness() and record_merge_override() have no production "
            "call sites. Note: it separates never-run from failed from unreviewable."
        ),
        "passed": False,
    },
    "gaps": [{"title": "Wire the merge-readiness check into a surface that runs before a merge"}],
    "spawned_work_orders": [{"work_order_id": "659671b4"}],
}


def test_a_real_failed_verdict_is_classified_failed_not_unreviewable(db):
    """The severest defect this module shipped: a verdict with three concrete gaps
    and a 0.793 composite was reported UNREVIEWABLE, telling an operator to re-run
    verify instead of showing them the gaps. Two causes, both here:

    1. the shape was invented — real verdicts have no top-level summary;
    2. the classifier substring-matched the word "unreviewable" in prose, and this
       verdict's own summary contains it while describing the distinction.
    """
    wo_id = _wo(db)
    _store_verdict(db, wo_id, _REAL_FAILED_VERDICT)
    out = merge_readiness(work_order_id=wo_id, db_path=db)
    assert out["state"] == "failed", f"a real failing verdict is FAILED: {out}"
    assert out["ready"] is False
    assert "no production call sites" in (out["summary"] or ""), "read the prose where it lives"
    assert "Fix them" in out["advice"], "advice must point at the gaps, not at a retry"


def test_the_word_unreviewable_in_prose_does_not_classify(db):
    """Classifying a judgement by a word appearing inside it is how a real failure
    gets softened into 'we could not tell'."""
    wo_id = _wo(db)
    _store_verdict(
        db,
        wo_id,
        {
            "passed": False,
            "completion": {"summary": "discusses unreviewable states at length"},
            "gaps": [{"title": "a real gap"}],
        },
    )
    assert merge_readiness(work_order_id=wo_id, db_path=db)["state"] == "failed"


def test_a_genuine_unreviewable_verdict_still_classifies(db):
    """verify opens its own warning with this phrase — a prefix, not a substring."""
    wo_id = _wo(db)
    _store_verdict(
        db,
        wo_id,
        {"passed": False, "summary": "independent review unreviewable: grader timed out"},
    )
    assert merge_readiness(work_order_id=wo_id, db_path=db)["state"] == "unreviewable"


def test_a_disk_stored_verdict_is_not_reported_as_never_run(db, tmp_path):
    """First smoke test against real data found this: the reader consulted only the
    authority, so a verdict on the disk fallback read as 'verify has not run' —
    opposite remedies (fix the gaps vs run it at all)."""
    import json as _json

    wo_id = _wo(db)
    vdir = tmp_path / "work-orders" / wo_id
    vdir.mkdir(parents=True)
    from core.work_orders.artifact_envelope import wrap

    (vdir / "review-verdict.json").write_text(
        wrap(
            _json.dumps(_REAL_FAILED_VERDICT),
            generator="ds work-order verify",
            head_commit_sha=None,
        ),
        encoding="utf-8",
    )
    out = merge_readiness(work_order_id=wo_id, db_path=db, planning_root=tmp_path)
    assert out["state"] == "failed", f"a disk-stored verdict must be read: {out}"


def test_the_cli_surface_exists_and_is_wired(db):
    """The finding that mattered most: merge_readiness had NO production call site,
    so the WO's own diagnosis ('a gate that sits where it cannot stop the thing it
    was built to stop') applied to its own fix. A checker nobody can invoke is not
    a check."""
    from interfaces.cli.commands.work_order_query import _work_order_merge_check

    assert callable(_work_order_merge_check)

    import inspect

    from interfaces.cli.commands import work_order_dispatch

    src = inspect.getsource(work_order_dispatch)
    assert '"merge-check"' in src, "the subcommand must be registered"
    assert "_work_order_merge_check(" in src, "and dispatched"
