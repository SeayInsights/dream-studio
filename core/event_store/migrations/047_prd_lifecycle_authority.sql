-- Migration 047: PRD Lifecycle And Route Authority
-- Created: 2026-05-15
-- Purpose:
--   Additive authority for project intake, PRD version lineage,
--   milestone/work-order planning, change orders, and route reconciliation.
--   Files remain optional exports; SQLite is the durable current authority.

CREATE TABLE IF NOT EXISTS project_intake_records (
    intake_id TEXT PRIMARY KEY,
    project_id TEXT,
    project_name TEXT,
    project_description TEXT NOT NULL DEFAULT '',
    question_mode TEXT NOT NULL DEFAULT 'standard_discovery',
    project_type TEXT NOT NULL DEFAULT 'unknown',
    deployment_expectation TEXT NOT NULL DEFAULT 'unknown',
    autonomy_level TEXT NOT NULL DEFAULT 'operator_review',
    security_classification TEXT NOT NULL DEFAULT 'unknown',
    readiness_classification TEXT NOT NULL DEFAULT 'unknown',
    critical_blockers_json TEXT NOT NULL DEFAULT '[]',
    assumptions_json TEXT NOT NULL DEFAULT '[]',
    known_unknowns_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft_generated',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (question_mode IN (
        'quick_start',
        'standard_discovery',
        'full_discovery',
        'import_existing_project'
    )),
    CHECK (status IN (
        'draft_generated',
        'in_flight_formalization',
        'user_review_required',
        'user_confirmed',
        'current',
        'needs_update',
        'superseded',
        'manual_review_required',
        'closed_reconciled'
    ))
);

CREATE TABLE IF NOT EXISTS project_intake_questions (
    question_id TEXT PRIMARY KEY,
    intake_id TEXT NOT NULL,
    project_id TEXT,
    question_mode TEXT NOT NULL DEFAULT 'standard_discovery',
    question_group TEXT NOT NULL,
    question_text TEXT NOT NULL,
    criticality TEXT NOT NULL DEFAULT 'important',
    already_answered INTEGER NOT NULL DEFAULT 0,
    inferred_answer TEXT,
    response_text TEXT,
    response_status TEXT NOT NULL DEFAULT 'pending',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (already_answered IN (0, 1)),
    CHECK (criticality IN ('critical', 'important', 'optional')),
    CHECK (response_status IN (
        'pending',
        'answered',
        'assumption',
        'unknown',
        'not_applicable',
        'operator_confirmation_required'
    ))
);

CREATE TABLE IF NOT EXISTS project_assumption_records (
    assumption_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    intake_id TEXT,
    prd_id TEXT,
    prd_version_id TEXT,
    assumption_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'assumption',
    confirmation_required INTEGER NOT NULL DEFAULT 1,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (confirmation_required IN (0, 1)),
    CHECK (status IN (
        'assumption',
        'confirmed',
        'rejected',
        'superseded',
        'needs_evidence',
        'operator_confirmation_required'
    ))
);

CREATE TABLE IF NOT EXISTS prd_version_records (
    prd_version_id TEXT PRIMARY KEY,
    prd_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    version_number INTEGER NOT NULL DEFAULT 1,
    title TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL DEFAULT 'draft_generated',
    confidence TEXT NOT NULL DEFAULT 'draft_generated_needs_operator_review',
    prd_json TEXT NOT NULL DEFAULT '{}',
    summary TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    assumption_refs_json TEXT NOT NULL DEFAULT '[]',
    known_unknowns_json TEXT NOT NULL DEFAULT '[]',
    change_order_refs_json TEXT NOT NULL DEFAULT '[]',
    supersedes_version_id TEXT,
    superseded_by_version_id TEXT,
    current_version INTEGER NOT NULL DEFAULT 0,
    operator_review_required INTEGER NOT NULL DEFAULT 1,
    last_reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (current_version IN (0, 1)),
    CHECK (operator_review_required IN (0, 1)),
    CHECK (lifecycle_status IN (
        'draft_generated',
        'in_flight_formalization',
        'user_review_required',
        'user_confirmed',
        'current',
        'needs_update',
        'superseded',
        'manual_review_required',
        'closed_reconciled'
    )),
    CHECK (confidence IN (
        'high_confidence_current',
        'medium_confidence_needs_review',
        'draft_generated_needs_operator_review',
        'manual_review_required'
    ))
);

CREATE TABLE IF NOT EXISTS project_milestone_records (
    milestone_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    prd_id TEXT,
    prd_version_id TEXT,
    sequence_number INTEGER NOT NULL,
    milestone_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    scope_json TEXT NOT NULL DEFAULT '{}',
    stage_gate_json TEXT NOT NULL DEFAULT '{}',
    validation_expectations_json TEXT NOT NULL DEFAULT '[]',
    security_readiness_checks_json TEXT NOT NULL DEFAULT '[]',
    rollback_strategy TEXT,
    evidence_requirements_json TEXT NOT NULL DEFAULT '[]',
    adapter_context_requirements_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    supersedes_milestone_id TEXT,
    superseded_by_milestone_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (status IN (
        'planned',
        'active',
        'blocked',
        'completed',
        'superseded',
        'retired',
        'manual_review_required'
    ))
);

