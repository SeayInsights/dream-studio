"""Unit tests for core.memory.ingestion — all ingestion consumers."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.memory.ingestion import (
    DecisionIngestionConsumer,
    GotchaIngestionConsumer,
    LessonIngestionConsumer,
    run_all_ingestion,
)
from core.memory.store import MemoryStore


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture()
def setup_db(db_path, monkeypatch):
    """Create test DB with raw_lessons and reg_gotchas + memory_entries tables."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            confidence TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'draft',
            title TEXT NOT NULL,
            what_happened TEXT,
            lesson TEXT,
            evidence TEXT,
            promoted_to TEXT,
            created_at TEXT NOT NULL,
            reviewed_at TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reg_gotchas (
            gotcha_id TEXT NOT NULL,
            skill_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            context TEXT,
            fix TEXT,
            keywords TEXT,
            discovered TEXT,
            times_hit INTEGER DEFAULT 0,
            last_hit TEXT,
            PRIMARY KEY (gotcha_id, skill_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_entries (
            memory_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            source_type TEXT DEFAULT 'unknown',
            source_id TEXT,
            lifecycle_state TEXT DEFAULT 'ACTIVE',
            metadata JSON,
            importance REAL NOT NULL DEFAULT 0.5,
            confidence REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            last_accessed TEXT,
            access_count INTEGER NOT NULL DEFAULT 0,
            tags TEXT,
            project TEXT,
            skill TEXT,
            provenance JSON,
            lineage JSON,
            relationships JSON
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_memory_lifecycle
        ON memory_entries(lifecycle_state)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_skill_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name TEXT NOT NULL,
            invoked_at TEXT NOT NULL,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            success INTEGER NOT NULL,
            execution_time_s REAL
        )
    """)

    # cor_skill_corrections dropped migration 131 (ingestion consumer retired).

    conn.execute("""
        CREATE TABLE IF NOT EXISTS canonical_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            trace TEXT DEFAULT '{}',
            severity TEXT DEFAULT 'info',
            payload TEXT DEFAULT '{}',
            actor TEXT,
            confidence_score REAL,
            source_type TEXT
        )
    """)

    conn.commit()
    conn.close()

    monkeypatch.setattr("core.memory.store.transaction", _make_tx(db_path))
    monkeypatch.setattr("core.memory.store.get_connection", _make_gc(db_path))
    monkeypatch.setattr("core.memory.ingestion.get_connection", _make_gc(db_path))


def _make_tx(db_path):
    from contextlib import contextmanager

    @contextmanager
    def _tx():
        conn = sqlite3.connect(db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    return _tx


def _make_gc(db_path):
    from contextlib import contextmanager

    @contextmanager
    def _gc(read_only=False):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    return _gc


def _seed_lessons(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO raw_lessons (lesson_id, source, confidence, status, title, what_happened, lesson, created_at)
        VALUES ('L-001', 'session', 'high', 'draft', 'Never mock the database',
                'Mocked tests passed but prod migration failed',
                'Integration tests must hit a real database',
                '2026-05-01T10:00:00Z')
    """)
    conn.execute("""
        INSERT INTO raw_lessons (lesson_id, source, confidence, status, title, lesson, created_at)
        VALUES ('L-002', 'review', 'medium', 'promoted', 'Check all selectors before rename',
                'Grep ALL selector variants across .css .astro .tsx before committing broad renames',
                '2026-05-02T10:00:00Z')
    """)
    conn.commit()
    conn.close()


