"""Tests for WS 8c-1: CLI UX Fixes."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, UTC
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _run_ds(*args: str, cwd: Path | None = None) -> tuple[int, str, str]:
    """Run ds CLI and return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, "-m", "interfaces.cli.ds", *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout, result.stderr


def _make_db_with_project(tmp_path: Path) -> tuple[Path, str]:
    """Create a minimal studio.db with one active project and one open work order."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    db_path = state_dir / "studio.db"

    project_id = str(uuid.uuid4())
    milestone_id = str(uuid.uuid4())
    wo_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    # WO-SQUASH-TESTS: apply the real lean baseline (migration 142) for schema
    # instead of a hand-built DDL mirror that had drifted (missing
    # business_work_orders.sequence_order, added migration 108) and PK-collided
    # with the baseline's seeded work-order types. Seeds are INSERT OR IGNORE so
    # they coexist with the baseline's own type seed.
    from core.config.sqlite_bootstrap import run_migrations

    with sqlite3.connect(str(db_path)) as conn:
        run_migrations(conn, apply_unreleased=True)
        conn.executescript(f"""
            INSERT OR IGNORE INTO business_projects (project_id, name, description, status, created_at, updated_at) VALUES (
                '{project_id}', 'Test Project', 'desc', 'active', '{now}', '{now}'
            );
            INSERT OR IGNORE INTO business_milestones (milestone_id, project_id, title, description, due_date, status, created_at, updated_at, order_index) VALUES (
                '{milestone_id}', '{project_id}', 'Foundation', 'First milestone',
                NULL, 'pending', '{now}', '{now}', 0
            );
            INSERT OR IGNORE INTO business_work_orders (work_order_id, project_id, milestone_id, title, description, status, work_order_type, created_at, updated_at) VALUES (
                '{wo_id}', '{project_id}', '{milestone_id}',
                'Wire Tauri shell', 'desc', 'created', 'infrastructure', '{now}', '{now}'
            );
            INSERT OR IGNORE INTO business_tasks (task_id, work_order_id, project_id, title, description, status, created_at, updated_at) VALUES (
                '{task_id}', '{wo_id}', '{project_id}',
                'Create Tauri config', 'desc', 'pending', '{now}', '{now}'
            );
        """)
        conn.commit()

    return db_path, project_id


# ── work-order list: exit code ────────────────────────────────────────────────


def test_work_order_list_exits_0(tmp_path):
    db_path, project_id = _make_db_with_project(tmp_path)
    rc, stdout, stderr = _run_ds(
        "--home",
        str(tmp_path),
        "work-order",
        "list",
        "--project",
        project_id,
    )
    assert rc == 0, f"Expected exit 0, got {rc}. stderr: {stderr}"


# ── work-order list: full UUIDs ───────────────────────────────────────────────


def test_work_order_list_returns_full_uuids(tmp_path):
    db_path, project_id = _make_db_with_project(tmp_path)
    rc, stdout, stderr = _run_ds(
        "--home",
        str(tmp_path),
        "work-order",
        "list",
        "--project",
        project_id,
    )
    assert rc == 0, f"stderr: {stderr}"
    data = json.loads(stdout)
    wo_list = data.get("work_orders", [])
    assert len(wo_list) >= 1, "Expected at least one work order in list"
    for wo in wo_list:
        wo_id = wo["id"]
        assert (
            len(wo_id) == 36
        ), f"Expected full UUID (36 chars), got '{wo_id}' ({len(wo_id)} chars)"
        # Must be a valid UUID format
        assert wo_id.count("-") == 4, f"Not a valid UUID format: {wo_id}"


# ── project next: next_command field ─────────────────────────────────────────


def test_project_next_returns_next_command_field(tmp_path):
    db_path, project_id = _make_db_with_project(tmp_path)
    rc, stdout, stderr = _run_ds(
        "--home",
        str(tmp_path),
        "project",
        "next",
        project_id,
    )
    assert rc == 0, f"stderr: {stderr}"
    data = json.loads(stdout)
    wo = data.get("work_order")
    assert wo is not None, "Expected work_order in response"
    assert "next_command" in wo, f"next_command field missing from: {wo}"


def test_project_next_command_contains_full_uuid(tmp_path):
    db_path, project_id = _make_db_with_project(tmp_path)
    rc, stdout, stderr = _run_ds(
        "--home",
        str(tmp_path),
        "project",
        "next",
        project_id,
    )
    assert rc == 0
    data = json.loads(stdout)
    wo = data.get("work_order", {})
    next_cmd = wo.get("next_command", "")
    assert (
        "ds work-order start" in next_cmd
    ), f"next_command should be 'ds work-order start <uuid>', got: {next_cmd}"
    # The UUID in next_command should be full (36 chars)
    parts = next_cmd.split()
    assert len(parts) == 4, f"Expected 'ds work-order start <uuid>', got: {next_cmd}"
    uuid_part = parts[-1]
    assert len(uuid_part) == 36, f"UUID in next_command is not full: {uuid_part}"


# ── project next: milestone field ────────────────────────────────────────────


def test_project_next_returns_milestone_field(tmp_path):
    db_path, project_id = _make_db_with_project(tmp_path)
    rc, stdout, stderr = _run_ds(
        "--home",
        str(tmp_path),
        "project",
        "next",
        project_id,
    )
    assert rc == 0
    data = json.loads(stdout)
    wo = data.get("work_order", {})
    assert "milestone" in wo, f"milestone field missing from: {wo}"
    assert wo["milestone"] == "Foundation"


# ── project start: activates and starts WO ────────────────────────────────────


def test_project_start_exits_0(tmp_path):
    db_path, project_id = _make_db_with_project(tmp_path)
    planning_root = tmp_path / ".planning"
    rc, stdout, stderr = _run_ds(
        "--home",
        str(tmp_path),
        "project",
        "start",
        project_id,
        "--planning-root",
        str(planning_root),
    )
    assert rc == 0, f"Expected exit 0, got {rc}. stderr: {stderr}\nstdout: {stdout}"


def test_project_start_prints_project_name(tmp_path):
    db_path, project_id = _make_db_with_project(tmp_path)
    planning_root = tmp_path / ".planning"
    rc, stdout, stderr = _run_ds(
        "--home",
        str(tmp_path),
        "project",
        "start",
        project_id,
        "--planning-root",
        str(planning_root),
    )
    assert rc == 0, f"stderr: {stderr}"
    combined = stdout + stderr
    assert "Test Project" in combined, "Expected project name in output"


def test_project_start_prints_work_order_title(tmp_path):
    db_path, project_id = _make_db_with_project(tmp_path)
    planning_root = tmp_path / ".planning"
    rc, stdout, stderr = _run_ds(
        "--home",
        str(tmp_path),
        "project",
        "start",
        project_id,
        "--planning-root",
        str(planning_root),
    )
    assert rc == 0
    combined = stdout + stderr
    assert (
        "Wire Tauri shell" in combined or "Starting:" in combined
    ), f"Expected work order title in output. Got: {combined[:500]}"


def test_project_start_stores_context_in_authority(tmp_path):
    """WO-FILESDB-C2: `ds project start` stores the WO context in the authority
    (business_work_order_artifacts, kind='context'), not on .planning disk."""
    import sqlite3

    db_path, project_id = _make_db_with_project(tmp_path)
    planning_root = tmp_path / ".planning"
    rc, stdout, stderr = _run_ds(
        "--home",
        str(tmp_path),
        "project",
        "start",
        project_id,
        "--planning-root",
        str(planning_root),
    )
    assert rc == 0
    # No context.md written to disk; the context lives in the authority.
    assert list(planning_root.rglob("context.md")) == []
    with sqlite3.connect(str(db_path)) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM business_work_order_artifacts WHERE kind = 'context'"
        ).fetchone()[0]
    assert count >= 1, "Expected the WO context stored as a kind='context' authority artifact"


# ── project start: no open WOs ────────────────────────────────────────────────


def test_project_start_no_open_wos_prints_helpful_message(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    db_path = state_dir / "studio.db"
    project_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    # WO-SQUASH-TESTS: real baseline schema (migration 142) instead of a drifted
    # hand-built DDL mirror; seed the one active project with no open work orders.
    from core.config.sqlite_bootstrap import run_migrations

    with sqlite3.connect(str(db_path)) as conn:
        run_migrations(conn, apply_unreleased=True)
        conn.executescript(f"""
            INSERT OR IGNORE INTO business_projects (project_id, name, description, status, created_at, updated_at) VALUES (
                '{project_id}', 'Empty Project', 'desc', 'active', '{now}', '{now}'
            );
        """)
        conn.commit()

    rc, stdout, stderr = _run_ds(
        "--home",
        str(tmp_path),
        "project",
        "start",
        project_id,
    )
    assert rc == 0, f"Expected exit 0 with no work orders, got {rc}. stderr: {stderr}"
    combined = stdout + stderr
    assert (
        "No open work orders" in combined or "no open" in combined.lower()
    ), f"Expected helpful 'no open work orders' message. Got: {combined[:500]}"


# ── adapters: exit code ───────────────────────────────────────────────────────


def test_adapters_exits_0(tmp_path):
    # ds adapters requires an initialized DB; bootstrap a rehearsal runtime first.
    _run_ds("rehearsal-install", "--rehearsal-home", str(tmp_path))
    rc, stdout, stderr = _run_ds("--home", str(tmp_path), "adapters")
    assert rc == 0, f"Expected exit 0, got {rc}. stderr: {stderr[:200]}"


# ── project list: exit code ───────────────────────────────────────────────────


def test_project_list_exits_0(tmp_path):
    db_path, project_id = _make_db_with_project(tmp_path)
    rc, stdout, stderr = _run_ds("--home", str(tmp_path), "project", "list")
    assert rc == 0, f"Expected exit 0, got {rc}. stderr: {stderr}"


# ── work-order tasks: exit code ──────────────────────────────────────────────


def test_work_order_tasks_exits_0_or_1_not_255(tmp_path):
    db_path, project_id = _make_db_with_project(tmp_path)
    # Get a real work order ID
    rc, stdout, stderr = _run_ds(
        "--home",
        str(tmp_path),
        "work-order",
        "list",
        "--project",
        project_id,
    )
    data = json.loads(stdout)
    wo_id = data["work_orders"][0]["id"]

    rc2, stdout2, stderr2 = _run_ds(
        "--home",
        str(tmp_path),
        "work-order",
        "tasks",
        wo_id,
    )
    # Should exit 0 or 1 (task lookup may vary), never 255
    assert rc2 != 255, f"work-order tasks exited 255 (success should be 0): {stderr2}"
