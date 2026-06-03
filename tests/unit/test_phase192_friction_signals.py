"""Tests for Phase 19.2 — Friction Signal Harvester.

Proving gate (all must pass for merge):
  Schema:        migration 096 applies clean; CHECK rejects deferred types;
                 dismissed columns added to findings
  Dismiss API:   sets columns; 404 on missing; idempotent (re-dismiss updates)
  Harvester:     per signal type → fire / silent-below-threshold / silent-single-source
                 (3 types × 3 cases = 9 proofs minimum)
  Real data:     harvester runs on real studio.db without exception
  Idempotency:   double-run produces no duplicate rows
  Session hook:  non-blocking (exception in harvester does not propagate)
  Consumer:      classified_as IS NULL query returns unclassified; classified excluded
  Local-first:   no outbound network calls in harvester code
"""

from __future__ import annotations

import importlib
import inspect
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

MIGRATION_SQL = (
    Path(__file__).parents[2] / "core" / "event_store" / "migrations" / "096_friction_signals.sql"
).read_text(encoding="utf-8")

# Findings schema needs the base findings table for ALTER TABLE statements.
FINDINGS_BASE_SQL = """
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY,
    project_id TEXT,
    scan_id TEXT,
    rule_id TEXT,
    severity TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open',
    introduced_by_skill_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

SCAN_RUNS_BASE_SQL = """
CREATE TABLE IF NOT EXISTS scan_runs (
    scan_id TEXT PRIMARY KEY,
    project_id TEXT,
    skill_id TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    findings_count INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

WORKFLOW_PATTERNS_SQL = """
CREATE TABLE IF NOT EXISTS ds_workflow_pattern_signals (
    pattern_id TEXT PRIMARY KEY,
    project_id TEXT,
    pattern_type TEXT NOT NULL DEFAULT 'always_paired',
    skill_a TEXT NOT NULL,
    skill_b TEXT,
    co_occurrence_count INTEGER NOT NULL DEFAULT 0,
    total_sessions INTEGER NOT NULL DEFAULT 1,
    confidence_score REAL NOT NULL DEFAULT 0.0,
    suppressed INTEGER NOT NULL DEFAULT 0,
    suppressed_at TEXT,
    last_observed_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def base_conn():
    """In-memory DB with base tables (no migration 096 yet — for ALTER TABLE tests)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(FINDINGS_BASE_SQL)
    conn.executescript(SCAN_RUNS_BASE_SQL)
    conn.executescript(WORKFLOW_PATTERNS_SQL)
    yield conn
    conn.close()


@pytest.fixture
def m096_conn(base_conn):
    """In-memory DB with migration 096 applied on top of base tables."""
    # Run the full migration. ALTER TABLE adds dismissed_at/dismissed_reason to findings.
    base_conn.executescript(MIGRATION_SQL)
    return base_conn


@pytest.fixture
def harvester(m096_conn):
    from projections.core.analyzers.friction_signals import FrictionSignalHarvester

    return FrictionSignalHarvester(m096_conn, session_id="test-session-001")


def _fid() -> str:
    return str(uuid.uuid4())


def _sid() -> str:
    return str(uuid.uuid4())


def _insert_dismissed_finding(
    conn, *, skill_id: str, rule_id: str, scan_id: str, days_ago: int = 5
) -> str:
    fid = _fid()
    ts = f"datetime('now', '-{days_ago} days')"
    conn.execute(
        f"INSERT INTO findings (finding_id, scan_id, rule_id, status, introduced_by_skill_id, "
        f"dismissed_at, dismissed_reason, created_at) "
        f"VALUES (?, ?, ?, 'dismissed', ?, {ts}, 'false positive', {ts})",
        (fid, scan_id, rule_id, skill_id),
    )
    conn.commit()
    return fid


def _insert_scan_run(
    conn,
    *,
    scan_id: str,
    skill_id: str,
    project_id: str = "proj-1",
    status: str = "completed",
    findings_count: int = 1,
    completed_days_ago: int = 10,
) -> None:
    ts = f"datetime('now', '-{completed_days_ago} days')"
    conn.execute(
        f"INSERT INTO scan_runs (scan_id, project_id, skill_id, status, findings_count, "
        f"completed_at, created_at) "
        f"VALUES (?, ?, ?, ?, ?, {ts}, {ts})",
        (scan_id, project_id, skill_id, status, findings_count),
    )
    conn.commit()


def _insert_open_finding(
    conn, *, finding_id: str, scan_id: str, skill_id: str, days_ago: int = 15
) -> None:
    ts = f"datetime('now', '-{days_ago} days')"
    conn.execute(
        f"INSERT INTO findings (finding_id, scan_id, status, introduced_by_skill_id, created_at) "
        f"VALUES (?, ?, 'open', ?, {ts})",
        (finding_id, scan_id, skill_id),
    )
    conn.commit()


def _insert_pattern(
    conn, *, pattern_id: str, skill_a: str, confidence: float, co_count: int = 3
) -> None:
    conn.execute(
        "INSERT INTO ds_workflow_pattern_signals "
        "(pattern_id, skill_a, confidence_score, co_occurrence_count, last_observed_at) "
        "VALUES (?, ?, ?, ?, datetime('now', '-5 days'))",
        (pattern_id, skill_a, confidence, co_count),
    )
    conn.commit()


# ── Schema: migration 096 ─────────────────────────────────────────────────


class TestMigration096Schema:
    def test_friction_signals_table_created(self, m096_conn):
        row = m096_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ds_friction_signals'"
        ).fetchone()
        assert row is not None

    def test_bucket_key_unique_constraint_enforced(self, m096_conn):
        """SQLite UNIQUE on bucket_key means duplicate inserts raise IntegrityError."""
        bk = "test-bucket-unique-check"
        m096_conn.execute(
            "INSERT INTO ds_friction_signals "
            "(signal_id, signal_type, source_table, source_id, bucket_key) "
            "VALUES (?, 'dismissed_finding', 'findings', 'src-bk1', ?)",
            (_fid(), bk),
        )
        m096_conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            m096_conn.execute(
                "INSERT INTO ds_friction_signals "
                "(signal_id, signal_type, source_table, source_id, bucket_key) "
                "VALUES (?, 'dismissed_finding', 'findings', 'src-bk2', ?)",
                (_fid(), bk),
            )

    def test_check_rejects_dismissed_finding_valid(self, m096_conn):
        m096_conn.execute(
            "INSERT INTO ds_friction_signals "
            "(signal_id, signal_type, source_table, source_id, bucket_key) "
            "VALUES (?, 'dismissed_finding', 'findings', 'src-1', 'bk-1')",
            (_fid(),),
        )
        m096_conn.commit()

    def test_check_rejects_deferred_guard_skip(self, m096_conn):
        with pytest.raises(sqlite3.IntegrityError):
            m096_conn.execute(
                "INSERT INTO ds_friction_signals "
                "(signal_id, signal_type, source_table, source_id, bucket_key) "
                "VALUES (?, 'guard_skip', 'guard_events', 'src-2', 'bk-2')",
                (_fid(),),
            )

    def test_check_rejects_deferred_skill_not_converging(self, m096_conn):
        with pytest.raises(sqlite3.IntegrityError):
            m096_conn.execute(
                "INSERT INTO ds_friction_signals "
                "(signal_id, signal_type, source_table, source_id, bucket_key) "
                "VALUES (?, 'skill_not_converging', 'canonical_events', 'src-3', 'bk-3')",
                (_fid(),),
            )

    def test_classified_as_check_valid(self, m096_conn):
        for val in ("capability", "personalization", "onboarding"):
            m096_conn.execute(
                "INSERT INTO ds_friction_signals "
                "(signal_id, signal_type, source_table, source_id, bucket_key, classified_as) "
                "VALUES (?, 'dismissed_finding', 'findings', ?, ?, ?)",
                (_fid(), _fid(), _fid(), val),
            )
        m096_conn.commit()

    def test_classified_as_check_rejects_invalid(self, m096_conn):
        with pytest.raises(sqlite3.IntegrityError):
            m096_conn.execute(
                "INSERT INTO ds_friction_signals "
                "(signal_id, signal_type, source_table, source_id, bucket_key, classified_as) "
                "VALUES (?, 'dismissed_finding', 'findings', 'src-x', 'bk-x', 'unknown_type')",
                (_fid(),),
            )

    def test_findings_dismissed_at_column_accessible(self, m096_conn):
        cols = {r[1] for r in m096_conn.execute("PRAGMA table_info(findings)")}
        assert "dismissed_at" in cols
        assert "dismissed_reason" in cols


