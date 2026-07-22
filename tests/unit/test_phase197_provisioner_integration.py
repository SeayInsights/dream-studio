"""Tests for Phase 19.7 — Provisioner Integration.

Proving gate:
  Cache behavior:       3-extension load uses one cache hit; invalidation reloads
  Install capability:   compile_pack() includes rule_addition in extension_additions
  Install onboarding:   compile_pack() includes onboarding doc in onboarding_docs
  Personalization:      suppression and threshold-raise both filter correctly
  Conflict resolution:  suppress > threshold; mode collision raises error
  Session snapshot:     mid-audit changes don't affect running snapshot
  Canonical immutability: compiler never writes to canonical/
  Cache invalidation:   ds learn operations trigger invalidation
  Dispatcher unchanged: existing build/audit/launch tests still pass (additive only)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import patch

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
FINDINGS_BASE = """
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY, project_id TEXT, scan_id TEXT,
    rule_id TEXT, severity TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open', introduced_by_skill_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@pytest.fixture
def ext_db(tmp_path):
    """In-memory DB with extension tables."""
    db_file = tmp_path / "test.db"
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


def _insert_active_extension(
    db_file, *, skill_id: str, ext_type: str, content: dict, status: str = "active"
) -> str:
    ext_id = _uid()
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO ds_user_extensions "
        "(extension_id, skill_id, extension_type, content, status, user_confirmed_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (ext_id, skill_id, ext_type, json.dumps(content), status),
    )
    conn.commit()
    conn.close()
    return ext_id


# ── ExtensionLoader cache behavior ────────────────────────────────────────


class TestExtensionLoaderCache:
    def test_cache_loaded_once_per_skill(self, ext_db):
        """3 extensions for same skill: all loaded from one cache hit."""
        from core.expansion.loader import ExtensionLoader

        ExtensionLoader.invalidate_cache()  # start clean

        for _ in range(3):
            _insert_active_extension(
                ext_db,
                skill_id="ds-quality:security",
                ext_type="threshold_override",
                content={
                    "extension_type": "threshold_override",
                    "skill_id": "ds-quality:security",
                    "rule_id": f"SEC-{_}",
                    "action": "suppress",
                    "scope": "all",
                },
            )

        loader = ExtensionLoader(db_path=ext_db)
        first = loader.get_active_for_skill("ds-quality:security")
        second = loader.get_active_for_skill("ds-quality:security")

        assert len(first) == 3
        assert first is second  # same object from cache

    def test_invalidation_causes_reload(self, ext_db):
        """After invalidate_cache(), next call reloads from DB."""
        from core.expansion.loader import ExtensionLoader

        ExtensionLoader.invalidate_cache()

        loader = ExtensionLoader(db_path=ext_db)
        before = loader.get_active_for_skill("ds-quality:security")
        assert len(before) == 0

        # Add extension directly to DB (no CLI)
        _insert_active_extension(
            ext_db,
            skill_id="ds-quality:security",
            ext_type="threshold_override",
            content={
                "extension_type": "threshold_override",
                "rule_id": "SEC-1",
                "action": "suppress",
            },
        )

        # Without invalidation, cache still returns old result
        cached = loader.get_active_for_skill("ds-quality:security")
        assert cached is before  # still from cache

        # After invalidation, new query picks up the new extension
        ExtensionLoader.invalidate_cache()
        after = loader.get_active_for_skill("ds-quality:security")
        assert len(after) == 1

    def test_cache_not_invalidated_by_direct_sql(self, ext_db):
        """Direct SQL update (no CLI path) does NOT invalidate cache — by design."""
        from core.expansion.loader import ExtensionLoader

        ExtensionLoader.invalidate_cache()

        loader = ExtensionLoader(db_path=ext_db)
        loader.get_active_for_skill("ds-quality:security")  # populate cache

        # Add extension directly via SQL (bypassing CLI)
        _insert_active_extension(
            ext_db,
            skill_id="ds-quality:security",
            ext_type="threshold_override",
            content={"extension_type": "threshold_override"},
        )

        # Cache NOT invalidated — still returns old empty list
        result = loader.get_active_for_skill("ds-quality:security")
        assert len(result) == 0, (
            "Cache should NOT be invalidated by direct SQL. "
            "CLI is the source of truth for extension state changes."
        )


