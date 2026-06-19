"""Integration tests for the dashboard truth gate (WO-LIVE-DATA-GATE T2/T3/T4).

Tests
-----
test_live_invariants_fail_when_authority_wrong
    Invariant #1 (token_model_null_fraction) fires when all token rows have
    NULL model_id; a fresh empty DB vacuously passes.

test_gate_blocks_close_and_merge
    A data_pipeline-type WO (one of the _DASHBOARD_TRUTH_GATED_TYPES) cannot
    close when a seeded DB violates dashboard truth invariants.  A cleanup-type
    WO with the same violating DB is NOT blocked by this gate.

test_end_to_end
    Broad end-to-end: invariants run, empty DB passes, violating DB fails,
    ``ds doctor dashboard-truth`` exits non-zero on violation.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.gates.dashboard_truth import run_dashboard_truth

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-01-01T00:00:00.000000Z"


# ---------------------------------------------------------------------------
# Helpers (mirrors test_close_ac_gate.py conventions)
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


def _seed_wo(
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
    title: str = "Task",
    desc: str = "desc",
    acceptance_criteria: str = "SQL-CHECK: SELECT 1 WHERE 1=1",
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
            " VALUES (?,?,?,?,'complete',?,?)",
            (task_id, work_order_id, project_id, title, NOW, NOW),
        )
    conn.commit()
    conn.close()
    return task_id


def _seed_violating_tokens(db_path: Path) -> None:
    """Insert token_usage_records rows ALL with model_id=NULL → violates invariant #1."""
    conn = sqlite3.connect(str(db_path))
    for _ in range(3):
        conn.execute(
            "INSERT INTO token_usage_records"
            " (token_usage_id, model_id, input_tokens, output_tokens, created_at)"
            " VALUES (?, NULL, 100, 50, ?)",
            (str(uuid.uuid4()), NOW),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# test_live_invariants_fail_when_authority_wrong  (T2 test)
# ---------------------------------------------------------------------------


def test_live_invariants_fail_when_authority_wrong(tmp_path: Path) -> None:
    """Invariant #1 fires when all token rows have NULL model_id.
    A freshly bootstrapped empty DB vacuously passes all invariants.
    """
    # ── 1. Violating DB: all token rows have NULL model_id ─────────────────
    db_violating = _make_db(tmp_path / "violating")
    _seed_violating_tokens(db_violating)

    result_violating = run_dashboard_truth(db_violating)

    assert result_violating["ok"] is False, (
        "Expected run_dashboard_truth to fail on all-NULL model_id tokens; "
        f"got ok=True: {result_violating}"
    )
    failed_names = [r["name"] for r in result_violating["results"] if not r["passed"]]
    assert (
        "token_model_null_fraction" in failed_names
    ), f"Expected token_model_null_fraction to fail; failed={failed_names}"

    # ── 2. Fresh empty DB → all vacuous passes ─────────────────────────────
    db_empty = _make_db(tmp_path / "empty")
    result_empty = run_dashboard_truth(db_empty)

    assert result_empty["ok"] is True, (
        f"Expected freshly bootstrapped empty DB to pass all invariants; " f"got: {result_empty}"
    )
    for inv in result_empty["results"]:
        assert inv["passed"], f"Invariant {inv['name']!r} should vacuously pass on empty DB"


# ---------------------------------------------------------------------------
# test_gate_blocks_close_and_merge  (T3 test)
# ---------------------------------------------------------------------------


def test_gate_blocks_close_and_merge(tmp_path: Path) -> None:
    """A data_pipeline-type WO is blocked at close when dashboard truth fails.
    A cleanup-type WO with the same violating DB is NOT blocked by this gate.
    """
    from core.work_orders.close import close_work_order

    db_path = _make_db(tmp_path)
    _seed_violating_tokens(db_path)

    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    planning_root = tmp_path / "planning"

    # ── 1. data_pipeline WO (gated type) → must be blocked ─────────────────
    wo_id_gated = str(uuid.uuid4())
    _seed_wo(
        db_path,
        project_id=project_id,
        milestone_id=milestone_id,
        work_order_id=wo_id_gated,
        wo_type="data_pipeline",
    )
    _add_task(
        db_path,
        work_order_id=wo_id_gated,
        project_id=project_id,
        acceptance_criteria="SQL-CHECK: SELECT 1 WHERE 1=1",
    )

    with _patch_db(db_path):
        result_gated = close_work_order(
            work_order_id=wo_id_gated,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=False,
        )

    assert result_gated["ok"] is False, (
        f"Expected data_pipeline WO to be blocked by dashboard_truth gate; "
        f"got ok=True: {result_gated}"
    )
    assert "failures" in result_gated
    dt_failures = [f for f in result_gated["failures"] if "dashboard_truth" in f]
    assert (
        dt_failures
    ), f"Expected a dashboard_truth gate failure; failures={result_gated['failures']}"

    # ── 2. cleanup WO (non-gated type) with same violating DB → NOT blocked ─
    # Note: cleanup has post_build_gate=independent_review (from migration 114).
    # Use a type that has no type-specific gates to isolate the dashboard gate.
    # 'documentation' has no pre/post gates — perfect for isolation.
    wo_id_ungated = str(uuid.uuid4())
    _seed_wo(
        db_path,
        project_id=project_id,
        milestone_id=milestone_id,
        work_order_id=wo_id_ungated,
        wo_type="documentation",
    )
    _add_task(
        db_path,
        work_order_id=wo_id_ungated,
        project_id=project_id,
        acceptance_criteria="SQL-CHECK: SELECT 1 WHERE 1=1",
    )

    with _patch_db(db_path):
        result_ungated = close_work_order(
            work_order_id=wo_id_ungated,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=planning_root,
            force=False,
        )

    # The dashboard_truth gate must NOT appear in any failure for the ungated type.
    if not result_ungated["ok"]:
        dt_fail_ungated = [f for f in result_ungated.get("failures", []) if "dashboard_truth" in f]
        assert not dt_fail_ungated, (
            f"dashboard_truth gate must not fire for documentation WO type; "
            f"failures={result_ungated.get('failures', [])}"
        )


# ---------------------------------------------------------------------------
# test_end_to_end  (T4 broad test)
# ---------------------------------------------------------------------------


def test_end_to_end(tmp_path: Path) -> None:
    """Broad: invariants run, empty passes, violating fails, doctor exits nonzero.

    Also verifies the CLI entry point behaviour for the dashboard-truth mode
    by calling the module-level main() with a patched resolved DB path.
    """
    # ── 1. Empty DB → ok=True ──────────────────────────────────────────────
    db_empty = _make_db(tmp_path / "empty")
    result_empty = run_dashboard_truth(db_empty)
    assert result_empty["ok"] is True, f"Empty DB should pass; got {result_empty}"
    assert len(result_empty["results"]) == 5, "Should have exactly 5 invariant results"
    for inv in result_empty["results"]:
        assert inv["passed"], f"Invariant {inv['name']!r} should pass on empty DB"

    # ── 2. Violating DB → ok=False ─────────────────────────────────────────
    db_violating = _make_db(tmp_path / "violating")
    _seed_violating_tokens(db_violating)
    result_violating = run_dashboard_truth(db_violating)
    assert result_violating["ok"] is False, f"Violating DB should fail; got {result_violating}"
    failed = [r for r in result_violating["results"] if not r["passed"]]
    assert failed, "Expected at least one failing invariant on violating DB"

    # ── 3. CLI doctor dashboard-truth exit code via main() ─────────────────
    from interfaces.cli.ds import main as ds_main

    # Violating DB → exit code 1.
    with _patch_db(db_violating):
        exit_code_fail = ds_main(["doctor", "dashboard-truth"])
    assert exit_code_fail == 1, f"Expected exit code 1 on violating DB; got {exit_code_fail}"

    # Empty DB → exit code 0.
    with _patch_db(db_empty):
        exit_code_ok = ds_main(["doctor", "dashboard-truth"])
    assert exit_code_ok == 0, f"Expected exit code 0 on empty DB; got {exit_code_ok}"


def test_missing_authority_file_vacuously_passes(tmp_path: Path) -> None:
    """A nonexistent authority DB (fresh CI checkout — no ~/.dream-studio) must
    vacuously pass every invariant, NOT fail on 'unable to open database file'.

    Regression for PR #401: pr-smoke failed because CI has no live authority
    and the gate treated an unopenable DB as a hard failure.
    """
    missing = tmp_path / "nope" / "state" / "studio.db"
    assert not missing.exists()
    result = run_dashboard_truth(missing)
    assert result["ok"] is True, f"Missing DB must pass; got {result}"
    assert len(result["results"]) == 5
    for inv in result["results"]:
        assert inv["passed"], f"Invariant {inv['name']!r} must pass when DB is absent"
        assert inv["error"] is None

    # CLI entry point mirrors it: exit 0 when the resolved DB does not exist.
    from interfaces.cli.ds import main as ds_main

    with _patch_db(missing):
        exit_code = ds_main(["doctor", "dashboard-truth"])
    assert exit_code == 0, f"Expected exit 0 when authority absent; got {exit_code}"
