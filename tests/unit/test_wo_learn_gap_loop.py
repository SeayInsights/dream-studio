"""WO-LEARN E2E: gap/learning → improvement loop verification.

Proves:
  1. WorkflowPatternAnalyzer.analyze() is now wired into end_session() (Phase 19.4)
  2. The full friction → classification → extension pipeline works end-to-end
  3. Extensions are proposed in ds_user_extensions via confirm_signal() (operator step)
  4. RetroactiveValidator.increment_for_session() increments past_wo_count for
     experimental extensions whose skills ran in the session

Architecture note (important): the loop is NOT fully automated. Step 3 (confirm_signal)
is an intentional operator gate. Improvement activates as a LAYERED EXTENSION applied
at dispatch — not as a SKILL.md edit. This test proves the wiring of each step.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, UTC
from pathlib import Path

import pytest

pytestmark = pytest.mark.runtime_reliability

# ── Minimal schema helpers ─────────────────────────────────────────────────────


def _make_db(tmp_path: Path) -> sqlite3.Connection:
    """Create in-memory DB with all Phase 19 tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        -- Friction signals (Phase 19.2)
        CREATE TABLE ds_friction_signals (
            signal_id TEXT PRIMARY KEY,
            session_id TEXT,
            project_id TEXT,
            signal_type TEXT NOT NULL,
            skill_id TEXT,
            rule_id TEXT,
            source_table TEXT NOT NULL DEFAULT 'test',
            source_id TEXT NOT NULL DEFAULT 'test',
            context TEXT NOT NULL DEFAULT '{}',
            bucket_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            classified_as TEXT,
            classified_at TEXT,
            classification_confidence REAL,
            classification_reason TEXT,
            classification_skipped INTEGER DEFAULT 0,
            extension_id TEXT
        );

        -- User extensions (Phase 19.4)
        CREATE TABLE ds_user_extensions (
            extension_id TEXT PRIMARY KEY,
            skill_id TEXT NOT NULL,
            extension_type TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '{}',
            source_signal TEXT,
            compiled_from TEXT,
            status TEXT NOT NULL DEFAULT 'proposed',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_validated_at TEXT,
            baseline_eval_score REAL,
            current_eval_score REAL,
            past_wo_count INTEGER NOT NULL DEFAULT 0,
            user_confirmed_at TEXT,
            user_confirmed_by TEXT,
            suppressed_reason TEXT
        );

        -- Workflow pattern signals (Phase 19.4)
        CREATE TABLE ds_workflow_pattern_signals (
            pattern_id TEXT PRIMARY KEY,
            project_id TEXT,
            pattern_type TEXT NOT NULL,
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

        -- Canonical events (for WorkflowPatternAnalyzer queries)
        CREATE TABLE canonical_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            trace TEXT NOT NULL DEFAULT '{}',
            severity TEXT NOT NULL DEFAULT 'info',
            payload TEXT NOT NULL DEFAULT '{}',
            actor TEXT,
            confidence_score REAL,
            source_type TEXT,
            raw_prompt_retained INTEGER NOT NULL DEFAULT 0,
            raw_tool_output_retained INTEGER NOT NULL DEFAULT 0,
            schema_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            invocation_mode TEXT
        );
    """)
    conn.commit()
    return conn


def _insert_friction_signal(
    conn: sqlite3.Connection,
    *,
    signal_id: str | None = None,
    skill_id: str = "ds-quality",
    rule_id: str | None = "SEC001",
    signal_type: str = "dismissed_finding",
    occurrence_count: int = 6,
    distinct_scans: int = 4,
    project_id: str | None = None,
    session_id: str | None = None,
) -> str:
    sid = signal_id or str(uuid.uuid4())
    bucket = f"{skill_id}|{rule_id or 'none'}|{signal_type}"
    context = json.dumps({"occurrence_count": occurrence_count, "distinct_scans": distinct_scans})
    conn.execute(
        """
        INSERT INTO ds_friction_signals
            (signal_id, session_id, project_id, signal_type, skill_id, rule_id,
             source_table, source_id, context, bucket_key)
        VALUES (?, ?, ?, ?, ?, ?, 'test', 'test', ?, ?)
        """,
        (sid, session_id, project_id, signal_type, skill_id, rule_id, context, bucket),
    )
    conn.commit()
    return sid


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestWorkflowPatternAnalyzerIsWired:
    """Prove WorkflowPatternAnalyzer is importable and wired into end_session() code path."""

    def test_analyzer_importable(self):
        from projections.core.analyzers.workflow_patterns import WorkflowPatternAnalyzer

        assert callable(WorkflowPatternAnalyzer)

    def test_analyzer_init_and_analyze_on_empty_db(self, tmp_path):
        from projections.core.analyzers.workflow_patterns import WorkflowPatternAnalyzer

        conn = _make_db(tmp_path)
        analyzer = WorkflowPatternAnalyzer(conn)
        results = analyzer.analyze()
        assert isinstance(results, list)
        # No canonical_events → no patterns → empty result, no exception
        assert results == []

    def test_end_session_code_includes_analyzer_block(self):
        """Verify the wiring exists in studio_db source without executing it."""
        import inspect

        from core.event_store import studio_db

        source = inspect.getsource(studio_db.end_session)
        assert (
            "WorkflowPatternAnalyzer" in source
        ), "WorkflowPatternAnalyzer not wired into end_session() — Task 1 regression"
        assert "analyzer.analyze()" in source

    def test_analyzer_wired_after_gap_classifier(self):
        """Pattern analysis must run after gap classification (Phase 19.4 after 19.3)."""
        import inspect

        from core.event_store import studio_db

        source = inspect.getsource(studio_db.end_session)
        gap_pos = source.find("GapClassifier")
        pattern_pos = source.find("WorkflowPatternAnalyzer")
        retroactive_pos = source.find("RetroactiveValidator")
        assert (
            gap_pos < pattern_pos < retroactive_pos
        ), "Phase 19 ordering violated: expected GapClassifier → WorkflowPatternAnalyzer → RetroactiveValidator"


class TestFrictionToClassificationPipeline:
    """Prove the friction signal → gap classification loop works end-to-end."""

    def test_gap_classifier_classifies_dismissed_finding(self, tmp_path):
        """A dismissed finding with ≥5 occurrences across ≥2 scans → personalization."""
        from projections.core.analyzers.gap_classifier import GapClassifier

        conn = _make_db(tmp_path)
        _insert_friction_signal(
            conn,
            skill_id="ds-security",
            rule_id="SEC001",
            signal_type="dismissed_finding",
            occurrence_count=6,
            distinct_scans=4,
        )

        classifier = GapClassifier(conn)
        result = classifier.classify_all()

        assert result["classified"] == 1, f"Expected 1 classified, got: {result}"
        row = conn.execute("SELECT classified_as FROM ds_friction_signals LIMIT 1").fetchone()
        assert row["classified_as"] == "personalization"

    def test_gap_classifier_defers_insufficient_data(self, tmp_path):
        """Single occurrence → insufficient data gate → deferred (not classified)."""
        from projections.core.analyzers.gap_classifier import GapClassifier

        conn = _make_db(tmp_path)
        _insert_friction_signal(
            conn,
            occurrence_count=1,
            distinct_scans=1,
        )

        classifier = GapClassifier(conn)
        result = classifier.classify_all()

        assert result["classified"] == 0
        assert result["deferred"] == 1

    def test_confirm_signal_creates_extension_in_ds_user_extensions(self, tmp_path):
        """confirm_signal() must create a ds_user_extensions row with status='proposed'."""
        from projections.core.analyzers.gap_classifier import GapClassifier

        conn = _make_db(tmp_path)
        signal_id = _insert_friction_signal(
            conn,
            skill_id="ds-security",
            rule_id="SEC001",
            signal_type="dismissed_finding",
            occurrence_count=6,
            distinct_scans=4,
        )

        classifier = GapClassifier(conn)
        classifier.classify_all()

        extension_id = classifier.confirm_signal(signal_id)

        ext = conn.execute(
            "SELECT * FROM ds_user_extensions WHERE extension_id = ?", (extension_id,)
        ).fetchone()
        assert ext is not None
        assert ext["status"] == "proposed"
        assert ext["skill_id"] == "ds-security"
        assert ext["extension_type"] == "option_override"  # personalization → option_override

        # signal linked back
        sig = conn.execute(
            "SELECT extension_id FROM ds_friction_signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        assert sig["extension_id"] == extension_id

    def test_extension_is_not_a_skill_md_edit(self, tmp_path):
        """The extension lives in ds_user_extensions — NOT in any SKILL.md file.
        Improvement is layered, not a canonical skill mutation.
        """
        from projections.core.analyzers.gap_classifier import GapClassifier

        conn = _make_db(tmp_path)
        signal_id = _insert_friction_signal(
            conn,
            skill_id="ds-quality",
            rule_id="CQ001",
            signal_type="dismissed_finding",
            occurrence_count=6,
            distinct_scans=3,
        )
        classifier = GapClassifier(conn)
        classifier.classify_all()
        extension_id = classifier.confirm_signal(signal_id)

        # The extension row has no file path — it is in-DB, not in a SKILL.md
        ext = conn.execute(
            "SELECT * FROM ds_user_extensions WHERE extension_id = ?", (extension_id,)
        ).fetchone()
        assert ext is not None
        assert "skill_id" in ext.keys()
        # compiled_from is JSON, not a file path
        compiled = json.loads(ext["compiled_from"] or "{}")
        assert "friction_signal_id" in compiled


class TestRetroactiveValidatorIncrement:
    """Prove RetroactiveValidator.increment_for_session() handles experimental extensions.

    increment_for_session() looks for recently-run skills in scan_runs, then
    increments past_wo_count for matching experimental/proposed extensions that
    have non-empty content (empty '{}' content is excluded by design).
    """

    def _make_scan_runs_table(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_runs (
                run_id TEXT PRIMARY KEY,
                skill_id TEXT,
                project_id TEXT,
                status TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

    def _insert_scan_run(self, conn: sqlite3.Connection, skill_id: str) -> None:
        conn.execute(
            "INSERT INTO scan_runs (run_id, skill_id, created_at) VALUES (?, ?, datetime('now'))",
            (str(uuid.uuid4()), skill_id),
        )
        conn.commit()

    def _make_experimental_extension(
        self, conn: sqlite3.Connection, skill_id: str = "ds-quality"
    ) -> str:
        ext_id = str(uuid.uuid4())
        # content must be non-empty (increment_for_session excludes '{}')
        content = json.dumps({"gap": "missing strict mode flag", "applies_to": "lint"})
        conn.execute(
            """
            INSERT INTO ds_user_extensions
                (extension_id, skill_id, extension_type, content, status, past_wo_count)
            VALUES (?, ?, 'gap_filler', ?, 'experimental', 0)
            """,
            (ext_id, skill_id, content),
        )
        conn.commit()
        return ext_id

    def test_increment_for_session_increments_past_wo_count(self, tmp_path):
        from core.expansion.validation import RetroactiveValidator

        conn = _make_db(tmp_path)
        self._make_scan_runs_table(conn)

        ext_id = self._make_experimental_extension(conn, skill_id="ds-quality")
        self._insert_scan_run(conn, skill_id="ds-quality")

        validator = RetroactiveValidator(conn)
        validator.increment_for_session(session_id=None)

        ext = conn.execute(
            "SELECT past_wo_count FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        assert ext["past_wo_count"] == 1

    def test_increment_ignores_empty_content_extensions(self, tmp_path):
        """Extensions with content='{}' are excluded — they have no compiled content yet."""
        from core.expansion.validation import RetroactiveValidator

        conn = _make_db(tmp_path)
        self._make_scan_runs_table(conn)

        # experimental extension with empty content — should NOT be incremented
        empty_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO ds_user_extensions
                (extension_id, skill_id, extension_type, content, status, past_wo_count)
            VALUES (?, 'ds-security', 'gap_filler', '{}', 'experimental', 0)
            """,
            (empty_id,),
        )
        self._insert_scan_run(conn, skill_id="ds-security")
        conn.commit()

        validator = RetroactiveValidator(conn)
        validator.increment_for_session(session_id=None)

        ext = conn.execute(
            "SELECT past_wo_count FROM ds_user_extensions WHERE extension_id = ?", (empty_id,)
        ).fetchone()
        assert ext["past_wo_count"] == 0