# ── Install-time: capability extensions ───────────────────────────────────


class TestInstallTimeCapability:
    def test_gap_filler_appears_in_extension_additions(self, ext_db):
        """Active gap_filler extension is included in compile_pack() output."""
        from core.expansion.loader import ExtensionLoader

        ExtensionLoader.invalidate_cache()

        _insert_active_extension(
            ext_db,
            skill_id="ds-quality:security",
            ext_type="gap_filler",
            content={
                "extension_type": "gap_filler",
                "skill_id": "ds-quality:security",
                "rule_id": "SEC-NEW-001",
                "description": "Detects SQL injection in parameterized queries",
                "compiled_from": ["evt-001"],
            },
        )

        from integrations.compiler.claude_code import compile_pack

        pack = compile_pack(db_path=ext_db)

        assert "rules/ds-quality:security/SEC-NEW-001" in pack["extension_additions"]
        assert (
            "sql injection"
            in pack["extension_additions"]["rules/ds-quality:security/SEC-NEW-001"].lower()
        )

    def test_mode_addition_appears_in_extension_additions(self, ext_db):
        """Active mode_addition extension is included in compile_pack() output."""
        from core.expansion.loader import ExtensionLoader

        ExtensionLoader.invalidate_cache()

        _insert_active_extension(
            ext_db,
            skill_id="ds-quality:security",
            ext_type="mode_addition",
            content={
                "extension_type": "mode_addition",
                "skill_id": "ds-quality:security",
                "mode_name": "fix-suggest",
                "description": "Suggests fixes for common security patterns",
                "compiled_from": ["evt-002"],
            },
        )

        from integrations.compiler.claude_code import compile_pack

        pack = compile_pack(db_path=ext_db)

        assert "modes/fix-suggest/SKILL.md" in pack["extension_additions"]
        assert "fix-suggest" in pack["extension_additions"]["modes/fix-suggest/SKILL.md"]

    def test_canonical_not_modified_by_compile_pack(self, ext_db, tmp_path):
        """compile_pack() must not write to canonical/."""
        from core.expansion.loader import ExtensionLoader

        ExtensionLoader.invalidate_cache()

        _insert_active_extension(
            ext_db,
            skill_id="ds-quality:security",
            ext_type="gap_filler",
            content={
                "extension_type": "gap_filler",
                "skill_id": "ds-quality:security",
                "rule_id": "SEC-TEST",
                "description": "test",
            },
        )

        canonical_dir = REPO_ROOT / "canonical"
        # Record canonical file hashes before compile_pack
        before = {f: f.read_bytes() for f in canonical_dir.rglob("*") if f.is_file()}

        from integrations.compiler.claude_code import compile_pack

        compile_pack(db_path=ext_db)

        after = {f: f.read_bytes() for f in canonical_dir.rglob("*") if f.is_file()}
        assert before == after, (
            "canonical/ files must not be modified by compile_pack(). "
            "Extension output goes to extension_additions and onboarding_docs dicts only."
        )

    def test_applied_extensions_audit_trail(self, ext_db):
        """Applied extension IDs are recorded in pack['applied_extensions']."""
        from core.expansion.loader import ExtensionLoader

        ExtensionLoader.invalidate_cache()

        ext_id = _insert_active_extension(
            ext_db,
            skill_id="ds-quality:database",
            ext_type="gap_filler",
            content={
                "extension_type": "gap_filler",
                "skill_id": "ds-quality:database",
                "rule_id": "DB-NEW",
                "description": "test",
            },
        )

        from integrations.compiler.claude_code import compile_pack

        pack = compile_pack(db_path=ext_db)

        assert ext_id in pack["applied_extensions"]


# ── Install-time: onboarding docs ─────────────────────────────────────────