def _seed_gotchas(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO reg_gotchas (gotcha_id, skill_id, severity, title, context, fix, keywords, discovered, times_hit)
        VALUES ('G-001', 'playwright', 'high', 'Ctrl+Z hits global undo',
                'Playwright keyboard shortcuts hit the editor, not the text element',
                'Use undo manager or avoid keyboard shortcuts in tests',
                'playwright,keyboard,undo', '2026-04-15T12:00:00Z', 3)
    """)
    conn.execute("""
        INSERT INTO reg_gotchas (gotcha_id, skill_id, severity, title, fix, keywords, discovered)
        VALUES ('G-002', 'build', 'critical', 'Python 3.14 breaks some deps',
                'Use Python 3.12 for compatibility',
                'python,version,compatibility', '2026-05-01T08:00:00Z')
    """)
    conn.commit()
    conn.close()


# ── Lesson ingestion ─────────────────────────────────────────────────────────


def test_lesson_ingestion_creates_entries(db_path, setup_db):
    _seed_lessons(db_path)
    store = MemoryStore(db_path)
    consumer = LessonIngestionConsumer()
    result = consumer.ingest(store)

    assert result.records_found == 2
    assert result.records_ingested == 2
    assert result.records_updated == 0
    assert len(result.errors) == 0


def test_lesson_ingestion_provenance(db_path, setup_db):
    _seed_lessons(db_path)
    store = MemoryStore(db_path)
    LessonIngestionConsumer().ingest(store)

    stats = store.stats()
    assert stats["by_source_type"].get("raw_lessons", 0) == 2

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM memory_entries WHERE source_id = 'L-001'").fetchone()
    conn.close()

    assert row is not None
    assert row["source"] == "lesson"
    assert row["source_type"] == "raw_lessons"
    assert row["lifecycle_state"] == "DRAFT"


def test_lesson_ingestion_is_idempotent(db_path, setup_db):
    _seed_lessons(db_path)
    store = MemoryStore(db_path)
    consumer = LessonIngestionConsumer()

    r1 = consumer.ingest(store)
    assert r1.records_ingested == 2

    r2 = consumer.ingest(store)
    assert r2.records_found == 0
    assert r2.records_ingested == 0

    stats = store.stats()
    assert stats["total_entries"] == 2


def test_lesson_content_includes_title_and_lesson(db_path, setup_db):
    _seed_lessons(db_path)
    store = MemoryStore(db_path)
    LessonIngestionConsumer().ingest(store)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT content FROM memory_entries WHERE source_id = 'L-001'").fetchone()
    conn.close()

    assert "Never mock the database" in row["content"]
    assert "Integration tests must hit a real database" in row["content"]


# ── Gotcha ingestion ─────────────────────────────────────────────────────────


def test_gotcha_ingestion_creates_entries(db_path, setup_db):
    _seed_gotchas(db_path)
    store = MemoryStore(db_path)
    consumer = GotchaIngestionConsumer()
    result = consumer.ingest(store)

    assert result.records_found == 2
    assert result.records_ingested == 2


def test_gotcha_ingestion_provenance(db_path, setup_db):
    _seed_gotchas(db_path)
    store = MemoryStore(db_path)
    GotchaIngestionConsumer().ingest(store)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM memory_entries WHERE source_id = 'G-001'").fetchone()
    conn.close()

    assert row["source"] == "gotcha"
    assert row["source_type"] == "reg_gotchas"
    assert row["lifecycle_state"] == "DRAFT"
    assert row["skill"] == "playwright"


def test_gotcha_ingestion_is_idempotent(db_path, setup_db):
    _seed_gotchas(db_path)
    store = MemoryStore(db_path)
    consumer = GotchaIngestionConsumer()

    consumer.ingest(store)
    r2 = consumer.ingest(store)
    assert r2.records_found == 0

    stats = store.stats()
    assert stats["total_entries"] == 2


def test_gotcha_severity_maps_to_importance(db_path, setup_db):
    _seed_gotchas(db_path)
    store = MemoryStore(db_path)
    GotchaIngestionConsumer().ingest(store)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    critical = conn.execute(
        "SELECT importance FROM memory_entries WHERE source_id = 'G-002'"
    ).fetchone()
    high = conn.execute(
        "SELECT importance FROM memory_entries WHERE source_id = 'G-001'"
    ).fetchone()
    conn.close()

    assert critical["importance"] == pytest.approx(0.95, abs=0.01)
    assert high["importance"] == pytest.approx(0.8, abs=0.01)


# ── Correction ingestion — RETIRED migration 131 ─────────────────────────────
# cor_skill_corrections table + CorrectionIngestionConsumer removed (the table's
# only writer skill_correct() was dead). Correction-ingestion tests deleted.


# ── Decision ingestion ───────────────────────────────────────────────────────


def _seed_decisions(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO canonical_events (event_id, event_type, timestamp, payload, severity, confidence_score, source_type)
        VALUES ('evt-d1', 'decision.model_selection', '2026-05-01T10:00:00Z',
                ?, 'info', 0.9, 'skill_router')
    """,
        (
            json.dumps(
                {
                    "decision_type": "model_selection",
                    "outcome": "Use Opus for architecture review",
                    "reasoning": {
                        "rationale": "Complex cross-cutting analysis requires strongest model"
                    },
                    "subsystem": "skill_router",
                    "confidence": 0.9,
                }
            ),
        ),
    )
    conn.execute(
        """
        INSERT INTO canonical_events (event_id, event_type, timestamp, payload, severity, source_type)
        VALUES ('evt-g1', 'guardrail.decision', '2026-05-02T10:00:00Z',
                ?, 'warning', 'guardrails')
    """,
        (
            json.dumps(
                {
                    "decision_type": "guardrail.policy_enforcement",
                    "outcome": "block",
                    "reasoning": {"rationale": "Critical security finding blocks deployment"},
                    "subsystem": "guardrails",
                }
            ),
        ),
    )
    conn.execute("""
        INSERT INTO canonical_events (event_id, event_type, timestamp, payload, severity, source_type)
        VALUES ('evt-other', 'workflow.started', '2026-05-02T10:00:00Z',
                '{"workflow_name": "build"}', 'info', 'workflow')
    """)
    conn.commit()
    conn.close()