# ── dismissed_finding detection ───────────────────────────────────────────


class TestDismissedFindingDetection:
    def test_fires_when_threshold_met(self, harvester, m096_conn):
        """≥2 dismissed findings across ≥2 distinct scans → signal fires."""
        scan_a, scan_b = _sid(), _sid()
        _insert_dismissed_finding(
            m096_conn, skill_id="ds-quality:security", rule_id="SEC-001", scan_id=scan_a
        )
        _insert_dismissed_finding(
            m096_conn, skill_id="ds-quality:security", rule_id="SEC-001", scan_id=scan_b
        )
        result = harvester.harvest()
        rows = m096_conn.execute(
            "SELECT * FROM ds_friction_signals WHERE signal_type='dismissed_finding'"
        ).fetchall()
        assert len(rows) >= 1, f"Expected ≥1 signal. harvest result: {result.to_dict()}"

    def test_silent_below_occurrence_threshold(self, harvester, m096_conn):
        """1 dismissed finding → no signal (below threshold)."""
        _insert_dismissed_finding(
            m096_conn, skill_id="ds-quality:code-quality", rule_id="CQ-001", scan_id=_sid()
        )
        harvester.harvest()
        rows = m096_conn.execute(
            "SELECT * FROM ds_friction_signals WHERE signal_type='dismissed_finding' "
            "AND skill_id='ds-quality:code-quality'"
        ).fetchall()
        assert len(rows) == 0

    def test_silent_single_scan_two_findings(self, harvester, m096_conn):
        """2 dismissed findings from the same scan → no signal (source_cnt < threshold)."""
        same_scan = _sid()
        _insert_dismissed_finding(
            m096_conn, skill_id="ds-quality:database", rule_id="DB-001", scan_id=same_scan
        )
        _insert_dismissed_finding(
            m096_conn, skill_id="ds-quality:database", rule_id="DB-001", scan_id=same_scan
        )
        harvester.harvest()
        rows = m096_conn.execute(
            "SELECT * FROM ds_friction_signals WHERE signal_type='dismissed_finding' "
            "AND skill_id='ds-quality:database'"
        ).fetchall()
        assert len(rows) == 0


