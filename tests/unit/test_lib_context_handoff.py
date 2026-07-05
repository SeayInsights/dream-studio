"""Tests for control/context/handoff.py — write_handoff, write_recap, git helpers."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from control.context.handoff import (  # noqa: E402
    active_files,
    draft_handoff_lesson,
    git,
    git_context,
    write_handoff,
    write_recap,
)

# ── git helpers ────────────────────────────────────────────────────────


def test_git_returns_empty_on_failure(tmp_path):
    result = git(["status", "--nonexistent-flag-xyz"], cwd=tmp_path)
    assert result == ""


def test_git_returns_string(tmp_path):
    # In a non-git dir, rev-parse should fail gracefully
    result = git(["rev-parse", "HEAD"], cwd=tmp_path)
    assert isinstance(result, str)


def test_git_context_returns_string(tmp_path):
    ctx = git_context(tmp_path)
    assert isinstance(ctx, str)
    assert "branch:" in ctx


def test_active_files_returns_list(tmp_path):
    files = active_files(tmp_path)
    assert isinstance(files, list)


# ── write_handoff ──────────────────────────────────────────────────────


def test_write_handoff_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = write_handoff(tmp_path, 65.0, session_id="abc12345", is_pct=True)
    assert result is not None
    assert result.exists()
    content = result.read_text(encoding="utf-8")
    assert "Handoff" in content
    assert "65" in content


def test_write_handoff_no_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    p1 = write_handoff(tmp_path, 65.0, session_id="abc12345", is_pct=True)
    p2 = write_handoff(tmp_path, 65.0, session_id="abc12345", is_pct=True)
    assert p1 != p2  # second call gets a numbered filename


def test_write_handoff_kb_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = write_handoff(tmp_path, 2600.0, session_id="kb123456", is_pct=False)
    assert result is not None
    content = result.read_text(encoding="utf-8")
    assert "2600" in content


# ── write_recap ────────────────────────────────────────────────────────


def test_write_recap_creates_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DREAM_STUDIO_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    handoff = tmp_path / "handoff.md"
    handoff.write_text("# Handoff", encoding="utf-8")
    write_recap(tmp_path, 65.0, session_id="abc12345", handoff_path=handoff)
    sessions = list((tmp_path / ".dream-studio" / ".sessions").glob("**/recap-*.md"))
    assert len(sessions) == 1
    content = sessions[0].read_text(encoding="utf-8")
    assert "Recap" in content


def test_write_recap_no_handoff_path(tmp_path, monkeypatch):
    monkeypatch.delenv("DREAM_STUDIO_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    write_recap(tmp_path, 65.0, session_id="nohandoff1", handoff_path=None)
    sessions = list((tmp_path / ".dream-studio" / ".sessions").glob("**/recap-*.md"))
    assert len(sessions) == 1


# ── draft_handoff_lesson ───────────────────────────────────────────────


def _ondisk_on_context_threshold_rows(tmp_path) -> int:
    """Count any on-context-threshold raw_lessons rows in the isolated home DB."""
    import sqlite3

    db_path = tmp_path / ".dream-studio" / "state" / "studio.db"
    if not db_path.exists():
        return 0
    con = sqlite3.connect(str(db_path))
    try:
        # raw_lessons may not exist if nothing ever wrote a lesson — treat as 0.
        try:
            rows = con.execute(
                "SELECT lesson_id FROM raw_lessons WHERE source='on-context-threshold'"
            ).fetchall()
        except sqlite3.OperationalError:
            return 0
        return len(rows)
    finally:
        con.close()


def test_draft_handoff_lesson_does_not_create_draft(tmp_path, monkeypatch):
    """WO-HANDOFF-LESSON-NOISE: the auto-handoff retrospective must NOT insert a
    body-less draft lesson into raw_lessons (it polluted the lessons pipeline)."""
    monkeypatch.delenv("DREAM_STUDIO_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    draft_handoff_lesson(
        65.0, "branch: main | last commit: abc | repo: /project", "sess9999", is_pct=True
    )
    assert (
        _ondisk_on_context_threshold_rows(tmp_path) == 0
    ), "handoff must not create an on-context-threshold draft lesson"


def test_draft_handoff_lesson_no_draft_on_repeat(tmp_path, monkeypatch):
    """Repeated handoffs still create zero draft lessons (no accumulation)."""
    monkeypatch.delenv("DREAM_STUDIO_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    draft_handoff_lesson(65.0, "ctx", "sessdupe1", is_pct=True)
    draft_handoff_lesson(65.0, "ctx", "sessdupe1", is_pct=True)
    assert _ondisk_on_context_threshold_rows(tmp_path) == 0


# ── git subprocess exception (lines 40-41) ────────────────────────────────


def test_git_subprocess_raises_returns_empty(tmp_path, monkeypatch):
    def fail_run(*a, **kw):
        raise OSError("git binary not found")

    monkeypatch.setattr(subprocess, "run", fail_run)
    assert git(["status"], cwd=tmp_path) == ""


# ── active_files: subprocess exception + loop body (lines 61-71) ──────────


def test_active_files_subprocess_raises_returns_empty_list(tmp_path, monkeypatch):
    def fail_run(*a, **kw):
        raise OSError("git not available")

    monkeypatch.setattr(subprocess, "run", fail_run)
    assert active_files(tmp_path) == []


def test_active_files_parses_status_lines(tmp_path, monkeypatch):
    mock_proc = MagicMock()
    # "ab" is < 4 chars → triggers `continue`; "M  modified.py" is valid
    mock_proc.stdout = "ab\nM  modified.py\n   empty_code.py\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_proc)
    result = active_files(tmp_path)
    assert ("modified", "modified.py") in result


# ── write_handoff: mkdir failure (lines 105-107) ──────────────────────────


def test_write_handoff_mkdir_failure_returns_none(tmp_path, monkeypatch):
    import control.context.handoff as handoff_mod
    from datetime import datetime, UTC

    monkeypatch.delenv("DREAM_STUDIO_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Mock utcnow to return a fixed date so we can pre-block it
    fixed_date = datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(handoff_mod, "utcnow", lambda: fixed_date)

    # Create sessions dir normally
    sessions = tmp_path / ".dream-studio" / ".sessions"
    sessions.mkdir(parents=True, exist_ok=True)

    # Block the date subdirectory by creating it as a file instead of a directory
    date_str = fixed_date.strftime("%Y-%m-%d")
    date_blocker = sessions / date_str
    date_blocker.write_text("blocked", encoding="utf-8")

    # Now write_handoff should fail when trying to mkdir the date directory
    assert write_handoff(tmp_path, 65.0, session_id="mkdirfail") is None


# ── write_handoff: write_text failure (lines 141-143) ─────────────────────


def test_write_handoff_write_text_failure_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with patch.object(Path, "write_text", side_effect=PermissionError("disk full")):
        assert write_handoff(tmp_path, 65.0, session_id="wfail001") is None


# ── write_recap: write_text failure (lines 188-189) ───────────────────────


def test_write_recap_write_failure_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with patch.object(Path, "write_text", side_effect=PermissionError("disk full")):
        write_recap(tmp_path, 65.0, session_id="rfail001", handoff_path=None)


# ── draft_handoff_lesson: outer exception swallowed (lines 228-229) ───────


def test_draft_handoff_lesson_outer_exception_swallowed(tmp_path, monkeypatch):
    import core.config.paths as lp

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    def fail_meta():
        raise RuntimeError("cannot access meta dir")

    monkeypatch.setattr(lp, "meta_dir", fail_meta)
    draft_handoff_lesson(65.0, "branch: main", "sess-ex1")
