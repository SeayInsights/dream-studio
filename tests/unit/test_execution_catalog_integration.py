"""Phase 4C integration tests — catalog-backed execution lifecycle validation.

Proves that ExecutionGraphManager uses the catalog for advisory state validation,
that persisted lowercase DB strings are preserved, and that no Enum objects leak
into SQLite.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.ontology.lifecycles import (
    LIFECYCLE_CATALOG,
    DocumentLifecycle,
    ExecutionLifecycle,
    MemoryLifecycle,
    to_db_value,
)

_EXECUTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    parent_id TEXT,
    project_id TEXT,
    prd_id TEXT,
    plan_id TEXT,
    phase_id TEXT,
    wave_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    metadata JSON,
    context_hash TEXT,
    context_summary TEXT,
    context_tokens INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    duration_seconds REAL
);

CREATE TABLE IF NOT EXISTS execution_dependencies (
    dependency_id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    dependency_type TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS execution_outputs (
    output_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    output_type TEXT NOT NULL,
    output_hash TEXT,
    output_summary TEXT,
    output_data JSON,
    file_paths TEXT,
    tokens_produced INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@pytest.fixture()
def graph(tmp_path, monkeypatch):
    """ExecutionGraphManager backed by a temp DB."""
    db_path = str(tmp_path / "test_exec.db")

    conn = sqlite3.connect(db_path)
    conn.executescript(_EXECUTION_SCHEMA)
    conn.close()

    monkeypatch.setattr("core.execution.graph.get_connection", _make_gc(db_path))
    monkeypatch.setattr("core.execution.graph.DatabaseContext", _make_dc(db_path))

    from core.execution.graph import ExecutionGraphManager

    return ExecutionGraphManager()


def _make_gc(db_path):
    @contextmanager
    def _gc(read_only=False):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    return _gc


class _make_dc:
    """Replacement for DatabaseContext that targets the temp DB."""

    def __init__(self, db_path):
        self._db_path = db_path
        self._read_only = False

    def __call__(self, read_only=False):
        inst = _make_dc(self._db_path)
        inst._read_only = read_only
        return inst

    def __enter__(self):
        self._conn = sqlite3.connect(self._db_path)
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None and not self._read_only:
            self._conn.commit()
        self._conn.close()


def _raw_status(db_path: str, node_id: str) -> str:
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT status FROM execution_nodes WHERE node_id = ?",
        (node_id,),
    ).fetchone()
    conn.close()
    return row[0] if row else None


# ── Module-level constants ──────────────────────────────────────────────────


class TestExecutionConstants:
    def test_pending_constant_is_lowercase(self):
        from core.execution.graph import _PENDING

        assert _PENDING == "pending"

    def test_active_constant_is_lowercase(self):
        from core.execution.graph import _ACTIVE

        assert _ACTIVE == "active"

    def test_terminal_states_are_lowercase(self):
        from core.execution.graph import _TERMINAL_STATES

        assert "completed" in _TERMINAL_STATES
        assert "failed" in _TERMINAL_STATES
        assert "skipped" in _TERMINAL_STATES

    def test_constants_are_plain_strings(self):
        from core.execution.graph import _PENDING, _ACTIVE, _TERMINAL_STATES

        assert type(_PENDING) is str
        assert type(_ACTIVE) is str
        for s in _TERMINAL_STATES:
            assert type(s) is str

    def test_constants_derived_from_enum(self):
        from core.execution.graph import _PENDING, _ACTIVE, _TERMINAL_STATES

        assert to_db_value(ExecutionLifecycle.PENDING) == _PENDING
        assert to_db_value(ExecutionLifecycle.ACTIVE) == _ACTIVE
        assert (
            to_db_value(ExecutionLifecycle.COMPLETED),
            to_db_value(ExecutionLifecycle.FAILED),
            to_db_value(ExecutionLifecycle.SKIPPED),
        ) == _TERMINAL_STATES


# ── Node creation persists lowercase string ─────────────────────────────────


class TestNodeCreationStatus:
    def test_new_node_defaults_to_pending(self, graph, tmp_path):
        db_path = str(tmp_path / "test_exec.db")
        node_id = graph.create_node(node_type="task", title="Test")
        raw = _raw_status(db_path, node_id)
        assert raw == "pending"

    def test_default_status_matches_enum(self, graph, tmp_path):
        db_path = str(tmp_path / "test_exec.db")
        node_id = graph.create_node(node_type="task", title="Test")
        raw = _raw_status(db_path, node_id)
        assert raw == to_db_value(ExecutionLifecycle.PENDING)

    def test_default_status_is_plain_string(self, graph, tmp_path):
        db_path = str(tmp_path / "test_exec.db")
        node_id = graph.create_node(node_type="task", title="Test")
        raw = _raw_status(db_path, node_id)
        assert type(raw) is str
        assert not isinstance(raw, ExecutionLifecycle)


# ── Status update persists lowercase strings ────────────────────────────────


class TestStatusUpdateStringPreservation:
    def test_active_persisted_as_lowercase(self, graph, tmp_path):
        db_path = str(tmp_path / "test_exec.db")
        node_id = graph.create_node(node_type="task", title="Test")
        graph.update_status(node_id, "active")
        assert _raw_status(db_path, node_id) == "active"

    def test_completed_persisted_as_lowercase(self, graph, tmp_path):
        db_path = str(tmp_path / "test_exec.db")
        node_id = graph.create_node(node_type="task", title="Test")
        graph.update_status(node_id, "completed", duration_seconds=10)
        assert _raw_status(db_path, node_id) == "completed"

    def test_failed_persisted_as_lowercase(self, graph, tmp_path):
        db_path = str(tmp_path / "test_exec.db")
        node_id = graph.create_node(node_type="task", title="Test")
        graph.update_status(node_id, "failed")
        assert _raw_status(db_path, node_id) == "failed"

    def test_skipped_persisted_as_lowercase(self, graph, tmp_path):
        db_path = str(tmp_path / "test_exec.db")
        node_id = graph.create_node(node_type="task", title="Test")
        graph.update_status(node_id, "skipped")
        assert _raw_status(db_path, node_id) == "skipped"

    def test_blocked_persisted_as_lowercase(self, graph, tmp_path):
        db_path = str(tmp_path / "test_exec.db")
        node_id = graph.create_node(node_type="task", title="Test")
        graph.update_status(node_id, "blocked")
        assert _raw_status(db_path, node_id) == "blocked"

    def test_all_execution_states_accepted(self, graph, tmp_path):
        db_path = str(tmp_path / "test_exec.db")
        for member in ExecutionLifecycle:
            state = to_db_value(member)
            node_id = graph.create_node(node_type="task", title=f"Test {state}")
            graph.update_status(node_id, state)
            assert _raw_status(db_path, node_id) == state


# ── No Enum objects in SQLite ───────────────────────────────────────────────


class TestNoEnumInSQLite:
    def test_status_typeof_is_text(self, graph, tmp_path):
        db_path = str(tmp_path / "test_exec.db")
        node_id = graph.create_node(node_type="task", title="Test")
        graph.update_status(node_id, "active")

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT status, typeof(status) FROM execution_nodes WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        conn.close()

        assert row[0] == "active"
        assert row[1] == "text"

    def test_node_status_field_is_str_type(self, graph):
        node_id = graph.create_node(node_type="task", title="Test")
        graph.update_status(node_id, "completed", duration_seconds=5)
        node = graph.get_node(node_id)
        assert type(node.status) is str


# ── Advisory catalog validation ─────────────────────────────────────────────


class TestAdvisoryValidation:
    def test_valid_state_no_warning(self, graph, caplog):
        node_id = graph.create_node(node_type="task", title="Test")
        with caplog.at_level(logging.WARNING, logger="core.execution.graph"):
            graph.update_status(node_id, "active")
        assert "Unrecognized execution status" not in caplog.text

    def test_invalid_state_logs_warning(self, graph, caplog):
        node_id = graph.create_node(node_type="task", title="Test")
        with caplog.at_level(logging.WARNING, logger="core.execution.graph"):
            graph.update_status(node_id, "NONEXISTENT")
        assert "Unrecognized execution status" in caplog.text

    def test_uppercase_active_logs_warning(self, graph, caplog):
        node_id = graph.create_node(node_type="task", title="Test")
        with caplog.at_level(logging.WARNING, logger="core.execution.graph"):
            graph.update_status(node_id, "ACTIVE")
        assert "Unrecognized execution status" in caplog.text

    def test_memory_state_logs_warning(self, graph, caplog):
        node_id = graph.create_node(node_type="task", title="Test")
        with caplog.at_level(logging.WARNING, logger="core.execution.graph"):
            graph.update_status(node_id, "DRAFT")
        assert "Unrecognized execution status" in caplog.text


# ── Catalog domain key verification ─────────────────────────────────────────


class TestCatalogDomainKey:
    def test_workflow_domain_registered(self):
        assert LIFECYCLE_CATALOG.has_lifecycle("workflow") is True

    def test_workflow_uses_execution_lifecycle(self):
        assert LIFECYCLE_CATALOG.get_lifecycle("workflow") is ExecutionLifecycle

    def test_all_execution_states_valid_in_catalog(self):
        for member in ExecutionLifecycle:
            assert LIFECYCLE_CATALOG.validate_state("workflow", member.value) is True

    def test_catalog_transitions_match_execution_states(self):
        assert LIFECYCLE_CATALOG.validate_transition("workflow", "pending", "active") is True
        assert LIFECYCLE_CATALOG.validate_transition("workflow", "active", "completed") is True
        assert LIFECYCLE_CATALOG.validate_transition("workflow", "active", "failed") is True
        assert LIFECYCLE_CATALOG.validate_transition("workflow", "completed", "active") is False

    def test_memory_states_invalid_in_workflow_domain(self):
        assert LIFECYCLE_CATALOG.validate_state("workflow", "DRAFT") is False
        assert LIFECYCLE_CATALOG.validate_state("workflow", "ARCHIVED") is False
        assert LIFECYCLE_CATALOG.validate_state("workflow", "PROMOTED") is False


# ── Cross-domain isolation ──────────────────────────────────────────────────


class TestCrossDomainIsolation:
    def test_execution_active_not_equal_to_raw_string(self):
        assert ExecutionLifecycle.ACTIVE != "active"

    def test_execution_active_not_equal_to_document_active(self):
        assert ExecutionLifecycle.ACTIVE != DocumentLifecycle.ACTIVE

    def test_execution_active_not_equal_to_memory_active(self):
        assert ExecutionLifecycle.ACTIVE != MemoryLifecycle.ACTIVE

    def test_same_persisted_value_different_domains(self):
        assert to_db_value(ExecutionLifecycle.ACTIVE) == to_db_value(DocumentLifecycle.ACTIVE)
        assert ExecutionLifecycle.ACTIVE != DocumentLifecycle.ACTIVE

    def test_execution_lifecycle_is_not_str(self):
        assert not isinstance(ExecutionLifecycle.ACTIVE, str)
        assert not isinstance(ExecutionLifecycle.PENDING, str)


# ── Task lifecycle flow ─────────────────────────────────────────────────────


class TestTaskLifecycleFlow:
    def test_pending_to_active_to_completed(self, graph):
        node_id = graph.create_node(node_type="task", title="Lifecycle test")
        node = graph.get_node(node_id)
        assert node.status == to_db_value(ExecutionLifecycle.PENDING)

        graph.update_status(node_id, to_db_value(ExecutionLifecycle.ACTIVE))
        node = graph.get_node(node_id)
        assert node.status == to_db_value(ExecutionLifecycle.ACTIVE)
        assert node.started_at is not None

        graph.update_status(node_id, to_db_value(ExecutionLifecycle.COMPLETED), duration_seconds=30)
        node = graph.get_node(node_id)
        assert node.status == to_db_value(ExecutionLifecycle.COMPLETED)
        assert node.completed_at is not None

    def test_pending_to_active_to_failed(self, graph):
        node_id = graph.create_node(node_type="task", title="Fail test")
        graph.update_status(node_id, to_db_value(ExecutionLifecycle.ACTIVE))
        graph.update_status(node_id, to_db_value(ExecutionLifecycle.FAILED), duration_seconds=5)
        node = graph.get_node(node_id)
        assert node.status == to_db_value(ExecutionLifecycle.FAILED)
        assert node.completed_at is not None

    def test_pending_to_skipped(self, graph):
        node_id = graph.create_node(node_type="task", title="Skip test")
        graph.update_status(node_id, to_db_value(ExecutionLifecycle.SKIPPED))
        node = graph.get_node(node_id)
        assert node.status == to_db_value(ExecutionLifecycle.SKIPPED)

    def test_pending_to_blocked(self, graph):
        node_id = graph.create_node(node_type="task", title="Block test")
        graph.update_status(node_id, to_db_value(ExecutionLifecycle.BLOCKED))
        node = graph.get_node(node_id)
        assert node.status == to_db_value(ExecutionLifecycle.BLOCKED)
