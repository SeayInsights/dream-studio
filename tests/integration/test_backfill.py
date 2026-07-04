"""Integration tests for backfill scripts."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


@pytest.fixture()
def test_db(tmp_path: Path) -> Path:
    """Create a test DB with schema via studio_db."""
    db_path = tmp_path / "studio.db"
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from core.event_store.studio_db import _connect

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


class TestBackfillSessions:
    def test_backfill_sessions(
        self, test_db: Path, token_log: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("core.config.paths.meta_dir", lambda: token_log.parent)
        from interfaces.cli.backfill_token_sessions import backfill_sessions

        result = backfill_sessions(test_db, project_id="test-project")
        assert result["inserted"] == 2
        assert result["with_duration"] == 2

        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        sessions = conn.execute("SELECT * FROM raw_sessions ORDER BY started_at").fetchall()
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


# TestBackfillTaskStatus removed — backfill_task_status.py and its backing
# tables (raw_specs, raw_tasks) were dropped in migration 128.
