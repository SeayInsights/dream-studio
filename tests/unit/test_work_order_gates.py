"""Slice 6b: ds work-order close / block / unblock command tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from interfaces.cli.ds import main

PROJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
WO_UI = "cccccccc-cccc-cccc-cccc-cccccccccccc"  # ui_component: pre=design_brief_locked, post=design_critique
WO_API = "dddddddd-dddd-dddd-dddd-dddddddddddd"  # api_endpoint: pre=api_contract_exists, post=security_scan
WO_GAME = (
    "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"  # game_mechanic: pre=spec_approved, post=game_validate
)
WO_DOCS = "ffffffff-ffff-ffff-ffff-ffffffffffff"  # documentation: pre=NULL, post=NULL
NOW = "2026-05-16T00:00:00+00:00"


@pytest.fixture
def db_home(tmp_path):
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True)
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO ds_projects VALUES (?, 'Test Project', 'desc', 'active', ?, ?)",
            (PROJECT_ID, NOW, NOW),
        )
        for wo_id, wo_type in [
            (WO_UI, "ui_component"),
            (WO_API, "api_endpoint"),
            (WO_GAME, "game_mechanic"),
            (WO_DOCS, "documentation"),
        ]:
            conn.execute(
                "INSERT INTO ds_work_orders"
                " (work_order_id, project_id, milestone_id, title, description, status,"
                " work_order_type, created_at, updated_at)"
                " VALUES (?, ?, NULL, 'Test WO', NULL, 'in_progress', ?, ?, ?)",
                (wo_id, PROJECT_ID, wo_type, NOW, NOW),
            )
        conn.commit()
    finally:
        conn.close()
    return tmp_path


def _close(db_home, tmp_path, monkeypatch, work_order_id, extra=None):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    argv = [
        "--home",
        str(db_home),
        "work-order",
        "close",
        work_order_id,
        "--planning-root",
        str(tmp_path / ".planning"),
    ]
    if extra:
        argv.extend(extra)
    return main(argv)


def _block(db_home, tmp_path, monkeypatch, work_order_id, reason):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    return main(
        [
            "--home",
            str(db_home),
            "work-order",
            "block",
            work_order_id,
            "--reason",
            reason,
        ]
    )


def _unblock(db_home, tmp_path, monkeypatch, work_order_id):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    return main(["--home", str(db_home), "work-order", "unblock", work_order_id])


def _add_design_brief(db_home):
    db_path = db_home / "state" / "studio.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO ds_design_briefs"
            " (brief_id, project_id, status, created_at, updated_at)"
            " VALUES ('brief-gate-test-001', ?, 'locked', ?, ?)",
            (PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()


# ── close: error / gate failure paths ────────────────────────────────────────


def test_close_exits_1_when_work_order_not_found(db_home, tmp_path, monkeypatch):
    rc = _close(db_home, tmp_path, monkeypatch, "00000000-0000-0000-0000-000000000000")
    assert rc == 1


def test_close_exits_1_when_pre_gate_fails(db_home, tmp_path, monkeypatch, capsys):
    # WO_UI pre gate = design_brief_locked; no brief inserted
    rc = _close(db_home, tmp_path, monkeypatch, WO_UI)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert any("design_brief_locked" in f for f in out["failures"])


def test_close_exits_1_when_post_gate_fails(db_home, tmp_path, monkeypatch, capsys):
    # Insert design brief so pre gate passes; leave design-critique.md absent
    _add_design_brief(db_home)
    rc = _close(db_home, tmp_path, monkeypatch, WO_UI)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert any("design_critique" in f for f in out["failures"])


# ── close: success paths ──────────────────────────────────────────────────────


def test_close_succeeds_when_all_gates_pass(db_home, tmp_path, monkeypatch, capsys):
    _add_design_brief(db_home)
    wo_dir = tmp_path / ".planning" / "work-orders" / WO_UI
    wo_dir.mkdir(parents=True, exist_ok=True)
    (wo_dir / "design-critique.md").write_text("Score: 4/5\nLooks good.", encoding="utf-8")
    (wo_dir / "lint-results.md").write_text("PASSED — no violations\n", encoding="utf-8")
    rc = _close(db_home, tmp_path, monkeypatch, WO_UI)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["status"] == "complete"


def test_close_updates_status_to_complete(db_home, tmp_path, monkeypatch):
    # WO_DOCS has NULL gates — closes without any artifacts
    rc = _close(db_home, tmp_path, monkeypatch, WO_DOCS)
    assert rc == 0
    conn = sqlite3.connect(str(db_home / "state" / "studio.db"))
    try:
        status = conn.execute(
            "SELECT status FROM ds_work_orders WHERE work_order_id = ?", (WO_DOCS,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert status == "complete"


def test_close_succeeds_when_gates_are_null(db_home, tmp_path, monkeypatch, capsys):
    rc = _close(db_home, tmp_path, monkeypatch, WO_DOCS)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True


def test_close_emits_work_order_closed_event(db_home, tmp_path, monkeypatch):
    spool_root = tmp_path / "spool-root"
    monkeypatch.setenv("DS_SPOOL_ROOT", str(spool_root))
    _close(db_home, tmp_path, monkeypatch, WO_DOCS)
    events = [
        json.loads(p.read_text(encoding="utf-8")) for p in (spool_root / "spool").glob("*.json")
    ]
    assert any(e["event_type"] == "work_order.closed" for e in events)


# ── close: --force paths ──────────────────────────────────────────────────────


def test_close_force_bypasses_failed_gates(db_home, tmp_path, monkeypatch, capsys):
    rc = _close(db_home, tmp_path, monkeypatch, WO_UI, extra=["--force"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["forced"] is True
    assert len(out["bypassed_gates"]) >= 1


def test_close_force_emits_gate_bypassed_events(db_home, tmp_path, monkeypatch):
    spool_root = tmp_path / "spool-root"
    monkeypatch.setenv("DS_SPOOL_ROOT", str(spool_root))
    main(
        [
            "--home",
            str(db_home),
            "work-order",
            "close",
            WO_UI,
            "--planning-root",
            str(tmp_path / ".planning"),
            "--force",
        ]
    )
    events = [
        json.loads(p.read_text(encoding="utf-8")) for p in (spool_root / "spool").glob("*.json")
    ]
    bypassed = [e for e in events if e["event_type"] == "gate.bypassed"]
    assert len(bypassed) >= 1


def test_close_force_prints_bypass_warning(db_home, tmp_path, monkeypatch, capsys):
    _close(db_home, tmp_path, monkeypatch, WO_UI, extra=["--force"])
    err = capsys.readouterr().err
    assert "[gate.bypassed] WARNING:" in err


# ── block ─────────────────────────────────────────────────────────────────────


def test_block_sets_status_and_reason(db_home, tmp_path, monkeypatch):
    rc = _block(db_home, tmp_path, monkeypatch, WO_UI, "waiting on design review")
    assert rc == 0
    conn = sqlite3.connect(str(db_home / "state" / "studio.db"))
    try:
        row = conn.execute(
            "SELECT status, block_reason FROM ds_work_orders WHERE work_order_id = ?", (WO_UI,)
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "blocked"
    assert row[1] == "waiting on design review"


def test_block_emits_work_order_blocked_event(db_home, tmp_path, monkeypatch):
    spool_root = tmp_path / "spool-root"
    monkeypatch.setenv("DS_SPOOL_ROOT", str(spool_root))
    _block(db_home, tmp_path, monkeypatch, WO_UI, "needs security review")
    events = [
        json.loads(p.read_text(encoding="utf-8")) for p in (spool_root / "spool").glob("*.json")
    ]
    assert any(e["event_type"] == "work_order.blocked" for e in events)


def test_block_exits_1_when_not_found(db_home, tmp_path, monkeypatch):
    rc = _block(db_home, tmp_path, monkeypatch, "00000000-0000-0000-0000-000000000000", "reason")
    assert rc == 1


# ── unblock ───────────────────────────────────────────────────────────────────


def test_unblock_restores_to_in_progress_and_clears_reason(db_home, tmp_path, monkeypatch):
    _block(db_home, tmp_path, monkeypatch, WO_UI, "temp block")
    rc = _unblock(db_home, tmp_path, monkeypatch, WO_UI)
    assert rc == 0
    conn = sqlite3.connect(str(db_home / "state" / "studio.db"))
    try:
        row = conn.execute(
            "SELECT status, block_reason FROM ds_work_orders WHERE work_order_id = ?", (WO_UI,)
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "in_progress"
    assert row[1] is None


def test_unblock_exits_1_when_not_found(db_home, tmp_path, monkeypatch):
    rc = _unblock(db_home, tmp_path, monkeypatch, "00000000-0000-0000-0000-000000000000")
    assert rc == 1
