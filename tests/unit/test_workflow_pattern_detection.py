"""Tests for workflow pattern detection (18.8.4).

Fixtures match the real canonical_events schema:
  - Events are inserted with full trace JSON blobs
  - Sessions are bounded by system.session.recorded / system.session.closed events
  - skill_id = json_extract(trace, '$.skill_specifier')
  - project_id = json_extract(trace, '$.project_id')
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from projections.core.analyzers.workflow_patterns import (
    WorkflowPatternAnalyzer,
    EVENT_SESSION_CLOSED,
    EVENT_SESSION_STARTED,
    EVENT_SKILL_INVOKED,
    EVENT_WO_CLOSED,
    _pattern_id,
)

# ── DB helpers ────────────────────────────────────────────────────────────


def _make_db(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE canonical_events (
            event_id   TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            trace      TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE ds_workflow_pattern_signals (
            pattern_id          TEXT PRIMARY KEY,
            project_id          TEXT,
            pattern_type        TEXT NOT NULL,
            skill_a             TEXT NOT NULL,
            skill_b             TEXT,
            co_occurrence_count INTEGER NOT NULL DEFAULT 0,
            total_sessions      INTEGER NOT NULL DEFAULT 1,
            confidence_score    REAL NOT NULL,
            suppressed          INTEGER NOT NULL DEFAULT 0,
            suppressed_at       TEXT,
            last_observed_at    TEXT NOT NULL DEFAULT (datetime('now')),
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def _session_start(conn, session_event_id, project_id="proj-a", ts="2026-06-01T10:00:00"):
    conn.execute(
        "INSERT INTO canonical_events (event_id, event_type, trace, created_at) VALUES (?, ?, ?, ?)",
        (session_event_id, EVENT_SESSION_STARTED, json.dumps({"project_id": project_id}), ts),
    )


def _session_end(conn, close_event_id, project_id="proj-a", ts="2026-06-01T11:00:00"):
    conn.execute(
        "INSERT INTO canonical_events (event_id, event_type, trace, created_at) VALUES (?, ?, ?, ?)",
        (close_event_id, EVENT_SESSION_CLOSED, json.dumps({"project_id": project_id}), ts),
    )


def _skill(conn, event_id, skill_specifier, project_id="proj-a", ts="2026-06-01T10:30:00"):
    conn.execute(
        "INSERT INTO canonical_events (event_id, event_type, trace, created_at) VALUES (?, ?, ?, ?)",
        (
            event_id,
            EVENT_SKILL_INVOKED,
            json.dumps({"skill_specifier": skill_specifier, "project_id": project_id}),
            ts,
        ),
    )


def _wo_close(conn, event_id, project_id="proj-a", ts="2026-06-01T10:45:00"):
    conn.execute(
        "INSERT INTO canonical_events (event_id, event_type, trace, created_at) VALUES (?, ?, ?, ?)",
        (event_id, EVENT_WO_CLOSED, json.dumps({"project_id": project_id}), ts),
    )


# ── _pattern_id ───────────────────────────────────────────────────────────


class TestPatternId:
    def test_stable_for_same_inputs(self):
        assert _pattern_id("always_paired", "sec", "cq", "p") == _pattern_id(
            "always_paired", "sec", "cq", "p"
        )

    def test_different_for_different_skill(self):
        assert _pattern_id("always_paired", "sec", "cq", "p") != _pattern_id(
            "always_paired", "sec", "db", "p"
        )


# ── always_paired ─────────────────────────────────────────────────────────


class TestAlwaysPaired:
    def test_high_confidence_pair_detected(self, tmp_path):
        """security + code-quality always appear together in 5 sessions → confidence 1.0."""
        conn = _make_db(tmp_path)
        for i in range(5):
            # Each session: start, both skills, end
            _session_start(conn, f"ses-{i}", ts=f"2026-06-0{i+1}T10:00:00")
            _skill(conn, f"sec-{i}", "security", ts=f"2026-06-0{i+1}T10:10:00")
            _skill(conn, f"cq-{i}", "code-quality", ts=f"2026-06-0{i+1}T10:20:00")
            _session_end(conn, f"end-{i}", ts=f"2026-06-0{i+1}T11:00:00")
        conn.commit()

        analyzer = WorkflowPatternAnalyzer(conn)
        signals = analyzer.analyze(min_occurrences=2, min_confidence=0.0)

        paired = [s for s in signals if s["pattern_type"] == "always_paired"]
        assert paired, "Expected always_paired signal"
        assert max(s["confidence_score"] for s in paired) >= 0.8

    def test_weak_pair_has_low_confidence(self, tmp_path):
        """security in 10 sessions, code-quality in only 3 → confidence ~0.3."""
        conn = _make_db(tmp_path)
        for i in range(10):
            _session_start(conn, f"ses-{i}", ts=f"2026-06-01T{10+i:02d}:00:00")
            _skill(conn, f"sec-{i}", "security", ts=f"2026-06-01T{10+i:02d}:15:00")
            if i < 3:
                _skill(conn, f"cq-{i}", "code-quality", ts=f"2026-06-01T{10+i:02d}:20:00")
            _session_end(conn, f"end-{i}", ts=f"2026-06-01T{10+i:02d}:59:00")
        conn.commit()

        analyzer = WorkflowPatternAnalyzer(conn)
        signals = analyzer.analyze(min_occurrences=2, min_confidence=0.0)

        paired = [s for s in signals if s["pattern_type"] == "always_paired"]
        if paired:
            assert any(
                s["confidence_score"] < 0.5 for s in paired
            ), f"Weak pair confidence should be < 0.5, got: {[s['confidence_score'] for s in paired]}"

    def test_no_events_returns_empty(self, tmp_path):
        conn = _make_db(tmp_path)
        signals = WorkflowPatternAnalyzer(conn).analyze()
        assert signals == []

    def test_events_outside_session_excluded(self, tmp_path):
        """Skill events outside session boundaries are not included."""
        conn = _make_db(tmp_path)
        # Skills emitted BEFORE any session.recorded — should be excluded
        _skill(conn, "orphan-sec", "security", ts="2026-06-01T08:00:00")
        _skill(conn, "orphan-cq", "code-quality", ts="2026-06-01T08:05:00")
        conn.commit()

        signals = WorkflowPatternAnalyzer(conn).analyze(min_occurrences=1, min_confidence=0.0)
        assert not signals, "Events outside sessions must not produce patterns"

    def test_open_session_included(self, tmp_path):
        """Events in an open session (no session.closed) are included."""
        conn = _make_db(tmp_path)
        # Session started, never closed — still active
        for i in range(3):
            _session_start(conn, f"ses-{i}", ts=f"2026-06-0{i+1}T10:00:00")
            _skill(conn, f"sec-{i}", "security", ts=f"2026-06-0{i+1}T10:10:00")
            _skill(conn, f"cq-{i}", "code-quality", ts=f"2026-06-0{i+1}T10:20:00")
            # No session_end — open sessions
        conn.commit()

        signals = WorkflowPatternAnalyzer(conn).analyze(min_occurrences=2, min_confidence=0.0)
        paired = [s for s in signals if s["pattern_type"] == "always_paired"]
        assert paired, "Open sessions should be included in pattern detection"


# ── post_completion ───────────────────────────────────────────────────────


class TestPostCompletion:
    def test_resume_after_close_detected(self, tmp_path):
        """Resume skill after WO close in 4 sessions → high confidence."""
        conn = _make_db(tmp_path)
        for i in range(4):
            _session_start(conn, f"ses-{i}", ts=f"2026-06-0{i+1}T10:00:00")
            _wo_close(conn, f"wc-{i}", ts=f"2026-06-0{i+1}T10:30:00")
            _skill(conn, f"res-{i}", "ds-project:resume", ts=f"2026-06-0{i+1}T10:35:00")
            _session_end(conn, f"end-{i}", ts=f"2026-06-0{i+1}T11:00:00")
        conn.commit()

        signals = WorkflowPatternAnalyzer(conn).analyze(min_occurrences=2, min_confidence=0.0)
        post = [s for s in signals if s["pattern_type"] == "post_completion"]
        assert post, "Expected post_completion signal"
        assert any("resume" in s["skill_a"] for s in post)

    def test_skill_outside_window_not_detected(self, tmp_path):
        """Skill 2 hours after WO close is outside the 60-min window."""
        conn = _make_db(tmp_path)
        for i in range(4):
            _session_start(conn, f"ses-{i}", ts=f"2026-06-0{i+1}T08:00:00")
            _wo_close(conn, f"wc-{i}", ts=f"2026-06-0{i+1}T09:00:00")
            _skill(
                conn, f"res-{i}", "ds-project:resume", ts=f"2026-06-0{i+1}T11:30:00"
            )  # 2.5h later
            _session_end(conn, f"end-{i}", ts=f"2026-06-0{i+1}T12:00:00")
        conn.commit()

        signals = WorkflowPatternAnalyzer(conn).analyze(min_occurrences=2, min_confidence=0.0)
        post = [s for s in signals if s["pattern_type"] == "post_completion"]
        assert not post, "Skill outside 60-min window should not be detected"


# ── pre_close ─────────────────────────────────────────────────────────────


class TestPreClose:
    def test_audit_before_close_detected(self, tmp_path):
        """Security audit before WO close in 4 sessions → high confidence."""
        conn = _make_db(tmp_path)
        for i in range(4):
            _session_start(conn, f"ses-{i}", ts=f"2026-06-0{i+1}T10:00:00")
            _skill(conn, f"sec-{i}", "ds-quality:security", ts=f"2026-06-0{i+1}T10:20:00")
            _wo_close(conn, f"wc-{i}", ts=f"2026-06-0{i+1}T10:30:00")
            _session_end(conn, f"end-{i}", ts=f"2026-06-0{i+1}T11:00:00")
        conn.commit()

        signals = WorkflowPatternAnalyzer(conn).analyze(min_occurrences=2, min_confidence=0.0)
        pre = [s for s in signals if s["pattern_type"] == "pre_close"]
        assert pre, "Expected pre_close signal"
        assert any("security" in s["skill_a"] for s in pre)


# ── Phase 19 contract ─────────────────────────────────────────────────────


class TestPhase19Contract:
    def _setup_patterns(self, tmp_path):
        conn = _make_db(tmp_path)
        for i in range(5):
            _session_start(conn, f"ses-{i}", ts=f"2026-06-0{i+1}T10:00:00")
            _skill(conn, f"sec-{i}", "security", ts=f"2026-06-0{i+1}T10:10:00")
            _skill(conn, f"cq-{i}", "code-quality", ts=f"2026-06-0{i+1}T10:20:00")
            _session_end(conn, f"end-{i}", ts=f"2026-06-0{i+1}T11:00:00")
        conn.commit()
        return conn

    def test_phase19_query_returns_high_confidence(self, tmp_path):
        conn = self._setup_patterns(tmp_path)
        analyzer = WorkflowPatternAnalyzer(conn)
        analyzer.analyze(min_occurrences=2)

        phase19 = analyzer.get_patterns(min_confidence=0.8, include_suppressed=False)
        assert phase19
        for p in phase19:
            assert p["confidence_score"] >= 0.8
            assert p["suppressed"] == 0

    def test_suppressed_excluded_from_phase19(self, tmp_path):
        conn = self._setup_patterns(tmp_path)
        analyzer = WorkflowPatternAnalyzer(conn)
        analyzer.analyze(min_occurrences=2)

        patterns = analyzer.get_patterns(min_confidence=0.8)
        pid = patterns[0]["pattern_id"]
        assert analyzer.suppress_pattern(pid)

        phase19_ids = {p["pattern_id"] for p in analyzer.get_patterns(min_confidence=0.8)}
        assert pid not in phase19_ids

    def test_suppressed_visible_with_flag(self, tmp_path):
        conn = self._setup_patterns(tmp_path)
        analyzer = WorkflowPatternAnalyzer(conn)
        analyzer.analyze(min_occurrences=2)

        patterns = analyzer.get_patterns()
        pid = patterns[0]["pattern_id"]
        analyzer.suppress_pattern(pid)

        all_ids = {p["pattern_id"] for p in analyzer.get_patterns(include_suppressed=True)}
        assert pid in all_ids

    def test_upsert_does_not_unsuppress(self, tmp_path):
        """Re-running analyze must NOT overwrite suppressed=1."""
        conn = self._setup_patterns(tmp_path)
        analyzer = WorkflowPatternAnalyzer(conn)
        analyzer.analyze(min_occurrences=2)
        patterns = analyzer.get_patterns()
        pid = patterns[0]["pattern_id"]
        analyzer.suppress_pattern(pid)

        analyzer.analyze(min_occurrences=2)  # Re-run

        row = conn.execute(
            "SELECT suppressed FROM ds_workflow_pattern_signals WHERE pattern_id = ?", (pid,)
        ).fetchone()
        assert row["suppressed"] == 1


# ── Suppress mechanism ────────────────────────────────────────────────────


class TestSuppressMechanism:
    def test_suppress_returns_true_when_found(self, tmp_path):
        conn = _make_db(tmp_path)
        conn.execute(
            "INSERT INTO ds_workflow_pattern_signals "
            "(pattern_id, pattern_type, skill_a, co_occurrence_count, "
            "total_sessions, confidence_score) VALUES ('pid', 'always_paired', 'sec', 3, 3, 1.0)"
        )
        conn.commit()
        assert WorkflowPatternAnalyzer(conn).suppress_pattern("pid") is True

    def test_suppress_returns_false_when_missing(self, tmp_path):
        conn = _make_db(tmp_path)
        assert WorkflowPatternAnalyzer(conn).suppress_pattern("nope") is False


# ── No ML/LLM check ───────────────────────────────────────────────────────


class TestNoMLLLM:
    def test_analyzer_has_no_ml_imports(self):
        src = (
            Path(__file__).parents[2]
            / "projections"
            / "core"
            / "analyzers"
            / "workflow_patterns.py"
        ).read_text(encoding="utf-8")

        for forbidden in [
            "from projections.ml",
            "import projections.ml",
            "from core.skills.dispatcher",
            "from anthropic",
            "import anthropic",
            "grade_behavior",
            "SkillDispatcher",
        ]:
            assert forbidden not in src, f"Forbidden import found: {forbidden!r}"
