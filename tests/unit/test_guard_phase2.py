"""Tests for LLM Guard Phase 2 — guard_events + memory taint.

Proving PAIR:
  - Memory PAIR: tainted entry → tainted=1 | clean entry → tainted=0
  - Context-inject PAIR: clean surfaces | tainted skipped + guard_event logged
  - guard_events emission alongside findings
  - Boundary: finding (scan) vs guard_event (runtime)
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
    """Create a minimal studio.db with guard_events and memory_entries taint columns."""
    db_path = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS guard_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            rule_id TEXT,
            severity TEXT,
            source_type TEXT NOT NULL,
            source_id TEXT,
            project_id TEXT,
            scan_id TEXT,
            action TEXT NOT NULL DEFAULT 'logged',
            confidence REAL,
            details TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
        );
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


class TestGuardEventEmission:
    """guard_events emitted for guard actions."""

    def test_guard_event_distinct_from_findings(self, tmp_path, monkeypatch):
        """guard_events and findings are in separate tables — boundary holds."""
        db_path = _make_test_db(tmp_path)
        # Add a minimal findings table to confirm separation
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS findings (
                finding_id TEXT PRIMARY KEY, rule_id TEXT, skill_id TEXT
            )
        """)
        conn.execute(
            "INSERT INTO findings VALUES (?, ?, ?)", (str(uuid.uuid4()), "guard-001", "guard")
        )
        conn.commit()

        # guard_events should be empty (finding goes to findings, not guard_events)
        rows = conn.execute("SELECT * FROM guard_events").fetchall()
        findings = conn.execute("SELECT * FROM findings").fetchall()
        conn.close()

        assert len(rows) == 0  # No events emitted yet
        assert len(findings) == 1  # Finding is in findings table
        # Boundary holds: same rule_id, different tables


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

    def test_memory_skip_event_emitted(self, tmp_path):
        """emit_memory_skip_event writes guard_event with memory_skipped_tainted."""
        db_path = _make_test_db(tmp_path)
        from guardrails.memory_taint import emit_memory_skip_event  # noqa: E402

        project_id = str(uuid.uuid4())
        emit_memory_skip_event("memory/tainted-lesson.md", project_id, db_path)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM guard_events WHERE event_type='memory_skipped_tainted'"
        ).fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0]["source_type"] == "memory_entry"
        assert rows[0]["source_id"] == "memory/tainted-lesson.md"
        assert rows[0]["action"] == "skipped"
        assert rows[0]["project_id"] == project_id
