-- Migration 040: Production Readiness Authority
-- Created: 2026-05-15
-- Purpose:
--   Additive authority tables for secure production readiness assessments,
--   control applicability, findings, remediation Work Order links, scorecards,
--   release-readiness records, and skill/control mappings.

CREATE TABLE IF NOT EXISTS production_readiness_assessment_runs (
    assessment_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    lifecycle_event TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence TEXT NOT NULL,
    full_review_required INTEGER NOT NULL DEFAULT 0,
    release_readiness_effect TEXT NOT NULL,
    health_score_json TEXT NOT NULL DEFAULT '{}',
    readiness_score_json TEXT NOT NULL DEFAULT '{}',
    missing_evidence_json TEXT NOT NULL DEFAULT '[]',
    blocking_factors_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prod_readiness_assessments_project
ON production_readiness_assessment_runs(project_id, created_at);

CREATE TABLE IF NOT EXISTS production_readiness_control_results (
    result_id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    control_id TEXT NOT NULL,
    control_family TEXT NOT NULL,
    name TEXT NOT NULL,
    skill_owner TEXT NOT NULL,
    workflow_owner TEXT NOT NULL,
    applicability TEXT NOT NULL,
    status TEXT NOT NULL,
    severity TEXT NOT NULL,
    blocking INTEGER NOT NULL DEFAULT 0,
    score_impact REAL,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    file_path TEXT,
    line INTEGER,
    remediation_work_order TEXT,
    reason_not_applicable TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (assessment_id) REFERENCES production_readiness_assessment_runs(assessment_id)
);

CREATE INDEX IF NOT EXISTS idx_prod_readiness_results_project
ON production_readiness_control_results(project_id, status, severity);

CREATE INDEX IF NOT EXISTS idx_prod_readiness_results_assessment
ON production_readiness_control_results(assessment_id, control_family);

CREATE TABLE IF NOT EXISTS production_readiness_findings (
    finding_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    control_id TEXT NOT NULL,
    control_family TEXT NOT NULL,
    skill_owner TEXT NOT NULL,
    workflow_owner TEXT NOT NULL,
    applicability TEXT NOT NULL,
    status TEXT NOT NULL,
    severity TEXT NOT NULL,
    blocking INTEGER NOT NULL DEFAULT 0,
    score_impact REAL,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    file_path TEXT,
    line INTEGER,
    remediation_work_order TEXT,
    reason_not_applicable TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (assessment_id) REFERENCES production_readiness_assessment_runs(assessment_id)
);

CREATE INDEX IF NOT EXISTS idx_prod_readiness_findings_project
ON production_readiness_findings(project_id, status, severity);

CREATE TABLE IF NOT EXISTS production_readiness_remediation_work_orders (
    remediation_work_order_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    control_id TEXT NOT NULL,
    finding_id TEXT,
    status TEXT NOT NULL,
    recommended_phase_type TEXT NOT NULL,
    objective TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prod_readiness_remediation_project
ON production_readiness_remediation_work_orders(project_id, status);

CREATE TABLE IF NOT EXISTS production_readiness_skill_control_mappings (
    mapping_id TEXT PRIMARY KEY,
    control_id TEXT NOT NULL,
    control_family TEXT NOT NULL,
    existing_skill_or_check TEXT NOT NULL,
    proposed_canonical_owner TEXT NOT NULL,
    overlap_reason TEXT NOT NULL,
    decision TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    validation_requirement TEXT NOT NULL,
    rollback_or_supersession_plan TEXT NOT NULL,
    dashboard_project_health_impact TEXT NOT NULL,
    contract_atlas_impact TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prod_readiness_skill_mappings_control
ON production_readiness_skill_control_mappings(control_id, decision);

CREATE TABLE IF NOT EXISTS project_readiness_scorecards (
    scorecard_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    readiness_score REAL,
    confidence TEXT NOT NULL,
    status TEXT NOT NULL,
    missing_evidence_json TEXT NOT NULL DEFAULT '[]',
    blocking_factors_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_project_readiness_scorecards_project
ON project_readiness_scorecards(project_id, created_at);

CREATE TABLE IF NOT EXISTS project_health_scorecards (
    scorecard_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    health_score REAL,
    confidence TEXT NOT NULL,
    status TEXT NOT NULL,
    missing_evidence_json TEXT NOT NULL DEFAULT '[]',
    blocking_factors_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_project_health_scorecards_project
ON project_health_scorecards(project_id, created_at);

-- release_readiness_records: dropped in migration 133 (dead writer — persist=False gate never
-- lifted in production; _record_scorecards() only reachable when persist=True, which no
-- production caller ever passes).

-- compliance_review_flags: dropped in migration 133 (same persist=False dead gate as
-- release_readiness_records; _record_compliance_flags() unreachable in production).

DROP VIEW IF EXISTS vw_project_readiness_latest;
CREATE VIEW vw_project_readiness_latest AS
SELECT
    pr.project_id,
    pr.assessment_id,
    pr.readiness_score,
    pr.confidence AS readiness_confidence,
    pr.status AS readiness_status,
    pr.missing_evidence_json,
    pr.blocking_factors_json,
    pr.created_at
FROM project_readiness_scorecards pr
JOIN (
    SELECT project_id, MAX(created_at) AS max_created_at
    FROM project_readiness_scorecards
    GROUP BY project_id
) latest
ON pr.project_id = latest.project_id AND pr.created_at = latest.max_created_at;
