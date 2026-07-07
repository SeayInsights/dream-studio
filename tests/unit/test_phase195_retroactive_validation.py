"""Tests for Phase 19.5 — Retroactive Validation.

Proving gate:
  Schema:          migration 098 adds validation_detail column
  Decision 6:      N=4 experimental, N=5+97% active, N=5+93% experimental-with-warning,
                   N=5+95% exactly → active (boundary)
  Personalization: SQL inference produces score; verdict correct
  Capability:      synthetic EvalCase via EvalRunner (mocked); verdict correct
  Onboarding:      gate skip → experimental immediately; on confirmed → active path documented
  Session hook:    past_wo_count increments; auto-validate triggers at N=5; non-blocking
  CLI validate:    single, batch, --force logged
  Eval harness:    EvalRunner used (no duplicate logic); 18.8.3 not modified
  Token cost:      personalization=0, capability>0 (via runner), onboarding=0
  Local-first:     no network imports
"""

from __future__ import annotations

import inspect
import json
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).parents[2]
# WO-SQUASH-BASELINE: migration 095 deleted (folded into 142); content inlined verbatim to preserve this test's scaffold.
M095 = """-- Migration 095: Unified Extensions Schema (Phase 19.1)
--
-- Foundation for Phase 19 Adaptive Learning + Skill Enrichment.
-- Stores operator-confirmed extensions that layer on top of canonical skills.
-- Canonical skills are NEVER modified; extensions are additive overlays.
--
-- ── Decision 6 readiness query ──────────────────────────────────────────────
-- Extensions eligible for activation (past the experimental gate):
--
--   SELECT * FROM ds_user_extensions
--   WHERE status = 'experimental'
--     AND past_wo_count >= 5
--     AND current_eval_score >= baseline_eval_score * 0.95
--     AND user_confirmed_at IS NOT NULL;
--
-- Rules (Decision 6):
--   past_wo_count < 5 → stays 'experimental', requires explicit user override
--   past_wo_count >= 5 AND score >= 0.95 × baseline → eligible for 'active'
--   past_wo_count >= 5 AND score < 0.95 × baseline → stays 'experimental' with warning
--   user_confirmed_at NULL → human has not approved → never activates automatically
--
-- ── Extension types ──────────────────────────────────────────────────────────
--   example       — compiled example from accepted past outputs (DSPy-style bootstrap)
--   gap_filler    — content addressing a capability gap not in canonical skill
--   threshold_override — adjusted detection threshold for a specific rule
--   option_override   — changed default option (e.g., severity weight)
--   mode_addition     — entirely new skill mode derived from usage patterns
--   trigger_alias     — additional routing keyword for an existing skill
--
-- ── Status transitions ───────────────────────────────────────────────────────
--   proposed → experimental (after user confirms proposal)
--   experimental → active    (after Decision 6 criteria met + explicit activation)
--   experimental → rejected  (user declines)
--   active → suppressed      (user suppresses; suppressed_reason required)
--   active → deprecated      (superseded by newer extension)
--   any → rejected           (retroactive validation fails hard)

CREATE TABLE IF NOT EXISTS ds_user_extensions (
    -- Identity
    extension_id            TEXT PRIMARY KEY,
    skill_id                TEXT NOT NULL,  -- canonical skill being extended (e.g., 'ds-quality:security')

    -- Extension definition
    extension_type          TEXT NOT NULL CHECK(extension_type IN (
                                'example', 'gap_filler', 'threshold_override',
                                'option_override', 'mode_addition', 'trigger_alias'
                            )),
    content                 TEXT NOT NULL,  -- JSON or markdown; type-specific structure

    -- Provenance
    source_signal           TEXT,           -- 'friction' | 'pattern' | 'manual' | 'eval_gap'
    compiled_from           TEXT,           -- JSON refs: WO IDs, session IDs, or signal IDs

    -- Lifecycle
    status                  TEXT NOT NULL DEFAULT 'proposed' CHECK(status IN (
                                'proposed', 'experimental', 'active',
                                'suppressed', 'rejected', 'deprecated'
                            )),
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    last_validated_at       TEXT,           -- when retroactive validation last ran

    -- Decision 6 validation fields
    baseline_eval_score     REAL CHECK(
                                baseline_eval_score IS NULL OR
                                (baseline_eval_score >= 0.0 AND baseline_eval_score <= 1.0)
                            ),
    current_eval_score      REAL CHECK(
                                current_eval_score IS NULL OR
                                (current_eval_score >= 0.0 AND current_eval_score <= 1.0)
                            ),
    past_wo_count           INTEGER NOT NULL DEFAULT 0
                                CHECK(past_wo_count >= 0),

    -- Human confirmation (required before activation)
    user_confirmed_at       TEXT,           -- NULL = not yet confirmed
    user_confirmed_by       TEXT,           -- operator ID who confirmed

    -- Suppression
    suppressed_reason       TEXT            -- required when status='suppressed'
);

-- ── Indexes ───────────────────────────────────────────────────────────────────

-- Primary lookup: active extensions for a given skill
CREATE INDEX IF NOT EXISTS idx_extensions_skill_status
    ON ds_user_extensions(skill_id, status);

-- Phase 19 activation candidates
CREATE INDEX IF NOT EXISTS idx_extensions_decision6
    ON ds_user_extensions(status, past_wo_count, current_eval_score)
    WHERE status = 'experimental';

-- Readiness query optimization
CREATE INDEX IF NOT EXISTS idx_extensions_active
    ON ds_user_extensions(skill_id)
    WHERE status = 'active';

-- ── Constraint: suppressed_reason required when suppressed ────────────────────
-- SQLite does not support CREATE CONSTRAINT directly; enforced via CHECK.
-- Application layer must validate this as well.
-- (CHECK on multi-column conditions not supported in SQLite without triggers)
"""
# WO-SQUASH-BASELINE: migration 096 deleted (folded into 142); content inlined verbatim to preserve this test's scaffold.
M096 = """-- Migration 096: Friction signals table + finding dismissal columns (Phase 19.2)
--
-- Adds:
--   1. ds_friction_signals — harvested friction observations (passive capture at session-end)
--   2. findings.dismissed_at — when operator dismissed a finding
--   3. findings.dismissed_reason — text reason for dismissal
--
-- Three signal types (roadmap-explicit -- deferred types added on demand):
--   dismissed_finding   — finding dismissed by operator (false positive pattern)
--   partial_completion  — scan completed but findings never engaged with
--   pattern_gap         — low-confidence workflow pattern (inconsistent skill usage)
--
-- Consumer contract for 19.3 (Gap Classifier):
--   SELECT * FROM ds_friction_signals WHERE classified_as IS NULL ORDER BY created_at
--
-- Idempotency: bucket_key TEXT UNIQUE — harvester uses INSERT OR IGNORE.
-- Consecutive harvester runs produce no duplicate rows.

CREATE TABLE IF NOT EXISTS ds_friction_signals (
    signal_id       TEXT PRIMARY KEY,
    session_id      TEXT,
    project_id      TEXT,
    signal_type     TEXT NOT NULL CHECK(signal_type IN (
                        'dismissed_finding',
                        'partial_completion',
                        'pattern_gap'
                    )),
    skill_id        TEXT,
    rule_id         TEXT,
    source_table    TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    context         TEXT NOT NULL DEFAULT '{}',
    bucket_key      TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),

    -- 19.3 Gap Classifier writes these back after classification
    classified_as   TEXT CHECK(classified_as IS NULL OR classified_as IN (
                        'capability', 'personalization', 'onboarding'
                    )),
    classified_at   TEXT,

    -- 19.4 Guided Expansion links extension after compilation
    extension_id    TEXT
);

CREATE INDEX IF NOT EXISTS idx_friction_signals_skill
    ON ds_friction_signals(skill_id)
    WHERE skill_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_friction_signals_unclassified
    ON ds_friction_signals(created_at)
    WHERE classified_as IS NULL;

CREATE INDEX IF NOT EXISTS idx_friction_signals_type
    ON ds_friction_signals(signal_type, created_at);

-- Add dismissal tracking to the findings table.
-- dismissed_at IS NOT NULL → finding was dismissed by operator.
-- dismissed_reason is free text (e.g. "false positive — test file").
ALTER TABLE findings ADD COLUMN dismissed_at TEXT;
ALTER TABLE findings ADD COLUMN dismissed_reason TEXT;
"""
# WO-SQUASH-BASELINE: migration 097 deleted (folded into 142); content inlined verbatim to preserve this test's scaffold.
M097 = """-- Migration 097: Gap Classifier columns on ds_friction_signals (Phase 19.3)
--
-- Adds three columns to ds_friction_signals to support the hybrid
-- SQL+LLM classifier and operator review workflow:
--
--   classification_confidence REAL  — 0.0-1.0; SQL Tier 1 sets >= 0.8,
--                                     LLM Tier 2 sets 0.6-0.79, NULL = deferred
--   classification_reason TEXT      — one-line explanation shown in ds learn review
--   classification_skipped INTEGER  — operator dismissed this signal from review;
--                                     excluded from ds learn review output
--
-- No new table. All classifier results write back to ds_friction_signals.
--
-- Consumer contract for 19.4 (Guided Expansion):
--   SELECT * FROM ds_friction_signals
--   WHERE classified_as IS NOT NULL
--     AND classification_skipped = 0
--     AND extension_id IS NULL
--   ORDER BY classification_confidence DESC

ALTER TABLE ds_friction_signals ADD COLUMN classification_confidence REAL;
ALTER TABLE ds_friction_signals ADD COLUMN classification_reason TEXT;
ALTER TABLE ds_friction_signals ADD COLUMN classification_skipped INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_friction_classified_ready
    ON ds_friction_signals(classified_as, classification_confidence)
    WHERE classified_as IS NOT NULL AND classification_skipped = 0 AND extension_id IS NULL;
"""
# WO-SQUASH-BASELINE: migration 098 deleted (folded into 142); content inlined verbatim to preserve this test's scaffold.
M098 = """-- Migration 098: Add validation_detail JSON column to ds_user_extensions (Phase 19.5)
--
-- Adds audit-trail storage for retroactive validation results. The Decision 6
-- gate uses the existing four columns (baseline_eval_score, current_eval_score,
-- past_wo_count, last_validated_at). This column stores the full evidence:
-- which WOs were sampled, per-case scores, verdict reason.
--
-- Format: JSON or NULL
-- {
--   "validated_at": "2026-06-03T14:00:00",
--   "scan_ids_sampled": ["scan-1", "scan-2"],
--   "verdict": "active|experimental|experimental_with_warning|skip_onboarding",
--   "verdict_reason": "N=7, score=0.87 >= baseline*0.95=0.81",
--   "classification_path": "personalization|capability|onboarding",
--   "eval_cases_scored": [
--     {"eval_id": "eval_01", "baseline": 0.85, "current": 0.82}
--   ],
--   "force_override": false
-- }

ALTER TABLE ds_user_extensions ADD COLUMN validation_detail TEXT;
"""

