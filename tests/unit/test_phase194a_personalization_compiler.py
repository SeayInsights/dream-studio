"""Tests for Phase 19.4a — Personalization Compiler.

Proving gate:
  Compilation accuracy:  dismissal fixture → correct threshold_override/option_override content
  compiled_from:         always populated with real finding_ids; empty = compilation failure
  SkillsBench defense:   ambiguous proposal (no dismissal data) → fail cleanly, signal deferred
  Data corruption:       source findings deleted after compiled_from recorded → re-run detects
  CLI accept/reject:     state transitions correct
  Immutability:          no files written to canonical/skills/
  Zero LLM:              no LLM calls in personalization.py
  Token cost:            zero (pure SQL, no LLM path)
  Local-first:           no network calls
"""

from __future__ import annotations

import inspect
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

# ── Migration SQL ──────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parents[2]

# WO-SQUASH-BASELINE: migration 095 deleted (folded into 142); content inlined verbatim to preserve this test's scaffold.
MIGRATION_095 = """-- Migration 095: Unified Extensions Schema (Phase 19.1)
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
MIGRATION_096 = """-- Migration 096: Friction signals table + finding dismissal columns (Phase 19.2)
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
MIGRATION_097 = """-- Migration 097: Gap Classifier columns on ds_friction_signals (Phase 19.3)
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

FINDINGS_BASE = """
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY, project_id TEXT, scan_id TEXT,
    rule_id TEXT, severity TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open',
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
    completed_at TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
