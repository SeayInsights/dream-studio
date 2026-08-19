"""WO-CI-COMPLETENESS: self-checking gate lists + retired string fallback.

The 2026-08-18 audit found the pre-push pin-tests and pr-smoke focused lists
were hardcoded with no completeness check (a deleted file silently stops
guarding anything), and the all_tests_pass gate fell back to a hand-writable
test-results.md containing the string "PASSED".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.gates import test_list_completeness as tlc

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── list completeness ───────────────────────────────────────────────────────────


def test_current_lists_are_complete():
    """The repo's own gate lists must have no dead entries (self-application)."""
    assert tlc.missing_listed_files() == []


def test_lists_are_nonempty_and_parsed():
    sources = tlc.listed_test_paths()
    assert len(sources.get("pre-push.yaml", [])) >= 10, sources
    assert len(sources.get("ci.yml", [])) >= 5, sources


def test_missing_listed_file_fails(monkeypatch, capsys):
    """A listed-but-vanished test file is a dead guard — the gate blocks."""
    fake = {"pre-push.yaml": ["tests/unit/definitely_not_a_real_test_file_xyz.py"]}
    monkeypatch.setattr(tlc, "listed_test_paths", lambda: fake)
    rc = tlc.main()
    assert rc == 1
    out = capsys.readouterr().out
    assert "dead guards" in out
    assert "definitely_not_a_real_test_file_xyz.py" in out


def test_unlisted_files_are_reported_not_blocking(monkeypatch, capsys):
    """Silent truncation becomes visible: the post-merge-only count is printed."""
    rc = tlc.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "post-merge" in out


# ── Path B fallback retired ─────────────────────────────────────────────────────


def test_path_b_fallback_removed(tmp_path):
    """A test-results.md containing 'PASSED' never satisfies all_tests_pass —
    without executable TEST-CHECKs the gate reports UNVERIFIED explicitly."""
    from core.work_orders.close_gates import run_gate_check

    wo_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    wo_dir = tmp_path / ".planning" / "work-orders" / wo_id
    wo_dir.mkdir(parents=True)
    (wo_dir / "test-results.md").write_text("All checks PASSED\n", encoding="utf-8")

    conn = sqlite3.connect(":memory:")
    try:
        passed, reason = run_gate_check(
            "all_tests_pass",
            planning_root=tmp_path / ".planning",
            work_order_id=wo_id,
            project_id="p",
            conn=conn,
            db_path=None,
        )
    finally:
        conn.close()
    assert passed is False
    assert "UNVERIFIED" in reason
    assert "TEST-CHECK" in reason


# ── symptom visibility ──────────────────────────────────────────────────────────


def test_symptom_check_detail_surfaces_sql_and_flags_trivial(tmp_path):
    from core.work_orders.close_gates import symptom_check_detail

    db = tmp_path / "studio.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE things (n INTEGER)")
    conn.execute("INSERT INTO things VALUES (1)")
    conn.commit()
    conn.close()

    symptom = (
        "Root cause prose here.\n"
        "SQL-CHECK: SELECT COUNT(*) FROM things\n"
        "SQL-CHECK: SELECT 1\n"
        "SQL-CHECK: SELECT COUNT(*) FROM missing_table\n"
    )
    details = symptom_check_detail(symptom, db)
    assert len(details) == 3
    real, trivial, broken = details
    assert real["passed"] is True and real["trivially_true"] is False
    assert trivial["passed"] is True and trivial["trivially_true"] is True
    assert broken["passed"] is False and "error" in broken
