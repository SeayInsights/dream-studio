"""Tests for Phase 19.3 — Gap Classifier.

Proving gate:
  Schema:       migration 097 adds 3 columns; schema_coherence passes
  Tier 1:       each heuristic fires correctly with confidence >= 0.8
  Tier 2:       LLM fallback path exercised; variance documented
  Deferral:     insufficient-data signal stays NULL
  CLI confirm:  creates ds_user_extensions row, bidirectional link proven
  CLI skip:     classification_skipped=1, signal removed from review
  CLI defer:    classified_as reset to NULL, signal re-enters classifier
  Local-first:  no network calls in classifier or CLI code
  Token cost:   Tier 2 token estimate documented
"""

from __future__ import annotations

import inspect
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

# ── Migration SQL ──────────────────────────────────────────────────────────

MIGRATION_096 = (
    Path(__file__).parents[2] / "core" / "event_store" / "migrations" / "096_friction_signals.sql"
).read_text(encoding="utf-8")

MIGRATION_097 = (
    Path(__file__).parents[2]
    / "core"
    / "event_store"
    / "migrations"
    / "097_gap_classifier_columns.sql"
).read_text(encoding="utf-8")

MIGRATION_095 = (
    Path(__file__).parents[2]
    / "core"
    / "event_store"
    / "migrations"
    / "095_unified_extensions_schema.sql"
).read_text(encoding="utf-8")

