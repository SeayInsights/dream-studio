"""Slice 7c+7d: anti_slop_passed gate, pipe-separated gates, design_critique thresholds,
skill invoke artifact writes, and migration 054 gate value update."""

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
            " VALUES (?, ?, NULL, 'Build hero component', NULL, 'open', 'ui_component', ?, ?)",
            (WO_UI_ID, PROJECT_ID, NOW, NOW),
        )
        # Locked design brief so the pre_build_gate (design_brief_locked) always passes
        conn.execute(
            "INSERT INTO ds_design_briefs"
            " (brief_id, project_id, status, created_at, updated_at)"
            " VALUES (?, ?, 'locked', ?, ?)",
            (BRIEF_ID, PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return tmp_path


def _db_path(db_home: Path) -> Path:
    return db_home / "state" / "studio.db"


def _write_critique(tmp_path: Path, score_str: str) -> None:
    d = tmp_path / ".planning" / "work-orders" / WO_UI_ID
    d.mkdir(parents=True, exist_ok=True)
    (d / "design-critique.md").write_text(
        f"# Design Critique\nScore: {score_str}\n", encoding="utf-8"
    )


def _write_lint(tmp_path: Path, content: str) -> None:
    d = tmp_path / ".planning" / "work-orders" / WO_UI_ID
    d.mkdir(parents=True, exist_ok=True)
    (d / "lint-results.md").write_text(content, encoding="utf-8")


def _close(db_home, tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    return main(
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


# ── 1. anti_slop_passed gate passes when lint-results.md contains PASSED ─────


def test_anti_slop_gate_passes_when_lint_results_contains_passed(
    db_home, tmp_path, monkeypatch, capsys
):
    _write_critique(tmp_path, "3/4")
    _write_lint(tmp_path, "Anti-Slop Lint: 0 violations\nResult: PASSED\n")
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True


# ── 2. anti_slop_passed gate fails when file missing ─────────────────────────


def test_anti_slop_gate_fails_when_file_missing(db_home, tmp_path, monkeypatch, capsys):
    _write_critique(tmp_path, "3/4")
    # no lint-results.md
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert any("anti_slop_passed" in f for f in out["failures"])
    assert any("lint-results.md not found" in f for f in out["failures"])


# ── 3. anti_slop_passed gate fails when file contains BLOCKED ────────────────


def test_anti_slop_gate_fails_when_file_contains_blocked(db_home, tmp_path, monkeypatch, capsys):
    _write_critique(tmp_path, "3/4")
    _write_lint(tmp_path, "BLOCKED: 2 critical violations found\n")
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert any("BLOCKED" in f for f in out["failures"])


# ── 4. pipe-separated gates: both must pass to close ─────────────────────────


def test_pipe_separated_gates_both_must_pass_to_close(db_home, tmp_path, monkeypatch, capsys):
    _write_critique(tmp_path, "4/4")
    _write_lint(tmp_path, "PASSED — no violations\n")
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["status"] == "complete"


# ── 5. pipe-separated gates: one fail blocks close ───────────────────────────


def test_pipe_separated_gates_one_fail_blocks_close(db_home, tmp_path, monkeypatch, capsys):
    # critique passes (Score: 3/4) but lint missing
    _write_critique(tmp_path, "3/4")
    # no lint-results.md → anti_slop_passed fails
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False


# ── 6. design_critique gate passes when Score: 3/4 ───────────────────────────


def test_design_critique_gate_passes_when_score_3(db_home, tmp_path, monkeypatch, capsys):
    _write_critique(tmp_path, "3/4")
    _write_lint(tmp_path, "PASSED\n")
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 0


# ── 7. design_critique gate passes when Score: 4/4 ───────────────────────────


def test_design_critique_gate_passes_when_score_4(db_home, tmp_path, monkeypatch, capsys):
    _write_critique(tmp_path, "4/4")
    _write_lint(tmp_path, "PASSED\n")
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 0


# ── 8. design_critique gate fails when Score: 2/4 ────────────────────────────


def test_design_critique_gate_fails_when_score_2(db_home, tmp_path, monkeypatch, capsys):
    _write_critique(tmp_path, "2/4")
    _write_lint(tmp_path, "PASSED\n")
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert any("design_critique" in f for f in out["failures"])


# ── 9. design_critique gate fails when Score: 1/4 ────────────────────────────


def test_design_critique_gate_fails_when_score_1(db_home, tmp_path, monkeypatch, capsys):
    _write_critique(tmp_path, "1/4")
    _write_lint(tmp_path, "PASSED\n")
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert any("design_critique" in f for f in out["failures"])


# ── 10. design_critique gate fails when Score: PENDING ───────────────────────


def test_design_critique_gate_fails_when_score_pending(db_home, tmp_path, monkeypatch, capsys):
    _write_critique(tmp_path, "[PENDING]/4")
    _write_lint(tmp_path, "PASSED\n")
    rc = _close(db_home, tmp_path, monkeypatch)
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert any("design_critique" in f for f in out["failures"])


# ── 11. skill invoke website:critique --work-order writes artifact template ───


def test_skill_invoke_critique_writes_artifact_template(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    planning_root = tmp_path / ".planning"
    rc = main(
        [
            "skill",
            "invoke",
            "website:critique",
            "--work-order",
            WO_UI_ID,
            "--planning-root",
            str(planning_root),
        ]
    )
    assert rc == 0
    artifact = planning_root / "work-orders" / WO_UI_ID / "design-critique.md"
    assert artifact.is_file(), "design-critique.md not written"
    content = artifact.read_text(encoding="utf-8")
    assert f"Work Order {WO_UI_ID}" in content
    assert "Score: [PENDING]/4" in content
    assert "Visual Hierarchy" in content
    assert "[PASS/FAIL]" in content


# ── 12. skill invoke security:scan --work-order writes artifact template ──────


def test_skill_invoke_security_scan_writes_artifact_template(tmp_path, monkeypatch):
    monkeypatch.setenv("DS_SPOOL_ROOT", str(tmp_path / "spool-root"))
    planning_root = tmp_path / ".planning"
    rc = main(
        [
            "skill",
            "invoke",
            "security:scan",
            "--work-order",
            WO_UI_ID,
            "--planning-root",
            str(planning_root),
        ]
    )
    assert rc == 0
    artifact = planning_root / "work-orders" / WO_UI_ID / "security-scan.md"
    assert artifact.is_file(), "security-scan.md not written"
    content = artifact.read_text(encoding="utf-8")
    assert f"Work Order {WO_UI_ID}" in content
    assert "Status: [PENDING]" in content
    assert "[PASS/BLOCKED]" in content


# ── 13. migration 054 updates gate values correctly ──────────────────────────


def test_migration_054_updates_gate_values(db_home):
    conn = sqlite3.connect(str(_db_path(db_home)))
    try:
        rows = conn.execute(
            "SELECT type_id, post_build_gate FROM ds_work_order_types"
            " WHERE type_id IN ('ui_component', 'ui_page') ORDER BY type_id",
        ).fetchall()
    finally:
        conn.close()
    by_type = {r[0]: r[1] for r in rows}
    assert by_type.get("ui_component") == "design_critique|anti_slop_passed"
    assert by_type.get("ui_page") == "design_critique|anti_slop_passed"


# ── 14. ui_component type has both gates in post_build_gate ──────────────────


def test_ui_component_type_has_both_gates(db_home):
    conn = sqlite3.connect(str(_db_path(db_home)))
    try:
        row = conn.execute(
            "SELECT post_build_gate FROM ds_work_order_types WHERE type_id = 'ui_component'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    gates = row[0].split("|")
    assert "design_critique" in gates
    assert "anti_slop_passed" in gates


# ── 15. ui_page type has both gates in post_build_gate ───────────────────────


def test_ui_page_type_has_both_gates(db_home):
    conn = sqlite3.connect(str(_db_path(db_home)))
    try:
        row = conn.execute(
            "SELECT post_build_gate FROM ds_work_order_types WHERE type_id = 'ui_page'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    gates = row[0].split("|")
    assert "design_critique" in gates
    assert "anti_slop_passed" in gates
