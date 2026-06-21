"""Tests for WO-REVIEW-GATE: ds work-order verify and independent_review close gate."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-01-01T00:00:00.000000Z"


# ---------------------------------------------------------------------------
# Helpers
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
        (work_order_id, project_id, milestone_id, "Test WO", "desc", wo_type, NOW, NOW, NOW),
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
    if has_ac and acceptance_criteria:
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
# verify_work_order: no commits found → passed=False (mock gap insertion)
# ---------------------------------------------------------------------------


def test_verify_no_commits_mock_gap(tmp_path: pytest.TempPathFactory) -> None:
    """With DREAM_STUDIO_VERIFY_MOCK=1, mock passes. No gaps, no WOs created."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    _add_task(db_path, work_order_id=work_order_id, project_id=project_id, title="T1", desc="do it")

    planning_root = tmp_path / "planning"
    with _patch_db(db_path):
        with patch.dict(os.environ, {"DREAM_STUDIO_VERIFY_MOCK": "1"}):
            from core.work_orders.verify import verify_work_order

            result = verify_work_order(
                work_order_id=work_order_id,
                source_root=REPO_ROOT,
                dream_studio_home=tmp_path,
                planning_root=planning_root,
            )

    assert result["ok"] is True
    assert result["passed"] is True
    assert result["spawned_work_orders"] == []
    # verdict file must be written
    verdict_path = planning_root / "work-orders" / work_order_id / "review-verdict.json"
    assert verdict_path.is_file()
    data = json.loads(verdict_path.read_text())
    assert data["passed"] is True


# ---------------------------------------------------------------------------
# verify_work_order: mock fixture with gaps → gap WOs created in SQLite
# ---------------------------------------------------------------------------


