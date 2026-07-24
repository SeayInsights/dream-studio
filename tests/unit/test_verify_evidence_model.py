"""WO cef6ddaa: verify evidence model — repo-aware + originating-WO traceability + no cascade.

Independent-review couldn't certify gap-spawned or external-repo WOs, re-spawning remediation
WOs endlessly. These tests lock the fix:
  A — commit search runs in the WO's TARGET repo (project_path), not the DS source_root.
  B — a gap WO ([gap-key: <parent>::cat]) certifies from commits under the PARENT id.
  C — a gap WO does not recursively spawn further gap WOs.
  ii — operator attestation records a passing review verdict that satisfies independent_review.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders import verify_git, verify_graders
from core.work_orders.artifacts import get_wo_artifact
from core.work_orders.close_gates import run_gate_check
from core.work_orders.verify import attest_work_order, verify_work_order

REPO = Path(__file__).resolve().parents[2]
NOW = "2026-07-23T00:00:00Z"
PROJ = "p-vem"
MS = "m-vem"

PASS_GRADERS = {
    "completion": {
        "passed": True,
        "completion_score": 1.0,
        "summary": "ok",
        "gaps": [],
        "tasks_verified": [],
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
GAP_GRADERS = {
    "completion": {
        "passed": False,
        "completion_score": 0.0,
        "summary": "incomplete",
        "gaps": [{"title": "wire the thing", "description": "", "category": "missing-impl"}],
        "tasks_verified": [],
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


@pytest.fixture
def env(tmp_path: Path):
    home = tmp_path / "home"
    db = home / "state" / "studio.db"
    db.parent.mkdir(parents=True)
    bootstrap_database(db)
    target_repo = tmp_path / "target-repo"
    target_repo.mkdir()
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_projects (project_id,name,description,status,project_path,created_at,updated_at)"
        " VALUES (?,'P','','active',?,?,?)",
        (PROJ, str(target_repo), NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_milestones (milestone_id,project_id,title,description,status,order_index,created_at,updated_at)"
        " VALUES (?,?,'M','','active',0,?,?)",
        (MS, PROJ, NOW, NOW),
    )
    conn.commit()
    conn.close()
    return home, db, target_repo


def _add_wo(db: Path, wo_id: str, description: str = "") -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO business_work_orders (work_order_id,project_id,milestone_id,title,description,status,work_order_type,created_at,updated_at)"
        " VALUES (?,?,?,?,?,'in_progress','infrastructure',?,?)",
        (wo_id, PROJ, MS, f"WO {wo_id[:8]}", description, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_tasks (task_id,work_order_id,project_id,title,description,status,created_at,updated_at)"
        " VALUES (?,?,?,'do it','','complete',?,?)",
        (f"t-{wo_id[:8]}", wo_id, PROJ, NOW, NOW),
    )
    conn.commit()
    conn.close()


def _verify(env, wo_id: str):
    home, _db, _repo = env
    return verify_work_order(work_order_id=wo_id, source_root=REPO, dream_studio_home=home)


# ── A: commit search runs in the WO's target repo ────────────────────────────


def test_commit_search_uses_target_repo_not_ds_source_root(env, monkeypatch):
    home, db, target_repo = env
    _add_wo(db, "wo-a-0001")
    calls: list[str] = []

    def fake_collect(root, wo_id, title=None):
        calls.append(str(root))
        return "commit-evidence-diff"

    monkeypatch.setattr(verify_git, "_collect_git_commits", fake_collect)
    monkeypatch.setattr(verify_graders, "_run_graders_parallel", lambda prompts: PASS_GRADERS)

    _verify(env, "wo-a-0001")
    assert calls, "commit search was not invoked"
    assert calls[0] == str(target_repo), f"searched {calls[0]}, expected target repo {target_repo}"


# ── B: gap WO certifies from the originating (parent) WO id ───────────────────


def test_gap_wo_falls_back_to_originating_id(env, monkeypatch):
    home, db, _repo = env
    parent = "parent-wo-1234"
    _add_wo(db, "wo-b-0001", description="Remediation. [gap-key: parent-wo-1234::coverage]")
    searched: list[str] = []

    def fake_collect(root, wo_id, title=None):
        searched.append(wo_id)
        return "parent-diff" if wo_id == parent else None  # own id finds nothing

    monkeypatch.setattr(verify_git, "_collect_git_commits", fake_collect)
    monkeypatch.setattr(verify_graders, "_run_graders_parallel", lambda prompts: PASS_GRADERS)

    _verify(env, "wo-b-0001")
    assert "wo-b-0001" in searched  # tried its own id first
    assert parent in searched, "did not fall back to the originating WO id"


# ── C: a gap WO does not recursively spawn further gap WOs ────────────────────


def test_non_gap_wo_spawns_but_gap_wo_does_not(env, monkeypatch):
    home, db, _repo = env
    _add_wo(db, "wo-c-plain")
    _add_wo(db, "wo-c-gap", description="Remediation. [gap-key: some-parent-99::missing-impl]")

    monkeypatch.setattr(verify_git, "_collect_git_commits", lambda root, wo_id, title=None: "diff")
    monkeypatch.setattr(verify_graders, "_run_graders_parallel", lambda prompts: GAP_GRADERS)

    plain = _verify(env, "wo-c-plain")
    gapwo = _verify(env, "wo-c-gap")

    assert plain["spawned_work_orders"], "a normal WO with gaps should spawn a remediation WO"
    assert (
        gapwo["spawned_work_orders"] == []
    ), "a gap-spawned WO must NOT recursively spawn (cascade)"


# ── ii: operator-attested close ──────────────────────────────────────────────


def test_operator_attestation_certifies_and_satisfies_gate(env):
    home, db, _repo = env
    _add_wo(db, "wo-ii-0001")

    result = attest_work_order(
        work_order_id="wo-ii-0001",
        reason="built + live-verified under M1-5; committed there",
        source_root=REPO,
        dream_studio_home=home,
    )
    assert result["ok"] is True
    assert result["certification_basis"] == "operator_attested"

    verdict = json.loads(get_wo_artifact("wo-ii-0001", "review_verdict", db_path=db))
    assert verdict["passed"] is True
    assert verdict["certification_basis"] == "operator_attested"
    assert "M1-5" in verdict["attestation"]

    # The independent_review close gate accepts the attested verdict.
    conn = sqlite3.connect(str(db))
    try:
        passed, reason = run_gate_check(
            "independent_review",
            planning_root=home / ".planning",
            work_order_id="wo-ii-0001",
            project_id=PROJ,
            conn=conn,
            db_path=db,
        )
    finally:
        conn.close()
    assert passed is True, reason


def test_attestation_requires_a_reason(env):
    home, db, _repo = env
    _add_wo(db, "wo-ii-0002")
    result = attest_work_order(
        work_order_id="wo-ii-0002", reason="   ", source_root=REPO, dream_studio_home=home
    )
    assert result["ok"] is False