CREATE TABLE IF NOT EXISTS project_work_order_authority_records (
    work_order_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    milestone_id TEXT,
    prd_id TEXT,
    prd_version_id TEXT,
    purpose TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    scope_json TEXT NOT NULL DEFAULT '{}',
    approved_surfaces_json TEXT NOT NULL DEFAULT '[]',
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    validation_json TEXT NOT NULL DEFAULT '[]',
    evidence_requirements_json TEXT NOT NULL DEFAULT '[]',
    stop_gates_json TEXT NOT NULL DEFAULT '[]',
    final_verdict_taxonomy_json TEXT NOT NULL DEFAULT '[]',
    route_decision_expectations_json TEXT NOT NULL DEFAULT '{}',
    rollback_strategy TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    supersedes_work_order_id TEXT,
    superseded_by_work_order_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (status IN (
        'draft',
        'ready',
        'active',
        'blocked',
        'completed',
        'superseded',
        'retired',
        'manual_review_required'
    ))
);

CREATE TABLE IF NOT EXISTS project_change_order_records (
    change_order_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    requested_by TEXT NOT NULL DEFAULT 'operator',
    requested_at TEXT NOT NULL DEFAULT (datetime('now')),
    user_request TEXT NOT NULL,
    change_type TEXT NOT NULL DEFAULT 'manual_review_required',
    reason_for_change TEXT,
    affected_prd_sections_json TEXT NOT NULL DEFAULT '[]',
    affected_milestones_json TEXT NOT NULL DEFAULT '[]',
    affected_work_orders_json TEXT NOT NULL DEFAULT '[]',
    affected_security_readiness_controls_json TEXT NOT NULL DEFAULT '[]',
    affected_architecture_contracts_json TEXT NOT NULL DEFAULT '[]',
    affected_timeline_scope_json TEXT NOT NULL DEFAULT '{}',
    affected_release_criteria_json TEXT NOT NULL DEFAULT '[]',
    risk_classification TEXT NOT NULL DEFAULT 'medium',
    validation_impact_json TEXT NOT NULL DEFAULT '[]',
    approval_requirement TEXT NOT NULL DEFAULT 'operator_approval_required',
    status TEXT NOT NULL DEFAULT 'draft',
    original_prd_refs_json TEXT NOT NULL DEFAULT '[]',
    original_milestone_refs_json TEXT NOT NULL DEFAULT '[]',
    resulting_prd_version_id TEXT,
    resulting_milestone_refs_json TEXT NOT NULL DEFAULT '[]',
    resulting_work_order_refs_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (change_type IN (
        'scope_addition',
        'scope_reduction',
        'requirement_change',
        'architecture_change',
        'data_model_change',
        'security_or_privacy_change',
        'integration_change',
        'UI_or_design_change',
        'release_target_change',
        'priority_change',
        'assumption_change',
        'non_goal_change',
        'milestone_replan',
        'manual_review_required'
    )),
    CHECK (status IN (
        'draft',
        'accepted',
        'rejected',
        'deferred',
        'manual_review_required'
    )),
    CHECK (risk_classification IN ('low', 'medium', 'high', 'critical', 'unknown'))
);

CREATE TABLE IF NOT EXISTS prd_amendment_records (
    amendment_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    prd_id TEXT NOT NULL,
    prd_version_id TEXT,
    change_order_id TEXT,
    amendment_type TEXT NOT NULL DEFAULT 'lightweight_prd_amendment',
    amended_sections_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'accepted',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (status IN ('accepted', 'rejected', 'deferred', 'superseded'))
);

CREATE TABLE IF NOT EXISTS prd_route_reconciliation_records (
    reconciliation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    prd_id TEXT,
    prd_version_id TEXT,
    reconciliation_event TEXT NOT NULL DEFAULT 'milestone_closeout',
    planned_route_json TEXT NOT NULL DEFAULT '{}',
    actual_route_json TEXT NOT NULL DEFAULT '{}',
    planned_vs_actual_json TEXT NOT NULL DEFAULT '{}',
    completed_milestones_json TEXT NOT NULL DEFAULT '[]',
    completed_work_orders_json TEXT NOT NULL DEFAULT '[]',
    approved_change_orders_json TEXT NOT NULL DEFAULT '[]',
    accepted_deviations_json TEXT NOT NULL DEFAULT '[]',
    unresolved_deviations_json TEXT NOT NULL DEFAULT '[]',
    validation_results_json TEXT NOT NULL DEFAULT '[]',
    security_readiness_outcomes_json TEXT NOT NULL DEFAULT '{}',
    final_project_status TEXT NOT NULL DEFAULT 'in_progress',
    current_next_action TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (reconciliation_event IN (
        'milestone_closeout',
        'release_closeout',
        'project_closeout',
        'manual_review_required'
    )),
    CHECK (final_project_status IN (
        'new',
        'in_progress',
        'paused',
        'released',
        'closed',
        'blocked',
        'manual_review_required'
    ))
);

CREATE INDEX IF NOT EXISTS idx_project_intake_records_project
ON project_intake_records(project_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_project_intake_questions_intake
ON project_intake_questions(intake_id, question_group, criticality);

CREATE INDEX IF NOT EXISTS idx_project_assumption_records_project
ON project_assumption_records(project_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_prd_version_records_project
ON prd_version_records(project_id, current_version, lifecycle_status, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_prd_version_records_current
ON prd_version_records(project_id, current_version)
WHERE current_version = 1;

CREATE INDEX IF NOT EXISTS idx_project_milestone_records_project
ON project_milestone_records(project_id, status, sequence_number);

CREATE INDEX IF NOT EXISTS idx_project_work_order_authority_project
ON project_work_order_authority_records(project_id, milestone_id, status);

CREATE INDEX IF NOT EXISTS idx_project_change_order_records_project
ON project_change_order_records(project_id, status, change_type, requested_at);

CREATE INDEX IF NOT EXISTS idx_prd_amendment_records_project
ON prd_amendment_records(project_id, prd_id, created_at);

CREATE INDEX IF NOT EXISTS idx_prd_route_reconciliation_project
ON prd_route_reconciliation_records(project_id, final_project_status, created_at);
