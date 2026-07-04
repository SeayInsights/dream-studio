"""Integration tests for operational table CRUD functions (T013)."""

from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.event_store.studio_db import (  # noqa: E402
    _connect,
    upsert_project,
    get_project,
    list_projects,
    update_project_stats,
    insert_session,
    get_session,
    get_latest_session,
    mark_handoff_consumed,
    end_session,
    insert_handoff,
    get_latest_handoff,
    get_handoffs_for_project,
    insert_lesson,
    get_lessons,
    promote_lesson,
    get_pending_lessons,
    set_sentinel,
    has_sentinel,
    clear_expired_sentinels,
)


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "test.db"
    _connect(p).close()
    return p


# ── reg_projects ───────────────────────────────────────────────────────────


class TestProjects:
    def test_upsert_and_get(self, db):
        assert upsert_project("proj-1", "/home/user/proj", project_name="My Project", db_path=db)
        p = get_project("proj-1", db_path=db)
        assert p is not None
        assert p["project_path"] == "/home/user/proj"
        assert p["project_name"] == "My Project"
        assert p["total_sessions"] == 0

    def test_upsert_preserves_existing_fields(self, db):
        upsert_project("proj-1", "/path", project_name="Name", project_type="python", db_path=db)
        upsert_project("proj-1", "/path/new", db_path=db)
        p = get_project("proj-1", db_path=db)
        assert p["project_path"] == "/path/new"
        assert p["project_name"] == "Name"
        assert p["project_type"] == "python"

    def test_list_projects(self, db):
        upsert_project("a", "/a", db_path=db)
        upsert_project("b", "/b", db_path=db)
        projects = list_projects(db_path=db)
        assert len(projects) == 2

    def test_update_stats(self, db):
        upsert_project("proj-1", "/path", db_path=db)
        update_project_stats("proj-1", sessions_delta=1, tokens_delta=5000, db_path=db)
        p = get_project("proj-1", db_path=db)
        assert p["total_sessions"] == 1
        assert p["total_tokens"] == 5000
        update_project_stats("proj-1", sessions_delta=2, tokens_delta=3000, db_path=db)
        p = get_project("proj-1", db_path=db)
        assert p["total_sessions"] == 3
        assert p["total_tokens"] == 8000

    def test_get_nonexistent(self, db):
        assert get_project("nope", db_path=db) is None


# ── raw_sessions ───────────────────────────────────────────────────────────


class TestSessions:
    def _seed_project(self, db):
        upsert_project("proj-1", "/path", db_path=db)

    def test_insert_and_get(self, db):
        self._seed_project(db)
        assert insert_session("s1", "proj-1", topic="feature build", db_path=db)
        s = get_session("s1", db_path=db)
        assert s is not None
        assert s["project_id"] == "proj-1"
        assert s["topic"] == "feature build"
        assert s["handoff_consumed"] == 0

    def test_latest_session(self, db):
        self._seed_project(db)
        insert_session("s1", "proj-1", topic="first", db_path=db)
        insert_session("s2", "proj-1", topic="second", db_path=db)
        latest = get_latest_session("proj-1", db_path=db)
        assert latest["session_id"] == "s2"

    def test_mark_handoff_consumed(self, db):
        self._seed_project(db)
        insert_session("s1", "proj-1", db_path=db)
        mark_handoff_consumed("s1", db_path=db)
        s = get_session("s1", db_path=db)
        assert s["handoff_consumed"] == 1

    def test_end_session(self, db):
        self._seed_project(db)
        insert_session("s1", "proj-1", db_path=db)
        end_session(
            "s1",
            outcome="completed",
            input_tokens=1000,
            output_tokens=500,
            tasks_completed=3,
            db_path=db,
        )
        s = get_session("s1", db_path=db)
        assert s["ended_at"] is not None
        assert s["duration_s"] is not None
        assert s["outcome"] == "completed"
        assert s["input_tokens"] == 1000
        assert s["tasks_completed"] == 3

    def test_get_nonexistent(self, db):
        assert get_session("nope", db_path=db) is None


# ── raw_handoffs ───────────────────────────────────────────────────────────


class TestHandoffs:
    def _seed(self, db):
        upsert_project("proj-1", "/path", db_path=db)
        insert_session("s1", "proj-1", db_path=db)

    def test_insert_and_get_latest(self, db):
        self._seed(db)
        hid = insert_handoff(
            "s1",
            "proj-1",
            "sqlite migration",
            plan_path=".planning/specs/sqlite/tasks.md",
            pipeline_phase="build",
            current_task_id="T006",
            tasks_completed=5,
            tasks_total=13,
            branch="feat/sqlite-pr2",
            working=["migration runner", "indexes"],
            broken=[],
            next_action="implement CRUD",
            db_path=db,
        )
        assert hid is not None
        h = get_latest_handoff("proj-1", db_path=db)
        assert h["topic"] == "sqlite migration"
        assert h["working"] == ["migration runner", "indexes"]
        assert h["broken"] == []
        assert h["pipeline_phase"] == "build"

    def test_multiple_handoffs(self, db):
        self._seed(db)
        insert_handoff("s1", "proj-1", "first handoff", db_path=db)
        insert_handoff("s1", "proj-1", "second handoff", db_path=db)
        handoffs = get_handoffs_for_project("proj-1", db_path=db)
        assert len(handoffs) == 2

    def test_fk_violation_bad_session(self, db):
        upsert_project("proj-1", "/path", db_path=db)
        result = insert_handoff("bad-session", "proj-1", "test", db_path=db)
        assert result is None

    def test_get_latest_nonexistent(self, db):
        assert get_latest_handoff("nope", db_path=db) is None


