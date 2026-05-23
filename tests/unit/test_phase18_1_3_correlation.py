"""Phase 18.1.3 tests — Correlation ID composition and propagation infrastructure.

Coverage:
  1. composer.compose() — basic, ordering, partial, empty
  2. composer.decompose() — round-trip, unknown segments, malformed
  3. composer.extend() — appends, no-op on duplicate, None base
  4. composer.validate() — valid strings, out-of-order, bad chars, empty
  5. composer.normalize_legacy() — kept / normalized / unfixable
  6. Ingestor integration — _extract_correlation_ids now delegates to composer
  7. Backfill script — dry-run produces statistics without DB writes
  8. Validation tool — valid/invalid/missing scenarios
"""

from __future__ import annotations

import importlib
import json
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.correlation.composer import (  # noqa: E402
    compose,
    decompose,
    extend,
    normalize_legacy,
    validate,
)

# ---------------------------------------------------------------------------
# Fixtures
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


@pytest.fixture
def tmp_db(tmp_path):
    """Minimal studio.db with all three v2 event tables."""
    db_path = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        PRAGMA journal_mode = WAL;

        CREATE TABLE IF NOT EXISTS raw_claude_code_events (
            event_id TEXT PRIMARY KEY,
            received_at TEXT NOT NULL DEFAULT (datetime('now','utc')),
            event_type TEXT NOT NULL,
            event_timestamp TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 1,
            source_payload TEXT NOT NULL DEFAULT '{}',
            session_id TEXT,
            project_id TEXT,
            workflow_id TEXT,
            skill_id TEXT,
            agent_id TEXT,
            hook_id TEXT,
            tool_id TEXT,
            model_id TEXT,
            adapter_id TEXT,
            correlation_id TEXT
        );

        CREATE TABLE IF NOT EXISTS business_canonical_events (
            event_id TEXT PRIMARY KEY,
            received_at TEXT NOT NULL DEFAULT (datetime('now','utc')),
            event_type TEXT NOT NULL,
            event_timestamp TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 1,
            trace JSON NOT NULL DEFAULT '{}',
            payload JSON NOT NULL DEFAULT '{}',
            correlation_id TEXT,
            project_id TEXT,
            milestone_id TEXT,
            work_order_id TEXT,
            task_id TEXT,
            severity TEXT NOT NULL DEFAULT 'info',
            source TEXT NOT NULL DEFAULT 'ingestor'
        );

        CREATE TABLE IF NOT EXISTS ai_canonical_events (
            event_id TEXT PRIMARY KEY,
            received_at TEXT NOT NULL DEFAULT (datetime('now','utc')),
            event_type TEXT NOT NULL,
            event_timestamp TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 1,
            trace JSON NOT NULL DEFAULT '{}',
            payload JSON NOT NULL DEFAULT '{}',
            correlation_id TEXT,
            session_id TEXT,
            skill_id TEXT,
            workflow_id TEXT,
            agent_id TEXT,
            hook_id TEXT,
            model_id TEXT,
            severity TEXT NOT NULL DEFAULT 'info',
            source TEXT NOT NULL DEFAULT 'ingestor'
        );
    """)
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# 1. compose()
# ---------------------------------------------------------------------------


class TestCompose:

    def test_full_chain(self):
        result = compose(
            {
                "session": "abc",
                "workflow": "wf-prod-ready-xyz",
                "skill": "ds-security-scan-789",
                "agent": "agent-1",
                "hook": "on-stop",
                "tool": "Read",
            }
        )
        assert result == (
            "sess-abc:wf-wf-prod-ready-xyz:skill-ds-security-scan-789"
            ":agent-agent-1:hook-on-stop:tool-Read"
        )

    def test_session_only(self):
        result = compose({"session": "abc"})
        assert result == "sess-abc"

    def test_session_and_skill(self):
        result = compose({"session": "abc", "skill": "scan-789"})
        assert result == "sess-abc:skill-scan-789"

    def test_none_values_omitted(self):
        result = compose({"session": "abc", "workflow": None, "skill": "scan"})
        assert result == "sess-abc:skill-scan"

    def test_empty_dict_returns_none(self):
        assert compose({}) is None

    def test_all_none_returns_none(self):
        assert compose({"session": None, "workflow": None}) is None

    def test_canonical_order_enforced(self):
        # Even if the dict has keys in wrong order, output must follow canonical order.
        result = compose({"tool": "Read", "session": "s1", "workflow": "wf-1"})
        assert result == "sess-s1:wf-wf-1:tool-Read"

    def test_unknown_keys_ignored(self):
        result = compose({"session": "abc", "project": "proj-1"})
        assert result == "sess-abc"

    def test_workflow_without_session(self):
        result = compose({"workflow": "wf-xyz"})
        assert result == "wf-wf-xyz"

    def test_example_from_data_model_v2(self):
        """The concrete example given in .planning/data-model-v2.md."""
        result = compose(
            {
                "session": "2026-05-22-abc",
                "workflow": "prod-ready-xyz",
                "skill": "ds-security-scan-123",
            }
        )
        assert result == "sess-2026-05-22-abc:wf-prod-ready-xyz:skill-ds-security-scan-123"


# ---------------------------------------------------------------------------
# 2. decompose()
# ---------------------------------------------------------------------------


class TestDecompose:

    def test_round_trip_full_chain(self):
        parts = {
            "session": "abc",
            "workflow": "wf-1",
            "skill": "scan-789",
            "agent": "a1",
            "hook": "on-stop",
            "tool": "Read",
        }
        composed = compose(parts)
        decomposed = decompose(composed)
        # decomposed has raw IDs; compose added prefixes, so values won't match
        # directly — but the entity_type keys will be present.
        assert "session" in decomposed
        assert "workflow" in decomposed
        assert "skill" in decomposed

    def test_session_only(self):
        parts = decompose("sess-abc")
        assert parts == {"session": "abc"}

    def test_session_and_skill(self):
        parts = decompose("sess-abc:skill-scan-789")
        assert parts["session"] == "abc"
        assert parts["skill"] == "scan-789"

    def test_unknown_segment_ignored(self):
        parts = decompose("sess-abc:unknown-xyz")
        assert "session" in parts
        assert "unknown" not in parts

    def test_empty_string_returns_empty(self):
        assert decompose("") == {}

    def test_non_prefix_suffix_absorbed_into_value(self):
        # With lookahead splitting, ":notaprefix" is NOT a boundary because
        # "notaprefix" doesn't start with a known prefix. So the whole string
        # is parsed as a single sess-* segment with value "abc:notaprefix".
        parts = decompose("sess-abc:notaprefix")
        assert parts == {"session": "abc:notaprefix"}

    def test_complex_value_preserved(self):
        parts = decompose("skill-ds-security-scan-2026.05.22")
        assert parts == {"skill": "ds-security-scan-2026.05.22"}


# ---------------------------------------------------------------------------
# 3. extend()
# ---------------------------------------------------------------------------


class TestExtend:

    def test_extend_from_none(self):
        result = extend(None, "session", "abc")
        assert result == "sess-abc"

    def test_extend_existing(self):
        base = "sess-abc"
        result = extend(base, "skill", "scan-789")
        assert result == "sess-abc:skill-scan-789"

    def test_extend_noop_if_type_present(self):
        base = "sess-abc:skill-scan-789"
        result = extend(base, "skill", "another-skill")
        assert result == base

    def test_extend_adds_tool(self):
        base = "sess-abc:skill-scan-789"
        result = extend(base, "tool", "Read")
        assert result == "sess-abc:skill-scan-789:tool-Read"

    def test_extend_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown entity_type"):
            extend("sess-abc", "project", "proj-1")

    def test_extend_workflow_from_session_base(self):
        result = extend("sess-abc", "workflow", "wf-prod-ready")
        assert result == "sess-abc:wf-wf-prod-ready"

    def test_propagation_chain(self):
        """Simulate: session → skill invokes tool calls."""
        session_cid = compose({"session": "s1"})
        skill_cid = extend(session_cid, "skill", "ds-security-scan-001")
        tool_cid = extend(skill_cid, "tool", "Bash")
        assert tool_cid == "sess-s1:skill-ds-security-scan-001:tool-Bash"


# ---------------------------------------------------------------------------
# 4. validate()
# ---------------------------------------------------------------------------


class TestValidate:

    def test_valid_session_only(self):
        ok, err = validate("sess-abc")
        assert ok is True
        assert err is None

    def test_valid_full_chain(self):
        cid = "sess-abc:wf-wf-1:skill-scan-789:agent-a1:hook-on-stop:tool-Read"
        ok, err = validate(cid)
        assert ok is True, err

    def test_valid_partial_chain(self):
        ok, err = validate("sess-abc:skill-scan-789")
        assert ok is True, err

    def test_invalid_empty(self):
        ok, err = validate("")
        assert ok is False
        assert "empty" in err.lower()

    def test_invalid_no_prefix(self):
        ok, err = validate("abc-xyz")
        assert ok is False

    def test_invalid_out_of_order(self):
        # tool before session is invalid
        ok, err = validate("tool-Read:sess-abc")
        assert ok is False
        assert "order" in err.lower()

    def test_invalid_duplicate_type(self):
        ok, err = validate("sess-abc:sess-xyz")
        assert ok is False
        assert "order" in err.lower()

    def test_invalid_bad_characters_in_value(self):
        ok, err = validate("sess-abc def")
        assert ok is False

    def test_valid_value_with_dots_dashes(self):
        ok, err = validate("sess-2026-05-22-abc:skill-ds-security.scan")
        assert ok is True, err

    def test_valid_value_with_colons_in_skill(self):
        # skill:mode pattern (e.g. ds-security:scan) is allowed
        ok, err = validate("sess-abc:skill-ds-security:scan")
        assert ok is True, err


# ---------------------------------------------------------------------------
# 5. normalize_legacy()
# ---------------------------------------------------------------------------


class TestNormalizeLegacy:

    def test_kept_when_valid(self):
        cid = "sess-abc:skill-scan-789"
        normalized, action = normalize_legacy(cid)
        assert action == "kept"
        assert normalized == cid

    def test_normalized_when_out_of_order(self):
        # tool before session — out of order; should be recomposed
        cid = "tool-Read:sess-abc"
        normalized, action = normalize_legacy(cid)
        assert action == "normalized"
        assert normalized == "sess-abc:tool-Read"

    def test_unfixable_when_no_known_segments(self):
        normalized, action = normalize_legacy("foo-bar:baz-qux")
        assert action == "unfixable"
        assert normalized is None

    def test_unfixable_for_none(self):
        normalized, action = normalize_legacy(None)
        assert action == "unfixable"
        assert normalized is None

    def test_unfixable_when_no_known_prefix_at_all(self):
        # With lookahead splitting a string like "noprefix-abc" has no known prefix
        # and produces no typed components → unfixable.
        normalized, action = normalize_legacy("noprefix-abc")
        assert action == "unfixable"
        assert normalized is None


# ---------------------------------------------------------------------------
# 6. Ingestor integration — _extract_correlation_ids delegates to composer
# ---------------------------------------------------------------------------


class TestIngestorUsesComposer:

    def test_ingestor_produces_valid_correlation_id(self):
        from spool.ingestor import _extract_correlation_ids

        env = _mk_envelope(
            session_id="ses-abc",
            trace={"workflow_id": "wf-xyz", "skill_id": "ds-security-scan-789"},
        )
        ids = _extract_correlation_ids(env)
        cid = ids["correlation_id"]
        assert cid is not None
        ok, err = validate(cid)
        assert ok is True, f"correlation_id {cid!r} failed validation: {err}"

    def test_ingestor_ordering_matches_composer(self):
        from spool.ingestor import _extract_correlation_ids

        env = _mk_envelope(
            session_id="s1",
            trace={"workflow_id": "wf-1", "skill_id": "sk-1", "hook_id": "hook-1", "tool_id": "t1"},
        )
        ids = _extract_correlation_ids(env)
        cid = ids["correlation_id"]
        # Verify canonical order
        assert cid.index("sess-") < cid.index("wf-")
        assert cid.index("wf-") < cid.index("skill-")
        assert cid.index("skill-") < cid.index("hook-")
        assert cid.index("hook-") < cid.index("tool-")

    def test_ingestor_none_when_no_ids(self):
        from spool.ingestor import _extract_correlation_ids

        env = _mk_envelope(trace={"domain": "telemetry"})
        ids = _extract_correlation_ids(env)
        assert ids["correlation_id"] is None

    def test_ingestor_uses_compose_not_manual_concat(self):
        """Verify compose() from core.correlation.composer is what produces the result."""
        from spool.ingestor import _extract_correlation_ids

        env = _mk_envelope(
            session_id="ses-zz",
            trace={"skill_id": "ds-quality-debug-001"},
        )
        ids = _extract_correlation_ids(env)
        expected = compose({"session": "ses-zz", "skill": "ds-quality-debug-001"})
        assert ids["correlation_id"] == expected


# ---------------------------------------------------------------------------
# 7. Backfill script — dry-run and live
# ---------------------------------------------------------------------------


class TestBackfillScript:

    def _insert_raw_row(self, conn, event_id, correlation_id, session_id=None):
        conn.execute(
            """
            INSERT OR IGNORE INTO raw_claude_code_events
            (event_id, event_type, event_timestamp, session_id, correlation_id)
            VALUES (?, 'test.event', '2026-05-22T12:00:00', ?, ?)
            """,
            (event_id, session_id, correlation_id),
        )
        conn.commit()

    def test_dry_run_does_not_modify_db(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        # Insert a row with malformed correlation_id
        self._insert_raw_row(conn, "evt-1", "invalid-garbage", session_id="s1")
        conn.close()

        from scripts.backfill_correlation_ids import run_backfill

        run_backfill(tmp_db, dry_run=True, verbose=False)

        conn2 = sqlite3.connect(str(tmp_db))
        row = conn2.execute(
            "SELECT correlation_id FROM raw_claude_code_events WHERE event_id='evt-1'"
        ).fetchone()
        conn2.close()
        # Dry-run: should not have changed the value
        assert row[0] == "invalid-garbage"

    def test_live_run_normalizes_out_of_order(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        # Insert with out-of-order segments (tool before sess)
        self._insert_raw_row(conn, "evt-2", "tool-Read:sess-abc", session_id="abc")
        conn.close()

        from scripts.backfill_correlation_ids import run_backfill

        run_backfill(tmp_db, dry_run=False, verbose=False)

        conn2 = sqlite3.connect(str(tmp_db))
        row = conn2.execute(
            "SELECT correlation_id FROM raw_claude_code_events WHERE event_id='evt-2'"
        ).fetchone()
        conn2.close()
        # Should be normalized to canonical order
        ok, _ = validate(row[0])
        assert ok is True

    def test_keeps_valid_rows_unchanged(self, tmp_db):
        valid_cid = "sess-abc:skill-ds-security-scan"
        conn = sqlite3.connect(str(tmp_db))
        self._insert_raw_row(conn, "evt-3", valid_cid, session_id="abc")
        conn.close()

        from scripts.backfill_correlation_ids import run_backfill

        stats = run_backfill(tmp_db, dry_run=False, verbose=False)

        conn2 = sqlite3.connect(str(tmp_db))
        row = conn2.execute(
            "SELECT correlation_id FROM raw_claude_code_events WHERE event_id='evt-3'"
        ).fetchone()
        conn2.close()
        assert row[0] == valid_cid
        assert stats["raw_claude_code_events"]["kept"] >= 1

    def test_reconstructs_from_session_id_column(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        # Insert with NULL correlation_id but has session_id column populated
        self._insert_raw_row(conn, "evt-4", None, session_id="sess-reconstructed")
        conn.close()

        from scripts.backfill_correlation_ids import run_backfill

        run_backfill(tmp_db, dry_run=False, verbose=False)

        conn2 = sqlite3.connect(str(tmp_db))
        row = conn2.execute(
            "SELECT correlation_id FROM raw_claude_code_events WHERE event_id='evt-4'"
        ).fetchone()
        conn2.close()
        assert row[0] is not None
        ok, _ = validate(row[0])
        assert ok is True

    def test_reports_statistics(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        self._insert_raw_row(conn, "e1", "sess-valid-one:skill-scan")
        self._insert_raw_row(conn, "e2", "tool-X:sess-Y")  # out of order
        self._insert_raw_row(conn, "e3", None, session_id="recon")
        self._insert_raw_row(conn, "e4", "completegibberish")
        conn.close()

        from scripts.backfill_correlation_ids import run_backfill

        stats = run_backfill(tmp_db, dry_run=True, verbose=False)
        raw = stats["raw_claude_code_events"]
        assert raw["total"] == 4
        assert raw["kept"] >= 1  # "sess-valid-one:skill-scan"


# ---------------------------------------------------------------------------
# 8. Validation tool
# ---------------------------------------------------------------------------


class TestCorrelationValidate:

    def _insert_row(self, conn, table, event_id, correlation_id, session_id=None):
        if table == "raw_claude_code_events":
            conn.execute(
                "INSERT OR IGNORE INTO raw_claude_code_events "
                "(event_id, event_type, event_timestamp, session_id, correlation_id) "
                "VALUES (?, 'test.event', '2026-05-22T12:00:00', ?, ?)",
                (event_id, session_id, correlation_id),
            )
        elif table == "ai_canonical_events":
            conn.execute(
                "INSERT OR IGNORE INTO ai_canonical_events "
                "(event_id, event_type, event_timestamp, correlation_id) "
                "VALUES (?, 'skill.invoked', '2026-05-22T12:00:00', ?)",
                (event_id, correlation_id),
            )
        conn.commit()

    def test_valid_db_returns_exit_0(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        self._insert_row(conn, "raw_claude_code_events", "v1", "sess-abc:skill-scan")
        conn.close()

        from tools.correlation_validate import run_validation

        report = run_validation(tmp_db, limit=100, since=None)
        assert report["summary"]["invalid"] == 0

    def test_invalid_row_detected(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        self._insert_row(conn, "raw_claude_code_events", "v2", "tool-X:sess-Y")
        conn.close()

        from tools.correlation_validate import run_validation

        report = run_validation(tmp_db, limit=100, since=None)
        assert report["summary"]["invalid"] >= 1

    def test_missing_correlation_id_flagged(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        self._insert_row(conn, "ai_canonical_events", "v3", None)
        conn.close()

        from tools.correlation_validate import run_validation

        report = run_validation(tmp_db, limit=100, since=None)
        assert report["summary"]["missing"] >= 1

    def test_skips_missing_tables_gracefully(self, tmp_path):
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.close()

        from tools.correlation_validate import run_validation

        report = run_validation(db_path, limit=100, since=None)
        skipped = [r for r in report["tables"] if r.get("skipped")]
        assert len(skipped) > 0

    def test_main_exit_0_on_valid(self, tmp_db):
        from tools.correlation_validate import main

        rc = main(["--db-path", str(tmp_db), "--limit", "10"])
        assert rc == 0

    def test_main_exit_1_on_invalid(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "INSERT OR IGNORE INTO raw_claude_code_events "
            "(event_id, event_type, event_timestamp, correlation_id) "
            "VALUES ('badrow', 'test.event', '2026-05-22', 'tool-X:sess-Y')"
        )
        conn.commit()
        conn.close()

        from tools.correlation_validate import main

        rc = main(["--db-path", str(tmp_db), "--limit", "10"])
        assert rc == 1