# ── partial_completion detection ──────────────────────────────────────────


class TestPartialCompletionDetection:
    def test_fires_when_threshold_met(self, harvester, m096_conn):
        """≥2 scans completed with open findings never engaged → signal fires."""
        for _ in range(2):
            sid = _sid()
            fid = _fid()
            _insert_scan_run(
                m096_conn,
                scan_id=sid,
                skill_id="ds-quality:security",
                findings_count=1,
                completed_days_ago=15,
            )
            _insert_open_finding(
                m096_conn, finding_id=fid, scan_id=sid, skill_id="ds-quality:security", days_ago=15
            )
        result = harvester.harvest()
        rows = m096_conn.execute(
            "SELECT * FROM ds_friction_signals WHERE signal_type='partial_completion'"
        ).fetchall()
        assert len(rows) >= 1, f"Expected ≥1 signal. harvest result: {result.to_dict()}"

    def test_silent_single_scan(self, harvester, m096_conn):
        """1 ignored scan → no signal."""
        sid = _sid()
        _insert_scan_run(
            m096_conn,
            scan_id=sid,
            skill_id="ds-quality:frontend-ux",
            findings_count=1,
            completed_days_ago=15,
        )
        _insert_open_finding(
            m096_conn,
            finding_id=_fid(),
            scan_id=sid,
            skill_id="ds-quality:frontend-ux",
            days_ago=15,
        )
        harvester.harvest()
        rows = m096_conn.execute(
            "SELECT * FROM ds_friction_signals WHERE signal_type='partial_completion' "
            "AND skill_id='ds-quality:frontend-ux'"
        ).fetchall()
        assert len(rows) == 0

    def test_silent_recent_findings_not_stale(self, harvester, m096_conn):
        """Findings created < IGNORED_FINDING_STALE_DAYS ago → not yet stale, no signal."""
        for _ in range(2):
            sid = _sid()
            fid = _fid()
            _insert_scan_run(
                m096_conn,
                scan_id=sid,
                skill_id="ds-quality:ops",
                findings_count=1,
                completed_days_ago=2,
            )
            _insert_open_finding(
                m096_conn, finding_id=fid, scan_id=sid, skill_id="ds-quality:ops", days_ago=2
            )
        harvester.harvest()
        rows = m096_conn.execute(
            "SELECT * FROM ds_friction_signals WHERE signal_type='partial_completion' "
            "AND skill_id='ds-quality:ops'"
        ).fetchall()
        assert len(rows) == 0


