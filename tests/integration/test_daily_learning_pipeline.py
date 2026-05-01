"""Integration tests for the daily learning pipeline.

Tests the full flow: micro_capture appends -> daily harvest reads micro-captures
-> lesson_queue lists drafts.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pytest

# Ensure hooks/ is importable (mirrors conftest.py convention)
_HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from lib import micro_capture, paths  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Redirect HOME/USERPROFILE/Path.home to a tmp dir for every test.

    This makes paths.meta_dir() resolve to tmp_path/.dream-studio/meta so no
    real user state is read or written during the test suite.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    return tmp_path


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_micro_capture_appends_to_today(isolated_home):
    """append_capture writes today.md with the correct one-line format."""
    micro_capture.append_capture("build", "pass", "test note")

    today_file = paths.meta_dir() / "today.md"
    assert today_file.exists(), "today.md should be created after first capture"

    content = today_file.read_text(encoding="utf-8")
    # The line must match HH:MM | skill:build | outcome:pass | note:test note
    lines = content.splitlines()
    capture_lines = [l for l in lines if "skill:build" in l]
    assert capture_lines, "Expected at least one capture line with skill:build"

    capture_line = capture_lines[0]
    assert "skill:build" in capture_line
    assert "outcome:pass" in capture_line
    assert "note:test note" in capture_line

    # Verify HH:MM timestamp prefix format
    time_part = capture_line.split("|")[0].strip()
    assert len(time_part) == 5 and time_part[2] == ":", (
        f"Expected HH:MM prefix, got: {time_part!r}"
    )


def test_micro_capture_rotates_daily(isolated_home):
    """append_capture moves yesterday's today.md to meta/daily/<date>.md."""
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    yesterday_str = yesterday.isoformat()

    # Simulate an existing today.md written on yesterday
    today_file = paths.meta_dir() / "today.md"
    today_file.write_text(
        f"# {yesterday_str}\n09:00 | skill:debug | outcome:pass | note:old note\n",
        encoding="utf-8",
    )

    # First capture of the new day triggers rotation
    micro_capture.append_capture("build", "pass", "new day note")

    # The old file should have been archived
    archive = paths.meta_dir() / "daily" / f"{yesterday_str}.md"
    assert archive.exists(), f"Expected archived file at {archive}"
    archived_content = archive.read_text(encoding="utf-8")
    assert f"# {yesterday_str}" in archived_content

    # today.md should now have today's date header
    new_content = today_file.read_text(encoding="utf-8")
    today_str = datetime.date.today().isoformat()
    assert f"# {today_str}" in new_content


def test_read_today_returns_lines(isolated_home):
    """read_today returns 1 header + N capture lines after N appends."""
    micro_capture.append_capture("core", "pass", "first note")
    micro_capture.append_capture("core", "fail", "second note")
    micro_capture.append_capture("quality", "pass", "third note")

    lines = micro_capture.read_today()

    # 1 header line + 3 capture lines = 4
    assert len(lines) == 4, f"Expected 4 lines (1 header + 3 captures), got {len(lines)}: {lines}"

    # First line is the date header
    assert lines[0].startswith("# "), f"First line should be date header, got: {lines[0]!r}"

    # Remaining lines are capture lines
    for capture_line in lines[1:]:
        assert "|" in capture_line, f"Capture line missing pipe separator: {capture_line!r}"


def test_lesson_queue_list_empty(isolated_home, capsys):
    """lesson_queue handles a missing draft-lessons directory gracefully."""
    import argparse
    import importlib.util

    # Load lesson_queue.py directly (scripts/ has no __init__.py)
    _SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
    spec = importlib.util.spec_from_file_location(
        "lesson_queue", _SCRIPTS_DIR / "lesson_queue.py"
    )
    lq = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lq)

    # Patch LESSONS_DIR to point at a non-existent dir so _load_lessons returns []
    empty_dir = isolated_home / ".dream-studio" / "meta" / "draft-lessons"
    # Intentionally do NOT create the directory — test the missing-dir path
    lq.LESSONS_DIR = empty_dir

    # Build minimal args for cmd_list (default: --pending)
    args = argparse.Namespace(promoted=False, rejected=False, pending=True, func=lq.cmd_list)
    lq.cmd_list(args)

    captured = capsys.readouterr()
    # Should not raise and should mention 0 lessons or "no lessons found"
    assert "0" in captured.out or "no lessons" in captured.out.lower(), (
        f"Expected empty-state output, got: {captured.out!r}"
    )
