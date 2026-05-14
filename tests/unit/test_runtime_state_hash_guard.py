"""Phase 8H runtime-state hash guard tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts import runtime_state_hash_guard as guard

pytestmark = pytest.mark.runtime_reliability


def test_default_watch_paths_are_native_runtime_files(tmp_path):
    paths = guard.default_watch_paths(home=tmp_path)

    assert paths == [
        tmp_path / ".dream-studio" / "state" / "studio.db",
        tmp_path / ".dream-studio" / "state" / "studio.db.bak",
        tmp_path / ".dream-studio" / "state" / "studio.db.pre-restore.bak",
    ]


def test_hash_guard_passes_when_watched_file_is_unchanged(tmp_path):
    watched = tmp_path / "studio.db"
    watched.write_text("stable", encoding="utf-8")

    exit_code, report = guard.run_guard(
        [sys.executable, "-c", "print('ok')"],
        watch_paths=[watched],
        label="unchanged",
    )

    assert exit_code == 0
    assert report["command_exit"] == 0
    assert report["changed_count"] == 0
    assert report["changed"] == []


def test_hash_guard_detects_watched_file_mutation(tmp_path):
    watched = tmp_path / "studio.db"
    watched.write_text("before", encoding="utf-8")

    exit_code, report = guard.run_guard(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                f"Path({str(watched)!r}).write_text('after', encoding='utf-8')"
            ),
        ],
        watch_paths=[watched],
        label="mutated",
    )

    assert exit_code == guard.MUTATION_EXIT_CODE
    assert report["command_exit"] == 0
    assert report["changed_count"] == 1
    assert report["changed"][0]["path"] == str(watched)


def test_hash_guard_script_remains_observational():
    source = Path(guard.__file__).read_text(encoding="utf-8")

    assert "sqlite3" not in source
    assert "shutil" not in source
    assert ".unlink(" not in source
    assert "os.replace" not in source
    assert ".write_bytes(" not in source
    assert ".write_text(" not in source
