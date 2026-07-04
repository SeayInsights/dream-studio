"""Tests for Phase 19.6 — Extension Description Disambiguation.

Proving gate:
  Jaccard correctness:    1.0, 0.33, 0.0 edge cases
  Threshold behavior:     clean / warning / critical / force-override
  Classification gating:  mode_addition and gap_filler checked; others skip
  Hook into 19.5:         validation → disambiguation → final status
  CLI:                    --rewrite / --accept-warning / --force tier-gating
  19.5 + 19.7 unchanged:  additive only
  Token cost:             0 (no LLM)
  Local-first:            no network calls
"""

from __future__ import annotations

import inspect
import json
import sqlite3
import uuid
from pathlib import Path

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
EVAL_BASELINES_BASE = """
CREATE TABLE IF NOT EXISTS ds_eval_baselines (
    eval_id TEXT PRIMARY KEY, version TEXT NOT NULL DEFAULT '1.0',
    baseline_score REAL NOT NULL, last_run_score REAL, last_run_at TEXT,
    regression_flag INTEGER DEFAULT 0, regression_threshold REAL DEFAULT 0.1,
    run_count INTEGER DEFAULT 1, last_updated_at TEXT, label TEXT
);
"""
CANONICAL_EVENTS_BASE = """
CREATE TABLE IF NOT EXISTS canonical_events (
    event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    payload TEXT NOT NULL DEFAULT '{}', trace TEXT NOT NULL DEFAULT '{}'
);
"""


@pytest.fixture
def full_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(FINDINGS_BASE)
    conn.executescript(WF_BASE)
    conn.executescript(EVAL_BASELINES_BASE)
    conn.executescript(CANONICAL_EVENTS_BASE)
    conn.executescript(M095)
    conn.executescript(M096)
    conn.executescript(M097)
    conn.executescript(M098)
    # Plant baseline data for 19.5 validator
    for i in range(1, 4):
        conn.execute(
            "INSERT OR REPLACE INTO ds_eval_baselines (eval_id, version, baseline_score, label) "
            "VALUES (?, '1.0', 0.85, 'pre_phase_19')",
            (f"eval_0{i}",),
        )
    conn.commit()
    return conn


@pytest.fixture
def ext_db_file(tmp_path):
    """SQLite file with base extension tables for CLI tests."""
    db_file = tmp_path / "test_disambig.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.executescript(FINDINGS_BASE)
    conn.executescript(WF_BASE)
    conn.executescript(M095)
    conn.executescript(M096)
    conn.executescript(M097)
    conn.executescript(M098)
    conn.close()
    return db_file


def _uid() -> str:
    return str(uuid.uuid4())


# ── Jaccard correctness ───────────────────────────────────────────────────


class TestJaccardSimilarity:
    def test_identical_strings(self):
        from core.expansion.disambiguation import jaccard_similarity

        assert jaccard_similarity("hello world", "hello world") == 1.0

    def test_one_word_overlap_of_three_union(self):
        from core.expansion.disambiguation import jaccard_similarity

        # A = {hello, world}; B = {goodbye, world}
        # intersection = {world} = 1; union = {hello, world, goodbye} = 3
        result = jaccard_similarity("hello world", "goodbye world")
        assert abs(result - 1 / 3) < 0.001

    def test_empty_string_returns_zero(self):
        from core.expansion.disambiguation import jaccard_similarity

        assert jaccard_similarity("", "anything") == 0.0
        assert jaccard_similarity("anything", "") == 0.0
        assert jaccard_similarity("", "") == 0.0

    def test_no_overlap_returns_zero(self):
        from core.expansion.disambiguation import jaccard_similarity

        result = jaccard_similarity("apple banana", "car truck")
        assert result == 0.0

    def test_case_insensitive(self):
        from core.expansion.disambiguation import jaccard_similarity

        assert jaccard_similarity("Hello World", "hello world") == 1.0

    def test_single_word_match(self):
        from core.expansion.disambiguation import jaccard_similarity

        # A = {security}; B = {security, check}
        # intersection = {security}; union = {security, check}
        result = jaccard_similarity("security", "security check")
        assert abs(result - 0.5) < 0.001


# ── Threshold tiers ───────────────────────────────────────────────────────