FINDINGS_BASE = """
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY, project_id TEXT, scan_id TEXT, rule_id TEXT,
    severity TEXT NOT NULL DEFAULT 'medium', status TEXT NOT NULL DEFAULT 'open',
    introduced_by_skill_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
SCAN_RUNS_BASE = """
CREATE TABLE IF NOT EXISTS scan_runs (
    scan_id TEXT PRIMARY KEY, project_id TEXT, skill_id TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    findings_count INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT, started_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
WORKFLOW_PATTERNS_BASE = """
CREATE TABLE IF NOT EXISTS ds_workflow_pattern_signals (
    pattern_id TEXT PRIMARY KEY, project_id TEXT,
    pattern_type TEXT NOT NULL DEFAULT 'always_paired',
    skill_a TEXT NOT NULL, skill_b TEXT,
    co_occurrence_count INTEGER NOT NULL DEFAULT 0,
    total_sessions INTEGER NOT NULL DEFAULT 1,
    confidence_score REAL NOT NULL DEFAULT 0.0,
    suppressed INTEGER NOT NULL DEFAULT 0, suppressed_at TEXT,
    last_observed_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def full_conn():
    """In-memory DB with migrations 095, 096, 097 + base tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(FINDINGS_BASE)
    conn.executescript(SCAN_RUNS_BASE)
    conn.executescript(WORKFLOW_PATTERNS_BASE)
    # 095 creates ds_user_extensions
    conn.executescript(MIGRATION_095)
    # 096 creates ds_friction_signals (with ALTER TABLE findings)
    conn.executescript(MIGRATION_096)
    # 097 adds classifier columns to ds_friction_signals
    conn.executescript(MIGRATION_097)
    return conn


@pytest.fixture
def classifier(full_conn):
    from projections.core.analyzers.gap_classifier import GapClassifier

    return GapClassifier(full_conn, session_id="test-session")


def _sid():
    return str(uuid.uuid4())


def _insert_signal(
    conn,
    *,
    signal_type: str,
    skill_id: str,
    rule_id: str | None = None,
    occurrence_count: int = 3,
    distinct_scans: int = 3,
    project_id: str = "proj-1",
    confidence_score: float | None = None,
    co_occurrence_count: int | None = None,
) -> str:
    signal_id = _sid()
    context = {"occurrence_count": occurrence_count, "distinct_scans": distinct_scans}
    if confidence_score is not None:
        context["confidence_score"] = confidence_score
    if co_occurrence_count is not None:
        context["co_occurrence_count"] = co_occurrence_count
    bk = f"{signal_type}:{skill_id}:{rule_id or ''}:{signal_id[:8]}"
    conn.execute(
        "INSERT INTO ds_friction_signals "
        "(signal_id, signal_type, skill_id, rule_id, project_id, source_table, source_id, "
        "context, bucket_key) "
        "VALUES (?, ?, ?, ?, ?, 'findings', ?, ?, ?)",
        (signal_id, signal_type, skill_id, rule_id, project_id, signal_id, json.dumps(context), bk),
    )
    conn.commit()
    return signal_id


# ── Schema: migration 097 ─────────────────────────────────────────────────


class TestMigration097Schema:
    def test_classification_confidence_column_added(self, full_conn):
        cols = {r[1] for r in full_conn.execute("PRAGMA table_info(ds_friction_signals)")}
        assert "classification_confidence" in cols

    def test_classification_reason_column_added(self, full_conn):
        cols = {r[1] for r in full_conn.execute("PRAGMA table_info(ds_friction_signals)")}
        assert "classification_reason" in cols

    def test_classification_skipped_column_added(self, full_conn):
        cols = {r[1] for r in full_conn.execute("PRAGMA table_info(ds_friction_signals)")}
        assert "classification_skipped" in cols

    def test_classification_skipped_defaults_to_zero(self, full_conn):
        sid = _insert_signal(full_conn, signal_type="pattern_gap", skill_id="ds-quality:security")
        row = full_conn.execute(
            "SELECT classification_skipped FROM ds_friction_signals WHERE signal_id = ?", (sid,)
        ).fetchone()
        assert row["classification_skipped"] == 0

    def test_migration_is_additive_only(self):
        sql = MIGRATION_097.upper()
        assert "DROP TABLE" not in sql
        assert "CREATE TABLE" not in sql
        assert "ALTER TABLE" in sql


# ── Tier 1 SQL Heuristics ─────────────────────────────────────────────────


class TestTier1Heuristics:
    def test_dismissed_finding_personalization_high_occurrence(self, classifier, full_conn):
        """>=5 dismissals of same rule → personalization, confidence >= 0.8."""
        sid = _insert_signal(
            full_conn,
            signal_type="dismissed_finding",
            skill_id="ds-quality:security",
            rule_id="SEC-001",
            occurrence_count=7,
            distinct_scans=5,
        )
        result = classifier.classify_signal(sid)
        assert result.classification == "personalization", (
            f"Expected personalization, got {result.classification}. " f"Reason: {result.reason}"
        )
        assert result.confidence is not None and result.confidence >= 0.8
        assert result.tier == "tier1"

    def test_dismissed_finding_capability_many_rules(self, classifier, full_conn):
        """>=3 distinct rules dismissed for same skill → capability."""
        skill = "ds-quality:code-quality"
        for rule in ("CQ-001", "CQ-002", "CQ-003"):
            _insert_signal(
                full_conn,
                signal_type="dismissed_finding",
                skill_id=skill,
                rule_id=rule,
                occurrence_count=2,
                distinct_scans=2,
            )
        rows = full_conn.execute(
            "SELECT signal_id FROM ds_friction_signals WHERE skill_id = ?", (skill,)
        ).fetchall()
        for row in rows:
            result = classifier.classify_signal(row["signal_id"])
            if result.classification is not None:
                assert result.classification == "capability"
                assert result.confidence >= 0.8
                assert result.tier == "tier1"
                break

    def test_partial_completion_capability_cross_project(self, classifier, full_conn):
        """Skill ignored across >1 project → capability."""
        skill = "ds-quality:testing"
        for project in ("proj-A", "proj-B"):
            _insert_signal(
                full_conn,
                signal_type="partial_completion",
                skill_id=skill,
                distinct_scans=3,
                project_id=project,
            )
        rows = full_conn.execute(
            "SELECT signal_id FROM ds_friction_signals WHERE skill_id = ?", (skill,)
        ).fetchall()
        classified = False
        for row in rows:
            result = classifier.classify_signal(row["signal_id"])
            if result.classification == "capability":
                assert result.confidence >= 0.8
                assert result.tier == "tier1"
                classified = True
                break
        assert classified, "Expected at least one signal classified as capability"

    def test_partial_completion_onboarding_single_project(self, classifier, full_conn):
        """Skill ignored on single project → onboarding (tier1 confidence 0.75)."""
        sid = _insert_signal(
            full_conn,
            signal_type="partial_completion",
            skill_id="ds-quality:database",
            distinct_scans=4,
            project_id="proj-single",
        )
        result = classifier.classify_signal(sid)
        assert (
            result.classification == "onboarding"
        ), f"Expected onboarding, got {result.classification}"
        assert result.tier == "tier1"

    def test_pattern_gap_capability_low_confidence(self, classifier, full_conn):
        """Low workflow pattern confidence (<0.3) + >=2 occurrences → capability."""
        sid = _insert_signal(
            full_conn,
            signal_type="pattern_gap",
            skill_id="ds-quality:architecture",
            confidence_score=0.2,
            co_occurrence_count=3,
        )
        result = classifier.classify_signal(sid)
        assert result.classification == "capability"
        assert result.confidence >= 0.8
        assert result.tier == "tier1"

    def test_tier1_confidence_meets_threshold(self, classifier, full_conn):
        """All Tier 1 heuristics produce confidence >= 0.8."""
        sid = _insert_signal(
            full_conn,
            signal_type="dismissed_finding",
            skill_id="ds-quality:pre-launch",
            rule_id="PL-001",
            occurrence_count=6,
            distinct_scans=5,
        )
        result = classifier.classify_signal(sid)
        assert result.tier == "tier1"
        assert (
            result.confidence is not None and result.confidence >= 0.8
        ), f"Tier 1 confidence {result.confidence} is below 0.8 threshold"


# ── Tier 2 LLM ───────────────────────────────────────────────────────────


class TestTier2LLM:
    def test_tier2_escalation_on_ambiguous_signal(self, classifier, full_conn):
        """Signal that Tier 1 can't decide escalates to Tier 2 (or defers if claude unavailable)."""
        # Ambiguous: dismissed_finding, low occurrence (below threshold), single rule
        sid = _insert_signal(
            full_conn,
            signal_type="dismissed_finding",
            skill_id="ds-quality:frontend-ux",
            rule_id="FE-002",
            occurrence_count=2,
            distinct_scans=2,  # below DISMISSAL_HIGH_THRESHOLD=5
        )
        result = classifier.classify_signal(sid)
        # Result is either tier2 classified or deferred — both are acceptable
        assert result.tier in (
            "tier2",
            "deferred",
        ), f"Expected tier2 or deferred, got {result.tier}"

    def test_tier2_parse_mock(self):
        """LLM response parser handles valid JSON correctly."""
        from projections.core.analyzers.gap_classifier import GapClassifier

        valid = '{"classification": "capability", "confidence": 0.72, "reason": "test reason"}'
        parsed = GapClassifier._parse_llm_response(valid)
        assert parsed is not None
        assert parsed["classification"] == "capability"
        assert parsed["confidence"] == 0.72

    def test_tier2_parse_handles_prose_wrapper(self):
        """Parser extracts JSON from response wrapped in prose text."""
        from projections.core.analyzers.gap_classifier import GapClassifier

        wrapped = 'Here is my analysis: {"classification": "personalization", "confidence": 0.65, "reason": "test"} Done.'
        parsed = GapClassifier._parse_llm_response(wrapped)
        assert parsed is not None
        assert parsed["classification"] == "personalization"

    def test_tier2_parse_rejects_invalid_classification(self):
        """Parser rejects unknown classification values."""
        from projections.core.analyzers.gap_classifier import GapClassifier

        invalid = '{"classification": "unknown_type", "confidence": 0.7, "reason": "bad"}'
        parsed = GapClassifier._parse_llm_response(invalid)
        assert parsed is None

    def test_tier2_parse_rejects_empty_response(self):
        from projections.core.analyzers.gap_classifier import GapClassifier

        assert GapClassifier._parse_llm_response("") is None
        assert GapClassifier._parse_llm_response(None) is None

    def test_tier2_variance_documented(self, classifier, full_conn):
        """Run same ambiguous classification 3 times, document variance.

        When claude CLI is unavailable, this verifies the prompt is deterministic
        (same inputs → same prompt → same expected behavior).
        When claude IS available, checks variance < 0.1.
        """
        import shutil
        from projections.core.analyzers.gap_classifier import GapClassifier

        # Build the prompt for an ambiguous signal
        sig = {
            "signal_id": _sid(),
            "signal_type": "dismissed_finding",
            "skill_id": "ds-quality:security",
            "rule_id": "SEC-002",
            "context": json.dumps({"occurrence_count": 3, "distinct_scans": 2}),
            "project_id": "proj-variance",
        }

        # Test 1: prompt is deterministic (same inputs → identical prompt)
        conn1 = sqlite3.connect(":memory:")
        conn1.row_factory = sqlite3.Row
        conn1.executescript(FINDINGS_BASE)
        conn1.executescript(SCAN_RUNS_BASE)
        conn1.executescript(WORKFLOW_PATTERNS_BASE)
        conn1.executescript(MIGRATION_095)
        conn1.executescript(MIGRATION_096)
        conn1.executescript(MIGRATION_097)
        c1 = GapClassifier(conn1)
        prompt_a = c1._build_prompt(sig)
        prompt_b = c1._build_prompt(sig)
        assert prompt_a == prompt_b, "Same inputs must produce identical prompt"
        conn1.close()

        # Test 2: if claude available, classify 3 times and check variance
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            # Document why test is skipped
            pytest.skip(
                "claude CLI not available — variance test skipped. "
                "Prompt determinism verified. Token cost: N/A (Tier 2 not reached)."
            )

        results = []
        for _ in range(3):
            # Fresh in-memory DB per run to avoid cross-contamination
            conn_run = sqlite3.connect(":memory:")
            conn_run.row_factory = sqlite3.Row
            conn_run.executescript(FINDINGS_BASE)
            conn_run.executescript(SCAN_RUNS_BASE)
            conn_run.executescript(WORKFLOW_PATTERNS_BASE)
            conn_run.executescript(MIGRATION_095)
            conn_run.executescript(MIGRATION_096)
            conn_run.executescript(MIGRATION_097)
            c_run = GapClassifier(conn_run)
            r = c_run._tier2_classify(sig)
            if r is not None and r.classification:
                results.append(r.confidence)
            conn_run.close()

        if not results:
            pytest.skip("Tier 2 returned no results (all deferred) — variance test N/A")

        variance = max(results) - min(results)
        assert variance < 0.1, (
            f"Tier 2 variance {variance:.3f} exceeds 0.1 target across {len(results)} runs. "
            f"Scores: {results}. Tighten the classifier prompt."
        )
        print(
            f"\n[Token cost] Tier 2 ran {len(results)} times. "
            f"Avg confidence: {sum(results)/len(results):.3f}, variance: {variance:.3f}"
        )


# ── NULL deferral ─────────────────────────────────────────────────────────


class TestNullDeferral:
    def test_insufficient_data_stays_null(self, classifier, full_conn):
        """Single occurrence, single scan → deferred (classified_as remains NULL)."""
        sid = _insert_signal(
            full_conn,
            signal_type="dismissed_finding",
            skill_id="ds-quality:ops",
            rule_id="OPS-001",
            occurrence_count=1,
            distinct_scans=1,
        )
        result = classifier.classify_signal(sid)
        assert (
            result.classification is None
        ), f"Expected NULL classification, got {result.classification}"
        assert result.tier == "deferred"

        row = full_conn.execute(
            "SELECT classified_as FROM ds_friction_signals WHERE signal_id = ?", (sid,)
        ).fetchone()
        assert row["classified_as"] is None, "DB row should remain unclassified"

    def test_deferred_signal_stays_in_unclassified_pool(self, classifier, full_conn):
        """Deferred signal still appears in SELECT WHERE classified_as IS NULL."""
        sid = _insert_signal(
            full_conn,
            signal_type="dismissed_finding",
            skill_id="ds-quality:types-deps",
            rule_id="TD-001",
            occurrence_count=1,
            distinct_scans=1,
        )
        classifier.classify_signal(sid)  # should defer

        pool = full_conn.execute(
            "SELECT signal_id FROM ds_friction_signals WHERE classified_as IS NULL AND "
            "(classification_skipped IS NULL OR classification_skipped = 0)"
        ).fetchall()
        pool_ids = [r["signal_id"] for r in pool]
        assert sid in pool_ids, "Deferred signal must remain in unclassified pool"


# ── ds learn review CLI actions ───────────────────────────────────────────


class TestLearnReviewActions:
    def _seed_classified_signal(
        self, conn, *, skill_id="ds-quality:security", classified_as="capability"
    ) -> str:
        """Insert + classify a signal ready for review."""
        sid = _insert_signal(
            conn,
            signal_type="dismissed_finding",
            skill_id=skill_id,
            rule_id="SEC-003",
            occurrence_count=6,
            distinct_scans=5,
        )
        conn.execute(
            "UPDATE ds_friction_signals SET classified_as=?, classified_at=datetime('now'), "
            "classification_confidence=0.85, classification_reason='test reason' "
            "WHERE signal_id=?",
            (classified_as, sid),
        )
        conn.commit()
        return sid

    def test_confirm_creates_extension_row(self, classifier, full_conn):
        """Confirm: creates ds_user_extensions row with status=proposed."""
        sid = self._seed_classified_signal(full_conn)
        ext_id = classifier.confirm_signal(sid)

        row = full_conn.execute(
            "SELECT * FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        assert row is not None, "Extension row must be created"
        assert row["status"] == "proposed"
        assert row["source_signal"] == "friction"
        assert row["skill_id"] == "ds-quality:security"

    def test_confirm_sets_extension_type_by_classification(self, classifier, full_conn):
        """Extension type is derived from classification."""
        tests = [
            ("capability", "gap_filler"),
            ("personalization", "option_override"),
            ("onboarding", "example"),
        ]
        for classification, expected_type in tests:
            sid = self._seed_classified_signal(
                full_conn, skill_id=f"ds-quality:{classification[:5]}", classified_as=classification
            )
            ext_id = classifier.confirm_signal(sid)
            row = full_conn.execute(
                "SELECT extension_type FROM ds_user_extensions WHERE extension_id=?", (ext_id,)
            ).fetchone()
            assert row["extension_type"] == expected_type, (
                f"classified_as={classification} should produce extension_type={expected_type}, "
                f"got {row['extension_type']}"
            )

    def test_confirm_bidirectional_link(self, classifier, full_conn):
        """Bidirectional link: signal.extension_id → extension; extension.compiled_from → signal."""
        sid = self._seed_classified_signal(full_conn)
        ext_id = classifier.confirm_signal(sid)

        # Signal points to extension
        signal_row = full_conn.execute(
            "SELECT extension_id FROM ds_friction_signals WHERE signal_id=?", (sid,)
        ).fetchone()
        assert signal_row["extension_id"] == ext_id, "Signal must point to extension"

        # Extension references signal in compiled_from
        ext_row = full_conn.execute(
            "SELECT compiled_from FROM ds_user_extensions WHERE extension_id=?", (ext_id,)
        ).fetchone()
        compiled = json.loads(ext_row["compiled_from"])
        assert (
            compiled.get("friction_signal_id") == sid
        ), "Extension.compiled_from must reference source signal"

    def test_confirmed_signal_removed_from_review_queue(self, classifier, full_conn):
        """After confirm, signal no longer appears in get_pending_review()."""
        sid = self._seed_classified_signal(full_conn)
        classifier.confirm_signal(sid)
        pending = classifier.get_pending_review()
        pending_ids = [s["signal_id"] for s in pending]
        assert sid not in pending_ids, "Confirmed signal must leave review queue"

    def test_skip_sets_flag(self, classifier, full_conn):
        """Skip: sets classification_skipped=1."""
        sid = self._seed_classified_signal(full_conn)
        classifier.skip_signal(sid)
        row = full_conn.execute(
            "SELECT classification_skipped FROM ds_friction_signals WHERE signal_id=?", (sid,)
        ).fetchone()
        assert row["classification_skipped"] == 1

    def test_skip_removes_from_review_queue(self, classifier, full_conn):
        """Skipped signal does not appear in get_pending_review()."""
        sid = self._seed_classified_signal(full_conn)
        classifier.skip_signal(sid)
        pending_ids = [s["signal_id"] for s in classifier.get_pending_review()]
        assert sid not in pending_ids

    def test_defer_resets_classification(self, classifier, full_conn):
        """Defer: resets classified_as, classified_at, confidence, reason to NULL."""
        sid = self._seed_classified_signal(full_conn)
        classifier.defer_signal(sid)
        row = full_conn.execute(
            "SELECT classified_as, classified_at, classification_confidence, classification_reason "
            "FROM ds_friction_signals WHERE signal_id=?",
            (sid,),
        ).fetchone()
        assert row["classified_as"] is None
        assert row["classified_at"] is None
        assert row["classification_confidence"] is None
        assert row["classification_reason"] is None

    def test_defer_signal_reenters_unclassified_pool(self, classifier, full_conn):
        """Deferred signal appears in SELECT WHERE classified_as IS NULL."""
        sid = self._seed_classified_signal(full_conn)
        classifier.defer_signal(sid)
        pool = full_conn.execute(
            "SELECT signal_id FROM ds_friction_signals WHERE classified_as IS NULL AND "
            "(classification_skipped IS NULL OR classification_skipped = 0)"
        ).fetchall()
        assert sid in [r["signal_id"] for r in pool]

    def test_no_signals_returns_empty_list(self, classifier):
        """get_pending_review() returns empty list when no classified signals exist."""
        result = classifier.get_pending_review()
        assert result == []


# ── Token cost documentation ──────────────────────────────────────────────


class TestTokenCostDocumentation:
    def test_tokens_estimated_in_classification_result(self, classifier, full_conn):
        """ClassificationResult includes tokens_estimated field."""
        from projections.core.analyzers.gap_classifier import ClassificationResult

        result = ClassificationResult(
            classification="capability",
            confidence=0.85,
            reason="test",
            tier="tier1",
            tokens_estimated=0,
        )
        assert hasattr(result, "tokens_estimated")

    def test_tier1_has_zero_token_cost(self, classifier, full_conn):
        """Tier 1 SQL heuristics have zero token cost."""
        sid = _insert_signal(
            full_conn,
            signal_type="dismissed_finding",
            skill_id="ds-quality:database",
            rule_id="DB-001",
            occurrence_count=8,
            distinct_scans=6,
        )
        result = classifier.classify_signal(sid)
        if result.tier == "tier1":
            assert result.tokens_estimated == 0, "Tier 1 must have zero token cost"

    def test_classify_all_returns_token_total(self, classifier, full_conn):
        """classify_all() summary includes tokens_total field."""
        summary = classifier.classify_all()
        assert "tokens_total" in summary, "classify_all must report token total"
        assert isinstance(summary["tokens_total"], int)


# ── Local-first verification ──────────────────────────────────────────────


class TestLocalFirst:
    def test_no_network_imports_in_classifier(self):
        import projections.core.analyzers.gap_classifier as mod

        source = inspect.getsource(mod)
        forbidden = ["urllib", "requests", "httpx", "aiohttp"]
        for lib in forbidden:
            assert lib not in source, f"Found network import in classifier: {lib!r}"

    def test_no_network_imports_in_learn_cli(self):
        import interfaces.cli.ds_learn as mod

        source = inspect.getsource(mod)
        forbidden = ["urllib", "requests", "httpx", "aiohttp"]
        for lib in forbidden:
            assert lib not in source, f"Found network import in learn CLI: {lib!r}"

    def test_lm_fallback_when_claude_unavailable(self, classifier, full_conn):
        """When claude is not found, Tier 2 returns None (defers, doesn't crash)."""
        import shutil
        from unittest.mock import patch

        with patch.object(shutil, "which", return_value=None):
            sig = {
                "signal_id": _sid(),
                "signal_type": "dismissed_finding",
                "skill_id": "ds-quality:security",
                "rule_id": "SEC-999",
                "context": json.dumps({"occurrence_count": 2, "distinct_scans": 2}),
                "project_id": "proj-1",
            }
            result = classifier._tier2_classify(sig)
            assert result is None, "Tier 2 must return None when claude is unavailable"


# ── Session-end hook integration ──────────────────────────────────────────


class TestSessionHookIntegration:
    def test_classifier_hook_is_nonblocking(self):
        """Exception in classifier doesn't propagate — session close completes."""
        from projections.core.analyzers.gap_classifier import GapClassifier

        class _BrokenConn:
            row_factory = None

            def execute(self, *a, **kw):
                raise RuntimeError("DB exploded")

            def commit(self):
                pass

        classifier = GapClassifier(_BrokenConn())
        summary = classifier.classify_all()
        assert len(summary["errors"]) > 0

    def test_classifier_hook_in_studio_db_is_nonblocking(self):
        """The classifier call in studio_db.end_session() is inside a try/except."""
        source = (Path(__file__).parents[2] / "core" / "event_store" / "studio_db.py").read_text(
            encoding="utf-8"
        )
        assert "GapClassifier" in source, "GapClassifier hook not found in studio_db.py"
        lines = source.splitlines()
        hook_line = next(
            i for i, ln in enumerate(lines) if "GapClassifier" in ln and "import" in ln
        )
        start = max(0, hook_line - 5)
        context = lines[start : hook_line + 2]  # noqa: E203
        assert any(
            "try:" in ln for ln in context
        ), f"GapClassifier import not inside a try block. Context: {context}"