def test_verify_gap_creates_work_orders(tmp_path: pytest.TempPathFactory) -> None:
    """When parallel graders return a completion result with gaps[], verify inserts
    new WOs under the same milestone."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    _add_task(db_path, work_order_id=work_order_id, project_id=project_id, title="T1", desc="do it")

    grader_results = {
        "completion": {
            "passed": False,
            "completion_score": 0.0,
            "tasks_verified": [
                {"task_title": "T1", "evidence": "not found in diff", "verdict": "missing"}
            ],
            "summary": "Task T1 was not addressed.",
            "gaps": [
                {
                    "title": "Fix missing T1 implementation",
                    "description": "T1 was not done",
                    "work_order_type": "cleanup",
                    "tasks": [
                        {"title": "Implement T1", "description": "Add the missing code"},
                    ],
                }
            ],
        },
        "correctness": {
            "correctness_passed": True,
            "correctness_score": 1.0,
            "violations": [],
            "coverage_gaps": [],
            "migration_gaps": [],
        },
        "quality": {
            "quality_passed": True,
            "quality_score": 1.0,
            "issues": [],
        },
    }

    planning_root = tmp_path / "planning"
    with _patch_db(db_path):
        with patch("core.work_orders.verify._run_graders_parallel", return_value=grader_results):
            with patch(
                "core.work_orders.verify._collect_git_commits",
                return_value="diff --git a/fake.py b/fake.py\n+# change",
            ):
                from core.work_orders.verify import verify_work_order

                result = verify_work_order(
                    work_order_id=work_order_id,
                    source_root=REPO_ROOT,
                    dream_studio_home=tmp_path,
                    planning_root=planning_root,
                )

    assert result["ok"] is True
    assert result["passed"] is False
    assert len(result["spawned_work_orders"]) == 1
    spawned_id = result["spawned_work_orders"][0]["work_order_id"]

    # Verify the gap WO and its task are in the DB under the same milestone.
    conn = sqlite3.connect(str(db_path))
    wo_row = conn.execute(
        "SELECT milestone_id, work_order_type FROM business_work_orders WHERE work_order_id = ?",
        (spawned_id,),
    ).fetchone()
    assert wo_row is not None
    assert wo_row[0] == milestone_id
    assert wo_row[1] == "cleanup"

    task_row = conn.execute(
        "SELECT title FROM business_tasks WHERE work_order_id = ?",
        (spawned_id,),
    ).fetchone()
    assert task_row is not None
    assert task_row[0] == "Implement T1"
    conn.close()


# ---------------------------------------------------------------------------
# independent_review close gate: missing verdict → blocked
# ---------------------------------------------------------------------------


def test_close_gate_missing_verdict_blocks(tmp_path: pytest.TempPathFactory) -> None:
    """close gate 'independent_review' blocks when review-verdict.json is absent."""
    from core.work_orders.close import run_gate_check

    conn = MagicMock()
    planning_root = tmp_path / "planning"
    work_order_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())

    passed, reason = run_gate_check(
        "independent_review",
        planning_root=planning_root,
        work_order_id=work_order_id,
        project_id=project_id,
        conn=conn,
    )
    assert passed is False
    assert "review-verdict.json not found" in reason
    assert "work-order verify" in reason


# ---------------------------------------------------------------------------
# independent_review close gate: passed=false verdict → blocked with summary
# ---------------------------------------------------------------------------


def test_close_gate_failed_verdict_blocks(tmp_path: pytest.TempPathFactory) -> None:
    """close gate 'independent_review' blocks when verdict has passed=false."""
    from core.work_orders.close import run_gate_check

    conn = MagicMock()
    work_order_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    planning_root = tmp_path / "planning"
    wo_dir = planning_root / "work-orders" / work_order_id
    wo_dir.mkdir(parents=True)
    spawned_id = str(uuid.uuid4())
    (wo_dir / "review-verdict.json").write_text(
        json.dumps(
            {
                "passed": False,
                "summary": "Task T1 was missing.",
                "spawned_work_orders": [
                    {"work_order_id": spawned_id, "title": "Fix T1", "type": "cleanup"}
                ],
            }
        ),
        encoding="utf-8",
    )

    passed, reason = run_gate_check(
        "independent_review",
        planning_root=planning_root,
        work_order_id=work_order_id,
        project_id=project_id,
        conn=conn,
    )
    assert passed is False
    assert "review failed" in reason
    assert spawned_id in reason


# ---------------------------------------------------------------------------
# independent_review close gate: passed=true → allowed
# ---------------------------------------------------------------------------


def test_close_gate_passed_verdict_allows(tmp_path: pytest.TempPathFactory) -> None:
    """close gate 'independent_review' passes when verdict has passed=true."""
    from core.work_orders.close import run_gate_check

    conn = MagicMock()
    work_order_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    planning_root = tmp_path / "planning"
    wo_dir = planning_root / "work-orders" / work_order_id
    wo_dir.mkdir(parents=True)
    (wo_dir / "review-verdict.json").write_text(
        json.dumps(
            {
                "passed": True,
                "summary": "All tasks addressed.",
                "spawned_work_orders": [],
            }
        ),
        encoding="utf-8",
    )

    passed, reason = run_gate_check(
        "independent_review",
        planning_root=planning_root,
        work_order_id=work_order_id,
        project_id=project_id,
        conn=conn,
    )
    assert passed is True
    assert reason == ""


# ---------------------------------------------------------------------------
# ds project state shows spawned gap WOs
# ---------------------------------------------------------------------------


def test_spawned_gap_wos_visible_in_project(tmp_path: pytest.TempPathFactory) -> None:
    """Gap WOs inserted by verify show up in business_work_orders for the project."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())
    _seed(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)
    _add_task(db_path, work_order_id=work_order_id, project_id=project_id, title="T1", desc="do it")

    grader_results = {
        "completion": {
            "passed": False,
            "completion_score": 0.0,
            "tasks_verified": [],
            "summary": "Gap found.",
            "gaps": [
                {
                    "title": "Gap WO Alpha",
                    "description": "needs fixing",
                    "work_order_type": "infrastructure",
                    "tasks": [{"title": "Fix alpha", "description": "do the fix"}],
                }
            ],
        },
        "correctness": {
            "correctness_passed": True,
            "correctness_score": 1.0,
            "violations": [],
            "coverage_gaps": [],
            "migration_gaps": [],
        },
        "quality": {
            "quality_passed": True,
            "quality_score": 1.0,
            "issues": [],
        },
    }

    planning_root = tmp_path / "planning"
    with _patch_db(db_path):
        with patch("core.work_orders.verify._run_graders_parallel", return_value=grader_results):
            with patch(
                "core.work_orders.verify._collect_git_commits",
                return_value="diff --git a/fake.py b/fake.py\n+# change",
            ):
                from core.work_orders.verify import verify_work_order

                result = verify_work_order(
                    work_order_id=work_order_id,
                    source_root=REPO_ROOT,
                    dream_studio_home=tmp_path,
                    planning_root=planning_root,
                )

    assert result["spawned_work_orders"][0]["work_order_id"]
    conn = sqlite3.connect(str(db_path))
    count = conn.execute(
        "SELECT COUNT(*) FROM business_work_orders WHERE project_id = ?",
        (project_id,),
    ).fetchone()[0]
    assert count == 2  # original + gap

    titles = conn.execute(
        "SELECT title FROM business_work_orders WHERE project_id = ? ORDER BY sequence_order",
        (project_id,),
    ).fetchall()
    assert any("Gap WO Alpha" in r[0] for r in titles)
    conn.close()


