"""Integration tests for migration script, sentinel replacement, and daily backup (T021)."""

from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from core.event_store.studio_db import _connect, has_sentinel, set_sentinel  # noqa: E402
from core.config.state import backup_db  # noqa: E402
from core.config import paths  # noqa: E402


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "test.db"
    _connect(p).close()
    return p


# ── Migration script unit tests ───────────────────────────────────────────


class TestMigrateHandoffJson:
    def test_ingest_handoff_json(self, tmp_path, monkeypatch):
        from interfaces.cli.migrate_to_db import _ingest_handoff_json, _COUNTS

        db_path = tmp_path / "test.db"
        _connect(db_path).close()
        monkeypatch.setattr("interfaces.cli.migrate_to_db.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("core.event_store.studio_db._db_path", lambda: db_path)
        _COUNTS.clear()

        handoff = {
            "topic": "test-migration",
            "date": "2026-05-01",
            "project_root": str(tmp_path / "my-project"),
            "pipeline_phase": "build",
            "current_task_id": "T001",
            "tasks_completed": 3,
            "tasks_total": 10,
            "branch": "feat/test",
            "working": ["item1"],
            "broken": [],
        }
        f = tmp_path / "handoff-test.json"
        f.write_text(json.dumps(handoff), encoding="utf-8")

        _ingest_handoff_json(f)
        assert _COUNTS.get("raw_handoffs", 0) == 1
        assert _COUNTS.get("raw_sessions", 0) == 1

    def test_idempotent_handoff(self, tmp_path, monkeypatch):
        from interfaces.cli.migrate_to_db import _ingest_handoff_json, _COUNTS

        db_path = tmp_path / "test.db"
        _connect(db_path).close()
        monkeypatch.setattr("interfaces.cli.migrate_to_db.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("core.event_store.studio_db._db_path", lambda: db_path)

        handoff = {
            "topic": "dedup-test",
            "date": "2026-05-01",
            "project_root": str(tmp_path),
        }
        f = tmp_path / "handoff-dedup.json"
        f.write_text(json.dumps(handoff), encoding="utf-8")

        _COUNTS.clear()
        _ingest_handoff_json(f)
        first_count = _COUNTS.get("raw_handoffs", 0)

        _COUNTS.clear()
        _ingest_handoff_json(f)
        second_count = _COUNTS.get("raw_handoffs", 0)

        assert first_count == 1
        assert second_count == 0


class TestMigrateLessons:
    def test_ingest_lesson_with_frontmatter(self, tmp_path, monkeypatch):
        from interfaces.cli.migrate_to_db import _ingest_lesson, _COUNTS

        db_path = tmp_path / "test.db"
        _connect(db_path).close()
        monkeypatch.setattr("core.event_store.studio_db._db_path", lambda: db_path)
        _COUNTS.clear()

        lesson = tmp_path / "2026-05-01-test-lesson.md"
        lesson.write_text(
            "---\nsource: build\nconfidence: high\n---\n\n"
            "## SQL splitter needs depth\n\n"
            "## What happened\nTrigger blocks failed.\n\n"
            "## Lesson\nUse regex depth tracking.\n",
            encoding="utf-8",
        )
        _ingest_lesson(lesson)
        assert _COUNTS.get("raw_lessons", 0) == 1


class TestMigrateSentinels:
    def test_ingest_sentinels(self, tmp_path, monkeypatch):
        from interfaces.cli.migrate_to_db import _ingest_sentinels, _COUNTS

        db_path = tmp_path / "test.db"
        _connect(db_path).close()
        monkeypatch.setattr("core.event_store.studio_db._db_path", lambda: db_path)
        _COUNTS.clear()

        (tmp_path / "handoff-done-abc123.json").write_text("{}", encoding="utf-8")
        (tmp_path / "harden-nudge-proj.json").write_text("{}", encoding="utf-8")

        _ingest_sentinels(tmp_path)
        assert _COUNTS.get("raw_sentinels", 0) == 2


# TestMigrateTokenLog removed — _ingest_token_log and raw_token_usage were
# dropped in migration 138 (WO 468ce225); superseded by canonical
# token.consumed events and the DuckDB token_usage_records view.


# ── Daily backup ──────────────────────────────────────────────────────────


class TestDailyBackup:
    def test_backup_creates_bak_file(self, tmp_path, monkeypatch):
        db_path = tmp_path / "studio.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.execute("INSERT INTO test VALUES (1)")
        conn.commit()
        conn.close()

        monkeypatch.setattr("core.config.paths.state_dir", lambda: tmp_path)
        bak = backup_db()
        assert bak is not None
        assert bak.exists()

        verify = sqlite3.connect(str(db_path))
        row = verify.execute("SELECT id FROM test").fetchone()
        verify.close()
        assert row[0] == 1

    def test_backup_returns_none_when_no_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.config.paths.state_dir", lambda: tmp_path)
        assert backup_db() is None
