"""Slice 6d: ds work-order task-done / tasks command tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from interfaces.cli.ds import main

PROJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
WO_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
TASK_A = "11111111-1111-1111-1111-111111111111"
TASK_B = "22222222-2222-2222-2222-222222222222"
TASK_C = "33333333-3333-3333-3333-333333333333"
OTHER_WO = "dddddddd-dddd-dddd-dddd-dddddddddddd"
OTHER_TASK = "44444444-4444-4444-4444-444444444444"
NOW = "2026-05-16T00:00:00+00:00"
NOW2 = "2026-05-16T00:00:01+00:00"
NOW3 = "2026-05-16T00:00:02+00:00"


@pytest.fixture
def db_home(tmp_path):
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True)
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, 'Test Project', 'desc', 'active', ?, ?)",
            (PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'Test WO', NULL, 'in_progress', 'documentation', ?, ?)",
            (WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'Other WO', NULL, 'in_progress', 'documentation', ?, ?)",
            (OTHER_WO, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks (task_id, work_order_id, project_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Write tests', 'pending', ?, ?)",
            (TASK_A, WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks (task_id, work_order_id, project_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Review PR', 'in_progress', ?, ?)",
            (TASK_B, WO_ID, PROJECT_ID, NOW2, NOW2),
        )
        conn.execute(
            "INSERT INTO business_tasks (task_id, work_order_id, project_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Deploy', 'pending', ?, ?)",
            (TASK_C, WO_ID, PROJECT_ID, NOW3, NOW3),
        )
        conn.execute(
            "INSERT INTO business_tasks (task_id, work_order_id, project_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Other task', 'pending', ?, ?)",
            (OTHER_TASK, OTHER_WO, PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return tmp_path


def _task_done(db_home, tmp_path, monkeypatch, work_order_id, task_id, planning_root=None):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    argv = ["--home", str(db_home), "work-order", "task-done", work_order_id, task_id]
    if planning_root:
        argv += ["--planning-root", str(planning_root)]
    return main(argv)


def _tasks(db_home, monkeypatch, work_order_id):
    return main(["--home", str(db_home), "work-order", "tasks", work_order_id])


# ── task-done: core behavior ──────────────────────────────────────────────────


def test_task_done_emits_event_not_direct_write(db_home, tmp_path, monkeypatch):
    # Phase 18.2.3: task.completed is now event-sourced. mark_task_done() emits
    # a canonical event; the TaskProjection applies it to business_tasks
    # asynchronously. The DB row stays 'pending' until the projection runs.
    spool_root = tmp_path / "spool-root"
    monkeypatch.setenv("DS_SPOOL_ROOT", str(spool_root))
    rc = _task_done(db_home, tmp_path, monkeypatch, WO_ID, TASK_A)
    assert rc == 0
    # DB row is NOT changed directly — projection owns the write.
    db_path = db_home / "state" / "studio.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT status FROM business_tasks WHERE task_id = ?", (TASK_A,)
        ).fetchone()
        assert row[0] == "pending"
    finally:
        conn.close()
    # Canonical event was emitted.
    spool_files = list(spool_root.rglob("*.jsonl")) + list(spool_root.rglob("*.json"))
    events = []
    for f in spool_files:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    assert any(e.get("event_type") == "task.completed" for e in events)


def test_task_done_updates_context_md_checkbox(db_home, tmp_path, monkeypatch):
    planning_root = tmp_path / ".planning"
    context_dir = planning_root / "work-orders" / WO_ID
    context_dir.mkdir(parents=True)
    context_path = context_dir / "context.md"
    context_path.write_text(
        "# Work Order: Test\n\n## Open Tasks\n\n- [ ] Write tests\n- [ ] Deploy\n",
        encoding="utf-8",
    )
    rc = _task_done(db_home, tmp_path, monkeypatch, WO_ID, TASK_A, planning_root=planning_root)
    assert rc == 0
    text = context_path.read_text(encoding="utf-8")
    assert "- [x] Write tests" in text
    assert "- [ ] Deploy" in text


def test_task_done_emits_task_completed_event(db_home, tmp_path, monkeypatch):
    rc = _task_done(db_home, tmp_path, monkeypatch, WO_ID, TASK_B)
    assert rc == 0
    events = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in (tmp_path / "spool-root" / "spool").glob("*.json")
    ]
    task_events = [e for e in events if e.get("event_type") == "task.completed"]
    assert len(task_events) == 1
    ev = task_events[0]
    assert ev["payload"]["task_id"] == TASK_B
    assert ev["payload"]["work_order_id"] == WO_ID
    assert "tasks_remaining" in ev["payload"]


def test_task_done_prints_all_complete_message_when_last_task(
    db_home, tmp_path, monkeypatch, capsys
):
    # Mark A and B complete first (raw DB to avoid spool noise)
    db_path = db_home / "state" / "studio.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("UPDATE business_tasks SET status = 'complete' WHERE task_id = ?", (TASK_A,))
        conn.execute("UPDATE business_tasks SET status = 'complete' WHERE task_id = ?", (TASK_B,))
        conn.commit()
    finally:
        conn.close()

    rc = _task_done(db_home, tmp_path, monkeypatch, WO_ID, TASK_C)
    assert rc == 0
    # Post-A1: handler returns structured JSON with a `suggested_action`
    # field; the wording was tightened from "Run: ds ..." to
    # "Close work order: ds ..." for the operator-facing prompt. Parse
    # the last JSON object printed (the result block — earlier blocks
    # are todowrite_update emissions in some environments).
    # Multiple JSON blocks may be emitted (todowrite_update + result);
    # parse the last one — that's the result.
    json_blocks = ("\n" + capsys.readouterr().out.strip()).split("\n{")[1:]
    data = json.loads("{" + json_blocks[-1])
    assert data.get("all_tasks_complete") is True
    assert (
        data["suggested_action"]
        == f"All tasks complete. Close work order: ds work-order close {WO_ID}"
    )


# ── task-done: error cases ────────────────────────────────────────────────────


def test_task_done_exits_1_on_unknown_task_id(db_home, tmp_path, monkeypatch):
    rc = _task_done(db_home, tmp_path, monkeypatch, WO_ID, "00000000-0000-0000-0000-000000000000")
    assert rc == 1


def test_task_done_exits_1_on_task_not_belonging_to_work_order(db_home, tmp_path, monkeypatch):
    rc = _task_done(db_home, tmp_path, monkeypatch, WO_ID, OTHER_TASK)
    assert rc == 1


# ── tasks: list ───────────────────────────────────────────────────────────────


def test_tasks_shows_correct_status_indicators(db_home, monkeypatch, capsys):
    db_path = db_home / "state" / "studio.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("UPDATE business_tasks SET status = 'complete' WHERE task_id = ?", (TASK_A,))
        conn.commit()
    finally:
        conn.close()

    rc = _tasks(db_home, monkeypatch, WO_ID)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    tasks_by_id = {t["task_id"]: t for t in out["tasks"]}
    assert tasks_by_id[TASK_A]["indicator"] == "[x]"
    assert tasks_by_id[TASK_B]["indicator"] == "[~]"
    assert tasks_by_id[TASK_C]["indicator"] == "[ ]"
