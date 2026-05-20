"""Slice 7e: milestone close workflow, list, status, and skill invoke --milestone."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from interfaces.cli.ds import main

PROJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MILESTONE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
WO_UI = "cccccccc-cccc-cccc-cccc-cccccccccccc"
WO_API = "dddddddd-dddd-dddd-dddd-dddddddddddd"
NOW = "2026-05-16T00:00:00+00:00"

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── fixtures ──────────────────────────────────────────────────────────────────


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
        conn.execute(
            "INSERT INTO ds_milestones"
            " (milestone_id, project_id, title, description, due_date, status, created_at, updated_at)"
            " VALUES (?, ?, 'Alpha Release', NULL, NULL, 'active', ?, ?)",
            (MILESTONE_ID, PROJECT_ID, NOW, NOW),
        )
        # UI work order (ui_component)
        conn.execute(
            "INSERT INTO ds_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Build hero', NULL, 'complete', 'ui_component', ?, ?)",
            (WO_UI, PROJECT_ID, MILESTONE_ID, NOW, NOW),
        )
        # API work order (api_endpoint)
        conn.execute(
            "INSERT INTO ds_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Auth endpoint', NULL, 'complete', 'api_endpoint', ?, ?)",
            (WO_API, PROJECT_ID, MILESTONE_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return tmp_path


def _db_path(db_home: Path) -> Path:
    return db_home / "state" / "studio.db"


def _ms_dir(tmp_path: Path) -> Path:
    return tmp_path / ".planning" / "milestones" / MILESTONE_ID


def _write_all_passing(tmp_path: Path) -> None:
    d = _ms_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "design-audit.md").write_text("Score: 3/4\nLooks solid.\n", encoding="utf-8")
    (d / "security-audit.md").write_text("All clear.\n", encoding="utf-8")
    (d / "harden-results.md").write_text("PASSED\n", encoding="utf-8")
    (d / "cwv-results.md").write_text("PASSED\n", encoding="utf-8")


def _close(db_home, tmp_path, monkeypatch, extra=None):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    argv = [
        "--home",
        str(db_home),
        "milestone",
        "close",
        MILESTONE_ID,
        "--planning-root",
        str(tmp_path / ".planning"),
    ]
    if extra:
        argv.extend(extra)
    return main(argv)


# ── 1. close fails when work orders are not all completed ─────────────────────


def test_close_fails_when_work_orders_not_all_completed(db_home, tmp_path, monkeypatch, capsys):
    conn = sqlite3.connect(str(_db_path(db_home)))
    try:
        conn.execute(
            "UPDATE ds_work_orders SET status = 'in_progress' WHERE work_order_id = ?",
            (WO_UI,),
        )
        conn.commit()
    finally:
        conn.close()
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "open_work_orders" in out
    assert any(w["work_order_id"] == WO_UI for w in out["open_work_orders"])


# ── 2. close fails when design-audit.md is missing ───────────────────────────


def test_close_fails_when_design_audit_missing(db_home, tmp_path, monkeypatch, capsys):
    d = _ms_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    # provide security, harden, cwv but NOT design-audit
    (d / "security-audit.md").write_text("clear\n", encoding="utf-8")
    (d / "harden-results.md").write_text("PASSED\n", encoding="utf-8")
    (d / "cwv-results.md").write_text("PASSED\n", encoding="utf-8")
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert any("Design audit required" in f for f in out["failures"])


# ── 3. close fails when security-audit.md has BLOCKED ────────────────────────


def test_close_fails_when_security_audit_has_blocked(db_home, tmp_path, monkeypatch, capsys):
    d = _ms_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "design-audit.md").write_text("Score: 3/4\n", encoding="utf-8")
    (d / "security-audit.md").write_text("BLOCKED — critical finding\n", encoding="utf-8")
    (d / "harden-results.md").write_text("PASSED\n", encoding="utf-8")
    (d / "cwv-results.md").write_text("PASSED\n", encoding="utf-8")
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert any("BLOCKED" in f for f in out["failures"])


# ── 4. close fails when harden-results.md missing ────────────────────────────


def test_close_fails_when_harden_results_missing(db_home, tmp_path, monkeypatch, capsys):
    d = _ms_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "design-audit.md").write_text("Score: 4/4\n", encoding="utf-8")
    (d / "security-audit.md").write_text("clear\n", encoding="utf-8")
    (d / "cwv-results.md").write_text("PASSED\n", encoding="utf-8")
    # no harden-results.md
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert any("Hardening check required" in f for f in out["failures"])


# ── 5. close requires cwv-results.md for UI milestones ───────────────────────


def test_close_requires_cwv_for_ui_milestone(db_home, tmp_path, monkeypatch, capsys):
    d = _ms_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "design-audit.md").write_text("Score: 3/4\n", encoding="utf-8")
    (d / "security-audit.md").write_text("clear\n", encoding="utf-8")
    (d / "harden-results.md").write_text("PASSED\n", encoding="utf-8")
    # no cwv-results.md — but milestone has ui_component WO
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert any("Core Web Vitals" in f for f in out["failures"])


# ── 6. close does NOT require cwv for non-UI milestones ──────────────────────


def test_close_does_not_require_cwv_for_non_ui_milestone(db_home, tmp_path, monkeypatch, capsys):
    # Remove the ui_component WO so milestone is non-UI
    conn = sqlite3.connect(str(_db_path(db_home)))
    try:
        conn.execute(
            "UPDATE ds_work_orders SET work_order_type = 'api_endpoint' WHERE work_order_id = ?",
            (WO_UI,),
        )
        conn.commit()
    finally:
        conn.close()
    d = _ms_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "design-audit.md").write_text("Score: 3/4\n", encoding="utf-8")
    (d / "security-audit.md").write_text("clear\n", encoding="utf-8")
    (d / "harden-results.md").write_text("PASSED\n", encoding="utf-8")
    # no cwv-results.md — should not be required
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 0


# ── 7. close passes when all artifact files present and passing ───────────────


def test_close_passes_when_all_artifacts_pass(db_home, tmp_path, monkeypatch, capsys):
    _write_all_passing(tmp_path)
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 0
    out = capsys.readouterr().out
    assert f"Milestone {MILESTONE_ID} closed." in out


# ── 8. close --force bypasses and emits gate.bypassed ────────────────────────


def test_close_force_bypasses_and_warns(db_home, tmp_path, monkeypatch, capsys):
    # Only design-audit is present — rest are missing → would normally fail
    d = _ms_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "design-audit.md").write_text("Score: 3/4\n", encoding="utf-8")
    rc = _close(db_home, tmp_path, monkeypatch, extra=["--force"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "gate.bypassed" in err or "WARNING" in err


# ── 9. close emits milestone.completed spool event ───────────────────────────


def test_close_emits_milestone_completed_event(db_home, tmp_path, monkeypatch):
    _write_all_passing(tmp_path)
    spool_root = tmp_path / "spool-root"
    monkeypatch.setenv("DS_SPOOL_ROOT", str(spool_root))
    _close(db_home, tmp_path, monkeypatch)
    events = list(spool_root.rglob("*.json")) if spool_root.exists() else []
    contents = [p.read_text(encoding="utf-8") for p in events]
    assert any("milestone.completed" in c for c in contents)


# ── 10. milestone list shows correct work order counts ───────────────────────


def test_milestone_list_shows_correct_work_order_counts(db_home, capsys):
    rc = main(["--home", str(db_home), "milestone", "list", PROJECT_ID])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    ms = next((m for m in data["milestones"] if MILESTONE_ID.startswith(m["milestone_id"])), None)
    assert ms is not None
    assert ms["work_order_count"] == 2
    assert ms["status"] == "active"


# ── 11. milestone status shows open gate checks ───────────────────────────────


def test_milestone_status_shows_open_gate_checks(db_home, tmp_path, capsys):
    rc = main(
        [
            "--home",
            str(db_home),
            "milestone",
            "status",
            MILESTONE_ID,
            "--planning-root",
            str(tmp_path / ".planning"),
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    # No artifacts written → all checks open
    checks = data["open_gate_checks"]
    assert "design_audit" in checks
    assert "security_audit" in checks
    assert "harden_results" in checks
    assert "cwv_results" in checks  # has ui_component WO


# ── 12. skill invoke --milestone writes to milestones directory ───────────────


def test_skill_invoke_milestone_writes_to_milestones_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    planning_root = tmp_path / ".planning"
    rc = main(
        [
            "skill",
            "invoke",
            "website:critique",
            "--milestone",
            MILESTONE_ID,
            "--planning-root",
            str(planning_root),
        ]
    )
    assert rc == 0
    artifact = planning_root / "milestones" / MILESTONE_ID / "design-critique.md"
    assert artifact.is_file(), "design-critique.md not written to milestones dir"
    content = artifact.read_text(encoding="utf-8")
    assert "Score: [PENDING]/4" in content


# ── 13. --milestone and --work-order are mutually exclusive ───────────────────


def test_milestone_and_work_order_are_mutually_exclusive(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "skill",
                "invoke",
                "website:critique",
                "--work-order",
                "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "--milestone",
                MILESTONE_ID,
            ]
        )
    assert exc_info.value.code != 0
