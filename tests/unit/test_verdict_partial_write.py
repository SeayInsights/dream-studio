"""WO-VERDICT-PARTIAL-WRITE: an interrupted verify must not block a passing close.

Registered after a killed verify produced a close failure reading
"independent_review: review failed — no summary." on a work order whose review had
actually passed.

MEASUREMENT CORRECTED THE PREMISE. The WO was registered claiming an envelope-less
partial file had slipped past the provenance guard. Driving the real gate showed it
does not: an envelope-less verdict is rejected outright as "lacks a provenance
envelope". The artifact that produced the observed message was therefore verify's
OWN enveloped verdict, written when the completion grader timed out — passed=False
with nothing explaining why. So:

  - task 3 (a summary-less failure is unreviewable, not failed) is the fix for the
    incident actually observed;
  - task 1 (atomic writes) removes a real hazard that was NOT the observed cause;
  - task 2 (scope the legacy exception) applies to the OTHER artifact gates, which
    do accept envelope-less artifacts — not to independent_review.

Recorded here because the WO's own description asserted a cause that turned out to
be wrong, and a test file is where the correction is least likely to be lost.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.close_gates import _PROVENANCE_CUTOVER, run_gate_check
from core.work_orders.verify_persist import _atomic_write


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "studio.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(path)
    return path


def _wo(db: Path, *, created: str = "2026-08-20T00:00:00+00:00") -> str:
    project_id, wo_id = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, "P", "", "active", created, created),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
        "  status, created_at, updated_at)"
        " VALUES (?,?,NULL,'WO','d','infrastructure','in_progress',?,?)",
        (wo_id, project_id, created, created),
    )
    conn.commit()
    conn.close()
    return wo_id


def _gate(name: str, db: Path, planning: Path, wo_id: str) -> tuple[bool, str]:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        return run_gate_check(
            name, planning_root=planning, work_order_id=wo_id, project_id="", conn=conn, db_path=db
        )
    finally:
        conn.close()


# ── Task 1: atomic writes ──────────────────────────────────────────────────────


def test_an_interrupted_verdict_write_leaves_no_artifact(tmp_path):
    """An absent verdict is recoverable (re-run verify); a truncated one reads as a
    failed review and blocks a close on work that passed. So: all or nothing."""
    target = tmp_path / "wo" / "review-verdict.json"

    class Boom(BaseException):
        """BaseException on purpose — a Ctrl-C mid-write is the real scenario."""

    payload = "x" * 100_000
    with pytest.raises(Boom):
        # Interrupt inside the write by making the encode step raise.
        class Exploding(str):
            def __str__(self) -> str:  # pragma: no cover - defensive
                raise Boom()

        def _boom(*_a, **_k):
            raise Boom()

        import core.work_orders.verify_persist as vp

        real = vp.os.fsync
        vp.os.fsync = _boom  # fail after content is written, before the rename
        try:
            _atomic_write(target, payload)
        finally:
            vp.os.fsync = real

    assert not target.exists(), "a partial verdict must never appear at the real path"
    leftovers = list((tmp_path / "wo").glob(".*tmp*")) if (tmp_path / "wo").is_dir() else []
    assert leftovers == [], f"the temp file must be cleaned up, found {leftovers}"


def test_a_completed_write_is_fully_present(tmp_path):
    target = tmp_path / "wo" / "review-verdict.json"
    _atomic_write(target, json.dumps({"passed": True, "summary": "ok"}))
    assert json.loads(target.read_text(encoding="utf-8"))["passed"] is True


def test_a_rewrite_replaces_rather_than_appends(tmp_path):
    target = tmp_path / "wo" / "review-verdict.json"
    _atomic_write(target, json.dumps({"run": 1}))
    _atomic_write(target, json.dumps({"run": 2}))
    assert json.loads(target.read_text(encoding="utf-8")) == {"run": 2}


# ── Task 3: a summary-less failure is unreviewable, not failed ─────────────────


def test_a_summaryless_failure_reads_as_unreviewable(db, tmp_path):
    """The incident actually observed. verify wrote an enveloped verdict recording a
    grader timeout: passed=False, nothing explaining why. The gate called that a
    failed review and blocked a close on work that had passed."""
    from core.work_orders.artifacts import set_wo_artifact

    wo_id = _wo(db)
    set_wo_artifact(
        wo_id,
        "review_verdict",
        json.dumps({"passed": False}),
        db_path=db,
        generator="ds work-order verify",
        project_root=Path("."),
    )
    passed, reason = _gate("independent_review", db, tmp_path, wo_id)
    assert passed is False, "no false green — the review genuinely did not certify"
    assert "UNREVIEWABLE" in reason
    assert "incomplete record" in reason
    assert "work-order verify" in reason, "the remedy must be named"
    assert (
        "review failed" not in reason
    ), "missing information must not be converted into a verdict against the work"


def test_a_real_failure_still_reads_as_failed(db, tmp_path):
    """The converse, so `unreviewable` cannot become a way for a genuine failure to
    read as inconclusive — that inversion would be worse than the defect."""
    from core.work_orders.artifacts import set_wo_artifact

    wo_id = _wo(db)
    set_wo_artifact(
        wo_id,
        "review_verdict",
        json.dumps({"passed": False, "summary": "task 3 was never implemented"}),
        db_path=db,
        generator="ds work-order verify",
        project_root=Path("."),
    )
    passed, reason = _gate("independent_review", db, tmp_path, wo_id)
    assert passed is False
    assert "review failed" in reason
    assert "task 3 was never implemented" in reason
    assert "UNREVIEWABLE" not in reason


def test_failure_reasons_alone_are_enough_to_be_a_real_verdict(db, tmp_path):
    """A verdict carrying reasons but no prose summary is still a real verdict."""
    from core.work_orders.artifacts import set_wo_artifact

    wo_id = _wo(db)
    set_wo_artifact(
        wo_id,
        "review_verdict",
        json.dumps({"passed": False, "failure_reasons": ["composite_score 0.41 < 0.70"]}),
        db_path=db,
        generator="ds work-order verify",
        project_root=Path("."),
    )
    _passed, reason = _gate("independent_review", db, tmp_path, wo_id)
    assert "UNREVIEWABLE" not in reason


# ── Task 2: the legacy exception is scoped to actual legacy ────────────────────


def test_a_new_envelopeless_verdict_is_rejected_not_believed(db, tmp_path):
    """Measured, not assumed: independent_review already rejects an envelope-less
    verdict outright, with no legacy exception. Pinned so the guard cannot be
    loosened into one later."""
    wo_id = _wo(db)
    vdir = tmp_path / "work-orders" / wo_id
    vdir.mkdir(parents=True)
    (vdir / "review-verdict.json").write_text(json.dumps({"passed": False}), encoding="utf-8")

    passed, reason = _gate("independent_review", db, tmp_path, wo_id)
    assert passed is False
    assert "lacks a provenance envelope" in reason


def test_a_post_cutover_security_scan_needs_an_envelope(db, tmp_path):
    """This gate DOES accept envelope-less artifacts, which is where the overbroad
    exception actually lived — a hand-written or half-written scan passed."""
    wo_id = _wo(db, created="2026-08-20T00:00:00+00:00")
    sdir = tmp_path / "work-orders" / wo_id
    sdir.mkdir(parents=True)
    (sdir / "security-scan.md").write_text("## Verdict\nPASS\n", encoding="utf-8")

    passed, reason = _gate("security_scan", db, tmp_path, wo_id)
    assert passed is False
    assert "lacks a provenance envelope" in reason
    assert _PROVENANCE_CUTOVER in reason


def test_a_pre_cutover_security_scan_keeps_its_historical_acceptance(db, tmp_path):
    """Artifacts stored before envelopes existed have no envelope through no fault
    of their own. Rejecting them would make historical WOs unclosable."""
    wo_id = _wo(db, created="2026-07-01T00:00:00+00:00")
    sdir = tmp_path / "work-orders" / wo_id
    sdir.mkdir(parents=True)
    (sdir / "security-scan.md").write_text("## Verdict\nPASS\n", encoding="utf-8")

    passed, reason = _gate("security_scan", db, tmp_path, wo_id)
    assert passed is True, f"pre-cutover artifacts stay acceptable: {reason}"
