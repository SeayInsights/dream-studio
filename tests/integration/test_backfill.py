"""Integration tests for backfill scripts."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


@pytest.fixture()
def test_db(tmp_path: Path) -> Path:
    """Create a test DB with schema via studio_db."""
    db_path = tmp_path / "studio.db"
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))
    from lib.studio_db import _connect
    conn = _connect(db_path)
    conn.close()
    return db_path


@pytest.fixture()
def token_log(tmp_path: Path) -> Path:
    """Create a minimal token-log.md for testing."""
    log = tmp_path / "token-log.md"
    log.write_text(
        "# Token Log\n\n"
        "| Timestamp | Session | Model | Prompt | Completion | Total |\n"
        "|---|---|---|---|---|---|\n"
        "| 2026-04-20T10:00:00+00:00 | aaaaaaaa-1111-2222-3333-444444444444 | claude-opus-4-6 | 100 | 500 | 600 |\n"
        "| 2026-04-20T10:05:00+00:00 | aaaaaaaa-1111-2222-3333-444444444444 | claude-opus-4-6 | 200 | 1000 | 1200 |\n"
        "| 2026-04-20T10:10:00+00:00 | aaaaaaaa-1111-2222-3333-444444444444 | claude-opus-4-6 | 300 | 1500 | 1800 |\n"
        "| 2026-04-20T11:00:00+00:00 | bbbbbbbb-1111-2222-3333-444444444444 | claude-sonnet-4-6 | 50 | 200 | 250 |\n"
        "| 2026-04-20T11:30:00+00:00 | bbbbbbbb-1111-2222-3333-444444444444 | claude-sonnet-4-6 | 100 | 400 | 500 |\n",
        encoding="utf-8",
    )
    return log


class TestBackfillTokenSessions:
    def test_backfill_token_usage(self, test_db: Path, token_log: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("lib.paths.meta_dir", lambda: token_log.parent)
        from backfill_token_sessions import backfill_token_usage

        result = backfill_token_usage(test_db, project_id="test-project")
        assert result["inserted"] == 5
        assert result["total"] == 5
        assert result["with_session_id"] == 5

        conn = sqlite3.connect(str(test_db))
        rows = conn.execute("SELECT * FROM raw_token_usage ORDER BY id").fetchall()
        assert len(rows) == 5
        assert rows[0][1] == "aaaaaaaa-1111-2222-3333-444444444444"  # session_id
        assert rows[0][2] == "test-project"  # project_id
        assert "2026-04-20T10:00:00" in rows[0][7]  # recorded_at has real timestamp
        conn.close()

    def test_backfill_dry_run(self, test_db: Path, token_log: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("lib.paths.meta_dir", lambda: token_log.parent)
        from backfill_token_sessions import backfill_token_usage

        result = backfill_token_usage(test_db, dry_run=True)
        assert result["dry_run"] is True

        conn = sqlite3.connect(str(test_db))
        count = conn.execute("SELECT COUNT(*) FROM raw_token_usage").fetchone()[0]
        assert count == 0
        conn.close()

    def test_backfill_idempotent(self, test_db: Path, token_log: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("lib.paths.meta_dir", lambda: token_log.parent)
        from backfill_token_sessions import backfill_token_usage

        backfill_token_usage(test_db)
        result2 = backfill_token_usage(test_db)
        assert result2["total"] == 5

    def test_backfill_sessions(self, test_db: Path, token_log: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("lib.paths.meta_dir", lambda: token_log.parent)
        from backfill_token_sessions import backfill_sessions

        result = backfill_sessions(test_db, project_id="test-project")
        assert result["inserted"] == 2
        assert result["with_duration"] == 2

        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        sessions = conn.execute(
            "SELECT * FROM raw_sessions ORDER BY started_at"
        ).fetchall()
        assert len(sessions) == 2

        s1 = dict(sessions[0])
        assert s1["session_id"] == "aaaaaaaa-1111-2222-3333-444444444444"
        assert s1["project_id"] == "test-project"
        assert s1["duration_s"] == 600.0  # 10 minutes
        assert s1["input_tokens"] == 300
        assert s1["output_tokens"] == 1500

        s2 = dict(sessions[1])
        assert s2["session_id"] == "bbbbbbbb-1111-2222-3333-444444444444"
        assert s2["duration_s"] == 1800.0  # 30 minutes
        conn.close()


def _seed_handoff(test_db: Path, session_id: str, project_id: str, topic: str,
                   tasks_completed: int, tasks_total: int) -> None:
    """Insert handoff with required FK parents (project + session)."""
    from lib.studio_db import upsert_project, insert_session, insert_handoff
    upsert_project(project_id, "/tmp/test", db_path=test_db)
    insert_session(session_id, project_id, db_path=test_db)
    insert_handoff(session_id, project_id, topic,
                   tasks_completed=tasks_completed, tasks_total=tasks_total,
                   db_path=test_db)


class TestBackfillTaskStatus:
    def test_backfill_marks_tasks(self, test_db: Path) -> None:
        from lib.studio_db import upsert_project, upsert_spec, upsert_task

        upsert_project("test-proj", "/tmp/test", db_path=test_db)
        upsert_spec("test-spec", "test-proj", "Test Spec", task_count=3, db_path=test_db)
        for i in range(1, 4):
            upsert_task(f"T{i:03d}", "test-spec", "test-proj", f"Task {i}", db_path=test_db)

        _seed_handoff(test_db, "sess-1", "test-proj", "test-spec",
                       tasks_completed=2, tasks_total=3)

        from backfill_task_status import backfill_task_status
        result = backfill_task_status(test_db)

        assert result["tasks_marked_completed"] == 2
        assert result["final_status_counts"]["completed"] == 2
        assert result["final_status_counts"]["planned"] == 1

    def test_backfill_dry_run(self, test_db: Path) -> None:
        from lib.studio_db import upsert_project, upsert_spec, upsert_task

        upsert_project("test-proj", "/tmp/test", db_path=test_db)
        upsert_spec("test-spec", "test-proj", "Test Spec", task_count=2, db_path=test_db)
        upsert_task("T001", "test-spec", "test-proj", "Task 1", db_path=test_db)
        upsert_task("T002", "test-spec", "test-proj", "Task 2", db_path=test_db)

        _seed_handoff(test_db, "sess-1", "test-proj", "test-spec",
                       tasks_completed=1, tasks_total=2)

        from backfill_task_status import backfill_task_status
        result = backfill_task_status(test_db, dry_run=True)

        assert result["dry_run"] is True
        assert result["final_status_counts"]["planned"] == 2

    def test_no_matching_spec(self, test_db: Path) -> None:
        _seed_handoff(test_db, "sess-1", "test-proj", "nonexistent-topic",
                       tasks_completed=5, tasks_total=10)

        from backfill_task_status import backfill_task_status
        result = backfill_task_status(test_db)
        assert result["tasks_marked_completed"] == 0
