"""C7 — DB-grounding evals.

Verifies that skill-backing functions surface state by calling named DB-touching
functions, not by reading session memory. Initial scope: assert the invocation
list is non-empty and contains expected functions.

Full claim-matching (verifying each fact in skill output traces back to a
specific query result) is deferred.

  eval_recorder_guard_raises_on_missing_attr — hasattr guard catches renames
  eval_recorder_records_call                 — wrapped calls land in invocations
  eval_get_project_state_consults_db         — resume backing calls _connect
  eval_start_work_order_invokes_read_brief   — start backing calls read_work_order_brief
  eval_start_work_order_consults_db          — start backing calls _connect
"""

from __future__ import annotations

import sqlite3
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-20T00:00:00+00:00"
PROJECT_ID = "77777777-7777-7777-7777-777777777777"
WO_DOCS_ID = "77770000-7777-7777-7777-777777770000"


class InvocationRecorder:
    """Patch named module attributes to record each call, then restore on exit.

    Each target must already exist on its module. Patching a missing attribute
    raises AttributeError immediately so an internal rename fails loudly instead
    of silently producing an empty invocation list.
    """

    def __init__(self, targets: list[tuple[object, str]]) -> None:
        for module, name in targets:
            if not hasattr(module, name):
                raise AttributeError(
                    f"InvocationRecorder target missing: "
                    f"{module.__name__}.{name} does not exist on the module. "
                    f"Was the function renamed?"
                )
        self._targets = list(targets)
        self._originals: list[tuple[object, str, object]] = []
        self.invocations: list[str] = []

    def __enter__(self) -> "InvocationRecorder":
        for module, name in self._targets:
            original = getattr(module, name)
            self._originals.append((module, name, original))
            label = f"{module.__name__}.{name}"
            self._install(module, name, original, label)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        for module, name, original in self._originals:
            setattr(module, name, original)
        return False

    def _install(self, module: object, name: str, original, label: str) -> None:
        invocations = self.invocations

        def wrapper(*args, **kwargs):
            invocations.append(label)
            return original(*args, **kwargs)

        setattr(module, name, wrapper)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    bootstrap_database(target)
    conn = sqlite3.connect(str(target))
    try:
        conn.execute(
            "INSERT INTO business_projects VALUES (?, 'C7 Project', '', 'active', ?, ?)",
            (PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'Docs WO', '', 'created', 'documentation', ?, ?)",
            (WO_DOCS_ID, PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return target


@pytest.fixture
def patched_paths(db_path: Path, tmp_path: Path):
    fake = MagicMock()
    fake.sqlite_path = db_path
    fake.source_root = REPO_ROOT
    fake.dream_studio_home = tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake):
        yield fake


# ── eval_recorder_guard_raises_on_missing_attr ────────────────────────────────


def test_recorder_guard_raises_on_missing_attr() -> None:
    """Patching a missing attribute must raise AttributeError, not silently no-op."""
    import core.projects.queries as projects_queries

    with pytest.raises(AttributeError, match="does not exist"):
        InvocationRecorder([(projects_queries, "function_that_does_not_exist")])


# ── eval_recorder_records_call ────────────────────────────────────────────────


def test_recorder_records_call() -> None:
    """Sanity: a wrapped function call lands in invocations and the call still works."""
    fake_module = types.ModuleType("fake_module_for_test")
    fake_module.double = lambda x: x * 2  # type: ignore[attr-defined]

    with InvocationRecorder([(fake_module, "double")]) as rec:
        assert fake_module.double(3) == 6  # type: ignore[attr-defined]
        assert fake_module.double(4) == 8  # type: ignore[attr-defined]

    assert len(rec.invocations) == 2
    assert all("double" in entry for entry in rec.invocations)


# ── eval_get_project_state_consults_db ────────────────────────────────────────


def test_get_project_state_consults_db(patched_paths, tmp_path: Path) -> None:
    """get_project_state() must reach the DB via _connect, not session memory."""
    import core.projects.queries as projects_queries

    with InvocationRecorder([(projects_queries, "_connect")]) as rec:
        result = projects_queries.get_project_state(
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=tmp_path / ".planning",
        )

    assert result["ok"] is True
    assert rec.invocations, "get_project_state did not call _connect; output is not DB-grounded"
    assert any("_connect" in entry for entry in rec.invocations)


# ── eval_start_work_order_invokes_read_brief ──────────────────────────────────


def test_start_work_order_invokes_read_brief(patched_paths, tmp_path: Path) -> None:
    """start_work_order() must route through the named read_work_order_brief helper."""
    import core.work_orders.start as start_module

    with InvocationRecorder([(start_module, "read_work_order_brief")]) as rec:
        result = start_module.start_work_order(
            work_order_id=WO_DOCS_ID,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=tmp_path / ".planning",
        )

    assert result["ok"] is True, f"start_work_order failed: {result}"
    assert rec.invocations, "start_work_order did not call read_work_order_brief"
    assert any("read_work_order_brief" in entry for entry in rec.invocations)


# ── eval_start_work_order_consults_db ─────────────────────────────────────────


def test_start_work_order_consults_db(patched_paths, tmp_path: Path) -> None:
    """start_work_order() must consult the DB via _connect for its mutation step."""
    import core.work_orders.start as start_module

    with InvocationRecorder([(start_module, "_connect")]) as rec:
        result = start_module.start_work_order(
            work_order_id=WO_DOCS_ID,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=tmp_path / ".planning",
        )

    assert result["ok"] is True
    assert rec.invocations, "start_work_order did not call _connect"
    assert any("_connect" in entry for entry in rec.invocations)
