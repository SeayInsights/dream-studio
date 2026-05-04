"""Integration tests for schema migration infrastructure (T005)."""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.studio_db import (  # noqa: E402
    _connect,
    _split_statements,
    schema_version,
    insert_approach,
    upsert_gotcha,
    search_gotchas_db,
    archive_workflow,
)


# ── Migration runner ────────────────────────────────────────────────────────

class TestMigrationRunner:
    def test_fresh_db_applies_all_migrations(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        v = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
        assert v == 9, f"Expected schema version 9, got {v}"
        conn.close()

    def test_schema_version_function(self, tmp_path):
        db = tmp_path / "test.db"
        _connect(db).close()
        assert schema_version(db) == 9

    def test_migration_is_idempotent(self, tmp_path):
        db = tmp_path / "test.db"
        conn1 = _connect(db)
        conn1.close()
        conn2 = _connect(db)
        v = conn2.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
        assert v == 9
        rows = conn2.execute("SELECT COUNT(*) FROM _schema_version").fetchone()[0]
        assert rows == 8, f"Expected 8 migration records, got {rows}"
        assert rows == 9, f"Expected 9 migration records, got {rows}"
        conn2.close()

    def test_existing_db_gets_upgraded(self, tmp_path):
        """Simulates an existing DB at version 8 that needs migration 9."""
        db = tmp_path / "test.db"
        conn = _connect(db)
        conn.close()
        conn = sqlite3.connect(str(db))
        conn.execute("DELETE FROM _schema_version WHERE version = 9")
        conn.commit()
        conn.close()
        conn2 = _connect(db)
        v = conn2.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
        assert v == 9
        conn2.close()

    def test_version_check_blocks_old_code(self, tmp_path):
        """If DB version > code version, connection must fail."""
        db = tmp_path / "test.db"
        conn = _connect(db)
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(999, '2099-01-01')"
        )
        conn.commit()
        conn.close()
        with pytest.raises(RuntimeError, match="newer than code"):
            _connect(db)


# ── SQL statement splitter ──────────────────────────────────────────────────

class TestSplitStatements:
    def test_simple_statements(self):
        sql = "CREATE TABLE foo (id INTEGER);\nCREATE TABLE bar (id INTEGER);"
        stmts = _split_statements(sql)
        assert len(stmts) == 2
        assert "foo" in stmts[0]
        assert "bar" in stmts[1]

    def test_multiline_statement(self):
        sql = """CREATE TABLE foo (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);"""
        stmts = _split_statements(sql)
        assert len(stmts) == 1
        assert "id INTEGER PRIMARY KEY" in stmts[0]

    def test_trigger_with_internal_semicolons(self):
        sql = """CREATE TRIGGER trg_test AFTER INSERT ON foo BEGIN
    INSERT INTO bar(x) VALUES(new.id);
    UPDATE baz SET count = count + 1;
END;"""
        stmts = _split_statements(sql)
        assert len(stmts) == 1
        assert "BEGIN" in stmts[0]
        assert "END" in stmts[0]

    def test_comments_stripped(self):
        sql = "-- This is a comment\nCREATE TABLE foo (id INTEGER);"
        stmts = _split_statements(sql)
        assert len(stmts) == 1

    def test_empty_input(self):
        assert _split_statements("") == []
        assert _split_statements("-- only comments\n-- here") == []


# ── Foreign key enforcement ─────────────────────────────────────────────────

class TestForeignKeys:
    def test_fk_pragma_is_on(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1, "PRAGMA foreign_keys should be ON"
        conn.close()

    def test_fk_violation_raises(self, tmp_path):
        """Inserting a raw_sessions row with a non-existent project_id should fail."""
        db = tmp_path / "test.db"
        conn = _connect(db)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO raw_sessions(session_id, project_id, started_at) "
                "VALUES('s1', 'nonexistent-project', '2026-01-01')"
            )
        conn.close()

    def test_fk_null_allowed(self, tmp_path):
        """NULL FK values should be allowed (for pre-migration data)."""
        db = tmp_path / "test.db"
        conn = _connect(db)
        conn.execute(
            "INSERT INTO raw_sessions(session_id, started_at) "
            "VALUES('s1', '2026-01-01')"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM raw_sessions WHERE session_id='s1'").fetchone()
        assert row is not None
        assert row["project_id"] is None
        conn.close()


# ── Indexes ─────────────────────────────────────────────────────────────────

class TestIndexes:
    EXPECTED_INDEXES = [
        "idx_approaches_skill",
        "idx_approaches_captured",
        "idx_approaches_project",
        "idx_approaches_session",
        "idx_telemetry_skill",
        "idx_telemetry_project",
        "idx_telemetry_session",
        "idx_corrections_telemetry",
        "idx_wfnodes_runkey",
        "idx_wfruns_workflow",
        "idx_gotchas_skill",
        "idx_gotchas_discovered",
        "idx_skills_pack",
        "idx_workflows_category",
        "idx_opsnapshots_project",
        "idx_pulse_date",
        "idx_specs_path",
        "idx_projects_last_session",
        "idx_sessions_project",
        "idx_sessions_started",
        "idx_handoffs_session",
        "idx_handoffs_project",
        "idx_specs_project",
        "idx_tasks_spec",
        "idx_tasks_project",
        "idx_lessons_status",
        "idx_lessons_source",
        "idx_sentinels_type",
        "idx_tokens_session",
        "idx_tokens_project_date",
        "idx_tokens_skill",
    ]

    def test_all_indexes_exist(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        existing = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ).fetchall()
        }
        conn.close()
        missing = set(self.EXPECTED_INDEXES) - existing
        assert not missing, f"Missing indexes: {missing}"

    def test_index_used_in_query_plan(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM raw_approaches WHERE skill_id='x' AND outcome='success'"
        ).fetchall()
        plan_text = " ".join(dict(r).get("detail", str(tuple(r))) for r in plan)
        assert "idx_approaches_skill" in plan_text, f"Expected index usage in: {plan_text}"
        conn.close()


