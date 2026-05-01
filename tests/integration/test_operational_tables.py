"""Integration tests for operational table CRUD functions (T013)."""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.studio_db import (  # noqa: E402
    _connect,
    upsert_project, get_project, list_projects, update_project_stats,
    insert_session, get_session, get_latest_session, mark_handoff_consumed, end_session,
    insert_handoff, get_latest_handoff, get_handoffs_for_project,
    upsert_spec, get_spec, list_specs,
    upsert_task, get_tasks_for_spec, get_blocked_tasks, update_task_status,
    insert_lesson, get_lessons, promote_lesson, get_pending_lessons,
    set_sentinel, has_sentinel, clear_expired_sentinels,
    insert_token_usage, get_token_summary,
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
        end_session("s1", outcome="completed", input_tokens=1000, output_tokens=500,
                    tasks_completed=3, db_path=db)
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
            "s1", "proj-1", "sqlite migration",
            plan_path=".planning/specs/sqlite/tasks.md",
            pipeline_phase="build",
            current_task_id="T006",
            tasks_completed=5, tasks_total=13,
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


# ── raw_specs + raw_tasks ──────────────────────────────────────────────────

class TestSpecsAndTasks:
    def _seed(self, db):
        upsert_project("proj-1", "/path", db_path=db)

    def test_spec_crud(self, db):
        self._seed(db)
        assert upsert_spec("spec-1", "proj-1", "SQLite Migration", task_count=26, db_path=db)
        s = get_spec("spec-1", db_path=db)
        assert s["title"] == "SQLite Migration"
        assert s["status"] == "draft"
        assert s["task_count"] == 26

    def test_spec_upsert_updates(self, db):
        self._seed(db)
        upsert_spec("spec-1", "proj-1", "Old Title", db_path=db)
        upsert_spec("spec-1", "proj-1", "New Title", status="active", db_path=db)
        s = get_spec("spec-1", db_path=db)
        assert s["title"] == "New Title"
        assert s["status"] == "active"

    def test_list_specs_filtered(self, db):
        self._seed(db)
        upsert_spec("s1", "proj-1", "Spec A", status="draft", db_path=db)
        upsert_spec("s2", "proj-1", "Spec B", status="active", db_path=db)
        all_specs = list_specs(project_id="proj-1", db_path=db)
        assert len(all_specs) == 2
        active = list_specs(project_id="proj-1", status="active", db_path=db)
        assert len(active) == 1
        assert active[0]["title"] == "Spec B"

    def test_task_crud(self, db):
        self._seed(db)
        upsert_spec("spec-1", "proj-1", "Test Spec", db_path=db)
        assert upsert_task("T001", "spec-1", "proj-1", "Migration runner",
                           depends_on=[], estimated_hours=1.5, db_path=db)
        assert upsert_task("T002", "spec-1", "proj-1", "Retry decorator",
                           depends_on=["T001"], estimated_hours=1.0, db_path=db)
        tasks = get_tasks_for_spec("spec-1", db_path=db)
        assert len(tasks) == 2
        assert tasks[0]["task_id"] == "T001"

    def test_update_task_status_and_spec_count(self, db):
        self._seed(db)
        upsert_spec("spec-1", "proj-1", "Test", task_count=2, db_path=db)
        upsert_task("T001", "spec-1", "proj-1", "Task A", db_path=db)
        upsert_task("T002", "spec-1", "proj-1", "Task B", db_path=db)
        update_task_status("T001", "spec-1", "completed", commit_sha="abc123", db_path=db)
        s = get_spec("spec-1", db_path=db)
        assert s["tasks_done"] == 1
        update_task_status("T002", "spec-1", "completed", db_path=db)
        s = get_spec("spec-1", db_path=db)
        assert s["tasks_done"] == 2

    def test_blocked_tasks(self, db):
        self._seed(db)
        upsert_spec("spec-1", "proj-1", "Test", db_path=db)
        upsert_task("T001", "spec-1", "proj-1", "Blocked task",
                    status="blocked", db_path=db)
        upsert_task("T002", "spec-1", "proj-1", "Normal task",
                    status="planned", db_path=db)
        blocked = get_blocked_tasks(project_id="proj-1", db_path=db)
        assert len(blocked) == 1
        assert blocked[0]["task_id"] == "T001"
        assert blocked[0]["spec_title"] == "Test"

    def test_blocked_tasks_cross_project(self, db):
        upsert_project("p1", "/p1", db_path=db)
        upsert_project("p2", "/p2", db_path=db)
        upsert_spec("s1", "p1", "Spec 1", db_path=db)
        upsert_spec("s2", "p2", "Spec 2", db_path=db)
        upsert_task("T1", "s1", "p1", "Blocked A", status="blocked", db_path=db)
        upsert_task("T2", "s2", "p2", "Blocked B", status="blocked", db_path=db)
        all_blocked = get_blocked_tasks(db_path=db)
        assert len(all_blocked) == 2

    def test_get_spec_nonexistent(self, db):
        assert get_spec("nope", db_path=db) is None


# ── raw_lessons ────────────────────────────────────────────────────────────

class TestLessons:
    def test_insert_and_query(self, db):
        assert insert_lesson("L001", "build", "SQL splitter needs depth tracking",
                             what_happened="Trigger blocks failed",
                             lesson="Use regex depth for BEGIN/END",
                             confidence="high", db_path=db)
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
        set_sentinel("old-key", "harden-nudge", expires_at="2020-01-01T00:00:00+00:00",
                     db_path=db)
        assert not has_sentinel("old-key", db_path=db)

    def test_future_sentinel(self, db):
        set_sentinel("future-key", "harden-nudge", expires_at="2099-01-01T00:00:00+00:00",
                     db_path=db)
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


# ── raw_token_usage ────────────────────────────────────────────────────────

class TestTokenUsage:
    def _seed(self, db):
        upsert_project("proj-1", "/path", db_path=db)
        insert_session("s1", "proj-1", db_path=db)

    def test_insert_and_summary_by_project(self, db):
        self._seed(db)
        insert_token_usage(session_id="s1", project_id="proj-1",
                           skill_name="core:build", input_tokens=1000,
                           output_tokens=500, model="sonnet", db_path=db)
        insert_token_usage(session_id="s1", project_id="proj-1",
                           skill_name="core:review", input_tokens=800,
                           output_tokens=300, model="haiku", db_path=db)
        summary = get_token_summary(db_path=db)
        assert len(summary) == 1
        assert summary[0]["total_tokens"] == 2600

    def test_summary_by_skill(self, db):
        self._seed(db)
        insert_token_usage(project_id="proj-1", skill_name="core:build",
                           input_tokens=500, output_tokens=200, db_path=db)
        insert_token_usage(project_id="proj-1", skill_name="core:build",
                           input_tokens=600, output_tokens=300, db_path=db)
        insert_token_usage(project_id="proj-1", skill_name="quality:debug",
                           input_tokens=100, output_tokens=50, db_path=db)
        summary = get_token_summary(project_id="proj-1", db_path=db)
        assert len(summary) == 2
        build_row = next(r for r in summary if r["skill_name"] == "core:build")
        assert build_row["total_input"] == 1100
        assert build_row["call_count"] == 2


# ── FK constraint enforcement ──────────────────────────────────────────────

class TestFKConstraints:
    def test_session_requires_valid_project(self, db):
        result = insert_session("s1", "nonexistent-project", db_path=db)
        assert result is False

    def test_handoff_requires_valid_session(self, db):
        upsert_project("proj-1", "/path", db_path=db)
        result = insert_handoff("bad-session", "proj-1", "test", db_path=db)
        assert result is None

    def test_task_allows_null_project(self, db):
        """Tasks with NULL project_id should not trigger FK violation."""
        upsert_project("proj-1", "/path", db_path=db)
        upsert_spec("spec-1", "proj-1", "Test", db_path=db)
        c = _connect(db)
        c.execute(
            "INSERT INTO raw_tasks (task_id, spec_id, project_id, title) VALUES (?, ?, NULL, ?)",
            ("T001", "spec-1", "Orphan task"),
        )
        c.commit()
        c.close()