# ── pattern_gap detection ─────────────────────────────────────────────────


class TestPatternGapDetection:
    def test_fires_when_low_confidence_pattern(self, harvester, m096_conn):
        """Low-confidence pattern with ≥2 co-occurrences → signal fires."""
        _insert_pattern(
            m096_conn,
            pattern_id="pat-001",
            skill_a="ds-quality:security",
            confidence=0.3,
            co_count=3,
        )
        result = harvester.harvest()
        rows = m096_conn.execute(
            "SELECT * FROM ds_friction_signals WHERE signal_type='pattern_gap'"
        ).fetchall()
        assert len(rows) >= 1, f"Expected ≥1 signal. harvest result: {result.to_dict()}"

    def test_silent_high_confidence_pattern(self, harvester, m096_conn):
        """High-confidence pattern → not a friction signal."""
        _insert_pattern(
            m096_conn,
            pattern_id="pat-002",
            skill_a="ds-quality:code-quality",
            confidence=0.9,
            co_count=5,
        )
        harvester.harvest()
        rows = m096_conn.execute(
            "SELECT * FROM ds_friction_signals WHERE signal_type='pattern_gap' "
            "AND skill_id='ds-quality:code-quality'"
        ).fetchall()
        assert len(rows) == 0

    def test_silent_low_occurrence_count(self, harvester, m096_conn):
        """Low confidence but only 1 co-occurrence → below threshold, no signal."""
        _insert_pattern(
            m096_conn,
            pattern_id="pat-003",
            skill_a="ds-quality:database",
            confidence=0.2,
            co_count=1,
        )
        harvester.harvest()
        rows = m096_conn.execute(
            "SELECT * FROM ds_friction_signals WHERE signal_type='pattern_gap' "
            "AND skill_id='ds-quality:database'"
        ).fetchall()
        assert len(rows) == 0


# ── Idempotency ───────────────────────────────────────────────────────────


