"""Phase 18.1.1 tests — raw_claude_code_events table and ingestor dual-write."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import uuid
from pathlib import Path

import pytest

from spool.ingestor import (
    REQUIRED_FIELDS,
    IngestResult,
    _extract_correlation_ids,
    _write_to_raw_sqlite,
    ingest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_envelope(
    event_type: str = "test.event",
    session_id: str | None = None,
    project_id: str | None = None,
    trace: dict | None = None,
    payload: dict | None = None,
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": "2026-05-22T12:00:00+00:00",
        "schema_version": 1,
        "session_id": session_id,
        "project_id": project_id,
        "severity": "info",
        "confidence": "exact",
        "source_type": "confirmed",
        "raw_prompt_retained": False,
        "raw_tool_output_retained": False,
        "trace": trace or {},
        "payload": payload or {},
    }


def _raw_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM raw_claude_code_events").fetchone()[0]


def _canonical_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM canonical_events").fetchone()[0]


# ---------------------------------------------------------------------------
# Tests: _extract_correlation_ids
# ---------------------------------------------------------------------------


class TestExtractCorrelationIds:

    def test_session_from_top_level(self):
        env = _mk_envelope(session_id="ses-abc")
        ids = _extract_correlation_ids(env)
        assert ids["session_id"] == "ses-abc"
        assert "sess-ses-abc" in ids["correlation_id"]

    def test_project_from_top_level(self):
        env = _mk_envelope(project_id="proj-xyz")
        ids = _extract_correlation_ids(env)
        assert ids["project_id"] == "proj-xyz"

    def test_project_from_trace(self):
        env = _mk_envelope(trace={"domain": "telemetry", "project_id": "dream-studio"})
        ids = _extract_correlation_ids(env)
        assert ids["project_id"] == "dream-studio"

    def test_hook_and_tool_from_trace(self):
        env = _mk_envelope(
            trace={
                "domain": "telemetry",
                "hook_id": "on-tool-activity",
                "tool_id": "Edit",
            }
        )
        ids = _extract_correlation_ids(env)
        assert ids["hook_id"] == "on-tool-activity"
        assert ids["tool_id"] == "Edit"
        corr = ids["correlation_id"]
        assert "hook-on-tool-activity" in corr
        assert "tool-Edit" in corr

    def test_workflow_id_from_stream_id(self):
        env = _mk_envelope(trace={"domain": "system", "stream_id": "studio-onboard-123"})
        ids = _extract_correlation_ids(env)
        assert ids["workflow_id"] == "studio-onboard-123"
        assert "wf-studio-onboard-123" in ids["correlation_id"]

    def test_skill_from_skill_specifier(self):
        env = _mk_envelope(trace={"domain": "sdlc", "skill_specifier": "ds-project:scope"})
        ids = _extract_correlation_ids(env)
        assert ids["skill_id"] == "ds-project:scope"
        assert "skill-ds-project:scope" in ids["correlation_id"]

    def test_correlation_id_none_when_no_ids(self):
        env = _mk_envelope(trace={"domain": "telemetry"})
        ids = _extract_correlation_ids(env)
        assert ids["correlation_id"] is None

    def test_correlation_id_composition_order(self):
        env = _mk_envelope(
            session_id="ses-1",
            trace={
                "workflow_id": "wf-1",
                "skill_id": "sk-1",
                "hook_id": "hook-1",
                "tool_id": "tool-1",
            },
        )
        ids = _extract_correlation_ids(env)
        corr = ids["correlation_id"]
        # Check canonical order: sess, wf, skill, hook, tool (no agent here)
        assert corr.index("sess-") < corr.index("wf-")
        assert corr.index("wf-") < corr.index("skill-")
        assert corr.index("skill-") < corr.index("hook-")
        assert corr.index("hook-") < corr.index("tool-")

    def test_trace_as_json_string(self):
        env = _mk_envelope()
        env["trace"] = json.dumps({"domain": "telemetry", "hook_id": "on-stop"})
        ids = _extract_correlation_ids(env)
        assert ids["hook_id"] == "on-stop"

    def test_session_fallback_to_payload(self):
        env = _mk_envelope(payload={"session_id": "sess-from-payload"})
        ids = _extract_correlation_ids(env)
        assert ids["session_id"] == "sess-from-payload"


# ---------------------------------------------------------------------------
# Tests: _write_to_raw_sqlite
# ---------------------------------------------------------------------------


class TestWriteToRawSqlite:

    def test_creates_table_and_inserts(self, tmp_path):
        db = tmp_path / "test.db"
        env = _mk_envelope(session_id="ses-1", project_id="proj-1")
        _write_to_raw_sqlite(env, db)
        conn = sqlite3.connect(str(db))
        assert conn.execute("SELECT COUNT(*) FROM raw_claude_code_events").fetchone()[0] == 1
        row = conn.execute("SELECT * FROM raw_claude_code_events").fetchone()
        assert row[0] == env["event_id"]  # event_id
        conn.close()

    def test_idempotent_double_write(self, tmp_path):
        db = tmp_path / "test.db"
        env = _mk_envelope()
        _write_to_raw_sqlite(env, db)
        _write_to_raw_sqlite(env, db)  # second write: INSERT OR IGNORE
        conn = sqlite3.connect(str(db))
        assert conn.execute("SELECT COUNT(*) FROM raw_claude_code_events").fetchone()[0] == 1
        conn.close()

    def test_source_payload_is_full_envelope(self, tmp_path):
        db = tmp_path / "test.db"
        env = _mk_envelope(event_type="hook.tool_activity", trace={"hook_id": "on-stop"})
        _write_to_raw_sqlite(env, db)
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT source_payload FROM raw_claude_code_events").fetchone()
        parsed = json.loads(row[0])
        assert parsed["event_id"] == env["event_id"]
        assert parsed["event_type"] == "hook.tool_activity"
        conn.close()

    def test_correlation_ids_extracted_to_columns(self, tmp_path):
        db = tmp_path / "test.db"
        env = _mk_envelope(
            session_id="ses-42",
            trace={"hook_id": "on-tool-activity", "tool_id": "Read"},
        )
        _write_to_raw_sqlite(env, db)
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM raw_claude_code_events").fetchone()
        assert row["session_id"] == "ses-42"
        assert row["hook_id"] == "on-tool-activity"
        assert row["tool_id"] == "Read"
        assert "sess-ses-42" in row["correlation_id"]
        conn.close()

    def test_indexes_created(self, tmp_path):
        db = tmp_path / "test.db"
        _write_to_raw_sqlite(_mk_envelope(), db)
        conn = sqlite3.connect(str(db))
        idx_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='raw_claude_code_events'"
        ).fetchall()
        idx_names = {r[0] for r in idx_rows}
        assert "idx_raw_cce_event_type" in idx_names
        assert "idx_raw_cce_received_at" in idx_names
        assert "idx_raw_cce_correlation_id" in idx_names
        assert "idx_raw_cce_session_id" in idx_names
        assert "idx_raw_cce_project_id" in idx_names
        conn.close()


# ---------------------------------------------------------------------------
# Tests: ingestor dual-write (end-to-end with spool)
# ---------------------------------------------------------------------------


class TestIngestorDualWrite:

    def _make_spool_root(self, tmp_path: Path) -> Path:
        root = tmp_path / "spool_root"
        from spool.states import ensure_dirs

        ensure_dirs(root)
        return root

    def _write_spool_file(self, spool_root: Path, envelope: dict) -> Path:
        from spool.states import SpoolState, state_dir

        inbox = state_dir(SpoolState.SPOOL, spool_root)
        p = inbox / f"{envelope['event_id']}.json"
        p.write_text(json.dumps(envelope), encoding="utf-8")
        return p

    def test_ingest_writes_raw_and_canonical(self, tmp_path):
        db = tmp_path / "studio.db"
        root = self._make_spool_root(tmp_path)
        env = _mk_envelope(session_id="ses-test", event_type="test.dual_write")
        self._write_spool_file(root, env)

        result = ingest(root=root, db_path=db)

        assert result.processed == 1
        assert result.failed == 0
        conn = sqlite3.connect(str(db))
        assert _raw_count(conn) == 1
        assert _canonical_count(conn) == 1
        conn.close()

    def test_raw_row_has_correct_fields(self, tmp_path):
        db = tmp_path / "studio.db"
        root = self._make_spool_root(tmp_path)
        env = _mk_envelope(
            session_id="ses-abc",
            project_id="proj-123",
            trace={"domain": "telemetry", "hook_id": "on-stop"},
        )
        self._write_spool_file(root, env)
        ingest(root=root, db_path=db)

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM raw_claude_code_events WHERE event_id=?", (env["event_id"],)
        ).fetchone()
        assert row is not None
        assert row["event_type"] == env["event_type"]
        assert row["event_timestamp"] == env["timestamp"]
        assert row["session_id"] == "ses-abc"
        assert row["project_id"] == "proj-123"
        assert row["hook_id"] == "on-stop"
        assert row["received_at"] is not None
        conn.close()

    def test_raw_written_before_canonical_on_success(self, tmp_path):
        """Both raw and canonical are written on success."""
        db = tmp_path / "studio.db"
        root = self._make_spool_root(tmp_path)
        env = _mk_envelope()
        self._write_spool_file(root, env)
        ingest(root=root, db_path=db)

        conn = sqlite3.connect(str(db))
        assert _raw_count(conn) == 1
        assert _canonical_count(conn) == 1
        conn.close()

    def test_spool_file_moves_to_processed_on_success(self, tmp_path):
        db = tmp_path / "studio.db"
        root = self._make_spool_root(tmp_path)
        env = _mk_envelope()
        self._write_spool_file(root, env)
        ingest(root=root, db_path=db)

        from spool.states import SpoolState, state_dir

        inbox = state_dir(SpoolState.SPOOL, root)
        processed = state_dir(SpoolState.PROCESSED, root)
        assert not (inbox / f"{env['event_id']}.json").exists()
        assert (processed / f"{env['event_id']}.json").exists()

    def test_multiple_events_all_written_to_raw(self, tmp_path):
        db = tmp_path / "studio.db"
        root = self._make_spool_root(tmp_path)
        envs = [_mk_envelope(event_type=f"test.event.{i}") for i in range(5)]
        for env in envs:
            self._write_spool_file(root, env)

        result = ingest(root=root, db_path=db)

        assert result.processed == 5
        conn = sqlite3.connect(str(db))
        assert _raw_count(conn) == 5
        assert _canonical_count(conn) == 5
        conn.close()


# ---------------------------------------------------------------------------
# Tests: migration 066 schema validation
# ---------------------------------------------------------------------------


class TestMigration066Schema:

    def test_migration_creates_raw_table(self, tmp_path):
        """Migration 066 SQL creates raw_claude_code_events with correct columns."""
        migration_path = (
            Path(__file__).parent.parent.parent
            / "core"
            / "event_store"
            / "migrations"
            / "066_raw_claude_code_events.sql"
        )
        assert migration_path.exists(), "Migration 066 file not found"

        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.executescript(migration_path.read_text(encoding="utf-8"))
        conn.commit()

        # Verify table exists
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='raw_claude_code_events'"
        ).fetchone()
        assert row is not None

        # Verify columns
        cols = {r[1] for r in conn.execute("PRAGMA table_info(raw_claude_code_events)").fetchall()}
        required_cols = {
            "event_id",
            "received_at",
            "event_type",
            "event_timestamp",
            "schema_version",
            "source_payload",
            "session_id",
            "project_id",
            "workflow_id",
            "skill_id",
            "agent_id",
            "hook_id",
            "tool_id",
            "model_id",
            "adapter_id",
            "correlation_id",
        }
        assert required_cols.issubset(cols)
        conn.close()

    def test_migration_creates_indexes(self, tmp_path):
        migration_path = (
            Path(__file__).parent.parent.parent
            / "core"
            / "event_store"
            / "migrations"
            / "066_raw_claude_code_events.sql"
        )
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.executescript(migration_path.read_text(encoding="utf-8"))
        conn.commit()

        idx_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='raw_claude_code_events'"
        ).fetchall()
        idx_names = {r[0] for r in idx_rows}

        # All required indexes per Commitment 8
        required_indexes = {
            "idx_raw_cce_session_id",
            "idx_raw_cce_project_id",
            "idx_raw_cce_workflow_id",
            "idx_raw_cce_skill_id",
            "idx_raw_cce_agent_id",
            "idx_raw_cce_hook_id",
            "idx_raw_cce_tool_id",
            "idx_raw_cce_correlation_id",
            "idx_raw_cce_event_type",
            "idx_raw_cce_received_at",
            "idx_raw_cce_event_timestamp",
            "idx_raw_cce_project_time",
            "idx_raw_cce_type_time",
            "idx_raw_cce_session_type",
        }
        assert required_indexes.issubset(
            idx_names
        ), f"Missing indexes: {required_indexes - idx_names}"
        conn.close()

    def test_migration_idempotent(self, tmp_path):
        """Running migration twice doesn't error (IF NOT EXISTS throughout)."""
        migration_path = (
            Path(__file__).parent.parent.parent
            / "core"
            / "event_store"
            / "migrations"
            / "066_raw_claude_code_events.sql"
        )
        db = tmp_path / "test.db"
        sql = migration_path.read_text(encoding="utf-8")
        conn = sqlite3.connect(str(db))
        conn.executescript(sql)
        conn.executescript(sql)  # second run — must not raise
        conn.close()