# ── raw_lessons ────────────────────────────────────────────────────────────


class TestLessons:
    def test_insert_and_query(self, db):
        assert insert_lesson(
            "L001",
            "build",
            "SQL splitter needs depth tracking",
            what_happened="Trigger blocks failed",
            lesson="Use regex depth for BEGIN/END",
            confidence="high",
            db_path=db,
        )
        lessons = get_lessons(source="build", db_path=db)
        assert len(lessons) == 1
        assert lessons[0]["title"] == "SQL splitter needs depth tracking"

    def test_insert_idempotent(self, db):
        insert_lesson("L001", "build", "First", db_path=db)
        insert_lesson("L001", "build", "Duplicate", db_path=db)
        lessons = get_lessons(db_path=db)
        assert len(lessons) == 1
        assert lessons[0]["title"] == "First"

    def test_promote_lifecycle(self, db):
        insert_lesson("L001", "build", "Test lesson", db_path=db)
        pending = get_pending_lessons(db_path=db)
        assert len(pending) == 1
        promote_lesson("L001", "gotcha:parallel-same-file", db_path=db)
        pending = get_pending_lessons(db_path=db)
        assert len(pending) == 0
        lessons = get_lessons(status="promoted", db_path=db)
        assert len(lessons) == 1
        assert lessons[0]["promoted_to"] == "gotcha:parallel-same-file"

    def test_filter_by_status(self, db):
        insert_lesson("L001", "build", "Draft", db_path=db)
        insert_lesson("L002", "debug", "Another", db_path=db)
        promote_lesson("L002", "memory", db_path=db)
        drafts = get_lessons(status="draft", db_path=db)
        assert len(drafts) == 1
        assert drafts[0]["lesson_id"] == "L001"


# ── raw_sentinels ──────────────────────────────────────────────────────────


class TestSentinels:
    def test_set_and_check(self, db):
        assert set_sentinel("handoff-done-2026-05-01", "handoff-done", db_path=db)
        assert has_sentinel("handoff-done-2026-05-01", db_path=db)

    def test_missing_sentinel(self, db):
        assert not has_sentinel("nonexistent", db_path=db)

    def test_expired_sentinel(self, db):
        set_sentinel("old-key", "harden-nudge", expires_at="2020-01-01T00:00:00+00:00", db_path=db)
        assert not has_sentinel("old-key", db_path=db)

    def test_future_sentinel(self, db):
        set_sentinel(
            "future-key", "harden-nudge", expires_at="2099-01-01T00:00:00+00:00", db_path=db
        )
        assert has_sentinel("future-key", db_path=db)

    def test_clear_expired(self, db):
        set_sentinel("expired", "test", expires_at="2020-01-01T00:00:00+00:00", db_path=db)
        set_sentinel("valid", "test", db_path=db)
        cleared = clear_expired_sentinels(db_path=db)
        assert cleared == 1
        assert not has_sentinel("expired", db_path=db)
        assert has_sentinel("valid", db_path=db)

    def test_replace_sentinel(self, db):
        set_sentinel("key", "type-a", db_path=db)
        set_sentinel("key", "type-b", db_path=db)
        c = _connect(db)
        r = c.execute("SELECT sentinel_type FROM raw_sentinels WHERE sentinel_key='key'").fetchone()
        c.close()
        assert r["sentinel_type"] == "type-b"


# raw_token_usage / insert_token_usage / get_token_summary removed: the table
# was dropped in migration 138 (WO 468ce225) — superseded by canonical
# token.consumed events and the DuckDB aggregate_metrics.db
# token_usage_records view.


# ── FK constraint enforcement ──────────────────────────────────────────────


class TestFKConstraints:
    def test_session_requires_valid_project(self, db):
        # FK from raw_sessions to reg_projects was removed in migration 088
        # (reg_projects deleted in 084). Sessions no longer enforce project existence.
        result = insert_session("s1", "nonexistent-project", db_path=db)
        assert result is True

    def test_handoff_requires_valid_session(self, db):
        upsert_project("proj-1", "/path", db_path=db)
        result = insert_handoff("bad-session", "proj-1", "test", db_path=db)
        assert result is None