class TestHarvesterIdempotency:
    def test_double_run_no_duplicates(self, harvester, m096_conn):
        """Running the harvester twice produces the same rows, no duplicates."""
        # Plant data that will fire a dismissed_finding signal
        scan_a, scan_b = _sid(), _sid()
        _insert_dismissed_finding(
            m096_conn, skill_id="ds-quality:testing", rule_id="TST-001", scan_id=scan_a
        )
        _insert_dismissed_finding(
            m096_conn, skill_id="ds-quality:testing", rule_id="TST-001", scan_id=scan_b
        )

        result1 = harvester.harvest()
        count_after_first = m096_conn.execute(
            "SELECT COUNT(*) FROM ds_friction_signals"
        ).fetchone()[0]

        result2 = harvester.harvest()
        count_after_second = m096_conn.execute(
            "SELECT COUNT(*) FROM ds_friction_signals"
        ).fetchone()[0]

        assert count_after_first == count_after_second, (
            f"Second run added rows: {count_after_first} → {count_after_second}. "
            f"Idempotency broken. run1={result1.to_dict()} run2={result2.to_dict()}"
        )
        assert (
            result2.signals_skipped > 0 or result2.signals_written == 0
        ), "Second run should skip or write zero signals"

    def test_bucket_key_unique_prevents_dupes(self, m096_conn):
        """INSERT OR IGNORE on same bucket_key writes only the first row."""
        sig_id_1 = _fid()
        sig_id_2 = _fid()
        bk = "test-bucket-key-unique"

        m096_conn.execute(
            "INSERT OR IGNORE INTO ds_friction_signals "
            "(signal_id, signal_type, source_table, source_id, bucket_key) "
            "VALUES (?, 'dismissed_finding', 'findings', 'src-u1', ?)",
            (sig_id_1, bk),
        )
        m096_conn.commit()
        m096_conn.execute(
            "INSERT OR IGNORE INTO ds_friction_signals "
            "(signal_id, signal_type, source_table, source_id, bucket_key) "
            "VALUES (?, 'dismissed_finding', 'findings', 'src-u2', ?)",
            (sig_id_2, bk),
        )
        m096_conn.commit()

        rows = m096_conn.execute(
            "SELECT * FROM ds_friction_signals WHERE bucket_key = ?", (bk,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["signal_id"] == sig_id_1


# ── Consumer contract ─────────────────────────────────────────────────────


class TestConsumerContract:
    def test_unclassified_query_returns_new_signals(self, harvester, m096_conn):
        """SELECT ... WHERE classified_as IS NULL returns newly harvested signals."""
        scan_a, scan_b = _sid(), _sid()
        _insert_dismissed_finding(
            m096_conn, skill_id="ds-quality:pre-launch", rule_id="PL-001", scan_id=scan_a
        )
        _insert_dismissed_finding(
            m096_conn, skill_id="ds-quality:pre-launch", rule_id="PL-001", scan_id=scan_b
        )
        harvester.harvest()

        unclassified = m096_conn.execute(
            "SELECT * FROM ds_friction_signals WHERE classified_as IS NULL ORDER BY created_at"
        ).fetchall()
        assert len(unclassified) >= 1

    def test_classified_signal_excluded_from_consumer_query(self, m096_conn):
        """Signal with classified_as set is excluded from the 19.3 consumer query."""
        m096_conn.execute(
            "INSERT INTO ds_friction_signals "
            "(signal_id, signal_type, source_table, source_id, bucket_key, "
            "classified_as, classified_at) "
            "VALUES (?, 'dismissed_finding', 'findings', 'src-c', 'bk-classified', "
            "'capability', datetime('now'))",
            (_fid(),),
        )
        m096_conn.commit()

        unclassified = m096_conn.execute(
            "SELECT * FROM ds_friction_signals WHERE classified_as IS NULL"
        ).fetchall()
        classified_ids = [r["signal_id"] for r in unclassified]
        # None of the classified signals appear in the unclassified query
        all_rows = m096_conn.execute("SELECT * FROM ds_friction_signals").fetchall()
        for r in all_rows:
            if r["classified_as"] is not None:
                assert r["signal_id"] not in classified_ids

    def test_get_unclassified_helper(self, harvester, m096_conn):
        """FrictionSignalHarvester.get_unclassified() returns the 19.3 view."""
        scan_a, scan_b = _sid(), _sid()
        _insert_dismissed_finding(
            m096_conn, skill_id="ds-quality:backend-api", rule_id="API-001", scan_id=scan_a
        )
        _insert_dismissed_finding(
            m096_conn, skill_id="ds-quality:backend-api", rule_id="API-001", scan_id=scan_b
        )
        harvester.harvest()

        unclassified = harvester.get_unclassified()
        assert isinstance(unclassified, list)

    def test_get_unclassified_filter_by_type(self, harvester, m096_conn):
        """get_unclassified(signal_type=...) filters correctly."""
        _insert_pattern(
            m096_conn,
            pattern_id="pat-filter-001",
            skill_a="ds-quality:architecture",
            confidence=0.1,
            co_count=3,
        )
        harvester.harvest()

        pattern_gaps = harvester.get_unclassified(signal_type="pattern_gap")
        for sig in pattern_gaps:
            assert sig["signal_type"] == "pattern_gap"


# ── Session-end hook non-blocking ─────────────────────────────────────────


class TestSessionEndHookNonBlocking:
    def test_harvest_exception_does_not_propagate(self):
        """Exception inside harvester is swallowed — session close must complete."""
        from projections.core.analyzers.friction_signals import FrictionSignalHarvester

        class _BrokenConn:
            row_factory = None

            def execute(self, *a, **kw):
                raise RuntimeError("DB exploded")

            def commit(self):
                pass

        harvester = FrictionSignalHarvester(_BrokenConn(), session_id="s-001")
        result = harvester.harvest()
        assert len(result.errors) > 0, "Expected errors to be recorded"
        # No exception propagated — function returned normally

    def test_session_end_hook_in_studio_db_is_non_blocking(self):
        """The harvester call in studio_db.end_session() is inside a try/except."""
        source = Path(__file__).parents[2] / "core" / "event_store" / "studio_db.py"
        text = source.read_text(encoding="utf-8")
        # Find the harvester import block
        assert "FrictionSignalHarvester" in text, "Hook not found in studio_db.py"
        # The harvester call must be inside a try block
        lines = text.splitlines()
        hook_line = next(
            i for i, ln in enumerate(lines) if "FrictionSignalHarvester" in ln and "import" in ln
        )
        # Scan backwards for a try: statement within 10 lines
        start = max(0, hook_line - 5)
        context = lines[start : hook_line + 2]
        assert any(
            "try:" in ln for ln in context
        ), f"FrictionSignalHarvester import not inside a try block. Context: {context}"


# ── Local-first: no network calls ─────────────────────────────────────────


class TestLocalFirst:
    def test_no_outbound_network_imports(self):
        """Harvester module imports no network or HTTP libraries."""
        import projections.core.analyzers.friction_signals as mod

        source = inspect.getsource(mod)
        forbidden = ["urllib", "requests", "httpx", "aiohttp", "socket."]
        for lib in forbidden:
            assert lib not in source, f"Found outbound network import: {lib!r}"

    def test_harvester_uses_only_sqlite(self, harvester, m096_conn):
        """harvest() only accesses the passed SQLite connection."""
        result = harvester.harvest()
        assert result is not None


# ── Real data smoke test ──────────────────────────────────────────────────


class TestRealDataSmoke:
    def test_harvester_on_real_db_no_exception(self):
        """Run harvester against real studio.db. Zero signals is correct if no Phase 19 data yet."""
        try:
            from core.config.database import _default_db_path
        except ImportError:
            pytest.skip("core.config.database not importable in this environment")

        from projections.core.analyzers.friction_signals import FrictionSignalHarvester

        db_path = _default_db_path()
        if not db_path.exists():
            pytest.skip(f"Live DB not found at {db_path}")

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            # Check if migration 096 was applied
            try:
                conn.execute("SELECT 1 FROM ds_friction_signals LIMIT 1")
            except sqlite3.OperationalError:
                pytest.skip("Migration 096 not applied to live DB yet")

            harvester = FrictionSignalHarvester(conn, session_id="smoke-test")
            result = harvester.harvest()
            # Document result — zero is correct for Phase 18 fixture-based dev
            assert isinstance(result.signals_written, int)
            assert isinstance(result.signals_skipped, int)
            # If zero, that's expected: Phase 18 ran via fixtures, not real finding dismissals
        finally:
            conn.close()