# ---------------------------------------------------------------------------
# _COMPLETION_PROMPT_TEMPLATE: work_order_type field and behavioral AC block
# Acceptance: template structure contracts proven; work_order_type appears in
# formatted output; behavioral AC check triggers and suppression conditions
# are both stated in the template.
# ---------------------------------------------------------------------------


def test_completion_prompt_template_contains_work_order_type_placeholder() -> None:
    """{work_order_type} placeholder is present in _COMPLETION_PROMPT_TEMPLATE."""
    from core.work_orders.verify import _COMPLETION_PROMPT_TEMPLATE

    assert "{work_order_type}" in _COMPLETION_PROMPT_TEMPLATE


def test_completion_prompt_template_work_order_type_interpolates() -> None:
    """Formatting the template with a known type produces a string containing that type."""
    from core.work_orders.verify import _COMPLETION_PROMPT_TEMPLATE

    rendered = _COMPLETION_PROMPT_TEMPLATE.format(
        title="Test WO",
        work_order_id="test-id",
        work_order_type="infrastructure",
        task_list="- T1",
        git_diff="diff",
    )
    assert "infrastructure" in rendered


def test_completion_prompt_template_behavioral_ac_check_mentions_triggering_types() -> None:
    """Template's behavioral AC block names 'feature' and 'infrastructure' as trigger types."""
    from core.work_orders.verify import _COMPLETION_PROMPT_TEMPLATE

    assert "feature" in _COMPLETION_PROMPT_TEMPLATE
    assert "infrastructure" in _COMPLETION_PROMPT_TEMPLATE


def test_completion_prompt_template_behavioral_ac_check_not_emit_conditions() -> None:
    """Template documents that the AC gap must NOT be emitted when AC is already present."""
    from core.work_orders.verify import _COMPLETION_PROMPT_TEMPLATE

    assert "Do NOT emit" in _COMPLETION_PROMPT_TEMPLATE
    assert "already present" in _COMPLETION_PROMPT_TEMPLATE


# ---------------------------------------------------------------------------
# WO-REVIEW-TRACEABILITY T4: unreviewable grader is NOT a certified pass.
#   - unreviewable + passing executable AC  → close PROCEEDS (AC gate compensates)
#   - unreviewable + failing/absent AC      → close BLOCKED  (the #358 false-done guard)
# ---------------------------------------------------------------------------


