"""Slice 6a: ds work-order start / list command tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from interfaces.cli.ds import main

REPO_ROOT = Path(__file__).resolve().parents[2]

PROJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PROJECT_ID_2 = "22222222-2222-2222-2222-222222222222"
MILESTONE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
WORK_ORDER_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
WORK_ORDER_ID_NULL_TYPE = "dddddddd-dddd-dddd-dddd-dddddddddddd"
WORK_ORDER_ID_BAD_TYPE = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
WORK_ORDER_ID_P2 = "ffffffff-ffff-ffff-ffff-ffffffffffff"
NOW = "2026-05-16T00:00:00+00:00"


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
            "INSERT INTO business_projects VALUES (?, 'Other Project', 'desc2', 'active', ?, ?)",
            (PROJECT_ID_2, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_milestones"
            " (milestone_id, project_id, title, description, due_date, status, created_at, updated_at)"
            " VALUES (?, ?, 'Milestone One', NULL, NULL, 'active', ?, ?)",
            (MILESTONE_ID, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Build login form', NULL, 'created', 'ui_component', ?, ?)",
            (WORK_ORDER_ID, PROJECT_ID, MILESTONE_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " created_at, updated_at)"
            " VALUES (?, ?, NULL, 'Typeless order', NULL, 'created', ?, ?)",
            (WORK_ORDER_ID_NULL_TYPE, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'Bad type order', NULL, 'created', 'nonexistent_type', ?, ?)",
            (WORK_ORDER_ID_BAD_TYPE, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'Other project order', NULL, 'created', 'api_endpoint', ?, ?)",
            (WORK_ORDER_ID_P2, PROJECT_ID_2, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, status, created_at, updated_at)"
            " VALUES ('task-0001', ?, ?, 'Write HTML', 'pending', ?, ?)",
            (WORK_ORDER_ID, PROJECT_ID, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_tasks"
            " (task_id, work_order_id, project_id, title, status, created_at, updated_at)"
            " VALUES ('task-0002', ?, ?, 'Already done', 'complete', ?, ?)",
            (WORK_ORDER_ID, PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return tmp_path


def _start(db_home, tmp_path, monkeypatch, work_order_id=WORK_ORDER_ID):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    return main(
        [
            "--home",
            str(db_home),
            "work-order",
            "start",
            work_order_id,
            "--planning-root",
            str(tmp_path / ".planning"),
        ]
    )


def _list(db_home, monkeypatch, extra=None):
    argv = ["--home", str(db_home), "work-order", "list"]
    if extra:
        argv.extend(extra)
    return main(argv)


# ── start: error paths ────────────────────────────────────────────────────────


def test_start_exits_1_when_work_order_not_found(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(
        [
            "--home",
            str(db_home),
            "work-order",
            "start",
            "00000000-0000-0000-0000-000000000000",
            "--planning-root",
            str(tmp_path / ".planning"),
        ]
    )
    assert rc == 1


def test_start_exits_1_when_type_is_null(db_home, tmp_path, monkeypatch):
    rc = _start(db_home, tmp_path, monkeypatch, work_order_id=WORK_ORDER_ID_NULL_TYPE)
    assert rc == 1


def test_start_exits_1_when_type_is_unrecognized(db_home, tmp_path, monkeypatch):
    rc = _start(db_home, tmp_path, monkeypatch, work_order_id=WORK_ORDER_ID_BAD_TYPE)
    assert rc == 1


# ── start: success path ───────────────────────────────────────────────────────


def test_start_writes_context_md_to_planning_root(db_home, tmp_path, monkeypatch):
    rc = _start(db_home, tmp_path, monkeypatch)
    assert rc == 0
    context_path = tmp_path / ".planning" / "work-orders" / WORK_ORDER_ID / "context.md"
    assert context_path.is_file()


def test_start_context_md_contains_work_order_fields(db_home, tmp_path, monkeypatch):
    _start(db_home, tmp_path, monkeypatch)
    text = (tmp_path / ".planning" / "work-orders" / WORK_ORDER_ID / "context.md").read_text()
    assert WORK_ORDER_ID in text
    assert "Build login form" in text
    assert "ui_component" in text
    assert "Test Project" in text
    assert PROJECT_ID in text


def test_start_context_md_contains_gates(db_home, tmp_path, monkeypatch):
    _start(db_home, tmp_path, monkeypatch)
    text = (tmp_path / ".planning" / "work-orders" / WORK_ORDER_ID / "context.md").read_text()
    assert "## Gates" in text
    assert "design_brief_locked" in text
    assert "fullstack:frontend" in text
    assert "design_critique" in text


def test_start_context_md_includes_pending_tasks_only(db_home, tmp_path, monkeypatch):
    _start(db_home, tmp_path, monkeypatch)
    text = (tmp_path / ".planning" / "work-orders" / WORK_ORDER_ID / "context.md").read_text()
    assert "Write HTML" in text
    assert "Already done" not in text


def test_start_updates_status_to_in_progress(db_home, tmp_path, monkeypatch):
    _start(db_home, tmp_path, monkeypatch)
    conn = sqlite3.connect(str(db_home / "state" / "studio.db"))
    try:
        status = conn.execute(
            "SELECT status FROM business_work_orders WHERE work_order_id = ?",
            (WORK_ORDER_ID,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert status == "in_progress"


def test_start_emits_spool_event_json(db_home, tmp_path, monkeypatch):
    spool_root = tmp_path / "spool-root"
    monkeypatch.setenv("DS_SPOOL_ROOT", str(spool_root))
    main(
        [
            "--home",
            str(db_home),
            "work-order",
            "start",
            WORK_ORDER_ID,
            "--planning-root",
            str(tmp_path / ".planning"),
        ]
    )
    events = list((spool_root / "spool").glob("*.json"))
    assert len(events) == 1
    event = json.loads(events[0].read_text(encoding="utf-8"))
    assert event["event_type"] == "work_order.started"
    assert event["payload"]["work_order_id"] == WORK_ORDER_ID


def test_start_spool_failure_is_non_blocking(db_home, tmp_path, monkeypatch):
    import spool.writer as _spool

    def _fail(envelope, root=None):
        raise OSError("disk full")

    monkeypatch.setattr(_spool, "write_event", _fail)
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(
        [
            "--home",
            str(db_home),
            "work-order",
            "start",
            WORK_ORDER_ID,
            "--planning-root",
            str(tmp_path / ".planning"),
        ]
    )
    assert rc == 0


# ── list ──────────────────────────────────────────────────────────────────────


def test_list_returns_all_work_orders(db_home, tmp_path, monkeypatch, capsys):
    rc = _list(db_home, monkeypatch)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    ids = {wo["id"] for wo in out["work_orders"]}
    assert WORK_ORDER_ID in ids
    assert all(len(wo["id"]) == 36 for wo in out["work_orders"])


def test_list_filters_by_project_id(db_home, tmp_path, monkeypatch, capsys):
    rc = _list(db_home, monkeypatch, extra=["--project", PROJECT_ID])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert all(wo["id"] != WORK_ORDER_ID_P2 for wo in out["work_orders"])
    assert any(wo["id"] == WORK_ORDER_ID for wo in out["work_orders"])


def test_list_filters_by_status(db_home, tmp_path, monkeypatch, capsys):
    rc = _list(db_home, monkeypatch, extra=["--status", "created"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert all(wo["status"] == "created" for wo in out["work_orders"])

    rc2 = _list(db_home, monkeypatch, extra=["--status", "closed"])
    assert rc2 == 0
    out2 = json.loads(capsys.readouterr().out)
    assert out2["work_orders"] == []


# ── WS 8a-3: enforcement block in context.md ─────────────────────────────────


def test_context_md_contains_enforcement_section(db_home, tmp_path, monkeypatch):
    _start(db_home, tmp_path, monkeypatch)
    text = (tmp_path / ".planning" / "work-orders" / WORK_ORDER_ID / "context.md").read_text()
    assert "## DREAM STUDIO ENFORCEMENT" in text


def test_context_md_enforcement_contains_module_boundary(db_home, tmp_path, monkeypatch):
    _start(db_home, tmp_path, monkeypatch)
    text = (tmp_path / ".planning" / "work-orders" / WORK_ORDER_ID / "context.md").read_text()
    # module_boundary is represented by the work order type_id (e.g. "ui_component")
    assert "ui_component" in text


def test_context_md_enforcement_contains_work_order_id(db_home, tmp_path, monkeypatch):
    _start(db_home, tmp_path, monkeypatch)
    text = (tmp_path / ".planning" / "work-orders" / WORK_ORDER_ID / "context.md").read_text()
    enforcement_start = text.index("## DREAM STUDIO ENFORCEMENT")
    section = text[enforcement_start:]
    assert WORK_ORDER_ID in section


def test_context_md_enforcement_contains_task_done_skill(db_home, tmp_path, monkeypatch):
    _start(db_home, tmp_path, monkeypatch)
    text = (tmp_path / ".planning" / "work-orders" / WORK_ORDER_ID / "context.md").read_text()
    assert "ds-workorder:execute" in text


def test_context_md_enforcement_contains_work_order_close_skill(db_home, tmp_path, monkeypatch):
    _start(db_home, tmp_path, monkeypatch)
    text = (tmp_path / ".planning" / "work-orders" / WORK_ORDER_ID / "context.md").read_text()
    assert "ds-workorder:close" in text
