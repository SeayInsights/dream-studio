"""TA2: Active task context tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database

PROJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MILESTONE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
WO_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
TASK_A = "11111111-1111-1111-1111-111111111111"
TASK_B = "22222222-2222-2222-2222-222222222222"
ORPHAN_TASK = "33333333-3333-3333-3333-333333333333"
NOW = "2026-05-21T00:00:00+00:00"


@pytest.fixture
def db_home(tmp_path):
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True)
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects VALUES (?, 'Test Project', 'desc', 'active', ?, ?)",
            (PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, status, created_at, updated_at)"
            " VALUES (?, ?, 'M1', 'active', ?, ?)",
            (MILESTONE_ID, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, 'WO1', NULL, 'in_progress', 'documentation', ?, ?)",
            (WO_ID, PROJECT_ID, MILESTONE_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, 'Task A', 'desc A', 'pending', ?, ?)",
            (TASK_A, WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, description, status,"
            " created_at, updated_at)"
            " VALUES (?, ?, ?, 'Task B', 'desc B', 'pending', ?, ?)",
            (TASK_B, WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return tmp_path


def _spool_events(spool_root: Path) -> list[dict]:
    spool_dir = spool_root / "spool"
    if not spool_dir.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(spool_dir.glob("*.json"))]


def _events_of_type(spool_root: Path, event_type: str) -> list[dict]:
    return [e for e in _spool_events(spool_root) if e.get("event_type") == event_type]


def test_set_active_task_resolves_full_sdlc_chain(db_home, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(db_home / "state" / "active_task.json"))
    from core.sdlc.active_task import set_active_task

    ctx = set_active_task(TASK_A)

    assert ctx.task_id == TASK_A
    assert ctx.work_order_id == WO_ID
    assert ctx.milestone_id == MILESTONE_ID
    assert ctx.project_id == PROJECT_ID
    assert ctx.set_at != ""


def test_set_active_task_raises_for_nonexistent_task_id(db_home, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(db_home / "state" / "active_task.json"))
    from core.sdlc.active_task import set_active_task

    with pytest.raises(ValueError, match="Task not found"):
        set_active_task("deadbeef-0000-0000-0000-000000000000")


def test_set_active_task_raises_if_parent_chain_broken(db_home, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(db_home / "state" / "active_task.json"))

    import unittest.mock as _mock

    broken_row = {
        "task_id": ORPHAN_TASK,
        "work_order_id": None,
        "project_id": None,
        "milestone_id": None,
    }

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, params=()):
            return _FakeCursor(broken_row)

    class _FakeCursor:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    import core.event_store.studio_db as _studio_db

    monkeypatch.setattr(_studio_db, "_connect", lambda *a, **kw: _FakeConn())

    from core.sdlc.active_task import set_active_task

    with pytest.raises(ValueError, match="no parent work order|SDLC chain"):
        set_active_task(ORPHAN_TASK)


def test_get_active_task_returns_context_after_set(db_home, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(db_home / "state" / "active_task.json"))
    from core.sdlc.active_task import get_active_task, set_active_task

    set_active_task(TASK_A)
    ctx = get_active_task()

    assert ctx is not None
    assert ctx.task_id == TASK_A
    assert ctx.work_order_id == WO_ID
    assert ctx.milestone_id == MILESTONE_ID
    assert ctx.project_id == PROJECT_ID


def test_get_active_task_returns_none_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "nonexistent_active_task.json"))
    from core.sdlc.active_task import get_active_task

    ctx = get_active_task()

    assert ctx is None


def test_get_active_task_returns_none_when_file_is_corrupt(tmp_path, monkeypatch):
    task_file = tmp_path / "active_task.json"
    task_file.write_text("this is not valid json {{{{", encoding="utf-8")
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(task_file))
    from core.sdlc.active_task import get_active_task

    ctx = get_active_task()

    assert ctx is None


def test_clear_active_task_removes_file(db_home, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    task_file = db_home / "state" / "active_task.json"
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(task_file))
    from core.sdlc.active_task import clear_active_task, set_active_task

    set_active_task(TASK_A)
    assert task_file.exists()

    removed = clear_active_task()

    assert removed is True
    assert not task_file.exists()


def test_clear_active_task_returns_false_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_such_file.json"))
    from core.sdlc.active_task import clear_active_task

    removed = clear_active_task()

    assert removed is False


def test_ds_active_task_path_env_override_is_honored(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    custom_path = tmp_path / "custom_dir" / "my_active_task.json"
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(custom_path))
    from core.sdlc.active_task import set_active_task

    set_active_task(TASK_A)

    assert custom_path.exists()
    data = json.loads(custom_path.read_text(encoding="utf-8"))
    assert data["task_id"] == TASK_A


def test_skill_invoked_emitter_populates_sdlc_trace_when_active_task_set(
    db_home, tmp_path, monkeypatch
):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(db_home / "state" / "active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from core.sdlc.active_task import set_active_task
    from core.skills.invocation import record_skill_invocation

    set_active_task(TASK_A)
    record_skill_invocation(
        specifier="ds-core:build",
        target=None,
        work_order_id=None,
        project_id=None,
        source_root=tmp_path,
        dream_studio_home=db_home,
    )

    events = _events_of_type(tmp_path / "spool-root", "skill.invoked")
    assert len(events) == 1
    trace = events[0]["trace"]
    assert trace["task_id"] == TASK_A
    assert trace["work_order_id"] == WO_ID
    assert trace["milestone_id"] == MILESTONE_ID
    assert trace["attribution_status"] == "fully_attributed"


def test_skill_invoked_emitter_emits_orphan_when_no_active_task(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "no_active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from core.skills.invocation import record_skill_invocation

    record_skill_invocation(
        specifier="ds-core:build",
        target=None,
        work_order_id=None,
        project_id=None,
        source_root=tmp_path,
        dream_studio_home=db_home,
    )

    events = _events_of_type(tmp_path / "spool-root", "skill.invoked")
    assert len(events) == 1
    trace = events[0]["trace"]
    assert trace["task_id"] is None
    assert trace["work_order_id"] is None
    assert trace["milestone_id"] is None
    assert trace["attribution_status"] == "orphan"


def test_task_completed_clears_active_task_if_completed_task_matches(
    db_home, tmp_path, monkeypatch
):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    task_file = db_home / "state" / "active_task.json"
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(task_file))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from core.sdlc.active_task import set_active_task
    from core.work_orders.mutations import mark_task_done

    set_active_task(TASK_A)
    assert task_file.exists()

    result = mark_task_done(
        work_order_id=WO_ID,
        task_id=TASK_A,
        source_root=tmp_path,
        dream_studio_home=db_home,
    )
    assert result["ok"] is True
    assert not task_file.exists()


def test_task_completed_does_not_clear_active_task_if_different_task(
    db_home, tmp_path, monkeypatch
):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    task_file = db_home / "state" / "active_task.json"
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(task_file))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from core.sdlc.active_task import set_active_task
    from core.work_orders.mutations import mark_task_done

    set_active_task(TASK_A)
    assert task_file.exists()

    result = mark_task_done(
        work_order_id=WO_ID,
        task_id=TASK_B,
        source_root=tmp_path,
        dream_studio_home=db_home,
    )
    assert result["ok"] is True
    assert task_file.exists()
    data = json.loads(task_file.read_text(encoding="utf-8"))
    assert data["task_id"] == TASK_A


def test_integration_set_active_then_invoke_skill_has_full_trace(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(db_home / "state" / "active_task.json"))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from core.sdlc.active_task import get_active_task, set_active_task
    from core.skills.invocation import record_skill_invocation

    ctx = set_active_task(TASK_B)
    assert ctx.task_id == TASK_B

    roundtrip = get_active_task()
    assert roundtrip is not None
    assert roundtrip.task_id == TASK_B

    record_skill_invocation(
        specifier="ds-quality:debug",
        target=None,
        work_order_id=None,
        project_id=None,
        source_root=tmp_path,
        dream_studio_home=db_home,
    )

    events = _events_of_type(tmp_path / "spool-root", "skill.invoked")
    assert len(events) == 1
    trace = events[0]["trace"]
    assert trace["task_id"] == TASK_B
    assert trace["work_order_id"] == WO_ID
    assert trace["project_id"] == PROJECT_ID
    assert trace["milestone_id"] == MILESTONE_ID
    assert trace["attribution_status"] == "fully_attributed"


def test_integration_complete_active_task_removes_active_task_json(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    task_file = db_home / "state" / "active_task.json"
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(task_file))
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    from core.sdlc.active_task import get_active_task, set_active_task
    from core.work_orders.mutations import mark_task_done

    set_active_task(TASK_A)
    assert get_active_task() is not None

    mark_task_done(
        work_order_id=WO_ID,
        task_id=TASK_A,
        source_root=tmp_path,
        dream_studio_home=db_home,
    )

    assert get_active_task() is None
    assert not task_file.exists()


def test_integration_cli_set_active_command(db_home, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(tmp_path / "active_task.json"))
    from interfaces.cli.ds import main

    exit_code = main(["task", "set-active", TASK_A])

    assert exit_code == 0
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["task_id"] == TASK_A
    assert output["work_order_id"] == WO_ID
    assert output["milestone_id"] == MILESTONE_ID
    assert output["project_id"] == PROJECT_ID


def test_integration_cli_active_command(db_home, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    task_file = tmp_path / "active_task.json"
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(task_file))
    from core.sdlc.active_task import set_active_task
    from interfaces.cli.ds import main

    set_active_task(TASK_B)

    exit_code = main(["task", "active"])

    assert exit_code == 0
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["active_task"]["task_id"] == TASK_B
    assert output["active_task"]["work_order_id"] == WO_ID


def test_integration_cli_clear_active_command(db_home, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_home / "state" / "studio.db"))
    task_file = tmp_path / "active_task.json"
    monkeypatch.setenv("DS_ACTIVE_TASK_PATH", str(task_file))
    from core.sdlc.active_task import set_active_task
    from interfaces.cli.ds import main

    set_active_task(TASK_A)
    assert task_file.exists()

    exit_code = main(["task", "clear-active"])

    assert exit_code == 0
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["ok"] is True
    assert output["cleared"] is True
    assert not task_file.exists()