def test_decision_ingestion_creates_entries(db_path, setup_db):
    _seed_decisions(db_path)
    store = MemoryStore(db_path)
    consumer = DecisionIngestionConsumer()
    result = consumer.ingest(store)

    assert result.records_found == 2
    assert result.records_ingested == 2


def test_decision_ingestion_provenance(db_path, setup_db):
    _seed_decisions(db_path)
    store = MemoryStore(db_path)
    DecisionIngestionConsumer().ingest(store)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM memory_entries WHERE source_id = 'evt-d1'").fetchone()
    conn.close()

    assert row["source"] == "decision"
    assert row["source_type"] == "canonical_events"
    assert "Opus" in row["content"]


def test_decision_ignores_non_decision_events(db_path, setup_db):
    _seed_decisions(db_path)
    store = MemoryStore(db_path)
    DecisionIngestionConsumer().ingest(store)

    stats = store.stats()
    assert stats["total_entries"] == 2


def test_decision_ingestion_is_idempotent(db_path, setup_db):
    _seed_decisions(db_path)
    store = MemoryStore(db_path)
    consumer = DecisionIngestionConsumer()
    consumer.ingest(store)
    r2 = consumer.ingest(store)
    assert r2.records_found == 0


# ── Combined ingestion ───────────────────────────────────────────────────────


def test_run_all_ingestion(db_path, setup_db):
    # CorrectionIngestionConsumer retired migration 131 — 3 consumers remain.
    _seed_lessons(db_path)
    _seed_gotchas(db_path)
    _seed_decisions(db_path)
    store = MemoryStore(db_path)
    results = run_all_ingestion(store)

    assert len(results) == 3

    total_ingested = sum(r.records_ingested for r in results)
    assert total_ingested == 6

    stats = store.stats()
    assert stats["total_entries"] == 6
    assert stats["by_memory_type"]["lesson"] == 2
    assert stats["by_memory_type"]["gotcha"] == 2
    assert stats["by_memory_type"]["decision"] == 2