def test_unreviewable_with_passing_ac_proceeds(tmp_path: pytest.TempPathFactory) -> None:
    """Unreviewable grader + passing executable AC → close PROCEEDS (AC gate compensates).

    WO-REVIEW-TRACEABILITY T4: an unreviewable independent_review verdict is NOT a
    certified pass (close.py returns it as a gate failure). Close proceeds here ONLY
    because the always-on executable-AC gate passes — the unreviewable gate failure is
    bypassed when, and only when, every executable check passes. The dangerous
    pre-WO-REVIEW-TRACEABILITY behavior (unreviewable ALONE → proceed) is asserted
    against by test_unreviewable_without_ac_blocks_close below and by
    tests/integration/test_review_traceability.py::test_unreviewable_blocks_close.
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
    # Add a passing SQL-CHECK so the always-on AC gate passes.
    # The project row is already inserted by _seed() above.
    _add_task(
        db_path,
        work_order_id=work_order_id,
        project_id=project_id,
        title="T1",
        desc="do it",
        acceptance_criteria=(
            f"SQL-CHECK: SELECT COUNT(*) FROM business_projects WHERE project_id='{project_id}'"
        ),
    )

    planning_root = tmp_path / "planning"
    mock_no_summary = {"unreviewable": True, "reason": "grader_no_summary"}

    with (
        _patch_db(db_path),
        patch(
            "core.work_orders.verify._collect_grader",
            return_value=mock_no_summary,
        ),
        patch(
            "core.work_orders.verify._spawn_grader",
            return_value=MagicMock(),
        ),
        patch(
            "core.work_orders.verify._collect_git_commits",
            return_value="diff --git a/fake.py b/fake.py\n+# change",
        ),
    ):
        from core.work_orders.close import close_work_order

        result = close_work_order(
            work_order_id=work_order_id,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
        )

    assert result["ok"] is True, f"Expected ok=True, got: {result}"
    assert result.get("forced") is False
    assert "verify_warning" in result

    # Verdict file must record unreviewable_graders
    verdict_path = planning_root / "work-orders" / work_order_id / "review-verdict.json"
    assert verdict_path.is_file()
    data = json.loads(verdict_path.read_text())
    assert data["unreviewable"] is True
    assert "unreviewable_graders" in data
    assert len(data["unreviewable_graders"]) > 0


def test_unreviewable_without_ac_blocks_close(tmp_path: pytest.TempPathFactory) -> None:
    """Unreviewable grader + failing executable AC → close is BLOCKED.

    The inverse of test_unreviewable_with_passing_ac_proceeds and the unit-level guard
    against the #358 false-done hole: an unreviewable independent_review verdict must
    never act as a certified pass. With no PASSING executable check to compensate,
    close_work_order must return ok=False without force=True — the AC gate is the
    authoritative blocker.
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
    # A FAILING SQL-CHECK: this project_id does not exist, so COUNT = 0 → falsy →
    # the always-on AC gate fails. There is no passing check to compensate.
    _add_task(
        db_path,
        work_order_id=work_order_id,
        project_id=project_id,
        title="T1",
        desc="do it",
        acceptance_criteria=(
            "SQL-CHECK: SELECT COUNT(*) FROM business_projects"
            " WHERE project_id='does-not-exist-00000000'"
        ),
    )

    planning_root = tmp_path / "planning"
    mock_no_summary = {"unreviewable": True, "reason": "grader_no_summary"}

    with (
        _patch_db(db_path),
        patch(
            "core.work_orders.verify._collect_grader",
            return_value=mock_no_summary,
        ),
        patch(
            "core.work_orders.verify._spawn_grader",
            return_value=MagicMock(),
        ),
        patch(
            "core.work_orders.verify._collect_git_commits",
            return_value="diff --git a/fake.py b/fake.py\n+# change",
        ),
    ):
        from core.work_orders.close import close_work_order

        result = close_work_order(
            work_order_id=work_order_id,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
        )

    assert (
        result["ok"] is False
    ), f"Expected close BLOCKED (unreviewable + failing AC); got ok=True: {result}"
    # The AC gate must be the blocker — unreviewable alone must not pass the close.
    assert any(
        "executable_ac" in f for f in result.get("failures", [])
    ), f"Expected an executable_ac failure in the block reasons; got: {result.get('failures')}"


# ---------------------------------------------------------------------------
# _run_sql_checks: pass path
# ---------------------------------------------------------------------------


def test_sql_check_pass(tmp_path: pytest.TempPathFactory) -> None:
    """SQL-CHECK query returning a non-zero count gives passed=True."""
    db_path = _make_db(tmp_path)

    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        ("sql-check-test-id", "SQLCheck", "", "active", NOW, NOW),
    )
    conn.commit()
    conn.close()

    from core.work_orders.verify import _run_sql_checks

    tasks = [
        {
            "title": "T1",
            "description": "insert a row",
            "acceptance_criteria": (
                "SQL-CHECK: SELECT COUNT(*) FROM business_projects"
                " WHERE project_id='sql-check-test-id'"
            ),
        }
    ]
    results = _run_sql_checks(tasks, db_path)
    assert "T1" in results
    assert len(results["T1"]) == 1
    assert results["T1"][0]["passed"] is True
    assert results["T1"][0]["error"] is None


# ---------------------------------------------------------------------------
# _run_sql_checks: fail path
# ---------------------------------------------------------------------------


def test_sql_check_fail(tmp_path: pytest.TempPathFactory) -> None:
    """SQL-CHECK query returning zero gives passed=False."""
    db_path = _make_db(tmp_path)

    from core.work_orders.verify import _run_sql_checks

    tasks = [
        {
            "title": "T1",
            "description": "check absent row",
            "acceptance_criteria": (
                "SQL-CHECK: SELECT COUNT(*) FROM business_projects"
                " WHERE project_id='does-not-exist'"
            ),
        }
    ]
    results = _run_sql_checks(tasks, db_path)
    assert "T1" in results
    assert results["T1"][0]["passed"] is False
    assert results["T1"][0]["error"] is None