FINDINGS_BASE = """
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY, project_id TEXT, scan_id TEXT,
    rule_id TEXT, severity TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open', introduced_by_skill_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
SCAN_RUNS_BASE = """
CREATE TABLE IF NOT EXISTS scan_runs (
    scan_id TEXT PRIMARY KEY, project_id TEXT, skill_id TEXT,
    status TEXT NOT NULL DEFAULT 'running', findings_count INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT, started_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
WF_BASE = """
CREATE TABLE IF NOT EXISTS ds_workflow_pattern_signals (
    pattern_id TEXT PRIMARY KEY, project_id TEXT,
    pattern_type TEXT NOT NULL DEFAULT 'always_paired',
    skill_a TEXT NOT NULL, skill_b TEXT,
    co_occurrence_count INTEGER NOT NULL DEFAULT 0, total_sessions INTEGER NOT NULL DEFAULT 1,
    confidence_score REAL NOT NULL DEFAULT 0.0, suppressed INTEGER NOT NULL DEFAULT 0,
    suppressed_at TEXT, last_observed_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
CANONICAL_EVENTS_BASE = """
CREATE TABLE IF NOT EXISTS canonical_events (
    event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    payload TEXT NOT NULL DEFAULT '{}', trace TEXT NOT NULL DEFAULT '{}'
);
"""
EVAL_BASELINES_BASE = """
CREATE TABLE IF NOT EXISTS ds_eval_baselines (
    eval_id TEXT PRIMARY KEY, version TEXT NOT NULL DEFAULT '1.0',
    baseline_score REAL NOT NULL, last_run_score REAL, last_run_at TEXT,
    regression_flag INTEGER DEFAULT 0, regression_threshold REAL DEFAULT 0.1,
    run_count INTEGER DEFAULT 1, last_updated_at TEXT, label TEXT
);
"""


@pytest.fixture
def full_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    for sql in (FINDINGS_BASE, SCAN_RUNS_BASE, WF_BASE, CANONICAL_EVENTS_BASE, EVAL_BASELINES_BASE):
        conn.executescript(sql)
    conn.executescript(M095)
    conn.executescript(M096)
    conn.executescript(M097)
    conn.executescript(M098)
    # Plant baseline data
    for i in range(1, 6):
        conn.execute(
            "INSERT OR REPLACE INTO ds_eval_baselines (eval_id, version, baseline_score, label) "
            "VALUES (?, '1.0', 0.85, 'pre_phase_19')",
            (f"eval_0{i}",),
        )
    conn.commit()
    return conn


@pytest.fixture
def validator(full_conn):
    from core.expansion.validation import RetroactiveValidator

    return RetroactiveValidator(full_conn)


def _uid() -> str:
    return str(uuid.uuid4())


def _insert_extension(
    conn,
    *,
    skill_id="ds-quality:security",
    classified_as="personalization",
    past_wo_count=5,
    status="proposed",
    rule_id="SEC-001",
) -> tuple[str, str]:
    signal_id = _uid()
    bk = f"{classified_as}:{skill_id}:{signal_id[:8]}"
    content_type = {
        "personalization": "threshold_override",
        "capability": "gap_filler",
        "onboarding": "example",
    }
    conn.execute(
        "INSERT INTO ds_friction_signals "
        "(signal_id, signal_type, skill_id, rule_id, source_table, source_id, context, "
        "bucket_key, classified_as, classified_at, classification_confidence, classification_reason) "
        "VALUES (?, 'dismissed_finding', ?, ?, 'findings', ?, '{}', ?, "
        "?, datetime('now'), 0.85, 'test reason')",
        (signal_id, skill_id, rule_id, signal_id, bk, classified_as),
    )
    ext_id = _uid()
    cf = json.dumps({"friction_signal_id": signal_id})
    ext_type = content_type.get(classified_as, "gap_filler")
    content_json = json.dumps(
        {
            "extension_type": ext_type,
            "skill_id": skill_id,
            "rule_id": rule_id,
            "description": "Test capability description",
            "compiled_from": [],
        }
    )
    conn.execute(
        "INSERT INTO ds_user_extensions "
        "(extension_id, skill_id, extension_type, content, source_signal, "
        "compiled_from, status, past_wo_count) "
        "VALUES (?, ?, ?, ?, 'friction', ?, ?, ?)",
        (ext_id, skill_id, ext_type, content_json, cf, status, past_wo_count),
    )
    conn.execute(
        "UPDATE ds_friction_signals SET extension_id = ? WHERE signal_id = ?", (ext_id, signal_id)
    )
    conn.commit()
    return signal_id, ext_id


def _insert_dismissed_finding(conn, skill_id, rule_id, n=5):
    for _ in range(n):
        conn.execute(
            "INSERT INTO findings (finding_id, introduced_by_skill_id, rule_id, "
            "dismissed_at, created_at) VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            (_uid(), skill_id, rule_id),
        )
    conn.commit()


# ── Schema: migration 098 ─────────────────────────────────────────────────


class TestMigration098Schema:
    def test_validation_detail_column_added(self, full_conn):
        cols = {r[1] for r in full_conn.execute("PRAGMA table_info(ds_user_extensions)")}
        assert "validation_detail" in cols

    def test_validation_detail_defaults_null(self, full_conn):
        _, ext_id = _insert_extension(full_conn)
        row = full_conn.execute(
            "SELECT validation_detail FROM ds_user_extensions WHERE extension_id = ?",
            (ext_id,),
        ).fetchone()
        assert row["validation_detail"] is None

    def test_migration_additive_only(self):
        sql = M098.upper()
        assert "DROP TABLE" not in sql
        assert "CREATE TABLE" not in sql
        assert "ALTER TABLE" in sql


# ── Decision 6 thresholds ─────────────────────────────────────────────────


class TestDecision6Thresholds:
    def test_n4_gives_experimental(self):
        from core.expansion.validation import apply_decision_6

        verdict, reason = apply_decision_6(score=0.97, baseline=1.0, n=4)
        assert verdict == "experimental"
        assert "insufficient_wo_count" in reason

    def test_n5_score_97pct_gives_active(self):
        from core.expansion.validation import apply_decision_6

        verdict, reason = apply_decision_6(score=0.97, baseline=1.0, n=5)
        assert verdict == "active"
        assert "N=5" in reason

    def test_n5_score_93pct_gives_experimental_with_warning(self):
        from core.expansion.validation import apply_decision_6

        # 0.93 < 0.95 × 1.0 = 0.95
        verdict, reason = apply_decision_6(score=0.93, baseline=1.0, n=5)
        assert verdict == "experimental_with_warning"
        assert "regression_detected" in reason

    def test_n5_score_exactly_95pct_gives_active(self):
        from core.expansion.validation import apply_decision_6

        # Exactly at boundary: 0.95 >= 1.0 * 0.95 = 0.95
        verdict, reason = apply_decision_6(score=0.95, baseline=1.0, n=5)
        assert verdict == "active", f"Exact boundary 0.95x should be active, got {verdict}"

    def test_force_override_n4_gives_active(self):
        from core.expansion.validation import apply_decision_6

        verdict, reason = apply_decision_6(score=0.97, baseline=1.0, n=4, force=True)
        assert verdict == "active"
        assert "force_override" in reason

    def test_n10_high_score_gives_active(self):
        from core.expansion.validation import apply_decision_6

        verdict, reason = apply_decision_6(score=0.90, baseline=0.85, n=10)
        # 0.90 >= 0.85 * 0.95 = 0.8075
        assert verdict == "active"


# ── Personalization validator ─────────────────────────────────────────────


class TestPersonalizationValidator:
    def test_high_dismissal_alignment_active(self, validator, full_conn):
        """Many dismissed findings for same rule → high alignment → active."""
        _, ext_id = _insert_extension(full_conn, classified_as="personalization", past_wo_count=5)
        _insert_dismissed_finding(full_conn, "ds-quality:security", "SEC-001", n=8)
        result = validator.validate(ext_id)
        assert result.success
        assert result.verdict in ("active", "experimental", "experimental_with_warning")
        assert result.tokens_estimated == 0  # SQL only

    def test_zero_token_cost(self, validator, full_conn):
        """Personalization validation uses zero tokens."""
        _, ext_id = _insert_extension(full_conn, classified_as="personalization", past_wo_count=5)
        result = validator.validate(ext_id)
        assert result.tokens_estimated == 0

    def test_verdict_detail_reason_populated(self, validator, full_conn):
        """Verdict reason contains N and threshold info."""
        _, ext_id = _insert_extension(full_conn, classified_as="personalization", past_wo_count=5)
        _insert_dismissed_finding(full_conn, "ds-quality:security", "SEC-001", n=5)
        result = validator.validate(ext_id)
        assert result.verdict_reason
        assert "N=5" in result.verdict_reason or "insufficient" in result.verdict_reason

    def test_n4_stays_experimental(self, validator, full_conn):
        """N < 5 must always produce experimental regardless of score."""
        _, ext_id = _insert_extension(full_conn, classified_as="personalization", past_wo_count=4)
        _insert_dismissed_finding(full_conn, "ds-quality:security", "SEC-001", n=10)
        result = validator.validate(ext_id)
        assert result.verdict == "experimental"
        assert "insufficient_wo_count" in result.verdict_reason

    def test_n5_score_regression_experimental_with_warning(self, validator, full_conn):
        """N=5 but score below threshold → experimental_with_warning."""
        _, ext_id = _insert_extension(full_conn, classified_as="personalization", past_wo_count=5)
        # No dismissed findings → alignment=0 → score=0.70 < baseline*0.95≈0.81
        result = validator.validate(ext_id)
        assert result.success
        assert result.current_eval_score is not None
        if result.past_wo_count >= 5:
            if result.current_eval_score < result.baseline_eval_score * 0.95:
                assert result.verdict in ("experimental_with_warning", "experimental")

    def test_validation_detail_persisted(self, validator, full_conn):
        """validation_detail JSON written to db after validation."""
        _, ext_id = _insert_extension(full_conn, classified_as="personalization", past_wo_count=5)
        validator.validate(ext_id)
        row = full_conn.execute(
            "SELECT validation_detail, status FROM ds_user_extensions WHERE extension_id = ?",
            (ext_id,),
        ).fetchone()
        assert row["validation_detail"] is not None
        detail = json.loads(row["validation_detail"])
        assert "verdict" in detail
        assert "verdict_reason" in detail


# ── Capability validator ──────────────────────────────────────────────────


class TestCapabilityValidator:
    def _mock_eval_result(self, score=0.88):
        from core.eval.schema import EvalResult, MatchResult

        match_result = MagicMock(spec=MatchResult)
        match_result.score = score
        match_result.negative_violations = []
        match_result.missing_events = []
        match_result.out_of_order = []
        match_result.matched_required = 1
        match_result.total_required = 1
        return EvalResult(
            eval_id="ext_test_v",
            version="19.5",
            passed=score >= 0.75,
            composite_score=score,
            event_score=score,
            match_result=match_result,
            regression_flagged=False,
            baseline_score=0.85,
            run_mode="fixture",
            tokens_consumed=200,
        )

    def test_capability_uses_eval_runner(self, validator, full_conn):
        """Capability validator calls EvalRunner.run_case (not a custom scorer)."""
        from core.expansion.validation import CapabilityValidator

        source = inspect.getsource(CapabilityValidator)
        assert "EvalRunner" in source, "CapabilityValidator must use EvalRunner"
        assert "EvalCase" in source, "CapabilityValidator must construct EvalCase"

    def test_capability_validation_with_mock_runner(self, validator, full_conn):
        """Capability validation produces correct verdict with mocked runner."""
        _, ext_id = _insert_extension(full_conn, classified_as="capability", past_wo_count=6)

        mock_result = self._mock_eval_result(score=0.88)
        with patch(
            "core.expansion.validation.CapabilityValidator._read_baseline", return_value=0.85
        ):
            with patch("core.eval.runner.EvalRunner") as MockRunner:
                MockRunner.return_value.run_case.return_value = mock_result
                result = validator.validate(ext_id)

        assert result.success
        assert result.current_eval_score == 0.88
        # 0.88 >= 0.85 * 0.95 = 0.8075 → active
        assert result.verdict == "active"
        assert result.tokens_estimated == 200  # from mock result

    def test_capability_score_below_threshold_experimental(self, full_conn):
        """Score below 0.95× baseline → experimental_with_warning."""
        from core.expansion.validation import RetroactiveValidator

        validator = RetroactiveValidator(full_conn)
        _, ext_id = _insert_extension(full_conn, classified_as="capability", past_wo_count=5)

        mock_result = self._mock_eval_result(score=0.70)
        with patch(
            "core.expansion.validation.CapabilityValidator._read_baseline", return_value=0.85
        ):
            with patch("core.eval.runner.EvalRunner") as MockRunner:
                MockRunner.return_value.run_case.return_value = mock_result
                result = validator.validate(ext_id)

        assert result.success
        # 0.70 < 0.85 * 0.95 = 0.8075
        assert result.verdict in ("experimental_with_warning", "experimental")

    def test_eval_harness_not_duplicated(self):
        """CapabilityValidator must not contain scoring logic; reuses EvalRunner."""
        from core.expansion.validation import CapabilityValidator

        source = inspect.getsource(CapabilityValidator)
        # Should not contain inline 70/30 scoring — that's in EvalRunner
        assert "0.7 *" not in source and "0.3 *" not in source, (
            "CapabilityValidator must not duplicate eval scoring logic. "
            "Use EvalRunner.run_case() instead."
        )


# ── Onboarding validator ──────────────────────────────────────────────────


class TestOnboardingValidator:
    def test_onboarding_skips_gate(self, validator, full_conn):
        """Onboarding extension goes directly to experimental, no score computed."""
        _, ext_id = _insert_extension(full_conn, classified_as="onboarding", past_wo_count=0)
        result = validator.validate(ext_id)
        assert result.success
        assert result.verdict == "experimental"
        assert "onboarding_skips_gate" in result.verdict_reason

    def test_onboarding_has_no_eval_score(self, validator, full_conn):
        """Onboarding current_eval_score must be None — gate is skipped."""
        _, ext_id = _insert_extension(full_conn, classified_as="onboarding", past_wo_count=0)
        result = validator.validate(ext_id)
        assert result.current_eval_score is None, (
            "Onboarding extensions must not have current_eval_score computed. "
            "The gate is intentionally skipped for documentation extensions."
        )

    def test_onboarding_zero_token_cost(self, validator, full_conn):
        _, ext_id = _insert_extension(full_conn, classified_as="onboarding")
        result = validator.validate(ext_id)
        assert result.tokens_estimated == 0

    def test_onboarding_status_transitions_on_confirm(self, full_conn):
        """After user_confirmed_at is set on an experimental onboarding ext, it can go active."""
        from core.expansion.validation import RetroactiveValidator

        v = RetroactiveValidator(full_conn)
        _, ext_id = _insert_extension(full_conn, classified_as="onboarding", status="experimental")
        v.validate(ext_id)

        # Set user_confirmed_at (simulate operator confirmation)
        full_conn.execute(
            "UPDATE ds_user_extensions SET user_confirmed_at = datetime('now') "
            "WHERE extension_id = ?",
            (ext_id,),
        )
        full_conn.commit()

        # Verify Decision 6 query would now include this extension for promotion
        row = full_conn.execute(
            "SELECT * FROM ds_user_extensions WHERE extension_id = ? "
            "AND user_confirmed_at IS NOT NULL",
            (ext_id,),
        ).fetchone()
        assert row is not None, "Extension with user_confirmed_at should be queryable for promotion"


# ── Session-end auto-increment ────────────────────────────────────────────


class TestSessionEndAutoIncrement:
    def _insert_scan_run(self, conn, skill_id="ds-quality:security"):
        conn.execute(
            "INSERT INTO scan_runs (scan_id, skill_id, status, created_at) "
            "VALUES (?, ?, 'completed', datetime('now'))",
            (_uid(), skill_id),
        )
        conn.commit()

    def test_past_wo_count_increments(self, validator, full_conn):
        """Session hook increments past_wo_count for matching extensions."""
        _, ext_id = _insert_extension(full_conn, past_wo_count=3, skill_id="ds-quality:security")
        self._insert_scan_run(full_conn, "ds-quality:security")
        validator.increment_for_session()
        row = full_conn.execute(
            "SELECT past_wo_count FROM ds_user_extensions WHERE extension_id = ?",
            (ext_id,),
        ).fetchone()
        assert row["past_wo_count"] == 4

    def test_count_3_to_4_no_auto_validate(self, validator, full_conn):
        """N=4 after increment should not trigger auto-validation."""
        _, ext_id = _insert_extension(full_conn, past_wo_count=3, classified_as="personalization")
        self._insert_scan_run(full_conn)
        validator.increment_for_session()
        row = full_conn.execute(
            "SELECT status FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        # Status is still 'proposed' — no auto-validate at N=4
        assert row["status"] == "proposed"

    def test_count_4_to_5_triggers_auto_validate(self, validator, full_conn):
        """N=5 after increment triggers full validation."""
        _, ext_id = _insert_extension(
            full_conn,
            past_wo_count=4,
            classified_as="personalization",
            skill_id="ds-quality:security",
        )
        self._insert_scan_run(full_conn)
        _insert_dismissed_finding(full_conn, "ds-quality:security", "SEC-001", n=5)
        validator.increment_for_session()
        row = full_conn.execute(
            "SELECT status, last_validated_at FROM ds_user_extensions WHERE extension_id = ?",
            (ext_id,),
        ).fetchone()
        # Auto-validate must have run (last_validated_at populated)
        assert (
            row["last_validated_at"] is not None
        ), "Auto-validation must fire when past_wo_count crosses 5"

    def test_session_hook_is_nonblocking(self, full_conn):
        """Exception in increment_for_session does not propagate."""
        from core.expansion.validation import RetroactiveValidator

        class _BrokenConn:
            row_factory = None

            def execute(self, *a, **k):
                raise RuntimeError("DB exploded")

            def commit(self):
                pass

        v = RetroactiveValidator(_BrokenConn())
        v.increment_for_session()  # must not raise

    def test_studio_db_has_validation_hook(self):
        """studio_db.py must include the Phase 19.5 validation hook."""
        source = (REPO_ROOT / "core/event_store/event_writer.py").read_text(encoding="utf-8")
        assert "RetroactiveValidator" in source
        assert "increment_for_session" in source


# ── Token cost documentation ──────────────────────────────────────────────


class TestTokenCostDocumentation:
    def test_personalization_zero_tokens(self, validator, full_conn):
        _, ext_id = _insert_extension(full_conn, classified_as="personalization", past_wo_count=5)
        result = validator.validate(ext_id)
        assert (
            result.tokens_estimated == 0
        ), "Personalization validation is pure SQL — zero token cost."

    def test_capability_reports_tokens(self, full_conn):
        from core.expansion.validation import RetroactiveValidator

        v = RetroactiveValidator(full_conn)
        _, ext_id = _insert_extension(full_conn, classified_as="capability", past_wo_count=5)

        mock_result = MagicMock()
        mock_result.composite_score = 0.88
        mock_result.tokens_consumed = 250
        mock_result.passed = True

        with patch(
            "core.expansion.validation.CapabilityValidator._read_baseline", return_value=0.85
        ):
            with patch("core.eval.runner.EvalRunner") as MockRunner:
                MockRunner.return_value.run_case.return_value = mock_result
                result = v.validate(ext_id)

        assert result.tokens_estimated == 250, (
            "Capability tokens_estimated must reflect EvalRunner.tokens_consumed. "
            f"Token cost documentation: ~250 tokens per capability validation. "
            f"Monthly (5/week × 4 weeks): ~{250 * 5 * 4:,} tokens."
        )

    def test_onboarding_zero_tokens(self, validator, full_conn):
        _, ext_id = _insert_extension(full_conn, classified_as="onboarding")
        result = validator.validate(ext_id)
        assert result.tokens_estimated == 0


# ── Local-first / boundary ────────────────────────────────────────────────


class TestLocalFirstAndBoundary:
    def test_no_network_imports_in_validation_py(self):
        import core.expansion.validation as mod

        source = inspect.getsource(mod)
        import_lines = [
            ln.strip()
            for ln in source.splitlines()
            if ln.strip().startswith("import ") or ln.strip().startswith("from ")
        ]
        import_text = "\n".join(import_lines).lower()
        forbidden = ["urllib", "requests", "httpx", "aiohttp", "openai", "anthropic"]
        for lib in forbidden:
            assert lib not in import_text, f"Forbidden import {lib!r} in validation.py"

    def test_eval_runner_source_unmodified(self):
        """core/eval/runner.py must not be modified by 19.5 (additive only)."""
        source = (REPO_ROOT / "core/eval/runner.py").read_text(encoding="utf-8")
        # Should not reference validation.py
        assert "RetroactiveValidator" not in source
        assert "from core.expansion" not in source

    def test_19_4_compilers_unmodified(self):
        """19.4a/b/c compilers not modified by 19.5."""
        for name in ("personalization", "capability", "onboarding"):
            source = (REPO_ROOT / f"core/expansion/{name}.py").read_text(encoding="utf-8")
            assert "RetroactiveValidator" not in source

    def test_decision_6_uses_exact_threshold(self):
        """Decision 6 uses exactly 0.95 tolerance (roadmap-explicit)."""
        from core.expansion.validation import DECISION_6_SCORE_TOLERANCE, DECISION_6_N_THRESHOLD

        assert (
            DECISION_6_SCORE_TOLERANCE == 0.95
        ), f"Threshold must be exactly 0.95 per roadmap. Got {DECISION_6_SCORE_TOLERANCE}"
        assert DECISION_6_N_THRESHOLD == 5
