"""Integration tests for WO-SYMPTOM-RESOLUTION: originating symptom capture and close gate.

Covers:
- Migration 125 adds originating_symptom to business_work_orders
- close_work_order() is blocked when the originating symptom SQL still fails
- End-to-end: WO with a passing symptom closes cleanly
"""

from __future__ import annotations

import sqlite3
import sys
import uuid
from contextlib import contextmanager
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
    wo_type: str = "documentation",
    originating_symptom: str | None = None,
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
        "  work_order_type, status, originating_symptom,"
        "  sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,1,?,?,?)",
        (
            work_order_id,
            project_id,
            milestone_id,
            "Test WO",
            "desc",
            wo_type,
            "in_progress",
            originating_symptom,
            NOW,
            NOW,
            NOW,
        ),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Migration: originating_symptom column exists
# ---------------------------------------------------------------------------


def test_migration_125_adds_originating_symptom_column(tmp_path):
    """After bootstrap, business_work_orders has an originating_symptom column."""
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(business_work_orders)").fetchall()}
    conn.close()
    assert (
        "originating_symptom" in cols
    ), "originating_symptom column missing from business_work_orders after migration 125"


# ---------------------------------------------------------------------------
# Close blocked when symptom persists
# ---------------------------------------------------------------------------


def test_close_blocked_when_symptom_persists(tmp_path):
    """close_work_order() returns ok=False when the originating symptom SQL still fails."""
    from core.work_orders.close import close_work_order

    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())

    # Symptom SQL that will always return 0 (empty table that doesn't exist →
    # SQLite raises an error, which the check maps to a failure).
    failing_symptom = "SQL-CHECK: SELECT COUNT(*) FROM no_such_table_xyz_12345"

    _seed_wo(
        db_path,
        project_id=project_id,
        milestone_id=milestone_id,
        work_order_id=work_order_id,
        originating_symptom=failing_symptom,
    )

    with _patch_db(db_path):
        result = close_work_order(
            work_order_id=work_order_id,
            source_root=tmp_path,
        )

    assert result["ok"] is False, f"Expected close to be blocked, got: {result}"
    assert any(
        "originating_symptom" in f for f in result.get("failures", [])
    ), f"Expected originating_symptom failure in result, got failures={result.get('failures')}"


def test_close_blocked_when_symptom_returns_zero(tmp_path):
    """close_work_order() returns ok=False when the symptom SQL returns 0 (not fixed)."""
    from core.work_orders.close import close_work_order

    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())

    # business_work_order_types always has rows, so this WHERE makes it return 0
    failing_symptom = "SQL-CHECK: SELECT COUNT(*) FROM business_work_order_types WHERE 1=0"

    _seed_wo(
        db_path,
        project_id=project_id,
        milestone_id=milestone_id,
        work_order_id=work_order_id,
        originating_symptom=failing_symptom,
    )

    with _patch_db(db_path):
        result = close_work_order(
            work_order_id=work_order_id,
            source_root=tmp_path,
        )

    assert result["ok"] is False
    assert any("originating_symptom" in f for f in result.get("failures", []))


# ---------------------------------------------------------------------------
# End-to-end: symptom passes → close succeeds
# ---------------------------------------------------------------------------


def test_end_to_end(tmp_path):
    """WO with a passing originating symptom closes cleanly."""
    from core.work_orders.close import close_work_order

    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())

    # business_projects always has the seeded row, so COUNT > 0 → passes
    passing_symptom = "SQL-CHECK: SELECT COUNT(*) FROM business_projects"

    _seed_wo(
        db_path,
        project_id=project_id,
        milestone_id=milestone_id,
        work_order_id=work_order_id,
        originating_symptom=passing_symptom,
    )

    with _patch_db(db_path):
        result = close_work_order(
            work_order_id=work_order_id,
            source_root=tmp_path,
        )

    assert result["ok"] is True, f"Expected successful close, got: {result}"
    assert result["status"] == "closed"


def test_end_to_end_no_symptom(tmp_path):
    """WO without an originating_symptom closes normally (symptom gate is a no-op)."""
    from core.work_orders.close import close_work_order

    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    work_order_id = str(uuid.uuid4())

    _seed_wo(
        db_path,
        project_id=project_id,
        milestone_id=milestone_id,
        work_order_id=work_order_id,
        originating_symptom=None,
    )

    with _patch_db(db_path):
        result = close_work_order(
            work_order_id=work_order_id,
            source_root=tmp_path,
        )

    assert result["ok"] is True
