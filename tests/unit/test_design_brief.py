"""Slice 7a: ds_design_briefs table, CLI commands, gate check, and work-order start integration."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from interfaces.cli.ds import main

PROJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BRIEF_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
WO_UI_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
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
            "INSERT INTO ds_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'Build dashboard widget', NULL, 'open', 'ui_component', ?, ?)",
            (WO_UI_ID, PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return tmp_path


def _db_path(db_home: Path) -> Path:
    return db_home / "state" / "studio.db"


def _insert_brief(
    db_home: Path, *, status: str = "draft", design_system: str | None = None
) -> None:
    conn = sqlite3.connect(str(_db_path(db_home)))
    try:
        conn.execute(
            "INSERT INTO ds_design_briefs"
            " (brief_id, project_id, status, purpose, audience, tone,"
            "  design_system, font_pairing, brand_tokens, raw_output, created_at, updated_at)"
            " VALUES (?, ?, ?, 'Build a fast UI', 'engineers', 'professional',"
            "         ?, NULL, NULL, NULL, ?, ?)",
            (BRIEF_ID, PROJECT_ID, status, design_system, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()


# ── 1. migration: ds_design_briefs table exists after bootstrap ───────────────


def test_migration_053_creates_ds_design_briefs_table(db_home):
    conn = sqlite3.connect(str(_db_path(db_home)))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ds_design_briefs'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "ds_design_briefs table not found after bootstrap"


# ── 2. ds design-brief create inserts a draft row ────────────────────────────


def test_design_brief_create_inserts_draft_row(db_home, capsys):
    rc = main(["--home", str(db_home), "design-brief", "create", PROJECT_ID])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Draft brief created:" in out

    conn = sqlite3.connect(str(_db_path(db_home)))
    try:
        row = conn.execute(
            "SELECT status FROM ds_design_briefs WHERE project_id = ?", (PROJECT_ID,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "draft"


# ── 2b. A2.5: direct-call create_design_brief returns a structured dict ──────


def test_create_design_brief_returns_dict_with_draft_status(db_home):
    """A2.5 extraction: ``create_design_brief`` is now directly callable
    and returns a result dict; the CLI wrapper only formats output."""
    from core.design_briefs.mutations import create_design_brief

    result = create_design_brief(
        project_id=PROJECT_ID,
        source_root=REPO_ROOT,
        dream_studio_home=db_home,
    )
    assert result["ok"] is True
    assert result["project_id"] == PROJECT_ID
    assert result["status"] == "draft"
    assert result["brief_id"]
    assert "created_at" in result
    assert "next_step" in result
    assert "website:discover" in result["next_step"]


def test_create_design_brief_inserts_row_in_db(db_home):
    from core.design_briefs.mutations import create_design_brief

    result = create_design_brief(
        project_id=PROJECT_ID,
        source_root=REPO_ROOT,
        dream_studio_home=db_home,
    )
    conn = sqlite3.connect(str(_db_path(db_home)))
    try:
        row = conn.execute(
            "SELECT brief_id, status FROM ds_design_briefs WHERE project_id = ?",
            (PROJECT_ID,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == result["brief_id"]
    assert row[1] == "draft"


def test_create_design_brief_each_call_produces_distinct_brief_id(db_home):
    from core.design_briefs.mutations import create_design_brief

    r1 = create_design_brief(
        project_id=PROJECT_ID, source_root=REPO_ROOT, dream_studio_home=db_home
    )
    r2 = create_design_brief(
        project_id=PROJECT_ID, source_root=REPO_ROOT, dream_studio_home=db_home
    )
    assert r1["brief_id"] != r2["brief_id"]


# ── 3. ds design-brief show prints brief fields ───────────────────────────────


def test_design_brief_show_prints_brief_fields(db_home, capsys):
    _insert_brief(db_home, status="draft")
    rc = main(["--home", str(db_home), "design-brief", "show", PROJECT_ID])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    assert data["brief_id"] == BRIEF_ID
    assert "DRAFT" in data["status"]
    assert data["purpose"] == "Build a fast UI"


# ── 4. ds design-brief lock sets status to locked ────────────────────────────


def test_design_brief_lock_sets_status_locked(db_home, capsys):
    _insert_brief(db_home, status="draft")
    rc = main(["--home", str(db_home), "design-brief", "lock", BRIEF_ID])
    assert rc == 0
    out = capsys.readouterr().out
    assert f"Brief {BRIEF_ID} locked." in out

    conn = sqlite3.connect(str(_db_path(db_home)))
    try:
        row = conn.execute(
            "SELECT status FROM ds_design_briefs WHERE brief_id = ?", (BRIEF_ID,)
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "locked"


# ── 4b. A2.6: direct-call lock_design_brief returns a structured dict ────────


def test_lock_design_brief_returns_dict_on_success(db_home):
    """A2.6 extraction: ``lock_design_brief`` is directly callable and
    returns a result dict; the CLI wrapper only formats output."""
    from core.design_briefs.mutations import lock_design_brief

    _insert_brief(db_home, status="draft")
    result = lock_design_brief(
        brief_id=BRIEF_ID,
        source_root=REPO_ROOT,
        dream_studio_home=db_home,
    )
    assert result["ok"] is True
    assert result["brief_id"] == BRIEF_ID
    assert result["status"] == "locked"
    assert "locked_at" in result


def test_lock_design_brief_updates_db_status(db_home):
    from core.design_briefs.mutations import lock_design_brief

    _insert_brief(db_home, status="draft")
    lock_design_brief(
        brief_id=BRIEF_ID,
        source_root=REPO_ROOT,
        dream_studio_home=db_home,
    )
    conn = sqlite3.connect(str(_db_path(db_home)))
    try:
        row = conn.execute(
            "SELECT status FROM ds_design_briefs WHERE brief_id = ?", (BRIEF_ID,)
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "locked"


def test_lock_design_brief_returns_error_for_unknown_brief(db_home):
    from core.design_briefs.mutations import lock_design_brief

    result = lock_design_brief(
        brief_id="does-not-exist",
        source_root=REPO_ROOT,
        dream_studio_home=db_home,
    )
    assert result["ok"] is False
    assert "not found" in result["error"]
    assert "does-not-exist" in result["error"]


def test_design_brief_lock_cli_returns_1_on_unknown_brief(db_home, capsys):
    """CLI surface: missing brief → exit 1 + JSON error to stdout."""
    rc = main(["--home", str(db_home), "design-brief", "lock", "missing-brief-id"])
    assert rc == 1
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["ok"] is False
    assert "not found" in data["error"]


# ── 5. ds design-brief update changes field on draft ─────────────────────────


def test_design_brief_update_changes_field_on_draft(db_home, capsys):
    _insert_brief(db_home, status="draft")
    rc = main(
        [
            "--home",
            str(db_home),
            "design-brief",
            "update",
            BRIEF_ID,
            "--field",
            "tone",
            "--value",
            "playful",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    assert data["field"] == "tone"
    assert data["value"] == "playful"

    conn = sqlite3.connect(str(_db_path(db_home)))
    try:
        row = conn.execute(
            "SELECT tone FROM ds_design_briefs WHERE brief_id = ?", (BRIEF_ID,)
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "playful"


# ── 6. ds design-brief update exits 1 on locked brief ────────────────────────


def test_design_brief_update_exits_1_on_locked_brief(db_home, capsys):
    _insert_brief(db_home, status="locked")
    rc = main(
        [
            "--home",
            str(db_home),
            "design-brief",
            "update",
            BRIEF_ID,
            "--field",
            "tone",
            "--value",
            "formal",
        ]
    )
    assert rc == 1
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is False
    assert "locked" in data["error"].lower()


# ── 7. ds design-brief set-system accepts valid system ───────────────────────


def test_design_brief_set_system_accepts_valid_system(db_home, capsys):
    _insert_brief(db_home, status="draft")
    rc = main(
        [
            "--home",
            str(db_home),
            "design-brief",
            "set-system",
            BRIEF_ID,
            "tech-minimal",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    assert data["design_system"] == "tech-minimal"

    conn = sqlite3.connect(str(_db_path(db_home)))
    try:
        row = conn.execute(
            "SELECT design_system FROM ds_design_briefs WHERE brief_id = ?", (BRIEF_ID,)
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "tech-minimal"


# ── 8. ds design-brief set-system rejects invalid system ─────────────────────


def test_design_brief_set_system_rejects_invalid_system(db_home, capsys):
    _insert_brief(db_home, status="draft")
    rc = main(
        [
            "--home",
            str(db_home),
            "design-brief",
            "set-system",
            BRIEF_ID,
            "nonexistent-system",
        ]
    )
    assert rc == 1
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is False
    assert "Invalid design system" in data["error"]


# ── 9. ds design-brief set-system exits 1 on locked brief ────────────────────


def test_design_brief_set_system_exits_1_on_locked_brief(db_home, capsys):
    _insert_brief(db_home, status="locked")
    rc = main(
        [
            "--home",
            str(db_home),
            "design-brief",
            "set-system",
            BRIEF_ID,
            "editorial-modern",
        ]
    )
    assert rc == 1
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is False
    assert "locked" in data["error"].lower()


# ── 10. gate check passes when locked brief exists ───────────────────────────


def test_gate_check_design_brief_locked_passes_when_locked(db_home, tmp_path, monkeypatch, capsys):
    _insert_brief(db_home, status="locked")
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(
        [
            "--home",
            str(db_home),
            "work-order",
            "close",
            WO_UI_ID,
            "--planning-root",
            str(tmp_path / ".planning"),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    # Gate passes — failure should not mention design_brief_locked
    failures = out.get("failures", [])
    assert not any("design_brief_locked" in f for f in failures)


# ── 11. gate check fails when no brief ───────────────────────────────────────


def test_gate_check_design_brief_locked_fails_when_no_brief(db_home, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(
        [
            "--home",
            str(db_home),
            "work-order",
            "close",
            WO_UI_ID,
            "--planning-root",
            str(tmp_path / ".planning"),
        ]
    )
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert any("design_brief_locked" in f for f in out["failures"])


# ── 12. gate check fails when brief is draft (not locked) ────────────────────


def test_gate_check_design_brief_locked_fails_when_draft(db_home, tmp_path, monkeypatch, capsys):
    _insert_brief(db_home, status="draft")
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(
        [
            "--home",
            str(db_home),
            "work-order",
            "close",
            WO_UI_ID,
            "--planning-root",
            str(tmp_path / ".planning"),
        ]
    )
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert any("design_brief_locked" in f for f in out["failures"])


# ── 13. work-order start includes design brief section when locked ────────────


def test_work_order_start_includes_design_brief_section(db_home, tmp_path, monkeypatch):
    _insert_brief(db_home, status="locked")
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(
        [
            "--home",
            str(db_home),
            "work-order",
            "start",
            WO_UI_ID,
            "--planning-root",
            str(tmp_path / ".planning"),
        ]
    )
    assert rc == 0
    context_path = tmp_path / ".planning" / "work-orders" / WO_UI_ID / "context.md"
    assert context_path.exists()
    content = context_path.read_text(encoding="utf-8")
    assert "## Design Brief" in content
    assert "Build a fast UI" in content


# ── 14. work-order start includes design system section when system is set ────


def test_work_order_start_includes_design_system_section(db_home, tmp_path, monkeypatch):
    _insert_brief(db_home, status="locked", design_system="tech-minimal")
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(
        [
            "--home",
            str(db_home),
            "work-order",
            "start",
            WO_UI_ID,
            "--planning-root",
            str(tmp_path / ".planning"),
        ]
    )
    assert rc == 0
    context_path = tmp_path / ".planning" / "work-orders" / WO_UI_ID / "context.md"
    content = context_path.read_text(encoding="utf-8")
    assert "## Design System" in content
    assert "tech-minimal" in content
    assert "canonical/skills/domains/design-systems/tech-minimal/" in content


# ── 15. work-order start warns when no brief for UI type ─────────────────────


def test_work_order_start_warns_when_no_brief_for_ui_type(db_home, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    rc = main(
        [
            "--home",
            str(db_home),
            "work-order",
            "start",
            WO_UI_ID,
            "--planning-root",
            str(tmp_path / ".planning"),
        ]
    )
    assert rc == 0
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "No locked design brief" in err

    context_path = tmp_path / ".planning" / "work-orders" / WO_UI_ID / "context.md"
    assert context_path.exists()
    content = context_path.read_text(encoding="utf-8")
    assert "WARNING" in content
