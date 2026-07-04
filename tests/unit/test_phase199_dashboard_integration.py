"""Tests for Phase 19.9 — Dashboard Integration.

Proving gate:
  API endpoints:      list, health, summary, detail, effect-summary, revert
  Revert flow:        status → dismissed, validation_detail logged, cache invalidated
  Cache invalidation: revert triggers ExtensionLoader.invalidate_cache()
  Empty state:        empty tables return empty arrays not errors
  Effect framing:     capability/onboarding return honest 'not yet tracked' (no false metrics)
  Existing tests:     additive only, nothing regresses
  Local-first:        no external network calls
  Mid-WO checkpoint:  API + revert end-to-end documented
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

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


@pytest.fixture
def ext_db(tmp_path):
    db = tmp_path / "test_dash.db"
    conn = sqlite3.connect(str(db))
    for sql in (FINDINGS_BASE, WF_BASE):
        conn.executescript(sql)
    for m in (M095, M096, M097, M098):
        conn.executescript(m)
    conn.close()
    return db


def _uid():
    return str(uuid.uuid4())


def _insert_ext(
    db_file,
    *,
    skill_id="ds-quality:security",
    ext_type="threshold_override",
    status="active",
    past_wo_count=6,
    score=0.88,
    baseline=0.85,
):
    ext_id = _uid()
    conn = sqlite3.connect(str(db_file))
    content = json.dumps(
        {
            "extension_type": ext_type,
            "skill_id": skill_id,
            "rule_id": "SEC-001",
            "action": "suppress",
        }
    )
    conn.execute(
        "INSERT INTO ds_user_extensions "
        "(extension_id, skill_id, extension_type, content, status, past_wo_count, "
        "current_eval_score, baseline_eval_score, user_confirmed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (ext_id, skill_id, ext_type, content, status, past_wo_count, score, baseline),
    )
    conn.commit()
    conn.close()
    return ext_id


def _insert_signal(
    db_file,
    *,
    signal_type="dismissed_finding",
    skill_id="ds-quality:security",
    classified_as="personalization",
):
    sig_id = _uid()
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO ds_friction_signals "
        "(signal_id, signal_type, skill_id, source_table, source_id, context, bucket_key, "
        "classified_as, classified_at, classification_confidence) "
        "VALUES (?, ?, ?, 'findings', ?, '{}', ?, ?, datetime('now'), 0.85)",
        (sig_id, signal_type, skill_id, sig_id, f"bk-{sig_id[:8]}", classified_as),
    )
    conn.commit()
    conn.close()
    return sig_id


@pytest.fixture
def test_client(ext_db):
    """FastAPI test client with patched get_connection pointing to test DB."""
    from projections.api.routes.extensions_api import app as _  # noqa: ensure imported
    from projections.api.main import app

    with patch("projections.api.routes.extensions_api.get_connection") as mock_conn:

        def _get_conn():
            c = sqlite3.connect(str(ext_db))
            c.row_factory = sqlite3.Row
            return c

        mock_conn.side_effect = _get_conn
        with TestClient(app) as client:
            yield client, ext_db


# ── GET /extensions ───────────────────────────────────────────────────────


class TestListExtensions:
    def test_returns_empty_for_empty_db(self, ext_db):
        from projections.api.routes.extensions_api import list_extensions
        import asyncio

        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            result = asyncio.run(list_extensions(status="active"))
        assert result["extensions"] == []
        assert result["count"] == 0

    def test_filters_by_status(self, ext_db):
        from projections.api.routes.extensions_api import list_extensions
        import asyncio

        _insert_ext(ext_db, status="active")
        _insert_ext(ext_db, status="experimental")
        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            active = asyncio.run(list_extensions(status="active"))
            experimental = asyncio.run(list_extensions(status="experimental"))
        assert active["count"] == 1
        assert experimental["count"] == 1

    def test_includes_health_tier_and_type_label(self, ext_db):
        from projections.api.routes.extensions_api import list_extensions
        import asyncio

        _insert_ext(ext_db, status="active", score=0.90, baseline=0.85)
        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            result = asyncio.run(list_extensions(status="active"))
        ext = result["extensions"][0]
        assert "health_tier" in ext
        assert "type_label" in ext
        assert ext["health_tier"] == "improving"  # 0.90 > 0.85
        assert ext["type_label"] == "suppression"  # threshold_override


# ── GET /extensions/health ────────────────────────────────────────────────


class TestExtensionHealth:
    def test_empty_returns_four_empty_buckets(self, ext_db):
        from projections.api.routes.extensions_api import get_extension_health
        import asyncio

        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            result = asyncio.run(get_extension_health())
        for bucket in ("improving", "steady", "degrading", "untracked"):
            assert bucket in result
            assert result[bucket] == []

    def test_classifies_correctly(self, ext_db):
        from projections.api.routes.extensions_api import get_extension_health
        import asyncio

        _insert_ext(ext_db, status="active", score=0.90, baseline=0.85)  # improving (0.90>0.85)
        _insert_ext(
            ext_db, status="active", score=0.82, baseline=0.85
        )  # steady (0.965 in [0.95,1.0))
        _insert_ext(ext_db, status="active", score=0.79, baseline=0.85)  # degrading (<0.95)
        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            result = asyncio.run(get_extension_health())
        assert len(result["improving"]) == 1
        assert len(result["steady"]) == 1
        assert len(result["degrading"]) == 1


# ── GET /extensions/summary ───────────────────────────────────────────────


class TestExtensionSummary:
    def test_returns_counts_for_populated_db(self, ext_db):
        from projections.api.routes.extensions_api import get_extension_summary
        import asyncio

        _insert_ext(ext_db, status="active")
        _insert_ext(ext_db, status="experimental")
        _insert_signal(ext_db)
        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            result = asyncio.run(get_extension_summary())
        assert result["extensions"]["active"] == 1
        assert result["extensions"]["experimental"] == 1
        assert result["friction_signals"]["total"] == 1
        assert result["friction_signals"]["classified"] == 1


# ── GET /extensions/{id}/effect-summary ──────────────────────────────────


class TestEffectSummary:
    def test_personalization_returns_tracked(self, ext_db):
        from projections.api.routes.extensions_api import get_extension_effect_summary
        import asyncio

        ext_id = _insert_ext(ext_db, ext_type="threshold_override", status="active")
        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            result = asyncio.run(get_extension_effect_summary(ext_id))
        assert result["tracked"] is True
        assert result["effect_type"] == "findings_suppressed"
        assert "count" in result

    def test_capability_returns_not_tracked(self, ext_db):
        """Capability extensions must not claim metrics that don't exist."""
        from projections.api.routes.extensions_api import get_extension_effect_summary
        import asyncio

        ext_id = _insert_ext(ext_db, ext_type="gap_filler", status="active")
        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            result = asyncio.run(get_extension_effect_summary(ext_id))
        assert result["tracked"] is False, (
            "Capability extensions must return tracked=False — no fire-count instrumentation exists. "
            "Claiming metrics that don't exist violates the honest framing requirement."
        )

    def test_onboarding_returns_not_tracked(self, ext_db):
        """Onboarding docs must not claim read-tracking that doesn't exist."""
        from projections.api.routes.extensions_api import get_extension_effect_summary
        import asyncio

        ext_id = _insert_ext(ext_db, ext_type="example", status="active")
        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            result = asyncio.run(get_extension_effect_summary(ext_id))
        assert result["tracked"] is False


