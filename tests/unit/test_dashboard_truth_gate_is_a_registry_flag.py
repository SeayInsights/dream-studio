"""The dashboard_truth close gate is a flag on a work-order type, not a literal set in close_main.

The gate used to be bound by ``_DASHBOARD_TRUTH_GATED_TYPES = {"dashboard", "telemetry",
"data_pipeline", "saas_feature"}`` in ``close_main``. Two of those names were never declared types
(nothing seeds them, ``create_work_order`` refuses them), so the set could not be extended by a
pack and half of it could not be reached. It is now ``dashboard_truth_gated`` on the type.

Two questions, kept apart.

1. THE BUILT-INS DID NOT CHANGE. The first test closes one work order of every built-in type with
   the gate failing and records which ones the gate stopped. The expected set is the parent's:
   exactly ``data_pipeline`` and ``saas_feature``. It uses only the public close function and raw
   rows, so it runs unchanged against the code before this change.
2. THE TWO DELETED NAMES WERE UNREACHABLE. They are not types, no row seeds them and the door
   refuses them, so deleting them removes no behaviour a work order could reach.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-05-20T00:00:00+00:00"

#: Spelled out from the parent's literal set, minus the two names that were never types.
PARENT_GATED_BUILT_INS = frozenset({"data_pipeline", "saas_feature"})
BUILT_INS = (
    "api_endpoint",
    "authentication",
    "data_pipeline",
    "deployment",
    "documentation",
    "game_mechanic",
    "infrastructure",
    "saas_feature",
    "ui_component",
    "ui_page",
)
FAILING = {
    "ok": False,
    "results": [{"name": "token_model_null_fraction", "passed": False, "error": None}],
}


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    target = tmp_path / "studio.db"
    bootstrap_database(target)
    return target


@pytest.fixture
def patched_paths(db_path: Path, tmp_path: Path):
    fake = MagicMock()
    fake.sqlite_path = db_path
    fake.source_root = REPO_ROOT
    fake.dream_studio_home = tmp_path
    with patch("interfaces.cli.ds.resolve_installed_runtime_paths", return_value=fake):
        yield fake


def _seed_project(db_path: Path) -> tuple[str, str]:
    project_id, milestone_id = str(uuid.uuid4()), str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects"
            " (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, 'P', '', 'active', ?, ?)",
            (project_id, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, status, order_index, created_at, updated_at)"
            " VALUES (?, ?, 'M', 'active', 0, ?, ?)",
            (milestone_id, project_id, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id, milestone_id


def _close_failures(db_path: Path, tmp_path: Path, wo_type: str) -> list[str]:
    """Close one pushed work order of ``wo_type`` with the dashboard-truth gate failing and
    return every gate failure. Whether OTHER gates also object is not this test's concern."""
    from core.work_orders.close import close_work_order

    project_id, milestone_id = _seed_project(db_path)
    wo_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, work_order_type,"
            "  status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'WO', 'd', ?, 'pushed', ?, ?)",
            (wo_id, project_id, milestone_id, wo_type, NOW, NOW),
        )
        for n in (1, 2):
            conn.execute(
                "INSERT INTO business_tasks"
                " (task_id, work_order_id, project_id, title, status, acceptance_criteria,"
                " created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 'complete', 'SQL-CHECK: SELECT 1', ?, ?)",
                (str(uuid.uuid4()), wo_id, project_id, f"T{n}", NOW, NOW),
            )
        conn.commit()
    finally:
        conn.close()
    with patch("core.gates.dashboard_truth.run_dashboard_truth", return_value=FAILING):
        result = close_work_order(
            work_order_id=wo_id,
            source_root=REPO_ROOT,
            dream_studio_home=tmp_path,
            planning_root=tmp_path / ".planning",
        )
    return result.get("failures", [])


def test_the_gate_stops_exactly_the_built_in_types_the_old_set_named(
    patched_paths, db_path, tmp_path
):
    """Runs unchanged against the parent: only the public close function and raw rows."""
    gated = {
        t
        for t in BUILT_INS
        if any("dashboard_truth" in f for f in _close_failures(db_path, tmp_path, t))
    }
    assert gated == PARENT_GATED_BUILT_INS


@pytest.mark.parametrize("name", BUILT_INS)
def test_the_registry_flag_agrees_with_the_old_set_for_each_built_in(name):
    from core.work_orders.type_registry import is_dashboard_truth_gated

    assert is_dashboard_truth_gated(name) is (name in PARENT_GATED_BUILT_INS)


@pytest.mark.parametrize("name", ["dashboard", "telemetry"])
def test_the_two_names_the_old_set_carried_were_not_types_anyone_could_reach(name, db_path):
    """The evidence for deleting them: not declared, not seeded (the baseline migration is the
    only seed of business_work_order_types and holds the ten built-ins), and refused by the door.
    Nothing outside a hand-edited row could have carried either as a work-order type."""
    from core.work_orders.mutations import create_work_order
    from core.work_orders.type_registry import get_work_order_type, is_dashboard_truth_gated

    assert get_work_order_type(name) is None
    assert is_dashboard_truth_gated(name) is False
    conn = sqlite3.connect(str(db_path))
    try:
        seeded = {r[0] for r in conn.execute("SELECT type_id FROM business_work_order_types")}
    finally:
        conn.close()
    assert name not in seeded and seeded == set(BUILT_INS)
    result = create_work_order(
        project_id="p",
        milestone_id="m",
        title="A thing",
        description="A description long enough to clear the prompt floor for a work order, easily.",
        work_order_type=name,
        source_root=REPO_ROOT,
    )
    assert result["ok"] is False and "is not one the platform declares" in result["error"]


def test_a_type_a_pack_flags_is_gated_and_one_it_does_not_flag_is_not(
    patched_paths, db_path, tmp_path
):
    """The point of the change: the flag is readable and settable by a manifest."""
    from core.work_orders.type_registry import scoped_pack_manifest

    packs = tmp_path / "packs.yaml"
    packs.write_text(
        "schema_version: 2\n"
        "packs:\n"
        "  finance:\n"
        "    contributes:\n"
        "      work_order_types:\n"
        "        - {name: ledger_extract, artifact_class: data, description: An extract,"
        " dashboard_truth_gated: true}\n"
        "        - {name: policy_memo, artifact_class: document, description: A memo}\n",
        encoding="utf-8",
    )
    with scoped_pack_manifest(packs):
        assert any(
            "dashboard_truth" in f for f in _close_failures(db_path, tmp_path, "ledger_extract")
        )
        assert not any(
            "dashboard_truth" in f for f in _close_failures(db_path, tmp_path, "policy_memo")
        )