class TestThresholdBehavior:
    def _ext(
        self,
        description: str,
        ext_type: str = "mode_addition",
        skill_id: str = "ds-quality:security",
    ) -> dict:
        return {
            "extension_id": _uid(),
            "extension_type": ext_type,
            "skill_id": skill_id,
            "content": json.dumps({"extension_type": ext_type, "description": description}),
        }

    def test_clean_below_70(self):
        """Score < 0.70 → clean, no collision."""
        from core.expansion.disambiguation import check_extension_description
        from unittest.mock import patch

        ext = self._ext("completely unrelated domain entirely different topic area")
        # Mock canonical descriptions to control scores
        with patch(
            "core.expansion.disambiguation.load_canonical_descriptions",
            return_value=[("skill-a", "hello world totally unrelated xyz abc def")],
        ):
            result = check_extension_description(ext)
        assert result.status == "clean"

    def test_warning_at_0_80(self):
        """Score 0.70-0.85 → warning tier.

        A = {a, b, c, d} (4 words); B = {a, b, c, d, e} (5 words)
        intersection = 4; union = 5; jaccard = 4/5 = 0.80 → warning
        """
        from core.expansion.disambiguation import check_extension_description
        from unittest.mock import patch

        ext = self._ext("a b c d")
        with patch(
            "core.expansion.disambiguation.load_canonical_descriptions",
            return_value=[("skill-x", "a b c d e")],
        ):
            result = check_extension_description(ext)
        assert (
            result.status == "warning"
        ), f"Expected warning (score=0.80 in 0.70-0.85 range), got {result.status}"

    def test_critical_at_0_90(self):
        """Score ≥ 0.85 → critical tier."""
        from core.expansion.disambiguation import check_extension_description
        from unittest.mock import patch

        # A = {a-i} = 9 words; B = {a-i, extra} = 10 words
        # intersection = 9; union = 10; jaccard = 0.9 → critical
        desc_a3 = "a b c d e f g h i"
        desc_b3 = "a b c d e f g h i extra"
        ext = self._ext(desc_a3)
        with patch(
            "core.expansion.disambiguation.load_canonical_descriptions",
            return_value=[("critical-skill", desc_b3)],
        ):
            result = check_extension_description(ext)
        assert result.status == "critical", f"Expected critical, got {result.status}"

    def test_thresholds_are_correct_values(self):
        """Thresholds match roadmap-explicit values from 18.9.9 decision log."""
        from core.expansion.disambiguation import WARNING_THRESHOLD, CRITICAL_THRESHOLD

        assert WARNING_THRESHOLD == 0.70
        assert CRITICAL_THRESHOLD == 0.85


# ── Classification gating ─────────────────────────────────────────────────


class TestClassificationGating:
    def _make_ext(self, ext_type: str) -> dict:
        return {
            "extension_id": _uid(),
            "extension_type": ext_type,
            "skill_id": "ds-quality:security",
            "content": json.dumps(
                {"extension_type": ext_type, "description": "detect security issues in code"}
            ),
        }

    def test_mode_addition_fires_check(self):
        from core.expansion.disambiguation import check_extension_description
        from unittest.mock import patch

        ext = self._make_ext("mode_addition")
        with patch(
            "core.expansion.disambiguation.load_canonical_descriptions",
            return_value=[("test-skill", "totally different unrelated domains xyz")],
        ):
            result = check_extension_description(ext)
        assert result.status == "clean"  # no collision, but check DID run

    def test_gap_filler_fires_within_skill(self):
        from core.expansion.disambiguation import check_extension_description
        from unittest.mock import patch

        ext = self._make_ext("gap_filler")
        with patch(
            "core.expansion.disambiguation.load_canonical_descriptions", return_value=[]
        ) as mock_load:
            result = check_extension_description(ext)
            # Was called with skill_id (within-skill check)
            mock_load.assert_called_once_with("ds-quality:security")
        assert result.status == "clean"

    def test_threshold_override_skipped(self):
        from core.expansion.disambiguation import check_extension_description

        ext = self._make_ext("threshold_override")
        result = check_extension_description(ext)
        assert result.status == "clean"
        assert "no check" in result.verdict_reason

    def test_option_override_skipped(self):
        from core.expansion.disambiguation import check_extension_description

        ext = self._make_ext("option_override")
        result = check_extension_description(ext)
        assert result.status == "clean"

    def test_onboarding_doc_skipped(self):
        from core.expansion.disambiguation import check_extension_description

        ext = {
            "extension_id": _uid(),
            "extension_type": "example",
            "skill_id": "ds-quality:security",
            "content": json.dumps(
                {"extension_type": "onboarding_doc", "doc_title": "Security Guide"}
            ),
        }
        result = check_extension_description(ext)
        assert result.status == "clean"

    def test_example_type_skipped(self):
        from core.expansion.disambiguation import check_extension_description

        ext = self._make_ext("example")
        result = check_extension_description(ext)
        assert result.status == "clean"


