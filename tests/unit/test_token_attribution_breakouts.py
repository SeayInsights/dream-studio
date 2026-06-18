"""Tests for WO-DASH-ATTRIBUTION-SURFACES T1: project name + entity breakouts in attribution-breakouts route."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.config.sqlite_bootstrap import bootstrap_database


def test_shows_name_and_entity_breakouts(tmp_path, monkeypatch) -> None:
    """T1: attribution-breakouts returns project_name and all five breakout dimensions."""
    db_path = tmp_path / "attribution-breakouts-test.db"
    bootstrap_database(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Seed two token_usage_records rows for the same project/milestone/agent
        conn.execute(
            "INSERT INTO token_usage_records"
            " (token_usage_id, project_id, milestone_id, task_id, skill_id, agent_id,"
            "  input_tokens, output_tokens, total_tokens)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "tu-1",
                "29ff0914-b15a-4a84-8bc7-5619cc5240f6",
                "ms-1",
                "task-1",
                "ds-project",
                "agent-1",
                1000,
                500,
                1500,
            ),
        )
        conn.execute(
            "INSERT INTO token_usage_records"
            " (token_usage_id, project_id, milestone_id, task_id, skill_id, agent_id,"
            "  input_tokens, output_tokens, total_tokens)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "tu-2",
                "29ff0914-b15a-4a84-8bc7-5619cc5240f6",
                "ms-1",
                "task-2",
                "ds-core",
                "agent-1",
                200,
                100,
                300,
            ),
        )
        # Seed the business_projects row so project_name can be resolved
        conn.execute(
            "INSERT OR IGNORE INTO business_projects"
            " (project_id, name, status, created_at, updated_at)"
            " VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            (
                "29ff0914-b15a-4a84-8bc7-5619cc5240f6",
                "Dream Studio",
                "active",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    from projections.api.main import app

    client = TestClient(app)

    resp = client.get("/api/v1/insights/attribution-breakouts")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    data = resp.json()

    assert data["data_status"] == "ok", f"Expected data_status='ok', got: {data['data_status']}"

    # by_project — non-empty and carries project_name
    assert data["by_project"], "by_project should be non-empty"
    first_project_row = data["by_project"][0]
    assert (
        "project_name" in first_project_row
    ), f"by_project row is missing 'project_name' key: {first_project_row}"
    assert (
        first_project_row["project_name"] == "Dream Studio"
    ), f"Expected project_name='Dream Studio', got: {first_project_row['project_name']!r}"

    # by_milestone — 1 row for ms-1
    assert data["by_milestone"], "by_milestone should be non-empty"

    # by_skill — 2 rows (ds-project and ds-core)
    assert data["by_skill"], "by_skill should be non-empty"
    skill_keys = {row["skill_id"] for row in data["by_skill"]}
    assert "ds-project" in skill_keys, f"Expected 'ds-project' in by_skill, got: {skill_keys}"
    assert "ds-core" in skill_keys, f"Expected 'ds-core' in by_skill, got: {skill_keys}"

    # by_agent — non-empty
    assert data["by_agent"], "by_agent should be non-empty"

    # by_task — non-empty (task-1 and task-2)
    assert data["by_task"], "by_task should be non-empty"