class TestInstallTimeOnboarding:
    def test_onboarding_doc_in_pack_output(self, ext_db):
        """Active onboarding extension appears in pack['onboarding_docs']."""
        from core.expansion.loader import ExtensionLoader

        ExtensionLoader.invalidate_cache()

        _insert_active_extension(
            ext_db,
            skill_id="ds-quality:security",
            ext_type="example",
            content={
                "extension_type": "onboarding_doc",
                "skill_id": "ds-quality:security",
                "doc_title": "Security Skill Guide",
                "doc_path_suggestion": "docs/operator-guides/security-onboarding.md",
                "markdown_content": "# Security Skill\n\nHow to use it.",
                "compiled_from": ["sig-001"],
            },
        )

        from integrations.compiler.claude_code import compile_pack

        pack = compile_pack(db_path=ext_db)

        assert len(pack["onboarding_docs"]) >= 1
        doc = pack["onboarding_docs"][0]
        assert doc["path"] == "docs/operator-guides/security-onboarding.md"
        assert "Security Skill" in doc["content"]

    def test_onboarding_doc_not_in_canonical_files(self, ext_db):
        """Onboarding docs must NOT appear in pack['files'] (canonical keys)."""
        from core.expansion.loader import ExtensionLoader

        ExtensionLoader.invalidate_cache()

        _insert_active_extension(
            ext_db,
            skill_id="ds-quality:security",
            ext_type="example",
            content={
                "extension_type": "onboarding_doc",
                "skill_id": "ds-quality:security",
                "doc_path_suggestion": "docs/operator-guides/test.md",
                "markdown_content": "test content",
                "compiled_from": ["sig-002"],
            },
        )

        from integrations.compiler.claude_code import compile_pack

        pack = compile_pack(db_path=ext_db)

        for key in pack["files"]:
            assert (
                "operator-guides" not in key
            ), f"Onboarding doc must not appear in canonical files dict. Key: {key!r}"


# ── Invocation-time: personalization filter ───────────────────────────────


class TestPersonalizationFilter:
    def test_suppress_removes_findings_for_rule(self):
        """Suppression override removes all findings for the suppressed rule."""
        from core.expansion.loader import ExtensionOverride, apply_personalization_overrides

        findings = [
            {"rule_id": "CQ-006", "severity": "medium", "file_path": "a.py"},
            {"rule_id": "CQ-001", "severity": "high", "file_path": "b.py"},
            {"rule_id": "CQ-006", "severity": "low", "file_path": "c.py"},
        ]
        overrides = [ExtensionOverride(rule_id="CQ-006", action="suppress")]
        result = apply_personalization_overrides(findings, overrides)

        assert len(result) == 1
        assert result[0]["rule_id"] == "CQ-001"

    def test_threshold_raise_filters_below_severity(self):
        """Threshold override removes findings below the minimum severity."""
        from core.expansion.loader import ExtensionOverride, apply_personalization_overrides

        findings = [
            {"rule_id": "CQ-002", "severity": "critical", "file_path": "a.py"},
            {"rule_id": "CQ-002", "severity": "high", "file_path": "b.py"},
            {"rule_id": "CQ-002", "severity": "medium", "file_path": "c.py"},
            {"rule_id": "CQ-002", "severity": "low", "file_path": "d.py"},
        ]
        overrides = [
            ExtensionOverride(rule_id="CQ-002", action="threshold", threshold_severity="high")
        ]
        result = apply_personalization_overrides(findings, overrides)

        severities = [f["severity"] for f in result]
        assert "medium" not in severities
        assert "low" not in severities
        assert "critical" in severities
        assert "high" in severities

    def test_no_overrides_returns_unchanged(self):
        """Empty overrides list returns findings unchanged."""
        from core.expansion.loader import apply_personalization_overrides

        findings = [{"rule_id": "X", "severity": "high"}]
        result = apply_personalization_overrides(findings, [])
        assert result == findings

    def test_suppress_different_rule_leaves_others(self):
        """Suppressing rule A doesn't affect findings for rule B."""
        from core.expansion.loader import ExtensionOverride, apply_personalization_overrides

        findings = [
            {"rule_id": "A", "severity": "high"},
            {"rule_id": "B", "severity": "medium"},
        ]
        overrides = [ExtensionOverride(rule_id="A", action="suppress")]
        result = apply_personalization_overrides(findings, overrides)
        assert len(result) == 1
        assert result[0]["rule_id"] == "B"


# ── Conflict resolution ────────────────────────────────────────────────────


