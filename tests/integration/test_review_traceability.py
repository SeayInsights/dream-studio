"""Integration tests for WO-REVIEW-TRACEABILITY: reliable independent-review grader.

Tests:
  T1 — test_grader_grades_wo_from_db_identity
  T2 — test_grader_finds_squash_merged_commits
  T3 — test_unreviewable_blocks_close
  T4 — test_recent_squash_merges_are_reviewable
  T5 — test_end_to_end
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-01-01T00:00:00.000000Z"


# ---------------------------------------------------------------------------
# DB / fixture helpers (mirrors test_wo_verify.py and test_close_ac_gate.py)
# ---------------------------------------------------------------------------


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


def _seed(
    db_path: Path,
    *,
    project_id: str,
    milestone_id: str,
    work_order_id: str,
    wo_type: str = "cleanup",
    title: str = "Test WO",
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "Test", "", "active", NOW, NOW),
    )
    conn.execute(
        "INSERT OR IGNORE INTO business_milestones"
        " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (milestone_id, project_id, "M1", "active", 1, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, description,"
        "  work_order_type, status, sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,'in_progress',1,?,?,?)",
        (work_order_id, project_id, milestone_id, title, "desc", wo_type, NOW, NOW, NOW),
    )
    conn.commit()
    conn.close()


def _add_task(
    db_path: Path,
    *,
    work_order_id: str,
    project_id: str,
    title: str,
    desc: str,
    acceptance_criteria: str = "",
) -> str:
    task_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    has_ac = any(
        r[1] == "acceptance_criteria"
        for r in conn.execute("PRAGMA table_info(business_tasks)").fetchall()
    )
    if has_ac:
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description,"
            "  acceptance_criteria, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,'complete',?,?)",
            (task_id, work_order_id, project_id, title, desc, acceptance_criteria, NOW, NOW),
        )
    else:
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description,"
            "  status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,'complete',?,?)",
            (task_id, work_order_id, project_id, title, desc, NOW, NOW),
        )
    conn.commit()
    conn.close()
    return task_id


# ---------------------------------------------------------------------------
# T1 — Grader identity comes from the DB, not from commit/artifact parsing
# ---------------------------------------------------------------------------


def test_grader_grades_wo_from_db_identity(tmp_path: Path) -> None:
    """With NO matching commits, the grader still grades the WO loaded by id.

    AC: tests/integration/test_review_traceability.py::test_grader_grades_wo_from_db_identity

    verify_work_order(work_order_id=...) must:
    - Load WO title and tasks from the DB (not infer them from commits).
    - Return ok=True with the correct work_order_id in the result.
    - Not raise an error when no commits are found (returns unreviewable verdict).
    - The returned work_order_id must match the id passed in (not some other WO).
    """
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    _seed(
        db_path,
        project_id=project_id,
        milestone_id=milestone_id,
        work_order_id=work_order_id,
        title="WO-TRACEABILITY - grader identity test",
    )
    _add_task(
        db_path,
        work_order_id=work_order_id,
        project_id=project_id,
        title="T1",
        desc="implement feature",
    )

    planning_root = tmp_path / "planning"

    with _patch_db(db_path):
        # Patch _collect_git_commits to return None — no commits found.
        # This simulates a squash-merge whose subject drops the UUID.
        with patch(
            "core.work_orders.verify._collect_git_commits",
            return_value=None,
        ):
            # Disable DREAM_STUDIO_VERIFY_MOCK so the unreviewable path executes.
            env = {k: v for k, v in os.environ.items() if k != "DREAM_STUDIO_VERIFY_MOCK"}
            with patch.dict(os.environ, env, clear=True):
                from core.work_orders.verify import verify_work_order

                result = verify_work_order(
                    work_order_id=work_order_id,
                    source_root=REPO_ROOT,
                    dream_studio_home=tmp_path,
                    planning_root=planning_root,
                )

    # Must return ok=True (not raise / not return ok=False with an error about WO not found)
    assert result["ok"] is True, f"Expected ok=True; got: {result}"
    # Identity: returned work_order_id must match what we passed in
    assert (
        result["work_order_id"] == work_order_id
    ), f"Expected work_order_id={work_order_id!r}, got {result['work_order_id']!r}"
    # No commits found → verdict is unreviewable (NOT a graded pass, NOT an error)
    assert (
        result.get("unreviewable") is True
    ), f"Expected unreviewable=True when no commits found; got result={result}"
    # Must NOT claim passed=True (unreviewable is not a certified pass)
    assert (
        result.get("passed") is not True
    ), f"Unreviewable verdict must not set passed=True; got {result}"


# ---------------------------------------------------------------------------
# T2 — _collect_git_commits finds commits via Work-Order: trailer
# ---------------------------------------------------------------------------


def _make_temp_git_repo(tmp_path: Path) -> Path:
    """Create a throwaway git repo with a squash-style commit carrying a Work-Order: trailer."""
    repo = tmp_path / "fake-repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    return repo


def test_grader_finds_squash_merged_commits(tmp_path: Path) -> None:
    """_collect_git_commits finds commits whose BODY carries Work-Order: <uuid>.

    AC: tests/integration/test_review_traceability.py::test_grader_finds_squash_merged_commits

    Seed a temp git repo with a squash-style commit whose subject does NOT carry the
    WO UUID or short-id — only the commit body carries `Work-Order: <uuid>`. Assert
    that _collect_git_commits finds it.
    """
    repo = _make_temp_git_repo(tmp_path)
    work_order_id = str(uuid.uuid4())

    # Create a file and commit with a body-only Work-Order: trailer.
    (repo / "change.py").write_text("# squash-merged change\n", encoding="utf-8")
    subprocess.run(["git", "add", "change.py"], cwd=str(repo), check=True, capture_output=True)
    # Subject has NO UUID — just a conventional squash-merge subject.
    commit_msg = (
        "feat(widget): implement widget display (#42)\n"
        "\n"
        f"Work-Order: {work_order_id}\n"
        "Reviewed-by: CI\n"
    )
    subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    from core.work_orders.verify import _collect_git_commits

    result = _collect_git_commits(repo, work_order_id, title=None)

    assert result is not None, (
        f"_collect_git_commits returned None — failed to find commit with "
        f"Work-Order: {work_order_id} in body. "
        "Ensure _collect_git_commits searches commit bodies for the Work-Order: trailer."
    )
    assert (
        work_order_id in result or "change.py" in result
    ), f"Result does not reference the expected WO or file: {result[:500]}"


# ---------------------------------------------------------------------------
# T3 — Unreviewable + no passing AC blocks close
# ---------------------------------------------------------------------------


def test_unreviewable_blocks_close(tmp_path: Path) -> None:
    """A WO with an unreviewable grader verdict AND no passing executable AC cannot close.

    AC: tests/integration/test_review_traceability.py::test_unreviewable_blocks_close

    Specifically: unreviewable + no executable ACs → blocked (AC gate fires).
    The independent_review gate must NOT act as a certified pass for unreviewable verdicts.
    """
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    # 'infrastructure' type has post_build_gate = 'independent_review'
    _seed(
        db_path,
        project_id=project_id,
        milestone_id=milestone_id,
        work_order_id=work_order_id,
        wo_type="infrastructure",
    )
    # Task with NO executable checks — this causes the AC gate to fire.
    _add_task(
        db_path,
        work_order_id=work_order_id,
        project_id=project_id,
        title="T1",
        desc="implement feature",
        acceptance_criteria="All tests should pass.",  # no *-CHECK lines
    )

    planning_root = tmp_path / "planning"
    # Write an unreviewable verdict to disk (simulating inline verify having already run).
    wo_dir = planning_root / "work-orders" / work_order_id
    wo_dir.mkdir(parents=True)
    unreviewable_verdict: dict[str, Any] = {
        "work_order_id": work_order_id,
        "passed": False,
        "unreviewable": True,
        "unreviewable_reason": (
            "independent_review: unreviewable — no commit evidence found; "
            "review manually or ensure commits carry the WO id / Work-Order: trailer"
        ),
        "scores": {
            "completion_score": 0.0,
            "correctness_score": 0.0,
            "quality_score": 0.0,
            "composite_score": 0.0,
        },
        "completion": {},
        "correctness": {},
        "quality": {},
        "gaps": [],
        "spawned_work_orders": [],
    }
    (wo_dir / "review-verdict.json").write_text(json.dumps(unreviewable_verdict), encoding="utf-8")

    # Patch verify at its definition site; close.py does a deferred
    # `from core.work_orders.verify import verify_work_order as _verify_wo`
    # inside the function, so patching the source module is the right target.
    mock_verify_result: dict[str, Any] = {
        "ok": True,
        "work_order_id": work_order_id,
        "passed": False,
        "unreviewable": True,
        "summary": "independent review unreviewable: no commits found",
        "completion": {},
        "correctness": {},
        "quality": {},
        "migration": None,
        "scores": {
            "completion_score": 0.0,
            "correctness_score": 0.0,
            "quality_score": 0.0,
            "composite_score": 0.0,
        },
        "gaps": [],
        "spawned_work_orders": [],
        "verdict_path": str(wo_dir / "review-verdict.json"),
    }
    with _patch_db(db_path):
        with patch(
            "core.work_orders.verify.verify_work_order",
            return_value=mock_verify_result,
        ):
            # Remove the pre-existing verdict so auto-verify fires (verdict file absent).
            (wo_dir / "review-verdict.json").unlink()
            from core.work_orders.close import close_work_order

            result = close_work_order(
                work_order_id=work_order_id,
                source_root=REPO_ROOT,
                dream_studio_home=tmp_path,
                planning_root=planning_root,
                force=False,
            )

    # Close must be blocked: unreviewable without passing AC
    assert (
        result["ok"] is False
    ), f"Expected close to be blocked (unreviewable + no passing AC); got ok=True: {result}"
    assert "failures" in result, f"Expected 'failures' key in result: {result}"

    # The block must come from the AC gate, not just the independent_review gate
    ac_failures = [f for f in result["failures"] if "executable_ac" in f]
    assert ac_failures, (
        f"Expected executable_ac gate failure (no executable checks); "
        f"failures={result['failures']}"
    )

    # Confirm with force=True it CAN close (bypass the AC gate)
    with _patch_db(db_path):
        # Re-create verdict file so auto-verify path is skipped (file present)
        (wo_dir / "review-verdict.json").write_text(
            json.dumps(unreviewable_verdict), encoding="utf-8"
        )
        from core.work_orders.close import close_work_order as _cwo

        result_forced = _cwo(
            work_order_id=work_order_id,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=True,
        )

    assert result_forced["ok"] is True, f"Expected force-close to succeed; got: {result_forced}"
    assert result_forced["forced"] is True


# ---------------------------------------------------------------------------
# T4 — Recently squash-merged WOs are reviewable via DB identity + evidence
# ---------------------------------------------------------------------------


def test_recent_squash_merges_are_reviewable(tmp_path: Path) -> None:
    """Confirm that recently squash-merged WOs can be graded via DB identity + evidence patterns.

    AC: tests/integration/test_review_traceability.py::test_recent_squash_merges_are_reviewable

    This test also serves as a grep-guard: no close path must treat "unreviewable" /
    "no commits found" as a certified completion (passed=True). We verify:
    1. A WO whose commits are found via Work-Order: trailer is graded (not unreviewable).
    2. An unreviewable verdict has passed=False (not True).
    3. The test_close_proceeds_on_unreviewable_grader in test_wo_verify.py still works
       because unreviewable + passing AC → closes. (Structural assertion via import.)
    """
    repo = _make_temp_git_repo(tmp_path)
    work_order_id = str(uuid.uuid4())

    # Commit with Work-Order: trailer — squash-merge style
    (repo / "feature.py").write_text("# feature impl\n", encoding="utf-8")
    subprocess.run(["git", "add", "feature.py"], cwd=str(repo), check=True, capture_output=True)
    commit_msg = "feat(api): wire up feature endpoint (#99)\n" "\n" f"Work-Order: {work_order_id}\n"
    subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    from core.work_orders.verify import _collect_git_commits

    # Evidence found via Work-Order: trailer
    diff = _collect_git_commits(repo, work_order_id, title="WO-TEST - squash merge test")
    assert (
        diff is not None
    ), "Squash-merged WO should be reviewable via Work-Order: trailer; got None"
    assert "feature.py" in diff, f"Expected diff to contain 'feature.py'; got: {diff[:500]}"

    # Grep-guard: unreviewable must set passed=False, never True
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    wo2_id = str(uuid.uuid4())
    _seed(
        db_path,
        project_id=project_id,
        milestone_id=milestone_id,
        work_order_id=wo2_id,
    )
    _add_task(
        db_path,
        work_order_id=wo2_id,
        project_id=project_id,
        title="T1",
        desc="do something",
    )

    planning_root = tmp_path / "planning2"

    with _patch_db(db_path):
        with patch(
            "core.work_orders.verify._collect_git_commits",
            return_value=None,
        ):
            env = {k: v for k, v in os.environ.items() if k != "DREAM_STUDIO_VERIFY_MOCK"}
            with patch.dict(os.environ, env, clear=True):
                from core.work_orders.verify import verify_work_order

                result = verify_work_order(
                    work_order_id=wo2_id,
                    source_root=REPO_ROOT,
                    dream_studio_home=tmp_path,
                    planning_root=planning_root,
                )

    # Grep-guard: unreviewable must NOT be passed=True
    assert (
        result.get("passed") is not True
    ), f"GREP-GUARD VIOLATION: unreviewable verdict set passed=True; result={result}"
    assert (
        result.get("unreviewable") is True
    ), f"Expected unreviewable=True when no commits found; result={result}"

    # Structural assertion: the bypass path in close.py exists (import check)
    # This confirms unreviewable + passing AC still closes (not hard-blocked).
    from core.work_orders import close as _close_module

    close_src = Path(_close_module.__file__).read_text(encoding="utf-8")
    assert "_is_unreviewable" in close_src, (
        "close.py must contain the _is_unreviewable bypass variable "
        "(unreviewable + passing AC → closes)"
    )
    assert (
        "not ac_failures" in close_src
    ), "close.py must gate the unreviewable bypass on ac_failures being empty"


# ---------------------------------------------------------------------------
# T5 — End-to-end: squash-style WO with Work-Order: trailer closes correctly
# ---------------------------------------------------------------------------


def test_end_to_end(tmp_path: Path) -> None:
    """Full close path for a WO whose evidence is only reachable via Work-Order: trailer.

    AC: tests/integration/test_review_traceability.py::test_end_to_end

    Scenario:
    - Seed a WO of type 'infrastructure' (has post_build_gate = 'independent_review').
    - Add a task with a passing SQL-CHECK (satisfies AC gate).
    - Mock verify to return an unreviewable verdict (squash commit found but grader empty).
    - Assert close proceeds without force (unreviewable + passing AC → closes).
    - Assert verify_warning is set in result.
    """
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    _seed(
        db_path,
        project_id=project_id,
        milestone_id=milestone_id,
        work_order_id=work_order_id,
        wo_type="infrastructure",
        title="WO-E2E - squash merged feature",
    )
    # Task with a passing SQL-CHECK — satisfies the always-on AC gate.
    _add_task(
        db_path,
        work_order_id=work_order_id,
        project_id=project_id,
        title="T1 - implement feature",
        desc="implement the feature",
        acceptance_criteria=(
            f"SQL-CHECK: SELECT 1 WHERE EXISTS"
            f" (SELECT 1 FROM business_projects WHERE project_id='{project_id}')"
        ),
    )

    planning_root = tmp_path / "planning"

    # The mock verify result: unreviewable (grader returned no summary after retry),
    # but the WO is identified by its DB id (work_order_id matches what we passed).
    mock_verify_result: dict[str, Any] = {
        "ok": True,
        "work_order_id": work_order_id,
        "passed": False,
        "unreviewable": True,
        "unreviewable_graders": ["completion", "correctness", "quality"],
        "summary": (
            "independent review unreviewable: grader(s) [completion, correctness, quality] "
            "returned empty output. Work is NOT certified — review manually."
        ),
        "completion": {},
        "correctness": {},
        "quality": {},
        "migration": None,
        "scores": {
            "completion_score": 0.0,
            "correctness_score": 0.0,
            "quality_score": 0.0,
            "composite_score": 0.0,
        },
        "auto_continue_warning": (
            "independent review unreviewable: grader(s) [completion, correctness, quality] "
            "returned empty output. Work is NOT certified — review manually."
        ),
        "gaps": [],
        "spawned_work_orders": [],
        "verdict_path": str(planning_root / "work-orders" / work_order_id / "review-verdict.json"),
    }

    with _patch_db(db_path):
        # Patch verify at its definition site; close.py does a deferred
        # `from core.work_orders.verify import verify_work_order as _verify_wo`
        # inside the function, so patching the source module is the right target.
        with patch(
            "core.work_orders.verify.verify_work_order",
            return_value=mock_verify_result,
        ):
            from core.work_orders.close import close_work_order

            result = close_work_order(
                work_order_id=work_order_id,
                source_root=REPO_ROOT,
                dream_studio_home=tmp_path,
                planning_root=planning_root,
                force=False,
            )

    # Unreviewable + passing AC (SQL-CHECK passes) → close proceeds without force
    assert (
        result["ok"] is True
    ), f"Expected ok=True (unreviewable + passing AC should close); got: {result}"
    assert result.get("forced") is False, f"Should not require force=True; got: {result}"
    assert result["status"] == "closed", f"Expected status=closed; got: {result}"

    # verify_warning must be set to surface the unreviewable advisory to the operator
    assert (
        "verify_warning" in result
    ), f"Expected verify_warning to be set for unreviewable verdict; got keys={list(result)}"
    assert result["verify_warning"], "verify_warning should be a non-empty string"

    # Confirm WO is now closed in DB
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT status FROM business_work_orders WHERE work_order_id = ?",
        (work_order_id,),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "closed", f"Expected WO status=closed in DB; got {row[0]}"