class TestWorkflowPatternAnalyzerDetectsPatterns:
    """Prove WorkflowPatternAnalyzer writes to ds_workflow_pattern_signals when data exists."""

    def test_always_paired_pattern_detected(self, tmp_path):
        """Two skills always invoked together across sessions → always_paired pattern."""
        from projections.core.analyzers.workflow_patterns import WorkflowPatternAnalyzer

        conn = _make_db(tmp_path)

        def ts(offset_minutes: int) -> str:
            """ISO timestamp offset_minutes ago."""
            from datetime import timedelta

            t = datetime(2026, 6, 8, 12, 0, 0, tzinfo=UTC)
            t -= timedelta(minutes=offset_minutes)
            return t.isoformat().replace("+00:00", "")

        # Insert 3 sessions where ds-core and ds-quality always co-occur
        for i in range(3):
            base = (i + 1) * 60  # offset: 60, 120, 180 minutes ago
            session_event_id = str(uuid.uuid4())
            # session.recorded
            conn.execute(
                "INSERT INTO canonical_events (event_id, event_type, trace, created_at)"
                " VALUES (?, 'system.session.recorded', ?, ?)",
                (session_event_id, json.dumps({"project_id": "proj-1"}), ts(base)),
            )
            # skill invocations in this session
            for j, skill in enumerate(("ds-core", "ds-quality")):
                conn.execute(
                    "INSERT INTO canonical_events (event_id, event_type, trace, created_at)"
                    " VALUES (?, 'skill.invoked', ?, ?)",
                    (
                        str(uuid.uuid4()),
                        json.dumps({"skill_specifier": skill, "project_id": "proj-1"}),
                        ts(base - j - 1),
                    ),
                )
            # session.closed
            conn.execute(
                "INSERT INTO canonical_events (event_id, event_type, trace, created_at)"
                " VALUES (?, 'system.session.closed', ?, ?)",
                (
                    str(uuid.uuid4()),
                    json.dumps({"project_id": "proj-1"}),
                    ts(base - 3),
                ),
            )
        conn.commit()

        analyzer = WorkflowPatternAnalyzer(conn)
        results = analyzer.analyze(min_occurrences=2, min_confidence=0.3)

        # Should detect ds-core + ds-quality always paired
        assert any(
            r["pattern_type"] == "always_paired"
            and {r.get("skill_a"), r.get("skill_b")} == {"ds-core", "ds-quality"}
            for r in results
        ), f"Expected always_paired pattern for ds-core + ds-quality, got: {results}"

        # Verify written to ds_workflow_pattern_signals
        count = conn.execute(
            "SELECT COUNT(*) FROM ds_workflow_pattern_signals WHERE pattern_type = 'always_paired'"
        ).fetchone()[0]
        assert count >= 1