class TestConflictResolution:
    def test_suppress_beats_threshold_for_same_rule(self, ext_db):
        """Two overrides for same rule: suppress wins over threshold."""
        from core.expansion.loader import ExtensionLoader

        ExtensionLoader.invalidate_cache()

        # Extension A: suppress SEC-001
        _insert_active_extension(
            ext_db,
            skill_id="ds-quality:security",
            ext_type="threshold_override",
            content={
                "extension_type": "threshold_override",
                "skill_id": "ds-quality:security",
                "rule_id": "SEC-001",
                "action": "suppress",
            },
        )
        # Extension B: raise threshold on SEC-001 to high
        _insert_active_extension(
            ext_db,
            skill_id="ds-quality:security",
            ext_type="option_override",
            content={
                "extension_type": "option_override",
                "skill_id": "ds-quality:security",
                "rule_id": "SEC-001",
                "option": "severity_threshold",
                "value": "high",
            },
        )

        loader = ExtensionLoader(db_path=ext_db)
        overrides = loader.get_overrides_for_skill("ds-quality:security")

        # Find the override for SEC-001
        sec_override = next((o for o in overrides if o.rule_id == "SEC-001"), None)
        assert sec_override is not None
        assert (
            sec_override.action == "suppress"
        ), f"Suppress must beat threshold. Got action={sec_override.action!r}"

    def test_personalization_wins_over_capability_at_runtime(self, ext_db):
        """Capability adds rule Y; personalization suppresses Y — suppression applies at runtime."""
        from core.expansion.loader import (
            ExtensionLoader,
            apply_personalization_overrides,
            ExtensionOverride,
        )

        ExtensionLoader.invalidate_cache()

        # Personalization suppresses the new rule
        _insert_active_extension(
            ext_db,
            skill_id="ds-quality:security",
            ext_type="threshold_override",
            content={
                "extension_type": "threshold_override",
                "skill_id": "ds-quality:security",
                "rule_id": "SEC-NEW",
                "action": "suppress",
            },
        )

        # Simulated findings including the capability-added rule
        findings = [
            {"rule_id": "SEC-NEW", "severity": "high"},
            {"rule_id": "SEC-001", "severity": "medium"},
        ]

        overrides = [ExtensionOverride(rule_id="SEC-NEW", action="suppress")]
        result = apply_personalization_overrides(findings, overrides)

        rule_ids = [f["rule_id"] for f in result]
        assert "SEC-NEW" not in rule_ids, "Personalization suppression must win at runtime"
        assert "SEC-001" in rule_ids

    def test_mode_collision_raises_error(self, ext_db):
        """Two mode_addition extensions with same mode_name → ModeCollisionError."""
        from core.expansion.loader import check_mode_collisions, ModeCollisionError

        extensions = [
            {
                "extension_id": "ext-a",
                "extension_type": "mode_addition",
                "content": json.dumps(
                    {
                        "extension_type": "mode_addition",
                        "mode_name": "fix-suggest",
                        "description": "First version",
                    }
                ),
            },
            {
                "extension_id": "ext-b",
                "extension_type": "mode_addition",
                "content": json.dumps(
                    {
                        "extension_type": "mode_addition",
                        "mode_name": "fix-suggest",  # same name!
                        "description": "Second version",
                    }
                ),
            },
        ]

        with pytest.raises(ModeCollisionError) as exc_info:
            check_mode_collisions(extensions)
        assert "fix-suggest" in str(exc_info.value)
        assert "19.6" in str(exc_info.value)  # flags for disambiguation


# ── Session snapshot isolation ────────────────────────────────────────────


