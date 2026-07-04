-- Migration 143: Rebuild audit_runs + capability_route_records without dead FK clauses
-- (WO-M143-STALE-FK, authority 57bc41bc — surfaced by the WO-SQUASH-BASELINE review)
--
-- Both tables carried FOREIGN KEY clauses referencing tables that were dropped
-- earlier in the chain and are absent from the lean baseline (142):
--   audit_runs.activity_id            -> activity_log            (dropped; activity-log retirement)
--   capability_route_records.
--     selected_model_profile_id       -> model_provider_profiles (dropped/tombstoned)
-- SQLite validates a FK's PARENT table at DML time when PRAGMA foreign_keys=ON
-- (which the runtime enforces), so ANY INSERT into these tables raises
-- "no such table: main.activity_log" / "model_provider_profiles" — the exact
-- migration-118 / migration-137 stale-FK failure mode. Both tables are empty
-- today (0 rows) so the fault is latent, but both have LIVE writers
-- (projections/api/routes/audits.py -> audit_runs;
-- core/shared_intelligence/authority.py -> capability_route_records), so the
-- next write with foreign_keys=ON would fail.
--
-- The lean baseline reproduced the broken clauses verbatim from the historical
-- schema (the parent tables existed at CREATE time and were dropped later;
-- SQLite does not retroactively strip FK clauses). This forward migration
-- reconstructs both tables sans the dead clauses (migration-118 pattern:
-- CREATE _new + INSERT..SELECT + DROP + RENAME), preserving every column,
-- CHECK, default, and the still-valid FK. Fixes fresh installs (142 creates the
-- broken tables, 143 fixes them) and existing DBs already at 142.

PRAGMA foreign_keys = OFF;

-- ── audit_runs: drop the dead activity_log FK (keep everything else) ─────────
CREATE TABLE audit_runs_m143 (
    audit_id TEXT PRIMARY KEY,
    activity_id INTEGER,  -- was FK to activity_log (dropped); now a plain nullable column
    audit_type TEXT NOT NULL CHECK(audit_type IN ('code_quality', 'security', 'performance', 'architecture', 'compliance')),
    audit_scope TEXT NOT NULL CHECK(audit_scope IN ('project', 'prd', 'task', 'skill', 'file', 'function')),
    target_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK(target_type IN ('project', 'prd', 'task', 'skill', 'file', 'function', 'module')),
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed', 'cancelled')) DEFAULT 'running',
    findings_count INTEGER DEFAULT 0,
    critical_count INTEGER DEFAULT 0,
    high_count INTEGER DEFAULT 0,
    medium_count INTEGER DEFAULT 0,
    low_count INTEGER DEFAULT 0,
    report_path TEXT,
    summary TEXT,
    started_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    completed_at TEXT,
    duration_s REAL
);
INSERT INTO audit_runs_m143 SELECT
    audit_id, activity_id, audit_type, audit_scope, target_id, target_type, status,
    findings_count, critical_count, high_count, medium_count, low_count,
    report_path, summary, started_at, completed_at, duration_s
FROM audit_runs;
DROP TABLE audit_runs;
ALTER TABLE audit_runs_m143 RENAME TO audit_runs;

CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_runs(target_id, target_type);
CREATE INDEX IF NOT EXISTS idx_audit_type_status ON audit_runs(audit_type, status);
CREATE INDEX IF NOT EXISTS idx_audit_started ON audit_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit_runs(critical_count DESC, high_count DESC)
    WHERE status = 'completed';

-- ── capability_route_records: drop the dead model_provider_profiles FK,
--    keep the still-valid adapter_authority_profiles FK ────────────────────────
CREATE TABLE capability_route_records_m143 (
    capability_route_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    task_class TEXT NOT NULL,
    selected_adapter_id TEXT,
    selected_model_profile_id TEXT,  -- was FK to model_provider_profiles (dropped); now a plain column
    route_basis_json TEXT NOT NULL DEFAULT '{}',
    risk_level TEXT NOT NULL DEFAULT 'medium',
    cost_sensitivity TEXT NOT NULL DEFAULT 'medium',
    validation_required INTEGER NOT NULL DEFAULT 1,
    operator_approval_required INTEGER NOT NULL DEFAULT 0,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (selected_adapter_id) REFERENCES adapter_authority_profiles(adapter_id)
);
INSERT INTO capability_route_records_m143 SELECT
    capability_route_id, project_id, milestone_id, task_id, process_run_id, task_class,
    selected_adapter_id, selected_model_profile_id, route_basis_json, risk_level,
    cost_sensitivity, validation_required, operator_approval_required,
    source_refs_json, evidence_refs_json, created_at
FROM capability_route_records;
DROP TABLE capability_route_records;
ALTER TABLE capability_route_records_m143 RENAME TO capability_route_records;

CREATE INDEX IF NOT EXISTS idx_capability_routes_scope
    ON capability_route_records(project_id, milestone_id, task_id, task_class);

PRAGMA foreign_keys = ON;
