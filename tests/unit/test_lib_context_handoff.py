"""Tests for hooks/lib/context_handoff.py — write_handoff, write_recap, git helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.context_handoff import (  # noqa: E402
    active_files,
    checkpoint_career_ops,
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
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    handoff = tmp_path / "handoff.md"
    handoff.write_text("# Handoff", encoding="utf-8")
    write_recap(tmp_path, 65.0, session_id="abc12345", handoff_path=handoff)
    sessions = list((tmp_path / ".sessions").glob("**/recap-*.md"))
    assert len(sessions) == 1
    content = sessions[0].read_text(encoding="utf-8")
    assert "Recap" in content


def test_write_recap_no_handoff_path(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    write_recap(tmp_path, 65.0, session_id="nohandoff1", handoff_path=None)
    sessions = list((tmp_path / ".sessions").glob("**/recap-*.md"))
    assert len(sessions) == 1


# ── checkpoint_career_ops ──────────────────────────────────────────────


def test_checkpoint_career_ops_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = checkpoint_career_ops("sess-1")
    assert result is None


def test_checkpoint_career_ops_in_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cp_dir = tmp_path / ".dream-studio" / "career-ops"
    cp_dir.mkdir(parents=True)
    (cp_dir / "checkpoint.json").write_text(
        json.dumps({"status": "in_progress", "last_action": "apply", "mode": "batch"}),
        encoding="utf-8",
    )
    result = checkpoint_career_ops("sess-1")
    assert result is not None
    assert "Career-Ops" in result


def test_checkpoint_career_ops_completed_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cp_dir = tmp_path / ".dream-studio" / "career-ops"
    cp_dir.mkdir(parents=True)
    (cp_dir / "checkpoint.json").write_text(
        json.dumps({"status": "completed"}), encoding="utf-8"
    )
    result = checkpoint_career_ops("sess-1")
    assert result is None


# ── draft_handoff_lesson ───────────────────────────────────────────────


def test_draft_handoff_lesson_creates_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    draft_handoff_lesson(65.0, "branch: main | last commit: abc | repo: /project", "sess9999", is_pct=True)
    drafts = list((tmp_path / ".dream-studio" / "meta" / "draft-lessons").glob("handoff-*.md"))
    assert len(drafts) == 1
    content = drafts[0].read_text(encoding="utf-8")
    assert "Context Budget Exceeded" in content


def test_draft_handoff_lesson_no_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    draft_handoff_lesson(65.0, "ctx", "sessdupe1", is_pct=True)
    draft_handoff_lesson(65.0, "ctx", "sessdupe1", is_pct=True)
    drafts = list((tmp_path / ".dream-studio" / "meta" / "draft-lessons").glob("handoff-*.md"))
    assert len(drafts) == 1  # second call is a no-op
