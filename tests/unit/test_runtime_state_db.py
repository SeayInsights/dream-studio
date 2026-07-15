"""WO-FILESDB-P2 task 2: singleton runtime-state JSON moved into raw_runtime_state.

Covers the authority store (db_write/read/clear_runtime_state) and proves a
repointed caller (platform) uses the authority row for the pure default, while
still falling back to the legacy JSON file when the table is absent.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.runtime_state import (
    db_clear_runtime_state,
    db_read_runtime_state,
    db_write_runtime_state,
)

# Mirrors core/event_store/migrations/146_runtime_state.sql
_CREATE = (
    "CREATE TABLE IF NOT EXISTS raw_runtime_state ("
    " key TEXT PRIMARY KEY, value TEXT NOT NULL,"
    " updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')))"
)


def _db_with_table(tmp_path: Path) -> Path:
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db))
    conn.execute(_CREATE)
    conn.commit()
    conn.close()
    return db


def test_runtime_state_roundtrip_and_clear(tmp_path: Path) -> None:
    """write -> read returns the exact dict; overwrite replaces; clear removes it."""
    db = _db_with_table(tmp_path)

    assert db_write_runtime_state("active_task", {"task_id": "t1", "project_id": "p1"}, db_path=db)
    assert db_read_runtime_state("active_task", db_path=db) == {"task_id": "t1", "project_id": "p1"}

    # Upsert replaces the value for the same key (singleton semantics).
    assert db_write_runtime_state("active_task", {"task_id": "t2", "project_id": "p1"}, db_path=db)
    assert db_read_runtime_state("active_task", db_path=db) == {"task_id": "t2", "project_id": "p1"}

    # Independent keys coexist as separate rows.
    assert db_write_runtime_state("active_skill", {"skill_id": "ds-core"}, db_path=db)
    assert db_read_runtime_state("active_skill", db_path=db) == {"skill_id": "ds-core"}
    assert db_read_runtime_state("active_task", db_path=db) == {"task_id": "t2", "project_id": "p1"}

    assert db_clear_runtime_state("active_task", db_path=db) is True
    assert db_read_runtime_state("active_task", db_path=db) is None
    assert db_clear_runtime_state("active_task", db_path=db) is False  # already gone


def test_absent_table_is_falsey_fallback(tmp_path: Path) -> None:
    """With the table absent (migration 146 unreleased), the store degrades so the
    caller falls back to the legacy JSON file."""
    db = tmp_path / "studio.db"
    sqlite3.connect(str(db)).close()  # empty DB, no raw_runtime_state

    assert db_write_runtime_state("platform", {"os_name": "Linux"}, db_path=db) is False
    assert db_read_runtime_state("platform", db_path=db) is None
    assert db_clear_runtime_state("platform", db_path=db) is False


def test_platform_uses_authority_for_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no explicit path and no env override, platform read/write go through
    the authority row — no platform.json file is created."""
    from core.config import platform as platform_mod

    db = _db_with_table(tmp_path)
    monkeypatch.setattr("core.config.database._default_db_path", lambda: db)
    monkeypatch.delenv(platform_mod.PLATFORM_PROFILE_ENV, raising=False)
    # Default JSON location must NOT be written when the authority row is used.
    monkeypatch.setattr(platform_mod, "_default_profile_path", lambda: tmp_path / "platform.json")

    recorded = platform_mod.ensure_platform_recorded()
    assert db_read_runtime_state("platform", db_path=db) is not None
    assert not (tmp_path / "platform.json").exists()

    read_back = platform_mod.get_platform_profile()
    assert read_back == recorded


def test_explicit_profile_path_still_writes_json(tmp_path: Path) -> None:
    """An explicit profile_path always uses that JSON file (never the authority)."""
    from core.config import platform as platform_mod

    profile_path = tmp_path / "explicit-platform.json"
    platform_mod.ensure_platform_recorded(profile_path)
    assert profile_path.is_file()


def test_active_task_reads_and_clears_authority_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With DS_ACTIVE_TASK_PATH unset (pure default), get/clear_active_task go
    through the authority row, not the JSON file."""
    from core.sdlc import active_task as at

    db = _db_with_table(tmp_path)
    monkeypatch.setattr("core.config.database._default_db_path", lambda: db)
    monkeypatch.delenv(at.ACTIVE_TASK_PATH_ENV, raising=False)
    # If the JSON path were touched, it would land here — assert it is not.
    monkeypatch.setattr(at, "_active_task_path", lambda: tmp_path / "active_task.json")

    db_write_runtime_state(
        "active_task",
        {
            "task_id": "t1",
            "work_order_id": "w1",
            "milestone_id": "m1",
            "project_id": "p1",
            "set_at": "2026-07-15T00:00:00Z",
        },
        db_path=db,
    )

    got = at.get_active_task()
    assert got is not None
    assert got.task_id == "t1" and got.work_order_id == "w1" and got.project_id == "p1"
    assert not (tmp_path / "active_task.json").exists()

    assert at.clear_active_task() is True
    assert at.get_active_task() is None
