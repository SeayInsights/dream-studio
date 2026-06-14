"""Unit tests for WO-SYMPTOM-RESOLUTION: symptom capture registration paths.

Covers:
- create_work_order() accepts originating_symptom parameter
- set_originating_symptom() stores the symptom for defect-class work orders
- _check_originating_symptom() correctly identifies failing/passing SQL checks
"""

from __future__ import annotations

import inspect
import sqlite3
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

NOW = "2026-01-01T00:00:00.000000+00:00"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    from core.config.sqlite_bootstrap import bootstrap_database

    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


def _seed_wo(db_path: Path, *, project_id: str, milestone_id: str, work_order_id: str) -> None:
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
        " (work_order_id, project_id, milestone_id, title, work_order_type,"
        "  status, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,'cleanup','in_progress',?,?,?)",
        (work_order_id, project_id, milestone_id, "Defect WO", NOW, NOW, NOW),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# create_work_order signature check
# ---------------------------------------------------------------------------


def test_create_work_order_accepts_originating_symptom():
    """create_work_order() must accept originating_symptom as a keyword argument."""
    from core.work_orders.mutations import create_work_order

    sig = inspect.signature(create_work_order)
    assert (
        "originating_symptom" in sig.parameters
    ), "create_work_order() missing originating_symptom parameter — registration path incomplete"


# ---------------------------------------------------------------------------
# set_originating_symptom: defect WO requires symptom
# ---------------------------------------------------------------------------


def test_defect_wo_requires_symptom(tmp_path):
    """set_originating_symptom() stores the symptom for defect-class work orders."""
    from core.work_orders.mutations import set_originating_symptom

    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())

    _seed_wo(db_path, project_id=project_id, milestone_id=milestone_id, work_order_id=work_order_id)

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        result = set_originating_symptom(
            work_order_id=work_order_id,
            symptom="SQL-CHECK: SELECT 1",
            source_root=tmp_path,
        )

    assert result["ok"] is True, f"set_originating_symptom failed: {result}"

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT originating_symptom FROM business_work_orders WHERE work_order_id = ?",
        (work_order_id,),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "SQL-CHECK: SELECT 1", f"Expected symptom to be stored, got: {row[0]!r}"


def test_set_originating_symptom_returns_error_for_unknown_wo(tmp_path):
    """set_originating_symptom() returns ok=False for a non-existent work order."""
    from core.work_orders.mutations import set_originating_symptom

    db_path = _make_db(tmp_path)

    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        result = set_originating_symptom(
            work_order_id="no-such-wo",
            symptom="SQL-CHECK: SELECT 1",
            source_root=tmp_path,
        )

    assert result["ok"] is False
    assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# _check_originating_symptom unit
# ---------------------------------------------------------------------------


def test_check_originating_symptom_passes_on_truthy_result(tmp_path):
    """_check_originating_symptom returns None when the SQL returns a truthy value."""
    from core.work_orders.close import _check_originating_symptom

    db_path = _make_db(tmp_path)
    # SELECT 1 always returns 1 (truthy)
    assert _check_originating_symptom("SQL-CHECK: SELECT 1", db_path) is None


def test_check_originating_symptom_fails_on_zero(tmp_path):
    """_check_originating_symptom returns a reason string when SQL returns 0."""
    from core.work_orders.close import _check_originating_symptom

    db_path = _make_db(tmp_path)
    result = _check_originating_symptom(
        "SQL-CHECK: SELECT COUNT(*) FROM business_work_order_types WHERE 1=0",
        db_path,
    )
    assert result is not None
    assert "originating_symptom" in result


def test_check_originating_symptom_fails_on_sql_error(tmp_path):
    """_check_originating_symptom returns a reason string on SQL error."""
    from core.work_orders.close import _check_originating_symptom

    db_path = _make_db(tmp_path)
    result = _check_originating_symptom(
        "SQL-CHECK: SELECT COUNT(*) FROM nonexistent_table_999",
        db_path,
    )
    assert result is not None
    assert "originating_symptom" in result


def test_check_originating_symptom_ignores_non_sql_check_lines(tmp_path):
    """_check_originating_symptom ignores lines that don't start with SQL-CHECK:."""
    from core.work_orders.close import _check_originating_symptom

    db_path = _make_db(tmp_path)
    # Only has a comment line, no SQL-CHECK — should pass (no check = no block)
    assert _check_originating_symptom("# This WO fixes the token pipeline.", db_path) is None