# ── POST /extensions/{id}/revert ─────────────────────────────────────────


class TestRevertEndpoint:
    def test_revert_changes_status_to_dismissed(self, ext_db):
        from projections.api.routes.extensions_api import revert_extension, RevertRequest
        import asyncio

        ext_id = _insert_ext(ext_db, status="active")
        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            result = asyncio.run(revert_extension(ext_id, RevertRequest(reason="test revert")))
        assert result["status"] == "deprecated"
        conn = sqlite3.connect(str(ext_db))
        row = conn.execute(
            "SELECT status FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        conn.close()
        assert row[0] == "deprecated"

    def test_revert_logs_reason_in_validation_detail(self, ext_db):
        from projections.api.routes.extensions_api import revert_extension, RevertRequest
        import asyncio

        ext_id = _insert_ext(ext_db, status="active")
        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            asyncio.run(revert_extension(ext_id, RevertRequest(reason="intentional revert")))
        conn = sqlite3.connect(str(ext_db))
        row = conn.execute(
            "SELECT validation_detail FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        conn.close()
        detail = json.loads(row[0] or "{}")
        assert "revert" in detail
        assert detail["revert"]["reason"] == "intentional revert"
        assert "reverted_at" in detail["revert"]

    def test_revert_invalidates_extension_loader_cache(self, ext_db):
        from projections.api.routes.extensions_api import revert_extension, RevertRequest
        import asyncio

        ext_id = _insert_ext(ext_db, status="active")
        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            with patch("core.expansion.loader.ExtensionLoader.invalidate_cache") as mock_inv:
                asyncio.run(revert_extension(ext_id, RevertRequest()))
                mock_inv.assert_called_once()

    def test_revert_404_for_missing_extension(self, ext_db):
        from projections.api.routes.extensions_api import revert_extension, RevertRequest
        from fastapi import HTTPException
        import asyncio

        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(revert_extension("does-not-exist", RevertRequest()))
        assert exc_info.value.status_code == 404

    def test_revert_then_dispatch_ignores_extension(self, ext_db):
        """After revert, ExtensionLoader.get_active_for_skill returns empty for this extension."""
        from projections.api.routes.extensions_api import revert_extension, RevertRequest
        from core.expansion.loader import ExtensionLoader
        import asyncio

        ext_id = _insert_ext(ext_db, status="active", skill_id="ds-quality:security")

        ExtensionLoader.invalidate_cache()
        loader = ExtensionLoader(db_path=ext_db)
        before = loader.get_active_for_skill("ds-quality:security")
        assert len(before) == 1  # extension present before revert

        with patch("projections.api.routes.extensions_api.get_connection") as m:
            m.side_effect = lambda: (lambda c: (setattr(c, "row_factory", sqlite3.Row) or c))(
                sqlite3.connect(str(ext_db))
            )
            asyncio.run(revert_extension(ext_id, RevertRequest(reason="test")))

        # After revert, cache is invalidated and next query sees dismissed status
        after = loader.get_active_for_skill("ds-quality:security")
        assert len(after) == 0, "After revert, extension must not be returned as active"


# ── Adaptation tab in frontend ────────────────────────────────────────────


class TestFrontendAdaptationTab:
    def test_adaptation_tab_content_exists(self):
        """The Adaptation tab content div must be present in dashboard.html."""
        source = (REPO_ROOT / "projections/frontend/dashboard.html").read_text(encoding="utf-8")
        assert 'id="adaptation"' in source, "Adaptation tab content div missing"

    def test_four_panels_present(self):
        """All four roadmap-specified panels must be present."""
        source = (REPO_ROOT / "projections/frontend/dashboard.html").read_text(encoding="utf-8")
        assert "ad-personalization-list" in source
        assert "ad-patterns-list" in source
        assert "ad-health-list" in source
        assert "ad-experimental-list" in source

    def test_revert_modal_present(self):
        """The revert modal is the most important UX element — must be present."""
        source = (REPO_ROOT / "projections/frontend/dashboard.html").read_text(encoding="utf-8")
        assert "ad-revert-modal" in source
        assert "confirmRevert" in source
        assert "openRevertModal" in source

    def test_operator_framing_language(self):
        """Operator-facing language must be present; technical jargon must not be in UI labels."""
        source = (REPO_ROOT / "projections/frontend/dashboard.html").read_text(encoding="utf-8")
        assert "Changes Applied to Your Builds" in source
        assert "Things Dream Studio Has Noticed" in source
        assert "Awaiting More Data" in source

    def test_no_jargon_in_panel_labels(self):
        """Technical terms must not appear as visible panel headings."""
        source = (REPO_ROOT / "projections/frontend/dashboard.html").read_text(encoding="utf-8")
        # These should only appear inside JS/code, not as panel h3 headings
        # The adaptation section should use operator language
        adapt_start = source.find('id="adaptation"')
        adapt_end = source.find("<!-- PRD Progress Tab", adapt_start)
        adapt_section = source[adapt_start:adapt_end]
        # These jargon terms should not appear as h3 headings in the section
        for jargon in ("threshold_override", "option_override", "compiled_from"):
            assert (
                f">{jargon}<" not in adapt_section
            ), f"Jargon {jargon!r} appears as visible text in adaptation section"


# ── Additive-only boundary ────────────────────────────────────────────────


class TestAdditiveOnly:
    def test_main_py_still_imports_existing_routes(self):
        """Existing routes must not be removed."""
        source = (REPO_ROOT / "projections/api/main.py").read_text(encoding="utf-8")
        for module in (
            "intelligence",
            "security",
            "guard_metrics_router",
            "aggregate_metrics_router",
        ):
            assert module in source

    def test_extensions_api_router_registered(self):
        """New extensions_api router must be registered in main.py."""
        source = (REPO_ROOT / "projections/api/main.py").read_text(encoding="utf-8")
        assert "extensions_api_router" in source

    def test_no_network_calls_in_extensions_api(self):
        import inspect
        import projections.api.routes.extensions_api as mod

        src = inspect.getsource(mod)
        import_lines = [
            ln.strip() for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))
        ]
        import_text = "\n".join(import_lines).lower()
        for lib in ("urllib", "requests", "httpx", "aiohttp"):
            assert lib not in import_text