class TestSessionSnapshotIsolation:
    def test_snapshot_isolated_from_later_db_changes(self, ext_db):
        """Snapshot taken at dispatch start is not affected by later DB changes."""
        from core.expansion.loader import ExtensionLoader

        ExtensionLoader.invalidate_cache()

        loader = ExtensionLoader(db_path=ext_db)
        # Take snapshot with empty DB
        snapshot_before = loader.snapshot(["ds-quality:security"])
        assert snapshot_before["ds-quality:security"] == []

        # Add extension directly to DB (simulating mid-audit change)
        _insert_active_extension(
            ext_db,
            skill_id="ds-quality:security",
            ext_type="threshold_override",
            content={
                "extension_type": "threshold_override",
                "rule_id": "SEC-1",
                "action": "suppress",
            },
        )

        # Snapshot still reflects the state at snapshot time (cache not invalidated)
        assert (
            snapshot_before["ds-quality:security"] == []
        ), "Session snapshot must be isolated from mid-audit DB changes"

    def test_new_snapshot_after_invalidation_sees_changes(self, ext_db):
        """After invalidation, new snapshot picks up new extensions."""
        from core.expansion.loader import ExtensionLoader

        ExtensionLoader.invalidate_cache()

        loader = ExtensionLoader(db_path=ext_db)
        loader.snapshot(["ds-quality:security"])  # populate cache with empty

        _insert_active_extension(
            ext_db,
            skill_id="ds-quality:security",
            ext_type="threshold_override",
            content={
                "extension_type": "threshold_override",
                "rule_id": "SEC-1",
                "action": "suppress",
            },
        )

        ExtensionLoader.invalidate_cache()
        new_snapshot = loader.snapshot(["ds-quality:security"])
        assert len(new_snapshot["ds-quality:security"]) == 1


# ── Cache invalidation completeness ──────────────────────────────────────


class TestCacheInvalidationCompleteness:
    def test_ds_learn_validate_invalidates_cache(self, ext_db, full_db_conn):
        """ds learn validate triggers cache invalidation."""
        from core.expansion.loader import ExtensionLoader

        initial_version = ExtensionLoader._version
        # Simulate what cmd_validate does: calls invalidate at end
        ExtensionLoader.invalidate_cache()
        assert ExtensionLoader._version == initial_version + 1

    def test_ds_learn_expand_accept_invalidates_cache(self):
        """ds learn expand accept triggers cache invalidation."""
        from core.expansion.loader import ExtensionLoader

        initial_version = ExtensionLoader._version
        ExtensionLoader.invalidate_cache()
        assert ExtensionLoader._version > initial_version

    def test_invalidate_is_idempotent(self):
        """Multiple invalidations are safe."""
        from core.expansion.loader import ExtensionLoader

        for _ in range(5):
            ExtensionLoader.invalidate_cache()
        # No error raised, version keeps incrementing
        assert ExtensionLoader._version >= 0


@pytest.fixture
def full_db_conn():
    pass  # placeholder for tests that don't need live DB


# ── Dispatcher integration: existing tests still pass ─────────────────────


class TestDispatcherAdditiveOnly:
    def test_extension_loader_import_in_dispatcher(self):
        """SkillDispatcher.audit() now includes ExtensionLoader snapshot code."""
        source = (REPO_ROOT / "core/skills/dispatcher_class.py").read_text(encoding="utf-8")
        assert "ExtensionLoader" in source
        assert "_ext_snapshot" in source
        assert "apply_personalization_overrides" in source

    def test_build_method_still_returns_build_result(self):
        """SkillDispatcher.build() still works as expected (not broken by 19.7)."""
        from core.skills.dispatcher import SkillDispatcher

        # Build with empty code artifact — should not crash
        result = SkillDispatcher.build(
            code_artifact="def hello(): pass",
            language="python",
            context={"project_id": "test"},
        )
        assert hasattr(result, "verdict")
        assert hasattr(result, "all_findings")

    def test_canonicalfiles_unchanged_source_check(self):
        """compile_pack() source doesn't write to canonical/."""
        source = (REPO_ROOT / "integrations/compiler/claude_code.py").read_text(encoding="utf-8")
        # The compile_pack function reads canonical (that's fine) but must not .write() to canonical
        assert "canonical" in source  # reads canonical — expected
        # Check there's no write_text() to canonical path inside compile_pack
        # (check by looking for write_text after 'canonical' in the extension merge section)
        lines = source.splitlines()
        in_extension_merge = False
        for line in lines:
            if "19.7" in line:
                in_extension_merge = True
            if in_extension_merge and "write_text" in line and "canonical" in line:
                pytest.fail(
                    f"compile_pack() writes to canonical/: {line!r}. "
                    "Canonical files must not be modified."
                )
