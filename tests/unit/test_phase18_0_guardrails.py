"""Tests for guardrails/evaluator.py data dependency update (Phase 18.0, C4)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import sys


@pytest.fixture(autouse=True, scope="module")
def _mock_heavy_deps():
    """Stub out heavy deps so guardrails.evaluator can be imported in tests."""
    stubs = {
        "core.event_store.studio_db": MagicMock(),
        "core.decisions": MagicMock(),
    }
    originals = {}
    for name, mock in stubs.items():
        if name not in sys.modules:
            sys.modules[name] = mock
            originals[name] = None
        else:
            originals[name] = sys.modules[name]
    yield
    for name, original in originals.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


@pytest.fixture
def in_memory_db():
    """SQLite in-memory DB with canonical_events and hook_invocations tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE canonical_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT,
            timestamp TEXT,
            session_id TEXT,
            project_id TEXT,
            severity TEXT,
            confidence TEXT,
            trace TEXT,
            payload TEXT,
            schema_version INTEGER,
            source_type TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE hook_invocations (
            id INTEGER PRIMARY KEY,
            hook_name TEXT,
            tool_name TEXT,
            session_id TEXT,
            invoked_at TEXT,
            duration_ms REAL
        )
    """)
    return conn


@pytest.fixture(scope="module")
def evaluator_module():
    """Import guardrails.evaluator once per module."""
    import importlib

    if "guardrails.evaluator" in sys.modules:
        importlib.reload(sys.modules["guardrails.evaluator"])
    from guardrails import evaluator

    return evaluator


class TestCustomQueryMatches:
    def test_valid_canonical_events_query_passes(self, evaluator_module, in_memory_db):
        """A valid SELECT against canonical_events must return True when rows match."""
        in_memory_db.execute(
            "INSERT INTO canonical_events (event_id, event_type, timestamp, session_id, project_id,"
            " severity, confidence, trace, payload, schema_version, source_type)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "ev1",
                "hook_finding.created",
                "2026-01-01",
                None,
                None,
                "info",
                "exact",
                "{}",
                "{}",
                1,
                "confirmed",
            ),
        )
        in_memory_db.commit()
        result = evaluator_module._custom_query_matches(
            in_memory_db,
            "SELECT event_id FROM canonical_events WHERE event_type = 'hook_finding.created'",
        )
        assert result is True

    def test_empty_canonical_events_returns_false(self, evaluator_module, in_memory_db):
        """Query against empty canonical_events must return False."""
        result = evaluator_module._custom_query_matches(
            in_memory_db,
            "SELECT event_id FROM canonical_events WHERE event_type = 'nonexistent'",
        )
        assert result is False

    def test_hook_invocations_query_is_allowed(self, evaluator_module, in_memory_db):
        """A valid SELECT against hook_invocations must be accepted."""
        in_memory_db.execute(
            "INSERT INTO hook_invocations (id, hook_name, tool_name, session_id, invoked_at, duration_ms)"
            " VALUES (?,?,?,?,?,?)",
            (1, "on-tool-activity", "Edit", "sess1", "2026-01-01", 12.5),
        )
        in_memory_db.commit()
        result = evaluator_module._custom_query_matches(
            in_memory_db,
            "SELECT id FROM hook_invocations WHERE hook_name = 'on-tool-activity'",
        )
        assert result is True

    def test_activity_log_query_raises(self, evaluator_module, in_memory_db):
        """A query referencing the removed activity_log table must raise EvaluationError."""
        with pytest.raises(evaluator_module.EvaluationError, match="activity_log"):
            evaluator_module._custom_query_matches(
                in_memory_db,
                "SELECT * FROM activity_log WHERE event_type = 'x'",
            )

    def test_non_select_query_raises(self, evaluator_module, in_memory_db):
        """Non-SELECT statements must raise EvaluationError."""
        with pytest.raises(evaluator_module.EvaluationError, match="read-only SELECT"):
            evaluator_module._custom_query_matches(
                in_memory_db,
                "DELETE FROM canonical_events",
            )

    def test_multiple_statements_raises(self, evaluator_module, in_memory_db):
        """Multiple statements in one query string must raise EvaluationError."""
        with pytest.raises(evaluator_module.EvaluationError, match="one SELECT statement"):
            evaluator_module._custom_query_matches(
                in_memory_db,
                "SELECT 1; SELECT 2 FROM canonical_events",
            )

    def test_unknown_table_raises(self, evaluator_module, in_memory_db):
        """Queries against any other table must raise EvaluationError."""
        with pytest.raises(evaluator_module.EvaluationError, match="canonical_events"):
            evaluator_module._custom_query_matches(
                in_memory_db,
                "SELECT * FROM some_other_table",
            )

    def test_evaluator_imports_without_error(self, evaluator_module):
        """guardrails.evaluator must expose expected public interface."""
        assert hasattr(evaluator_module, "evaluate")
        assert hasattr(evaluator_module, "_custom_query_matches")
        assert hasattr(evaluator_module, "CANONICAL_EVENTS_FIELDS")
        assert "activity_log" not in str(evaluator_module.CANONICAL_EVENTS_FIELDS)
