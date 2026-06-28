"""Tests for LLM Guard Phase 2 — memory taint.

Proving PAIR:
  - Memory PAIR: tainted entry → tainted=1 | clean entry → tainted=0
  - Context-inject PAIR: tainted path detected by get_tainted_paths()

guard_events table dropped in migration 133 (all writers were test-only reachable;
no hook/CLI/projection ever called emit_memory_skip_event or guard_delta_pairs from
a production entry path). Tests for guard_events emission removed.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

# Ensure REPO_ROOT in sys.path before imports
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402


def _make_test_db(tmp_path: Path) -> Path:
    """Create a minimal studio.db with memory_entries taint columns.

    guard_events table not created — dropped in migration 133.
    """
    db_path = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memory_entries (
            memory_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            content TEXT NOT NULL,
            metadata JSON,
            importance REAL NOT NULL DEFAULT 0.5,
            created_at TEXT NOT NULL,
            last_accessed TEXT,
            access_count INTEGER NOT NULL DEFAULT 0,
            tags TEXT,
            project TEXT,
            skill TEXT,
            source_repo_id TEXT,
            tainted INTEGER NOT NULL DEFAULT 0,
            taint_reason TEXT,
            taint_timestamp TEXT
        );
    """)
    conn.commit()
    conn.close()
    return db_path


class TestMemoryTaintPair:
    """Memory PAIR: tainted source → tainted=1 | clean source → tainted=0"""

    def test_tainted_entry_has_tainted_flag(self, tmp_path):
        """A memory entry sourced from a tainted project_id gets tainted=1."""
        db_path = _make_test_db(tmp_path)
        project_id = str(uuid.uuid4())
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        # Insert memory entry from the project
        conn.execute(
            """INSERT INTO memory_entries
               (memory_id, source, category, content, importance, created_at, source_repo_id, tainted)
               VALUES (?, ?, ?, ?, ?, datetime('now'), ?, 0)""",
            (str(uuid.uuid4()), "repo_extract", "lesson", "learned something", 0.7, project_id),
        )
        conn.commit()

        # Taint all entries from project_id
        conn.execute(
            """UPDATE memory_entries SET tainted=1, taint_reason=?, taint_timestamp=datetime('now')
               WHERE source_repo_id=? AND tainted=0""",
            ("CRITICAL guard finding detected", project_id),
        )
        conn.commit()

        row = conn.execute(
            "SELECT tainted, taint_reason FROM memory_entries WHERE source_repo_id=?",
            (project_id,),
        ).fetchone()
        conn.close()

        assert row["tainted"] == 1
        assert "CRITICAL" in row["taint_reason"]

    def test_clean_entry_stays_untainted(self, tmp_path):
        """A memory entry from a clean (non-repo) source stays tainted=0."""
        db_path = _make_test_db(tmp_path)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        mem_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO memory_entries
               (memory_id, source, category, content, importance, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (mem_id, "manual", "general", "manual note", 0.5),
        )
        conn.commit()

        row = conn.execute(
            "SELECT tainted, source_repo_id FROM memory_entries WHERE memory_id=?", (mem_id,)
        ).fetchone()
        conn.close()

        assert row["tainted"] == 0
        assert row["source_repo_id"] is None


# TestGuardEventEmission removed — guard_events table dropped in migration 133;
# emit_memory_skip_event() is now a no-op; guard_delta_pairs() no longer writes to guard_events.


class TestContextInjectFilter:
    """Context-inject PAIR: clean entry surfaces | tainted entry skipped + guard_event."""

    def test_tainted_path_detected(self, tmp_path):
        """get_tainted_paths returns sources where tainted=1."""
        db_path = _make_test_db(tmp_path)
        conn = sqlite3.connect(str(db_path))
        mem_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO memory_entries
               (memory_id, source, category, content, importance, created_at, tainted)
               VALUES (?, 'memory/tainted-lesson.md', 'lesson', 'content', 0.5, datetime('now'), 1)""",
            (mem_id,),
        )
        conn.execute(
            """INSERT INTO memory_entries
               (memory_id, source, category, content, importance, created_at, tainted)
               VALUES (?, 'memory/clean-lesson.md', 'general', 'other', 0.5, datetime('now'), 0)""",
            (str(uuid.uuid4()),),
        )
        conn.commit()
        conn.close()

        from guardrails.memory_taint import get_tainted_paths  # noqa: E402

        tainted = get_tainted_paths(db_path)
        assert "memory/tainted-lesson.md" in tainted
        assert "memory/clean-lesson.md" not in tainted

    # test_memory_skip_event_emitted removed — guard_events dropped migration 133;
    # emit_memory_skip_event() is now a no-op (the skip detection logic is preserved
    # via get_tainted_paths() — callers still avoid injecting tainted memory).