# ── Hook into 19.5 ────────────────────────────────────────────────────────


class TestHookInto195:
    def _insert_proposed_extension(
        self,
        conn,
        *,
        classified_as="capability",
        ext_type="mode_addition",
        description="detect security issues",
        past_wo_count=5,
    ) -> tuple[str, str]:
        signal_id = _uid()
        bk = f"{classified_as}:{signal_id[:8]}"
        conn.execute(
            "INSERT INTO ds_friction_signals "
            "(signal_id, signal_type, skill_id, source_table, source_id, context, bucket_key, "
            "classified_as, classified_at, classification_confidence, classification_reason) "
            "VALUES (?, 'pattern_gap', 'ds-quality:security', 'ds_workflow_pattern_signals', "
            "?, '{}', ?, ?, datetime('now'), 0.85, 'test')",
            (signal_id, signal_id, bk, classified_as),
        )
        ext_id = _uid()
        cf = json.dumps({"friction_signal_id": signal_id})
        conn.execute(
            "INSERT INTO ds_user_extensions "
            "(extension_id, skill_id, extension_type, content, source_signal, compiled_from, "
            "status, past_wo_count, user_confirmed_at, baseline_eval_score, current_eval_score) "
            "VALUES (?, 'ds-quality:security', ?, ?, 'friction', ?, 'experimental', ?, "
            "datetime('now'), 0.85, 0.87)",
            (
                ext_id,
                ext_type,
                json.dumps(
                    {
                        "extension_type": ext_type,
                        "description": description,
                        "skill_id": "ds-quality:security",
                    }
                ),
                cf,
                past_wo_count,
            ),
        )
        conn.execute(
            "UPDATE ds_friction_signals SET extension_id = ? WHERE signal_id = ?",
            (ext_id, signal_id),
        )
        conn.commit()
        return signal_id, ext_id

    def test_clean_check_allows_active(self, full_conn):
        """Clean disambiguation check → extension goes active."""
        from core.expansion.validation import RetroactiveValidator
        from unittest.mock import patch, MagicMock
        from core.expansion.disambiguation import CollisionResult

        _, ext_id = self._insert_proposed_extension(
            full_conn, description="unique unrelated capability"
        )

        clean_result = CollisionResult(
            status="clean",
            extension_id=ext_id,
            candidate_description="unique unrelated capability",
            verdict_reason="no collision",
        )
        mock_eval = MagicMock()
        mock_eval.composite_score = 0.88
        mock_eval.tokens_consumed = 50
        mock_eval.passed = True

        with patch(
            "core.expansion.disambiguation.check_extension_description", return_value=clean_result
        ):
            with patch("core.eval.runner.EvalRunner") as MockRunner:
                MockRunner.return_value.run_case.return_value = mock_eval
                with patch(
                    "core.expansion.validation.CapabilityValidator._read_baseline",
                    return_value=0.85,
                ):
                    v = RetroactiveValidator(full_conn)
                    v.validate(ext_id)

        row = full_conn.execute(
            "SELECT status FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        assert row["status"] == "active"

    def test_warning_collision_blocks_active(self, full_conn):
        """Warning-tier collision → extension stays experimental."""
        from core.expansion.validation import RetroactiveValidator
        from unittest.mock import patch, MagicMock
        from core.expansion.disambiguation import CollisionResult, CollisionPair

        _, ext_id = self._insert_proposed_extension(full_conn, description="test description")

        warning_result = CollisionResult(
            status="warning",
            extension_id=ext_id,
            candidate_description="test description",
            collisions=[
                CollisionPair(
                    compared_id="skill-x",
                    compared_description="test description similar",
                    similarity_score=0.75,
                )
            ],
            verdict_reason="description collision: similarity=0.75 with 'skill-x'",
        )
        mock_eval = MagicMock()
        mock_eval.composite_score = 0.88
        mock_eval.tokens_consumed = 50
        mock_eval.passed = True

        with patch(
            "core.expansion.disambiguation.check_extension_description", return_value=warning_result
        ):
            with patch("core.eval.runner.EvalRunner") as MockRunner:
                MockRunner.return_value.run_case.return_value = mock_eval
                with patch(
                    "core.expansion.validation.CapabilityValidator._read_baseline",
                    return_value=0.85,
                ):
                    v = RetroactiveValidator(full_conn)
                    v.validate(ext_id)

        row = full_conn.execute(
            "SELECT status, validation_detail FROM ds_user_extensions WHERE extension_id = ?",
            (ext_id,),
        ).fetchone()
        assert row["status"] == "experimental"
        detail = json.loads(row["validation_detail"])
        assert "collision_check" in detail
        assert detail["collision_check"]["status"] == "warning"

    def test_critical_collision_blocks_active(self, full_conn):
        """Critical-tier collision → extension stays experimental."""
        from core.expansion.validation import RetroactiveValidator
        from unittest.mock import patch, MagicMock
        from core.expansion.disambiguation import CollisionResult, CollisionPair

        _, ext_id = self._insert_proposed_extension(full_conn, description="test description")

        critical_result = CollisionResult(
            status="critical",
            extension_id=ext_id,
            candidate_description="test description",
            collisions=[
                CollisionPair(
                    compared_id="skill-y",
                    compared_description="test description very close",
                    similarity_score=0.90,
                )
            ],
            verdict_reason="critical collision: similarity=0.90",
        )
        mock_eval = MagicMock()
        mock_eval.composite_score = 0.88
        mock_eval.tokens_consumed = 50
        mock_eval.passed = True

        with (
            patch(
                "core.expansion.disambiguation.check_extension_description",
                return_value=critical_result,
            ),
            patch("core.eval.runner.EvalRunner") as MockRunner,
        ):
            MockRunner.return_value.run_case.return_value = mock_eval
            with patch(
                "core.expansion.validation.CapabilityValidator._read_baseline",
                return_value=0.85,
            ):
                v = RetroactiveValidator(full_conn)
                v.validate(ext_id)

        row = full_conn.execute(
            "SELECT status FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        assert row["status"] == "experimental"


# ── CLI tier-gating ───────────────────────────────────────────────────────


class TestCliTierGating:
    def _insert_blocked_extension(
        self, conn, *, status="experimental", collision_status="warning", similarity_score=0.75
    ) -> str:
        ext_id = _uid()
        detail = json.dumps(
            {
                "verdict": status,
                "collision_check": {
                    "status": collision_status,
                    "top_collision": {
                        "compared_id": "test-skill",
                        "similarity_score": similarity_score,
                    },
                    "accepted": False,
                    "force_reason": "",
                },
            }
        )
        conn.execute(
            "INSERT INTO ds_user_extensions "
            "(extension_id, skill_id, extension_type, content, status, validation_detail) "
            "VALUES (?, 'ds-quality:security', 'mode_addition', ?, ?, ?)",
            (
                ext_id,
                json.dumps(
                    {
                        "extension_type": "mode_addition",
                        "description": "test description for collision check",
                    }
                ),
                status,
                detail,
            ),
        )
        conn.commit()
        return ext_id

    def test_accept_warning_succeeds_for_warning_tier(self, ext_db_file):
        """--accept-warning activates a warning-tier blocked extension."""
        from core.expansion.disambiguation import CollisionResult
        from unittest.mock import patch

        conn = sqlite3.connect(str(ext_db_file))
        conn.row_factory = sqlite3.Row
        ext_id = self._insert_blocked_extension(conn, collision_status="warning")
        conn.commit()

        warning_result = CollisionResult(
            status="warning",
            extension_id=ext_id,
            candidate_description="test",
            collisions=[],
            verdict_reason="warning",
        )
        with patch(
            "core.expansion.disambiguation.check_extension_description", return_value=warning_result
        ):
            import argparse

            args = argparse.Namespace(
                extension_id=ext_id,
                rewrite=None,
                accept_warning=True,
                force=None,
                db_path=ext_db_file,
            )
            from interfaces.cli.ds_learn import cmd_disambiguate

            cmd_disambiguate(args)

        row = conn.execute(
            "SELECT status FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        conn.close()
        assert row["status"] == "active"

    def test_accept_warning_rejects_critical_tier(self, ext_db_file):
        """--accept-warning must not activate a critical-tier collision."""
        from core.expansion.disambiguation import CollisionResult
        from unittest.mock import patch

        conn = sqlite3.connect(str(ext_db_file))
        conn.row_factory = sqlite3.Row
        ext_id = self._insert_blocked_extension(
            conn, collision_status="critical", similarity_score=0.92
        )
        conn.commit()

        critical_result = CollisionResult(
            status="critical",
            extension_id=ext_id,
            candidate_description="test",
            collisions=[],
            verdict_reason="critical",
        )
        with patch(
            "core.expansion.disambiguation.check_extension_description",
            return_value=critical_result,
        ):
            import argparse

            args = argparse.Namespace(
                extension_id=ext_id,
                rewrite=None,
                accept_warning=True,
                force=None,
                db_path=ext_db_file,
            )
            from interfaces.cli.ds_learn import cmd_disambiguate

            exit_code = cmd_disambiguate(args)

        assert exit_code == 1, "--accept-warning must return exit 1 for critical tier"
        row = conn.execute(
            "SELECT status FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        conn.close()
        assert row["status"] != "active"

    def test_force_override_logs_reason(self, ext_db_file):
        """--force activates any tier and logs the reason."""
        from core.expansion.disambiguation import CollisionResult
        from unittest.mock import patch

        conn = sqlite3.connect(str(ext_db_file))
        conn.row_factory = sqlite3.Row
        ext_id = self._insert_blocked_extension(
            conn, collision_status="critical", similarity_score=0.90
        )
        conn.commit()

        critical_result = CollisionResult(
            status="critical",
            extension_id=ext_id,
            candidate_description="test",
            collisions=[],
            verdict_reason="critical",
        )
        with patch(
            "core.expansion.disambiguation.check_extension_description",
            return_value=critical_result,
        ):
            import argparse

            args = argparse.Namespace(
                extension_id=ext_id,
                rewrite=None,
                accept_warning=False,
                force="intentional override for production fix",
                db_path=ext_db_file,
            )
            from interfaces.cli.ds_learn import cmd_disambiguate

            cmd_disambiguate(args)

        row = conn.execute(
            "SELECT status, validation_detail FROM ds_user_extensions WHERE extension_id = ?",
            (ext_id,),
        ).fetchone()
        conn.close()
        assert row["status"] == "active"
        detail = json.loads(row["validation_detail"])
        assert "intentional override" in detail.get("verdict_reason", "")


# ── Zero LLM / local-first ────────────────────────────────────────────────


class TestZeroLlmLocalFirst:
    def test_no_llm_in_disambiguation_py(self):
        import core.expansion.disambiguation as mod

        source = inspect.getsource(mod)
        import_lines = [
            ln.strip()
            for ln in source.splitlines()
            if ln.strip().startswith("import ") or ln.strip().startswith("from ")
        ]
        import_text = "\n".join(import_lines).lower()
        forbidden = ["subprocess", "shutil", "anthropic", "openai", "requests", "httpx", "urllib"]
        for lib in forbidden:
            assert lib not in import_text, f"Forbidden import {lib!r} in disambiguation.py"

    def test_token_cost_zero(self):
        from core.expansion.disambiguation import check_extension_description, CollisionResult
        from unittest.mock import patch

        ext = {
            "extension_id": "test-id",
            "extension_type": "mode_addition",
            "skill_id": "ds-quality:security",
            "content": json.dumps({"extension_type": "mode_addition", "description": "test"}),
        }
        with patch("core.expansion.disambiguation.load_canonical_descriptions", return_value=[]):
            result = check_extension_description(ext)
        # CollisionResult has no tokens field — confirms zero token design
        assert not hasattr(result, "tokens_estimated")


# ── 19.5 and 19.7 still pass ──────────────────────────────────────────────


class TestAdditiveOnly:
    def test_validation_module_hook_is_non_blocking(self):
        """Exception in disambiguation doesn't break 19.5 validation."""
        source = (REPO_ROOT / "core/expansion/validation.py").read_text(encoding="utf-8")
        assert "_check_disambiguation" in source
        assert "except Exception" in source  # non-blocking try/except

    def test_loader_import_lines_unchanged(self):
        """19.7 loader.py imports are not modified by 19.6."""
        source = (REPO_ROOT / "core/expansion/loader.py").read_text(encoding="utf-8")
        import_lines = [
            ln
            for ln in source.splitlines()
            if ln.strip().startswith("import ") or ln.strip().startswith("from ")
        ]
        import_text = "\n".join(import_lines).lower()
        assert (
            "disambiguation" not in import_text
        ), "loader.py must not import from disambiguation module"
