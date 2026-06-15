"""Tests for the executable acceptance-criteria runner (T1 — WO-AC-EXECUTABLE).

Covers: SQL-CHECK, TEST-CHECK, API-CHECK — passing and failing cases,
plus the fail-closed behaviour for unknown *-CHECK tokens.

AC: tests/unit/test_ac_runner.py::test_sql_test_and_api_checks_all_execute_and_fail_closed
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
# Trivial test fixture used for TEST-CHECK — always passes, no recursion risk.
_TRIVIAL_PASS_NODE = "tests/fixtures/trivial_pass_test.py::test_trivial_always_passes"
# A non-existent node that will make pytest exit non-zero.
_TRIVIAL_FAIL_NODE = "tests/fixtures/trivial_pass_test.py::test_does_not_exist"

NOW = "2026-01-01T00:00:00.000000Z"


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    # Seed one project row so SQL-CHECK pass queries work.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        ("ac-runner-test-project", "ACRunnerTest", "", "active", NOW, NOW),
    )
    conn.commit()
    conn.close()
    return db_path


def test_sql_test_and_api_checks_all_execute_and_fail_closed(tmp_path: Path) -> None:
    """All three check kinds execute; passing + failing case for each; unknown token fails closed."""
    from core.work_orders.verify import run_executable_checks

    db_path = _make_db(tmp_path)

    tasks = [
        # ── SQL-CHECK passing ──
        {
            "title": "sql-pass",
            "description": "",
            "acceptance_criteria": (
                "SQL-CHECK: SELECT COUNT(*) FROM business_projects"
                " WHERE project_id='ac-runner-test-project'"
            ),
        },
        # ── SQL-CHECK failing (count = 0) ──
        {
            "title": "sql-fail",
            "description": "",
            "acceptance_criteria": (
                "SQL-CHECK: SELECT COUNT(*) FROM business_projects"
                " WHERE project_id='does-not-exist-xyz'"
            ),
        },
        # ── TEST-CHECK passing ──
        {
            "title": "test-pass",
            "description": "",
            "acceptance_criteria": f"TEST-CHECK: {_TRIVIAL_PASS_NODE}",
        },
        # ── TEST-CHECK failing (node doesn't exist → pytest exits non-zero) ──
        {
            "title": "test-fail",
            "description": "",
            "acceptance_criteria": f"TEST-CHECK: {_TRIVIAL_FAIL_NODE}",
        },
        # ── API-CHECK passing ──
        {
            "title": "api-pass",
            "description": "",
            "acceptance_criteria": "API-CHECK: GET /api/health",
        },
        # ── API-CHECK failing (path returns 404 or doesn't exist) ──
        {
            "title": "api-fail",
            "description": "",
            "acceptance_criteria": "API-CHECK: GET /api/nonexistent_endpoint_xyz_12345",
        },
        # ── Unknown *-CHECK token — must fail closed ──
        {
            "title": "unknown-check",
            "description": "",
            "acceptance_criteria": "UNKNOWN-CHECK: something random",
        },
        # ── Free text line (no *-CHECK prefix) — must be ignored ──
        {
            "title": "free-text",
            "description": "",
            "acceptance_criteria": "This is just a description with no check prefix.",
        },
    ]

    results = run_executable_checks(tasks, db_path, source_root=REPO_ROOT)

    # SQL-CHECK pass
    assert "sql-pass" in results
    sql_pass_checks = results["sql-pass"]
    assert len(sql_pass_checks) == 1
    assert sql_pass_checks[0]["kind"] == "SQL-CHECK"
    assert (
        sql_pass_checks[0]["passed"] is True
    ), f"Expected SQL-CHECK pass; got {sql_pass_checks[0]}"

    # SQL-CHECK fail
    assert "sql-fail" in results
    sql_fail_checks = results["sql-fail"]
    assert len(sql_fail_checks) == 1
    assert sql_fail_checks[0]["kind"] == "SQL-CHECK"
    assert sql_fail_checks[0]["passed"] is False

    # TEST-CHECK pass
    assert "test-pass" in results
    test_pass_checks = results["test-pass"]
    assert len(test_pass_checks) == 1
    assert test_pass_checks[0]["kind"] == "TEST-CHECK"
    assert (
        test_pass_checks[0]["passed"] is True
    ), f"TEST-CHECK pass node should pass; got {test_pass_checks[0]}"

    # TEST-CHECK fail
    assert "test-fail" in results
    test_fail_checks = results["test-fail"]
    assert len(test_fail_checks) == 1
    assert test_fail_checks[0]["kind"] == "TEST-CHECK"
    assert (
        test_fail_checks[0]["passed"] is False
    ), f"TEST-CHECK non-existent node should fail; got {test_fail_checks[0]}"

    # API-CHECK pass
    assert "api-pass" in results
    api_pass_checks = results["api-pass"]
    assert len(api_pass_checks) == 1
    assert api_pass_checks[0]["kind"] == "API-CHECK"
    assert (
        api_pass_checks[0]["passed"] is True
    ), f"API-CHECK GET /api/health should pass; got {api_pass_checks[0]}"

    # API-CHECK fail (non-existent endpoint → 404 or import error)
    assert "api-fail" in results
    api_fail_checks = results["api-fail"]
    assert len(api_fail_checks) == 1
    assert api_fail_checks[0]["kind"] == "API-CHECK"
    assert (
        api_fail_checks[0]["passed"] is False
    ), f"API-CHECK non-existent path should fail; got {api_fail_checks[0]}"

    # Unknown *-CHECK token — fail closed
    assert "unknown-check" in results
    unknown_checks = results["unknown-check"]
    assert len(unknown_checks) == 1
    assert unknown_checks[0]["kind"] == "UNKNOWN-CHECK"
    assert (
        unknown_checks[0]["passed"] is False
    ), f"Unknown CHECK token must fail closed; got {unknown_checks[0]}"
    assert unknown_checks[0]["error"] is not None

    # Free-text line — not collected (no entry produced)
    assert "free-text" not in results, "Free-text lines without a *-CHECK prefix must be ignored"
