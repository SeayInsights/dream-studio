"""Integration tests for migration script, sentinel replacement, and daily backup (T021)."""
from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from lib.studio_db import _connect, has_sentinel, set_sentinel  # noqa: E402
from lib.state import backup_db  # noqa: E402
from lib import paths  # noqa: E402


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "test.db"
    _connect(p).close()
    return p


# ── Migration script unit tests ───────────────────────────────────────────

class TestMigrateHandoffJson:
    def test_ingest_handoff_json(self, tmp_path, monkeypatch):
        from migrate_to_db import _ingest_handoff_json, _COUNTS

        db_path = tmp_path / "test.db"
        _connect(db_path).close()
        monkeypatch.setattr("migrate_to_db.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("lib.studio_db._db_path", lambda: db_path)
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
        from migrate_to_db import _ingest_handoff_json, _COUNTS

        db_path = tmp_path / "test.db"
        _connect(db_path).close()
        monkeypatch.setattr("migrate_to_db.paths.state_dir", lambda: tmp_path)
        monkeypatch.setattr("lib.studio_db._db_path", lambda: db_path)

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
        from migrate_to_db import _ingest_lesson, _COUNTS

        db_path = tmp_path / "test.db"
        _connect(db_path).close()
        monkeypatch.setattr("lib.studio_db._db_path", lambda: db_path)
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
        from migrate_to_db import _ingest_sentinels, _COUNTS

        db_path = tmp_path / "test.db"
        _connect(db_path).close()
        monkeypatch.setattr("lib.studio_db._db_path", lambda: db_path)
        _COUNTS.clear()

        (tmp_path / "handoff-done-abc123.json").write_text("{}", encoding="utf-8")
        (tmp_path / "harden-nudge-proj.json").write_text("{}", encoding="utf-8")

        _ingest_sentinels(tmp_path)
        assert _COUNTS.get("raw_sentinels", 0) == 2


class TestMigrateTokenLog:
    def test_ingest_token_log(self, tmp_path, monkeypatch):
        from migrate_to_db import _ingest_token_log, _COUNTS

        db_path = tmp_path / "test.db"
        _connect(db_path).close()
        monkeypatch.setattr("lib.studio_db._db_path", lambda: db_path)
        _COUNTS.clear()

        log = tmp_path / "token-log.md"
        log.write_text(
            "# Token Log\n\n"
            "| Timestamp | Session | Model | Prompt | Completion | Total |\n"
            "|---|---|---|---|---|---|\n"
            "| 2026-05-01T00:00:00Z | sess-1 | sonnet | 100 | 50 | 150 |\n"
            "| 2026-05-01T00:01:00Z | sess-1 | haiku | 200 | 80 | 280 |\n",
            encoding="utf-8",
        )
        _ingest_token_log(log)
        assert _COUNTS.get("raw_token_usage", 0) == 2

    def test_token_log_idempotent(self, tmp_path, monkeypatch):
        from migrate_to_db import _ingest_token_log, _COUNTS

        db_path = tmp_path / "test.db"
        _connect(db_path).close()
        monkeypatch.setattr("lib.studio_db._db_path", lambda: db_path)

        log = tmp_path / "token-log.md"
        log.write_text(
            "# Token Log\n\n| Ts | S | M | P | C | T |\n|---|---|---|---|---|---|\n"
            "| 2026-05-01 | s1 | sonnet | 100 | 50 | 150 |\n",
            encoding="utf-8",
        )

        _COUNTS.clear()
        _ingest_token_log(log)
        first = _COUNTS.get("raw_token_usage", 0)

        _COUNTS.clear()
        _ingest_token_log(log)
        second = _COUNTS.get("raw_token_usage", 0)

        assert first == 1
        assert second == 0


# ── Daily backup ──────────────────────────────────────────────────────────

class TestDailyBackup:
    def test_backup_creates_bak_file(self, tmp_path, monkeypatch):
        db_path = tmp_path / "studio.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.execute("INSERT INTO test VALUES (1)")
        conn.commit()
        conn.close()

        monkeypatch.setattr("lib.state.paths.state_dir", lambda: tmp_path)
        bak = backup_db()
        assert bak is not None
        assert bak.exists()

        verify = sqlite3.connect(str(bak))
        row = verify.execute("SELECT id FROM test").fetchone()
        verify.close()
        assert row[0] == 1

    def test_backup_returns_none_when_no_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr("lib.state.paths.state_dir", lambda: tmp_path)
        assert backup_db() is None
