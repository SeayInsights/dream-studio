from __future__ import annotations

from pathlib import Path

import pytest

from core.event_store.studio_db import _connect
from core.shared_intelligence.prd_authority import (
    build_project_intake_plan,
    project_prd_authority_summary,
)


def test_standard_intake_does_not_overask_when_description_answers_groups() -> None:
    sparse = build_project_intake_plan("Build something useful.", mode="standard_discovery")
    detailed = build_project_intake_plan(
        (
            "Build a dashboard for operators with target users, core workflows, MVP, "
            "SQLite storage, API integrations, deployment expectations, success "
            "criteria, constraints, and autonomy level."
        ),
        mode="standard_discovery",
    )

    assert detailed["question_count"] < sparse["question_count"]
    assert detailed["assumptions"]


def test_prd_authority_summary_returns_empty_when_project_tables_absent(tmp_path: Path) -> None:
    """Guard: project_prd_authority_summary returns empty state when project_* tables are dropped."""
    with _connect(_db(tmp_path)) as conn:
        _seed_project(conn, project_id="demo-project")
        summary = project_prd_authority_summary(conn, project_id="demo-project")

    assert summary["prd_count"] == 0
    assert summary["current_milestones"] == []
    assert summary["active_work_orders"] == []
    assert summary["source_status"]["status"] == "unavailable"
    assert summary["empty_state"] == "PRD lifecycle authority tables are unavailable."


def _seed_project(
    conn,
    *,
    project_id: str,
    project_path: str | None = None,
) -> None:
    # reg_projects deleted in migration 084; use business_projects
    conn.execute(
        """
        INSERT OR IGNORE INTO business_projects (
            project_id, name, description, status,
            project_path, detected_stack, stack_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, 'active', ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (
            project_id,
            "Demo Project",
            "application",
            project_path or str(Path.cwd()),
            "python",
            '{"dependencies": ["fastapi"], "config_files": ["pyproject.toml"]}',
        ),
    )


def _db(tmp_path: Path) -> Path:
    return tmp_path / "prd-authority" / "studio.db"