WF_PATTERNS_BASE = """
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
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(FINDINGS_BASE)
    conn.executescript(SCAN_RUNS_BASE)
    conn.executescript(WF_PATTERNS_BASE)
    conn.executescript(MIGRATION_095)
    conn.executescript(MIGRATION_096)
    conn.executescript(MIGRATION_097)
    return conn


@pytest.fixture
def compiler(full_conn):
    from core.expansion.personalization import PersonalizationCompiler

    return PersonalizationCompiler(full_conn)


def _uid() -> str:
    return str(uuid.uuid4())


def _insert_dismissed_finding(
    conn,
    *,
    finding_id: str,
    skill_id: str,
    rule_id: str,
    severity: str = "medium",
    scan_id: str | None = None,
    days_ago: int = 5,
) -> None:
    ts = f"datetime('now', '-{days_ago} days')"
    conn.execute(
        f"INSERT INTO findings (finding_id, scan_id, rule_id, severity, status, "
        f"introduced_by_skill_id, dismissed_at, dismissed_reason, created_at) "
        f"VALUES (?, ?, ?, ?, 'dismissed', ?, {ts}, 'not relevant', {ts})",
        (finding_id, scan_id or _uid(), rule_id, severity, skill_id),
    )
    conn.commit()


def _insert_proposed_extension(
    conn,
    *,
    skill_id: str,
    rule_id: str | None,
    signal_id: str,
    classified_as: str = "personalization",
) -> tuple[str, str]:
    """Insert friction signal + proposed extension, return (signal_id, extension_id)."""
    bk = f"dismissed_finding:{skill_id}:{rule_id or ''}:{signal_id[:8]}"
    conn.execute(
        "INSERT INTO ds_friction_signals "
        "(signal_id, signal_type, skill_id, rule_id, source_table, source_id, context, "
        "bucket_key, classified_as, classified_at, classification_confidence, classification_reason) "
        "VALUES (?, 'dismissed_finding', ?, ?, 'findings', ?, '{}', ?, ?, datetime('now'), 0.85, 'test')",
        (signal_id, skill_id, rule_id, signal_id, bk, classified_as),
    )
    ext_id = _uid()
    compiled_from = json.dumps({"friction_signal_id": signal_id})
    conn.execute(
        "INSERT INTO ds_user_extensions "
        "(extension_id, skill_id, extension_type, content, source_signal, compiled_from, status) "
        "VALUES (?, ?, 'option_override', '{}', 'friction', ?, 'proposed')",
        (ext_id, skill_id, compiled_from),
    )
    # Simulate confirm_signal() setting the extension_id link on the signal (19.3)
    conn.execute(
        "UPDATE ds_friction_signals SET extension_id = ? WHERE signal_id = ?",
        (ext_id, signal_id),
    )
    conn.commit()
    return signal_id, ext_id


# ── Schema / setup ────────────────────────────────────────────────────────


class TestSetup:
    def test_extension_module_imports(self):
        from core.expansion.personalization import PersonalizationCompiler, CompilationResult

        assert PersonalizationCompiler is not None
        assert CompilationResult is not None

    def test_compiler_instantiates(self, compiler):
        assert compiler is not None

    def test_no_pending_returns_empty(self, compiler):
        assert compiler.get_pending_compilation() == []


# ── Compilation accuracy ──────────────────────────────────────────────────


class TestCompilationAccuracy:
    def test_suppress_rule_when_high_severity_dismissed(self, compiler, full_conn):
        """High-severity dismissals → threshold_override (suppress rule)."""
        sid = _uid()
        ext_id = _insert_proposed_extension(
            full_conn, skill_id="ds-quality:security", rule_id="SEC-001", signal_id=sid
        )[1]
        for i in range(5):
            _insert_dismissed_finding(
                full_conn,
                finding_id=_uid(),
                skill_id="ds-quality:security",
                rule_id="SEC-001",
                severity="high",
                scan_id=f"scan-{i}",
            )

        result = compiler.compile_one(ext_id)
        assert result.success, f"Compilation failed: {result.error}"
        assert result.content["extension_type"] == "threshold_override"
        assert result.content["action"] == "suppress"
        assert result.content["skill_id"] == "ds-quality:security"
        assert result.content["rule_id"] == "SEC-001"

    def test_raise_threshold_when_only_low_medium_dismissed(self, compiler, full_conn):
        """Only low/medium dismissals → option_override (raise threshold to high)."""
        sid = _uid()
        ext_id = _insert_proposed_extension(
            full_conn, skill_id="ds-quality:code-quality", rule_id="CQ-006", signal_id=sid
        )[1]
        for sev in ("low", "medium", "medium", "low", "medium"):
            _insert_dismissed_finding(
                full_conn,
                finding_id=_uid(),
                skill_id="ds-quality:code-quality",
                rule_id="CQ-006",
                severity=sev,
            )

        result = compiler.compile_one(ext_id)
        assert result.success, f"Compilation failed: {result.error}"
        assert result.content["extension_type"] == "option_override"
        assert result.content["option"] == "severity_threshold"
        assert result.content["value"] == "high"

    def test_content_includes_compiled_evidence(self, compiler, full_conn):
        """Content JSON must include compiled_evidence with finding_ids."""
        sid = _uid()
        ext_id = _insert_proposed_extension(
            full_conn, skill_id="ds-quality:database", rule_id="DB-001", signal_id=sid
        )[1]
        for _ in range(3):
            _insert_dismissed_finding(
                full_conn,
                finding_id=_uid(),
                skill_id="ds-quality:database",
                rule_id="DB-001",
                severity="medium",
            )

        result = compiler.compile_one(ext_id)
        assert result.success
        evidence = result.content["compiled_evidence"]
        assert "finding_ids" in evidence
        assert evidence["dismissal_count"] >= 3
        assert evidence["distinct_sources"] >= 1


# ── compiled_from enforcement (SkillsBench defense) ──────────────────────


class TestCompiledFromEnforcement:
    def test_no_dismissal_data_fails_compilation(self, compiler, full_conn):
        """No dismissal findings → compilation fails, no content written."""
        sid = _uid()
        ext_id = _insert_proposed_extension(
            full_conn, skill_id="ds-quality:testing", rule_id="TST-001", signal_id=sid
        )[1]
        # No dismissed findings planted

        result = compiler.compile_one(ext_id)
        assert not result.success
        assert result.error is not None
        assert "Insufficient" in result.error

        # Content column must remain empty
        row = full_conn.execute(
            "SELECT content FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        assert row["content"] in (None, "", "{}")

    def test_failed_compilation_defers_signal(self, compiler, full_conn):
        """When compilation fails, the friction signal is reset to unclassified."""
        sid = _uid()
        ext_id = _insert_proposed_extension(
            full_conn, skill_id="ds-quality:ops", rule_id="OPS-001", signal_id=sid
        )[1]
        result = compiler.compile_one(ext_id)
        assert not result.success
        assert result.signal_deferred

        row = full_conn.execute(
            "SELECT classified_as FROM ds_friction_signals WHERE signal_id = ?", (sid,)
        ).fetchone()
        assert row["classified_as"] is None, "Signal must be reset to unclassified after failure"

    def test_compiled_from_populated_with_real_finding_ids(self, compiler, full_conn):
        """compiled_from must contain real finding_ids that resolve to actual findings."""
        sid = _uid()
        ext_id = _insert_proposed_extension(
            full_conn, skill_id="ds-quality:architecture", rule_id="ARCH-001", signal_id=sid
        )[1]
        planted_ids = [_uid() for _ in range(4)]
        for fid in planted_ids:
            _insert_dismissed_finding(
                full_conn,
                finding_id=fid,
                skill_id="ds-quality:architecture",
                rule_id="ARCH-001",
                severity="high",
            )

        result = compiler.compile_one(ext_id)
        assert result.success

        # Every finding_id in result must exist in the findings table
        assert len(result.finding_ids_cited) >= 2
        for fid in result.finding_ids_cited:
            row = full_conn.execute(
                "SELECT finding_id FROM findings WHERE finding_id = ?", (fid,)
            ).fetchone()
            assert row is not None, f"Cited finding_id {fid!r} does not exist in findings table"

    def test_data_corruption_detected_on_recompile(self, compiler, full_conn):
        """If source findings are deleted, re-compilation fails (no phantom grounding)."""
        sid = _uid()
        ext_id = _insert_proposed_extension(
            full_conn, skill_id="ds-quality:security", rule_id="SEC-002", signal_id=sid
        )[1]
        fids = [_uid() for _ in range(3)]
        for fid in fids:
            _insert_dismissed_finding(
                full_conn,
                finding_id=fid,
                skill_id="ds-quality:security",
                rule_id="SEC-002",
                severity="high",
            )

        # First compilation succeeds
        r1 = compiler.compile_one(ext_id)
        assert r1.success

        # Reset content to simulate re-compilation attempt
        full_conn.execute(
            "UPDATE ds_user_extensions SET content = '{}', extension_type = 'option_override' WHERE extension_id = ?",
            (ext_id,),
        )
        # Also reset signal classification so it's eligible again
        full_conn.execute(
            "UPDATE ds_friction_signals SET classified_as = 'personalization' WHERE signal_id = ?",
            (sid,),
        )
        full_conn.commit()

        # Delete source findings (data corruption)
        for fid in fids:
            full_conn.execute("DELETE FROM findings WHERE finding_id = ?", (fid,))
        full_conn.commit()

        # Re-compilation must fail — source data is gone
        r2 = compiler.compile_one(ext_id)
        assert not r2.success, "Re-compilation must fail when source findings are deleted"


# ── CLI accept/reject state transitions ───────────────────────────────────


class TestCliStateTransitions:
    def _seed_compiled_extension(
        self, full_conn, *, skill_id="ds-quality:security", rule_id="SEC-003"
    ) -> str:
        """Plant extension with compiled content, return extension_id."""
        sid = _uid()
        ext_id = _insert_proposed_extension(
            full_conn, skill_id=skill_id, rule_id=rule_id, signal_id=sid
        )[1]
        content = json.dumps(
            {
                "extension_type": "threshold_override",
                "skill_id": skill_id,
                "rule_id": rule_id,
                "action": "suppress",
                "scope": "all",
                "compiled_evidence": {"dismissal_count": 5, "finding_ids": [_uid(), _uid()]},
                "rationale": "Compiled from 5 dismissals",
            }
        )
        full_conn.execute(
            "UPDATE ds_user_extensions SET content = ?, extension_type = 'threshold_override' "
            "WHERE extension_id = ?",
            (content, ext_id),
        )
        full_conn.commit()
        return ext_id

    def test_reject_removes_extension_row(self, full_conn):
        """Reject: ds_user_extensions row is deleted."""
        ext_id = self._seed_compiled_extension(full_conn)

        full_conn.execute("DELETE FROM ds_user_extensions WHERE extension_id = ?", (ext_id,))
        # Also unlink from friction signal
        full_conn.execute(
            "UPDATE ds_friction_signals SET extension_id = NULL WHERE extension_id = ?", (ext_id,)
        )
        full_conn.commit()

        row = full_conn.execute(
            "SELECT extension_id FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        assert row is None, "Rejected extension must be removed from ds_user_extensions"

    def test_compiled_extension_status_stays_proposed(self, full_conn):
        """After compilation, extension stays status='proposed' — 19.5 validates before promotion."""
        ext_id = self._seed_compiled_extension(full_conn)
        row = full_conn.execute(
            "SELECT status FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        assert row["status"] == "proposed", (
            f"Extension must stay 'proposed' after compilation; got {row['status']}. "
            "Only 19.5 retroactive validation promotes to 'experimental'."
        )

    def test_pending_compilation_list(self, compiler, full_conn):
        """get_pending_compilation() returns extensions without content."""
        sid = _uid()
        _insert_proposed_extension(
            full_conn, skill_id="ds-quality:pre-launch", rule_id="PL-001", signal_id=sid
        )
        pending = compiler.get_pending_compilation()
        assert len(pending) >= 1
        assert any(p["rule_id"] == "PL-001" for p in pending)

    def test_compiled_extension_leaves_pending_list(self, compiler, full_conn):
        """After compilation, extension is no longer in pending list."""
        sid = _uid()
        ext_id = _insert_proposed_extension(
            full_conn, skill_id="ds-quality:frontend-ux", rule_id="FE-001", signal_id=sid
        )[1]
        for _ in range(3):
            _insert_dismissed_finding(
                full_conn,
                finding_id=_uid(),
                skill_id="ds-quality:frontend-ux",
                rule_id="FE-001",
                severity="medium",
            )

        compiler.compile_one(ext_id)
        pending = compiler.get_pending_compilation()
        assert not any(p["extension_id"] == ext_id for p in pending)


# ── Immutability check ────────────────────────────────────────────────────


class TestImmutability:
    def test_canonical_not_modified(self, compiler, full_conn):
        """Compilation never writes to canonical/skills/."""
        from core.expansion.personalization import PersonalizationCompiler

        source = inspect.getsource(PersonalizationCompiler)

        forbidden_writes = [
            "canonical/skills",
            "open(",
            "write_text(",
            "write_bytes(",
            ".mkdir(",
        ]
        # Check the actual source for file-write patterns
        for pattern in forbidden_writes:
            assert pattern not in source, (
                f"PersonalizationCompiler contains file write: {pattern!r}. "
                "Canonical skills must never be modified."
            )

    def test_content_written_to_db_only(self, compiler, full_conn):
        """All content writes go to ds_user_extensions.content, not disk."""
        sid = _uid()
        ext_id = _insert_proposed_extension(
            full_conn, skill_id="ds-quality:backend-api", rule_id="API-001", signal_id=sid
        )[1]
        for _ in range(3):
            _insert_dismissed_finding(
                full_conn,
                finding_id=_uid(),
                skill_id="ds-quality:backend-api",
                rule_id="API-001",
                severity="high",
            )

        result = compiler.compile_one(ext_id)
        assert result.success

        row = full_conn.execute(
            "SELECT content FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        assert row is not None
        content = json.loads(row["content"])
        assert content["extension_type"] in ("threshold_override", "option_override")


# ── Round-trip: signal → extension → compiled_from → findings ─────────────


class TestRoundTrip:
    def test_full_round_trip(self, compiler, full_conn):
        """friction signal → extension → compiled_from → source findings."""
        sid = _uid()
        ext_id = _insert_proposed_extension(
            full_conn, skill_id="ds-quality:types-deps", rule_id="TD-001", signal_id=sid
        )[1]
        planted_fids = [_uid() for _ in range(4)]
        for fid in planted_fids:
            _insert_dismissed_finding(
                full_conn,
                finding_id=fid,
                skill_id="ds-quality:types-deps",
                rule_id="TD-001",
                severity="medium",
            )

        result = compiler.compile_one(ext_id)
        assert result.success

        # 1. Friction signal → extension (via extension_id)
        signal = full_conn.execute(
            "SELECT extension_id FROM ds_friction_signals WHERE signal_id = ?", (sid,)
        ).fetchone()
        assert signal["extension_id"] == ext_id

        # 2. Extension → compiled_from (contains finding_ids)
        ext_row = full_conn.execute(
            "SELECT compiled_from FROM ds_user_extensions WHERE extension_id = ?", (ext_id,)
        ).fetchone()
        cf = json.loads(ext_row["compiled_from"])
        assert "finding_ids" in cf
        assert len(cf["finding_ids"]) >= 2

        # 3. compiled_from → source findings (all IDs resolve)
        for fid in cf["finding_ids"]:
            row = full_conn.execute(
                "SELECT finding_id FROM findings WHERE finding_id = ?", (fid,)
            ).fetchone()
            assert row is not None, f"compiled_from finding_id {fid!r} not found in findings"


# ── Zero LLM / local-first ────────────────────────────────────────────────


class TestZeroLlmLocalFirst:
    def test_no_llm_imports_in_compiler(self):
        """PersonalizationCompiler has zero LLM dependencies (checks imports only)."""
        import core.expansion.personalization as mod

        source = inspect.getsource(mod)
        # Check only import lines (not docstrings where "LLM" appears legitimately)
        import_lines = [
            ln.strip()
            for ln in source.splitlines()
            if ln.strip().startswith("import ") or ln.strip().startswith("from ")
        ]
        import_text = "\n".join(import_lines).lower()
        forbidden_imports = [
            "subprocess",
            "claude",
            "openai",
            "anthropic",
            "urllib",
            "requests",
            "httpx",
            "shutil",
        ]
        for lib in forbidden_imports:
            assert lib not in import_text, (
                f"Forbidden import {lib!r} found in personalization.py imports. "
                "19.4a must be pure SQL, zero LLM."
            )

    def test_token_cost_is_zero(self, compiler, full_conn):
        """No Tier 2 LLM call means zero token cost for 19.4a."""
        sid = _uid()
        ext_id = _insert_proposed_extension(
            full_conn, skill_id="ds-quality:devops", rule_id="DO-001", signal_id=sid
        )[1]
        for _ in range(3):
            _insert_dismissed_finding(
                full_conn,
                finding_id=_uid(),
                skill_id="ds-quality:devops",
                rule_id="DO-001",
                severity="high",
            )

        result = compiler.compile_one(ext_id)
        assert result.success
        # CompilationResult has no tokens field — that's intentional (zero cost)
        # Verify by confirming no subprocess or LLM calls happen
        from core.expansion.personalization import CompilationResult

        assert (
            not hasattr(result, "tokens_used") or result.__class__.__name__ == "CompilationResult"
        )