# ── Retry decorator ─────────────────────────────────────────────────────────

class TestRetry:
    def test_retry_on_simulated_busy(self, tmp_path):
        """Verify _with_retry retries on SQLITE_BUSY and eventually succeeds."""
        db = tmp_path / "test.db"
        _connect(db).close()

        call_count = 0
        original_archive = archive_workflow.__wrapped__

        def patched(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise sqlite3.OperationalError("database is locked")
            return original_archive(*args, **kwargs)

        import lib.studio_db as mod
        orig = mod.archive_workflow
        try:
            mod.archive_workflow = mod._with_retry(patched, backoffs=(0.01, 0.01, 0.01))
            wf = {
                "workflow": "test",
                "yaml_path": "/tmp/test.yaml",
                "status": "completed",
                "nodes": {},
            }
            result = mod.archive_workflow("retry-test", wf, db_path=db)
            assert result is True
            assert call_count == 3
        finally:
            mod.archive_workflow = orig


# ── New operational tables exist ────────────────────────────────────────────

class TestOperationalTables:
    EXPECTED_TABLES = [
        "reg_projects",
        "raw_sessions",
        "raw_handoffs",
        "raw_specs",
        "raw_tasks",
        "raw_lessons",
        "raw_sentinels",
        "raw_token_usage",
    ]

    def test_all_new_tables_created(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        missing = set(self.EXPECTED_TABLES) - tables
        assert not missing, f"Missing tables: {missing}"

    def test_project_id_session_id_on_approaches(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(raw_approaches)").fetchall()}
        assert "project_id" in cols
        assert "session_id" in cols
        conn.close()

    def test_project_id_session_id_on_telemetry(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(raw_skill_telemetry)").fetchall()}
        assert "project_id" in cols
        assert "session_id" in cols
        conn.close()


# ── FTS5 ────────────────────────────────────────────────────────────────────

class TestFTS5:
    def test_fts5_table_exists(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fts_gotchas'"
            ).fetchall()
        }
        conn.close()
        opts = [
            r[0]
            for r in sqlite3.connect(str(db)).execute("PRAGMA compile_options").fetchall()
        ]
        if "ENABLE_FTS5" in opts:
            assert "fts_gotchas" in tables
        else:
            pytest.skip("FTS5 not available in this SQLite build")

    def test_fts5_search_after_insert(self, tmp_path):
        db = tmp_path / "test.db"
        conn = _connect(db)
        opts = [r[0] for r in conn.execute("PRAGMA compile_options").fetchall()]
        if "ENABLE_FTS5" not in opts:
            conn.close()
            pytest.skip("FTS5 not available")

        upsert_gotcha(
            "g1", "core:build", "high", "Migration concurrency issue",
            context="Running migrations in parallel causes locks",
            fix="Use WAL mode and busy_timeout",
            keywords="migration concurrency sqlite",
            db_path=db,
        )
        results = search_gotchas_db("migration", db_path=db)
        assert len(results) >= 1
        assert any("migration" in r.get("keywords", "").lower() for r in results)
        conn.close()

    def test_search_gotchas_like_fallback(self, tmp_path):
        """search_gotchas_db falls back to LIKE when FTS5 unavailable or empty."""
        db = tmp_path / "test.db"
        upsert_gotcha(
            "g2", "core:plan", "medium", "Plan drift warning",
            keywords="drift plan scope",
            db_path=db,
        )
        results = search_gotchas_db("drift", db_path=db)
        assert len(results) >= 1


# ── Insert with new columns ─────────────────────────────────────────────────

class TestNewColumns:
    def test_insert_approach_with_project_id(self, tmp_path):
        db = tmp_path / "test.db"
        ok = insert_approach(
            "core:build", "subagent-per-task", "success",
            project_id="proj-1", session_id="sess-1",
            db_path=db,
        )
        assert ok is True
        conn = _connect(db)
        row = conn.execute(
            "SELECT project_id, session_id FROM raw_approaches WHERE skill_id='core:build'"
        ).fetchone()
        assert row["project_id"] == "proj-1"
        assert row["session_id"] == "sess-1"
        conn.close()

    def test_insert_approach_without_new_cols(self, tmp_path):
        """Existing callers that don't pass project_id/session_id still work."""
        db = tmp_path / "test.db"
        ok = insert_approach("core:plan", "think-first", "success", db_path=db)
        assert ok is True
        conn = _connect(db)
        row = conn.execute(
            "SELECT project_id, session_id FROM raw_approaches WHERE skill_id='core:plan'"
        ).fetchone()
        assert row["project_id"] is None
        assert row["session_id"] is None
        conn.close()
