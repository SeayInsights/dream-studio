"""Tests for WO-ORD: explicit work-order ordering (sequence_order + dependencies)."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]

NOW_A = "2026-01-01T00:00:00.000000Z"
NOW_B = "2026-01-01T00:01:00.000000Z"
NOW_C = "2026-01-01T00:02:00.000000Z"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "studio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_database(db_path)
    return db_path


@contextmanager
def _patch_db(db_path: Path):
    """Patch resolve_installed_runtime_paths so _require_db resolves to db_path."""
    fake_paths = MagicMock()
    fake_paths.sqlite_path = db_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake_paths):
        yield


def _seed(db_path: Path, *, project_id: str, milestone_id: str, milestone_order: int = 0) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO business_projects"
        " (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "Test", "", "active", NOW_A, NOW_A),
    )
    conn.execute(
        "INSERT OR IGNORE INTO business_milestones"
        " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (milestone_id, project_id, "M1", "active", milestone_order, NOW_A, NOW_A),
    )
    conn.commit()
    conn.close()


def _seed_wo(
    db_path: Path,
    *,
    work_order_id: str,
    project_id: str,
    milestone_id: str | None,
    status: str = "created",
    created_at: str = NOW_A,
    sequence_order: int | None = None,
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO business_work_orders"
        " (work_order_id, project_id, milestone_id, title, status,"
        "  sequence_order, created_at, updated_at, last_updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (
            work_order_id,
            project_id,
            milestone_id,
            f"WO-{work_order_id[:4]}",
            status,
            sequence_order,
            created_at,
            created_at,
            created_at,
        ),
    )
    conn.commit()
    conn.close()


def _add_dep(db_path: Path, *, work_order_id: str, depends_on_id: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO work_order_dependencies (work_order_id, depends_on_id, created_at)"
        " VALUES (?,?,?)",
        (work_order_id, depends_on_id, NOW_A),
    )
    conn.commit()
    conn.close()


def _get_next(db_path: Path, project_id: str) -> str | None:
    from core.projects.queries import get_next_work_order

    with _patch_db(db_path):
        result = get_next_work_order(
            project_id=project_id,
            source_root=REPO_ROOT,
            dream_studio_home=None,
        )
    wo = result.get("work_order")
    return wo["work_order_id"] if wo else None


# ---------------------------------------------------------------------------
# Migration: schema columns exist
# ---------------------------------------------------------------------------


def test_migration_sequence_order_column_exists(tmp_path):
    """sequence_order column must be present on business_work_orders after bootstrap."""
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(business_work_orders)")}
    conn.close()
    assert "sequence_order" in cols


def test_migration_work_order_dependencies_table_exists(tmp_path):
    """work_order_dependencies table must be present after bootstrap."""
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "work_order_dependencies" in tables


# ---------------------------------------------------------------------------
# Ready-set selector: dependency gating
# ---------------------------------------------------------------------------


def test_wo_with_open_dependency_not_selected(tmp_path):
    """A WO with an unresolved dependency must not be returned by the selector."""
    db_path = _make_db(tmp_path)
    pid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    _seed(db_path, project_id=pid, milestone_id=mid)

    blocker_id = str(uuid.uuid4())
    dependent_id = str(uuid.uuid4())
    _seed_wo(db_path, work_order_id=blocker_id, project_id=pid, milestone_id=mid, status="created")
    _seed_wo(
        db_path,
        work_order_id=dependent_id,
        project_id=pid,
        milestone_id=mid,
        status="created",
    )
    _add_dep(db_path, work_order_id=dependent_id, depends_on_id=blocker_id)

    selected = _get_next(db_path, pid)
    assert selected == blocker_id, f"Expected blocker to be picked, got {selected!r}"


def test_dependency_resolved_when_blocker_closed(tmp_path):
    """Once the blocker is closed, the dependent becomes selectable."""
    db_path = _make_db(tmp_path)
    pid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    _seed(db_path, project_id=pid, milestone_id=mid)

    blocker_id = str(uuid.uuid4())
    dependent_id = str(uuid.uuid4())
    _seed_wo(db_path, work_order_id=blocker_id, project_id=pid, milestone_id=mid, status="closed")
    _seed_wo(
        db_path,
        work_order_id=dependent_id,
        project_id=pid,
        milestone_id=mid,
        status="created",
    )
    _add_dep(db_path, work_order_id=dependent_id, depends_on_id=blocker_id)

    selected = _get_next(db_path, pid)
    assert selected == dependent_id


# ---------------------------------------------------------------------------
# Ready-set selector: sequence_order changes the pick
# ---------------------------------------------------------------------------


def test_lower_sequence_order_wins(tmp_path):
    """WO with lower sequence_order is selected over one created earlier."""
    db_path = _make_db(tmp_path)
    pid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    _seed(db_path, project_id=pid, milestone_id=mid)

    first_created = str(uuid.uuid4())
    second_created = str(uuid.uuid4())
    # first_created has earlier timestamp but higher sequence_order
    _seed_wo(
        db_path,
        work_order_id=first_created,
        project_id=pid,
        milestone_id=mid,
        created_at=NOW_A,
        sequence_order=20,
    )
    _seed_wo(
        db_path,
        work_order_id=second_created,
        project_id=pid,
        milestone_id=mid,
        created_at=NOW_B,
        sequence_order=10,
    )

    selected = _get_next(db_path, pid)
    assert selected == second_created, f"Expected sequence_order=10 WO, got {selected!r}"


def test_null_sequence_order_sorts_last(tmp_path):
    """WOs with NULL sequence_order sort after those with an explicit value."""
    db_path = _make_db(tmp_path)
    pid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    _seed(db_path, project_id=pid, milestone_id=mid)

    wo_null = str(uuid.uuid4())
    wo_explicit = str(uuid.uuid4())
    # wo_null created earlier but has no sequence_order
    _seed_wo(
        db_path,
        work_order_id=wo_null,
        project_id=pid,
        milestone_id=mid,
        created_at=NOW_A,
        sequence_order=None,
    )
    _seed_wo(
        db_path,
        work_order_id=wo_explicit,
        project_id=pid,
        milestone_id=mid,
        created_at=NOW_B,
        sequence_order=10,
    )

    selected = _get_next(db_path, pid)
    assert selected == wo_explicit, f"Expected explicit-order WO, got {selected!r}"


def test_created_at_breaks_ties(tmp_path):
    """When sequence_order is equal, earlier created_at is preferred."""
    db_path = _make_db(tmp_path)
    pid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    _seed(db_path, project_id=pid, milestone_id=mid)

    wo_early = str(uuid.uuid4())
    wo_late = str(uuid.uuid4())
    _seed_wo(
        db_path,
        work_order_id=wo_early,
        project_id=pid,
        milestone_id=mid,
        created_at=NOW_A,
        sequence_order=10,
    )
    _seed_wo(
        db_path,
        work_order_id=wo_late,
        project_id=pid,
        milestone_id=mid,
        created_at=NOW_B,
        sequence_order=10,
    )

    selected = _get_next(db_path, pid)
    assert selected == wo_early


# ---------------------------------------------------------------------------
# Ready-set selector: strays (no milestone) never surfaced
# ---------------------------------------------------------------------------


def test_stray_wo_never_surfaced(tmp_path):
    """A WO with milestone_id=NULL must never be returned by the selector."""
    db_path = _make_db(tmp_path)
    pid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    _seed(db_path, project_id=pid, milestone_id=mid)

    stray_id = str(uuid.uuid4())
    legit_id = str(uuid.uuid4())
    # Stray: milestone_id = NULL
    _seed_wo(
        db_path,
        work_order_id=stray_id,
        project_id=pid,
        milestone_id=None,
        created_at=NOW_A,
    )
    _seed_wo(
        db_path,
        work_order_id=legit_id,
        project_id=pid,
        milestone_id=mid,
        created_at=NOW_B,
    )

    selected = _get_next(db_path, pid)
    assert selected == legit_id, f"Stray WO must not be selected; got {selected!r}"


def test_only_strays_returns_none(tmp_path):
    """When only stray WOs exist, the selector returns no work order."""
    db_path = _make_db(tmp_path)
    pid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    _seed(db_path, project_id=pid, milestone_id=mid)

    stray_id = str(uuid.uuid4())
    _seed_wo(
        db_path,
        work_order_id=stray_id,
        project_id=pid,
        milestone_id=None,
        created_at=NOW_A,
    )

    selected = _get_next(db_path, pid)
    assert selected is None


# ---------------------------------------------------------------------------
# set_sequence_order mutation
# ---------------------------------------------------------------------------


def test_set_sequence_order_updates_row(tmp_path):
    db_path = _make_db(tmp_path)
    pid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    wo_id = str(uuid.uuid4())
    _seed(db_path, project_id=pid, milestone_id=mid)
    _seed_wo(db_path, work_order_id=wo_id, project_id=pid, milestone_id=mid)

    from core.work_orders.ordering import set_sequence_order

    with _patch_db(db_path):
        result = set_sequence_order(
            work_order_id=wo_id,
            sequence_order=30,
            source_root=REPO_ROOT,
            dream_studio_home=None,
        )
    assert result["ok"] is True
    assert result["sequence_order"] == 30

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT sequence_order FROM business_work_orders WHERE work_order_id = ?", (wo_id,)
    ).fetchone()
    conn.close()
    assert row[0] == 30


def test_set_sequence_order_not_found(tmp_path):
    db_path = _make_db(tmp_path)
    from core.work_orders.ordering import set_sequence_order

    with _patch_db(db_path):
        result = set_sequence_order(
            work_order_id=str(uuid.uuid4()),
            sequence_order=10,
            source_root=REPO_ROOT,
            dream_studio_home=None,
        )
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# add_dependency / remove_dependency mutations
# ---------------------------------------------------------------------------


def test_add_dependency_inserts_edge(tmp_path):
    db_path = _make_db(tmp_path)
    pid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    wo_a = str(uuid.uuid4())
    wo_b = str(uuid.uuid4())
    _seed(db_path, project_id=pid, milestone_id=mid)
    _seed_wo(db_path, work_order_id=wo_a, project_id=pid, milestone_id=mid)
    _seed_wo(db_path, work_order_id=wo_b, project_id=pid, milestone_id=mid)

    from core.work_orders.ordering import add_dependency

    with _patch_db(db_path):
        result = add_dependency(
            work_order_id=wo_b,
            depends_on_id=wo_a,
            source_root=REPO_ROOT,
            dream_studio_home=None,
        )
    assert result["ok"] is True

    conn = sqlite3.connect(str(db_path))
    edge = conn.execute(
        "SELECT 1 FROM work_order_dependencies WHERE work_order_id=? AND depends_on_id=?",
        (wo_b, wo_a),
    ).fetchone()
    conn.close()
    assert edge is not None


def test_add_dependency_self_is_error(tmp_path):
    db_path = _make_db(tmp_path)
    from core.work_orders.ordering import add_dependency

    wo_id = str(uuid.uuid4())
    with _patch_db(db_path):
        result = add_dependency(
            work_order_id=wo_id,
            depends_on_id=wo_id,
            source_root=REPO_ROOT,
            dream_studio_home=None,
        )
    assert result["ok"] is False
    assert "itself" in result["error"]


def test_add_dependency_idempotent(tmp_path):
    db_path = _make_db(tmp_path)
    pid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    wo_a = str(uuid.uuid4())
    wo_b = str(uuid.uuid4())
    _seed(db_path, project_id=pid, milestone_id=mid)
    _seed_wo(db_path, work_order_id=wo_a, project_id=pid, milestone_id=mid)
    _seed_wo(db_path, work_order_id=wo_b, project_id=pid, milestone_id=mid)

    from core.work_orders.ordering import add_dependency

    with _patch_db(db_path):
        add_dependency(
            work_order_id=wo_b,
            depends_on_id=wo_a,
            source_root=REPO_ROOT,
            dream_studio_home=None,
        )
        result2 = add_dependency(
            work_order_id=wo_b,
            depends_on_id=wo_a,
            source_root=REPO_ROOT,
            dream_studio_home=None,
        )
    assert result2["ok"] is True
    assert result2.get("already_exists") is True


def test_remove_dependency_deletes_edge(tmp_path):
    db_path = _make_db(tmp_path)
    pid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    wo_a = str(uuid.uuid4())
    wo_b = str(uuid.uuid4())
    _seed(db_path, project_id=pid, milestone_id=mid)
    _seed_wo(db_path, work_order_id=wo_a, project_id=pid, milestone_id=mid)
    _seed_wo(db_path, work_order_id=wo_b, project_id=pid, milestone_id=mid)
    _add_dep(db_path, work_order_id=wo_b, depends_on_id=wo_a)

    from core.work_orders.ordering import remove_dependency

    with _patch_db(db_path):
        result = remove_dependency(
            work_order_id=wo_b,
            depends_on_id=wo_a,
            source_root=REPO_ROOT,
            dream_studio_home=None,
        )
    assert result["ok"] is True

    conn = sqlite3.connect(str(db_path))
    edge = conn.execute(
        "SELECT 1 FROM work_order_dependencies WHERE work_order_id=? AND depends_on_id=?",
        (wo_b, wo_a),
    ).fetchone()
    conn.close()
    assert edge is None


def test_remove_dependency_not_found(tmp_path):
    db_path = _make_db(tmp_path)
    pid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    wo_a = str(uuid.uuid4())
    _seed(db_path, project_id=pid, milestone_id=mid)
    _seed_wo(db_path, work_order_id=wo_a, project_id=pid, milestone_id=mid)

    from core.work_orders.ordering import remove_dependency

    with _patch_db(db_path):
        result = remove_dependency(
            work_order_id=wo_a,
            depends_on_id=str(uuid.uuid4()),
            source_root=REPO_ROOT,
            dream_studio_home=None,
        )
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# in_progress WOs bypass the dependency gate
# ---------------------------------------------------------------------------


def test_in_progress_wo_not_blocked_by_dependency(tmp_path):
    """An already in_progress WO must still surface even if it has an open dependency."""
    db_path = _make_db(tmp_path)
    pid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    _seed(db_path, project_id=pid, milestone_id=mid)

    blocker_id = str(uuid.uuid4())
    in_progress_id = str(uuid.uuid4())
    _seed_wo(db_path, work_order_id=blocker_id, project_id=pid, milestone_id=mid, status="created")
    _seed_wo(
        db_path,
        work_order_id=in_progress_id,
        project_id=pid,
        milestone_id=mid,
        status="in_progress",
        created_at=NOW_A,
    )
    _add_dep(db_path, work_order_id=in_progress_id, depends_on_id=blocker_id)

    selected = _get_next(db_path, pid)
    assert selected == in_progress_id
