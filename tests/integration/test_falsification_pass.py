"""WO-FALSIFY-FIRST-PASS: the falsification analyst stage end-to-end.

Every other grader checks COMPLIANCE with criteria the author wrote. None asked
"what should have been tested and wasn't" — the question a human reviewer asked
across seven rounds of gw#619, and the one DS structurally could not ask (2026-08-18
audit). This stage asks it by construction: every worst-case scenario it raises is
classified COVERED / PROPOSED / UNVERIFIED, error-severity PROPOSED items become
tracked work, and UNVERIFIED items become a named ledger instead of silence.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.verify_prompts import _FALSIFICATION_PROMPT_TEMPLATE

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-16T00:00:00.000000Z"


# ── taxonomy (task 0cac9a45) ────────────────────────────────────────────────────


def test_taxonomy_includes_reachability_class():
    """The scenario taxonomy must carry the exposed-host / config-drift class:
    for any secret or token, what it is VALID AGAINST vs what the code CHECKS.
    Source incident: the Fulcrum magic-link dev_link gated on a base-URL config
    while BIND_HOST controlled actual exposure (2026-08-18)."""
    # COMPOSED, not the raw template. The taxonomy was extracted to
    # core.work_orders.scenario_taxonomy so the orchestrator's diagnosis can walk the same
    # classes; it now reaches this prompt at format time. Asserting against the bare
    # template would fail for a reason that says nothing about scenario coverage.
    from core.work_orders.scenario_taxonomy import SCENARIO_TAXONOMY

    tpl = _FALSIFICATION_PROMPT_TEMPLATE.format(
        title="t", task_list="tl", git_diff="d", scenario_taxonomy=SCENARIO_TAXONOMY
    )
    assert "reachability_vs_config" in tpl
    assert "VALID AGAINST" in tpl
    assert "bind address" in tpl
    # The other durable-state classes from the gw#619 family.
    for cls in (
        "crash_mid_write",
        "race_between_writers",
        "version_skew",
        "partial_failure",
        "malformed_input",
        "interrupted_io",
        "empty_absent_state",
    ):
        assert cls in tpl, f"taxonomy missing {cls}"
    # Every raised scenario must be classified — no silent unknowns.
    for status in ("COVERED", "PROPOSED", "UNVERIFIED"):
        assert status in tpl


# ── end-to-end verdict + ledger (task cecd70ca) ─────────────────────────────────


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


@contextmanager
def _patch_db(db_path: Path):
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        yield


def _seed(db_path: Path) -> tuple[str, str]:
    project_id, milestone_id, work_order_id = (str(uuid.uuid4()) for _ in range(3))
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "Test", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones"
        " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description,"
        "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,'in_progress',1,?,?,?)",
        (work_order_id, project_id, milestone_id, "WO under review", "d", "cleanup", NOW, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_tasks"
        " (task_id, work_order_id, project_id, title, description, acceptance_criteria,"
        "  status, created_at, updated_at)"
        " VALUES (?,?,?,'T1','store a marker the read path trusts',?, 'complete', ?, ?)",
        (str(uuid.uuid4()), work_order_id, project_id, "SQL-CHECK: SELECT 1", NOW, NOW),
    )
    conn.commit()
    conn.close()
    return project_id, work_order_id


_CLEAN = {
    "completion": {
        "passed": True,
        "completion_score": 1.0,
        "tasks_verified": [{"task_title": "T1", "evidence": "done", "verdict": "pass"}],
        "summary": "done",
        "gaps": [],
    },
    "correctness": {
        "correctness_passed": True,
        "correctness_score": 1.0,
        "violations": [],
        "coverage_gaps": [],
        "migration_gaps": [],
    },
    "quality": {"quality_passed": True, "quality_score": 1.0, "issues": []},
}

_FALSIFICATION = {
    "falsification_score": 0.75,
    "summary": "A crash between the marker write and the read leaves a trusted marker unbacked.",
    "scenarios": [
        {
            "scenario_class": "crash_mid_write",
            "surface": "core/x.py::store_marker",
            "scenario": "process dies after the marker row commits but before the payload write",
            "status": "PROPOSED",
            "evidence": "test_marker_without_payload_is_rejected: kill between writes, assert reader errors",
            "severity": "error",
        },
        {
            "scenario_class": "reachability_vs_config",
            "surface": "core/x.py::issue_token",
            "scenario": "token returned when BASE_URL looks local but BIND_HOST exposes the port",
            "status": "UNVERIFIED",
            "evidence": "needs a real bound-host deploy; no harness binds a second interface in CI",
            "severity": "error",
        },
        {
            "scenario_class": "empty_absent_state",
            "surface": "core/x.py::read_marker",
            "scenario": "fresh install with no marker row",
            "status": "COVERED",
            "evidence": "tests/unit/test_x.py::test_missing_marker_returns_none",
            "severity": "info",
        },
    ],
}


def _run_verify(db_path: Path, tmp_path: Path, work_order_id: str, graders: dict) -> dict:
    with _patch_db(db_path):
        with patch("core.work_orders.verify_graders._run_graders_parallel", return_value=graders):
            with patch(
                "core.work_orders.verify_git._collect_git_commits",
                return_value="diff --git a/core/x.py b/core/x.py\n+marker write",
            ):
                from core.work_orders.verify import verify_work_order

                return verify_work_order(
                    work_order_id=work_order_id,
                    source_root=REPO_ROOT,
                    dream_studio_home=tmp_path,
                    planning_root=tmp_path / "planning",
                )


def test_verdict_contains_falsification_ledger(tmp_path, monkeypatch):
    """The verdict carries the falsification section; UNVERIFIED scenarios land
    in the authority ledger; error-severity PROPOSED scenarios spawn tracked
    work; COVERED scenarios spawn nothing."""
    monkeypatch.delenv("DREAM_STUDIO_VERIFY_MOCK", raising=False)
    db_path = _make_db(tmp_path)
    _, work_order_id = _seed(db_path)

    graders = dict(_CLEAN)
    graders["falsification"] = _FALSIFICATION
    result = _run_verify(db_path, tmp_path, work_order_id, graders)

    assert result["ok"] is True
    # Falsification is additive evidence — it records and spawns, never certifies.
    assert result["passed"] is True, result.get("gaps")

    # The verdict carries the analysis verbatim.
    from core.work_orders.artifact_envelope import unwrap

    verdict_path = tmp_path / "planning" / "work-orders" / work_order_id / "review-verdict.json"
    verdict = json.loads(unwrap(verdict_path.read_text(encoding="utf-8"))[0])
    assert verdict["falsification"]["falsification_score"] == 0.75
    assert len(verdict["falsification"]["scenarios"]) == 3

    # UNVERIFIED risk is NAMED in the verdict and in the authority ledger.
    assert len(verdict["unverified_risks"]) == 1
    assert verdict["unverified_risks"][0]["scenario_class"] == "reachability_vs_config"

    from core.work_orders.verify_persist import read_unverified_ledger

    ledger = read_unverified_ledger(
        work_order_id, planning_root=tmp_path / "planning", db_path=db_path
    )
    assert ledger is not None, "the UNVERIFIED ledger must be durable state"
    assert ledger["count"] == 1
    assert ledger["unverified"][0]["surface"] == "core/x.py::issue_token"

    # The error-severity PROPOSED scenario became tracked work; COVERED did not.
    spawned_titles = [s.get("title", "") for s in result["spawned_work_orders"]]
    assert any("adversarial tests" in t for t in spawned_titles), spawned_titles
    conn = sqlite3.connect(str(db_path))
    try:
        task_titles = [
            r[0]
            for r in conn.execute(
                "SELECT title FROM business_tasks WHERE work_order_id = ?",
                (result["spawned_work_orders"][0]["work_order_id"],),
            ).fetchall()
        ]
    finally:
        conn.close()
    assert any("crash_mid_write" in t for t in task_titles), task_titles
    assert not any("empty_absent_state" in t for t in task_titles), "COVERED must not spawn"


def test_absent_analysis_is_recorded_not_silent(tmp_path, monkeypatch):
    """A falsification grader that could not run is recorded as unavailable — an
    absent analysis must never read as 'no worst cases found'."""
    monkeypatch.delenv("DREAM_STUDIO_VERIFY_MOCK", raising=False)
    db_path = _make_db(tmp_path)
    _, work_order_id = _seed(db_path)

    graders = dict(_CLEAN)
    graders["falsification"] = {"_grader_error": "provider quota exhausted"}
    result = _run_verify(db_path, tmp_path, work_order_id, graders)

    assert result["ok"] is True
    assert "quota" in (result["falsification_unavailable"] or "")
    assert result["unverified_risks"] == []

    from core.work_orders.verify_persist import read_unverified_ledger

    # No ledger is written when no analysis ran — the unavailable marker carries
    # the meaning instead, so an empty ledger cannot be misread as "clean".
    assert (
        read_unverified_ledger(work_order_id, planning_root=tmp_path / "planning", db_path=db_path)
        is None
    )


def test_empty_ledger_is_written_when_analysis_finds_nothing(tmp_path, monkeypatch):
    """'The analyst found no untestable residual' and 'no analysis ran' must not
    look identical downstream: a clean run writes an EMPTY ledger."""
    monkeypatch.delenv("DREAM_STUDIO_VERIFY_MOCK", raising=False)
    db_path = _make_db(tmp_path)
    _, work_order_id = _seed(db_path)

    graders = dict(_CLEAN)
    graders["falsification"] = {
        "falsification_score": 1.0,
        "summary": "no untestable residual",
        "scenarios": [
            {
                "scenario_class": "crash_mid_write",
                "surface": "core/x.py",
                "scenario": "covered",
                "status": "COVERED",
                "evidence": "tests/unit/test_x.py::test_crash",
                "severity": "info",
            }
        ],
    }
    result = _run_verify(db_path, tmp_path, work_order_id, graders)
    assert result["falsification_unavailable"] is None

    from core.work_orders.verify_persist import read_unverified_ledger

    ledger = read_unverified_ledger(
        work_order_id, planning_root=tmp_path / "planning", db_path=db_path
    )
    assert ledger is not None, "a clean analysis still writes an EMPTY ledger"
    assert ledger["count"] == 0
