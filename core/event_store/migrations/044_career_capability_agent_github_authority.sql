-- Migration 044: Career Ops, Capability Center, scoped agents, and GitHub repo intake authority
-- Adds optional/private authority records. This migration is additive only and
-- does not make any of these capabilities public or enabled by default.

CREATE TABLE IF NOT EXISTS career_profiles (
    profile_id TEXT PRIMARY KEY,
    owner_label TEXT,
    enabled INTEGER NOT NULL DEFAULT 0,
    privacy_scope TEXT NOT NULL DEFAULT 'private_local',
    profile_status TEXT NOT NULL DEFAULT 'draft',
    headline TEXT,
    summary TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (enabled IN (0, 1)),
    CHECK (privacy_scope IN ('private_local', 'redacted_export_candidate', 'public_approved')),
    CHECK (profile_status IN ('draft', 'active', 'paused', 'manual_review_required'))
);

CREATE TABLE IF NOT EXISTS career_profile_fields (
    field_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    field_key TEXT NOT NULL,
    field_value TEXT,
    sensitivity TEXT NOT NULL DEFAULT 'private',
    value_status TEXT NOT NULL DEFAULT 'operator_confirmation_required',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(profile_id, field_key),
    FOREIGN KEY (profile_id) REFERENCES career_profiles(profile_id),
    CHECK (sensitivity IN ('public', 'private', 'sensitive')),
    CHECK (value_status IN ('confirmed', 'needs_evidence', 'estimate_candidate', 'operator_confirmation_required'))
);

CREATE TABLE IF NOT EXISTS career_role_targets (
    role_target_id TEXT PRIMARY KEY,
    profile_id TEXT,
    role_path TEXT NOT NULL,
    target_status TEXT NOT NULL DEFAULT 'active',
    fit_summary TEXT,
    scorecard_json TEXT NOT NULL DEFAULT '{}',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES career_profiles(profile_id)
);

CREATE TABLE IF NOT EXISTS career_resume_versions (
    resume_version_id TEXT PRIMARY KEY,
    profile_id TEXT,
    role_target_id TEXT,
    variant_label TEXT NOT NULL,
    version_status TEXT NOT NULL DEFAULT 'draft',
    private_storage_ref TEXT,
    sanitized_export_ref TEXT,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    claims_requiring_evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES career_profiles(profile_id),
    FOREIGN KEY (role_target_id) REFERENCES career_role_targets(role_target_id)
);

CREATE TABLE IF NOT EXISTS career_cover_letter_versions (
    cover_letter_version_id TEXT PRIMARY KEY,
    profile_id TEXT,
    role_target_id TEXT,
    job_opportunity_id TEXT,
    variant_label TEXT NOT NULL,
    version_status TEXT NOT NULL DEFAULT 'draft',
    private_storage_ref TEXT,
    sanitized_export_ref TEXT,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    claims_requiring_evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS career_portfolio_artifacts (
    portfolio_artifact_id TEXT PRIMARY KEY,
    profile_id TEXT,
    artifact_title TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    visibility_status TEXT NOT NULL DEFAULT 'private',
    readiness_status TEXT NOT NULL DEFAULT 'partial',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    redaction_requirements_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES career_profiles(profile_id),
    CHECK (visibility_status IN ('private', 'redaction_required', 'operator_approved_public')),
    CHECK (readiness_status IN ('unavailable', 'partial', 'ready', 'manual_review_required'))
);

CREATE TABLE IF NOT EXISTS career_case_studies (
    case_study_id TEXT PRIMARY KEY,
    profile_id TEXT,
    portfolio_artifact_id TEXT,
    title TEXT NOT NULL,
    audience TEXT,
    privacy_status TEXT NOT NULL DEFAULT 'private',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    missing_evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES career_profiles(profile_id),
    FOREIGN KEY (portfolio_artifact_id) REFERENCES career_portfolio_artifacts(portfolio_artifact_id)
);

CREATE TABLE IF NOT EXISTS career_job_opportunities (
    job_opportunity_id TEXT PRIMARY KEY,
    profile_id TEXT,
    employer_label TEXT,
    role_title TEXT NOT NULL,
    posting_url TEXT,
    opportunity_status TEXT NOT NULL DEFAULT 'prospect',
    fit_status TEXT NOT NULL DEFAULT 'unscored',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    notes_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES career_profiles(profile_id)
);

CREATE TABLE IF NOT EXISTS career_applications (
    application_id TEXT PRIMARY KEY,
    profile_id TEXT,
    job_opportunity_id TEXT,
    application_status TEXT NOT NULL DEFAULT 'tracked',
    submission_policy TEXT NOT NULL DEFAULT 'explicit_operator_approval_required',
    submitted_at TEXT,
    follow_up_at TEXT,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    notes_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES career_profiles(profile_id),
    FOREIGN KEY (job_opportunity_id) REFERENCES career_job_opportunities(job_opportunity_id),
    CHECK (submission_policy IN ('explicit_operator_approval_required', 'approved_per_application_policy'))
);

CREATE TABLE IF NOT EXISTS career_application_events (
    application_event_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_status TEXT NOT NULL DEFAULT 'recorded',
    event_summary TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (application_id) REFERENCES career_applications(application_id)
);

CREATE TABLE IF NOT EXISTS career_application_field_mappings (
    field_mapping_id TEXT PRIMARY KEY,
    profile_id TEXT,
    application_id TEXT,
    external_field_label TEXT NOT NULL,
    local_field_key TEXT,
    fill_status TEXT NOT NULL DEFAULT 'requires_operator_input',
    sensitivity TEXT NOT NULL DEFAULT 'private',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES career_profiles(profile_id),
    FOREIGN KEY (application_id) REFERENCES career_applications(application_id),
    CHECK (fill_status IN ('filled', 'skipped', 'requires_operator_input', 'ambiguous_pause')),
    CHECK (sensitivity IN ('public', 'private', 'sensitive'))
);

CREATE TABLE IF NOT EXISTS career_browser_automation_runs (
    automation_run_id TEXT PRIMARY KEY,
    profile_id TEXT,
    application_id TEXT,
    run_status TEXT NOT NULL,
    account_creation_attempted INTEGER NOT NULL DEFAULT 0,
    captcha_bypass_attempted INTEGER NOT NULL DEFAULT 0,
    submission_attempted INTEGER NOT NULL DEFAULT 0,
    operator_approval_ref TEXT,
    filled_fields_json TEXT NOT NULL DEFAULT '[]',
    skipped_fields_json TEXT NOT NULL DEFAULT '[]',
    operator_input_required_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES career_profiles(profile_id),
    FOREIGN KEY (application_id) REFERENCES career_applications(application_id),
    CHECK (account_creation_attempted IN (0, 1)),
    CHECK (captcha_bypass_attempted IN (0, 1)),
    CHECK (submission_attempted IN (0, 1))
);

CREATE TABLE IF NOT EXISTS career_interview_story_bank (
    story_id TEXT PRIMARY KEY,
    profile_id TEXT,
    story_title TEXT NOT NULL,
    target_competency TEXT,
    evidence_strength TEXT NOT NULL DEFAULT 'needs_evidence',
    story_status TEXT NOT NULL DEFAULT 'draft',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    claims_requiring_evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES career_profiles(profile_id)
);

CREATE TABLE IF NOT EXISTS career_evidence_refs (
    career_evidence_id TEXT PRIMARY KEY,
    profile_id TEXT,
    target_record_type TEXT NOT NULL,
    target_record_id TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    evidence_status TEXT NOT NULL DEFAULT 'needs_review',
    privacy_status TEXT NOT NULL DEFAULT 'private',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES career_profiles(profile_id)
);

CREATE TABLE IF NOT EXISTS career_scorecards (
    scorecard_id TEXT PRIMARY KEY,
    profile_id TEXT,
    scorecard_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unavailable',
    confidence TEXT NOT NULL DEFAULT 'unknown',
    score_value REAL,
    missing_evidence_json TEXT NOT NULL DEFAULT '[]',
    blocking_factors_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES career_profiles(profile_id),
    CHECK (status IN ('unavailable', 'partial', 'ready', 'manual_review_required')),
    CHECK (confidence IN ('high', 'medium', 'low', 'unknown'))
);

CREATE TABLE IF NOT EXISTS capability_center_records (
    capability_record_id TEXT PRIMARY KEY,
    component_type TEXT NOT NULL,
    component_id TEXT NOT NULL,
    name TEXT NOT NULL,
    purpose TEXT,
    version TEXT,
    owner TEXT,
    input_contract_json TEXT NOT NULL DEFAULT '{}',
    output_contract_json TEXT NOT NULL DEFAULT '{}',
    trigger_conditions_json TEXT NOT NULL DEFAULT '[]',
    when_not_to_run_json TEXT NOT NULL DEFAULT '[]',
    known_gaps_json TEXT NOT NULL DEFAULT '[]',
    hardening_candidates_json TEXT NOT NULL DEFAULT '[]',
    evaluation_status TEXT NOT NULL DEFAULT 'unavailable',
    evaluation_score REAL,
    supersession_status TEXT NOT NULL DEFAULT 'current',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    last_reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (component_type IN ('skill', 'workflow', 'agent', 'control', 'evaluation', 'hardening_candidate')),
    CHECK (evaluation_status IN ('unavailable', 'partial', 'validated', 'manual_review_required')),
    CHECK (supersession_status IN ('current', 'superseded', 'deprecated', 'manual_review_required'))
);

CREATE TABLE IF NOT EXISTS agent_registry_records (
    agent_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    purpose TEXT NOT NULL,
    allowed_tools_json TEXT NOT NULL DEFAULT '[]',
    read_scope_json TEXT NOT NULL DEFAULT '[]',
    write_scope_json TEXT NOT NULL DEFAULT '[]',
    data_sensitivity_scope_json TEXT NOT NULL DEFAULT '[]',
    required_context_json TEXT NOT NULL DEFAULT '[]',
    forbidden_context_json TEXT NOT NULL DEFAULT '[]',
    output_contract_json TEXT NOT NULL DEFAULT '{}',
    validation_requirements_json TEXT NOT NULL DEFAULT '[]',
    approval_boundaries_json TEXT NOT NULL DEFAULT '[]',
    risk_level TEXT NOT NULL DEFAULT 'medium',
    max_context_budget INTEGER NOT NULL DEFAULT 8000,
    allowed_data_classes_json TEXT NOT NULL DEFAULT '[]',
    result_schema_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (risk_level IN ('low', 'medium', 'high')),
    CHECK (enabled IN (0, 1))
);

CREATE TABLE IF NOT EXISTS agent_context_scope_policies (
    policy_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    policy_status TEXT NOT NULL DEFAULT 'active',
    required_context_json TEXT NOT NULL DEFAULT '[]',
    forbidden_context_json TEXT NOT NULL DEFAULT '[]',
    forbidden_by_default_json TEXT NOT NULL DEFAULT '[]',
    approval_required_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agent_registry_records(agent_id)
);

CREATE TABLE IF NOT EXISTS workflow_agent_skill_mappings (
    mapping_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    agent_id TEXT,
    skill_id TEXT,
    mapping_status TEXT NOT NULL DEFAULT 'current',
    allowed_context_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agent_registry_records(agent_id)
);

CREATE TABLE IF NOT EXISTS agent_result_records (
    agent_result_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    project_id TEXT,
    task_id TEXT,
    result_status TEXT NOT NULL,
    normalized_target_tables_json TEXT NOT NULL DEFAULT '[]',
    result_payload_json TEXT NOT NULL DEFAULT '{}',
    validation_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agent_registry_records(agent_id)
);

CREATE TABLE IF NOT EXISTS github_repo_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    repo_url TEXT NOT NULL,
    owner_name TEXT,
    repo_name TEXT,
    commit_sha_reviewed TEXT,
    license TEXT,
    languages_json TEXT NOT NULL DEFAULT '[]',
    dependency_files_json TEXT NOT NULL DEFAULT '[]',
    security_files_json TEXT NOT NULL DEFAULT '[]',
    package_manifests_json TEXT NOT NULL DEFAULT '[]',
    candidate_components_json TEXT NOT NULL DEFAULT '[]',
    risk_score REAL,
    fit_score REAL,
    integration_decision TEXT NOT NULL,
    manual_review_required INTEGER NOT NULL DEFAULT 0,
    legal_review_required INTEGER NOT NULL DEFAULT 0,
    security_review_required INTEGER NOT NULL DEFAULT 0,
    attribution_requirements_json TEXT NOT NULL DEFAULT '[]',
    recommended_action TEXT,
    linked_work_orders_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (manual_review_required IN (0, 1)),
    CHECK (legal_review_required IN (0, 1)),
    CHECK (security_review_required IN (0, 1))
);

CREATE TABLE IF NOT EXISTS github_repo_license_findings (
    license_finding_id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL,
    license_status TEXT NOT NULL,
    attribution_required INTEGER NOT NULL DEFAULT 0,
    legal_review_required INTEGER NOT NULL DEFAULT 0,
    finding_summary TEXT,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (evaluation_id) REFERENCES github_repo_evaluations(evaluation_id)
);

CREATE TABLE IF NOT EXISTS github_repo_security_findings (
    security_finding_id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'manual_review_required',
    finding_summary TEXT,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (evaluation_id) REFERENCES github_repo_evaluations(evaluation_id)
);

CREATE TABLE IF NOT EXISTS github_repo_dependency_findings (
    dependency_finding_id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL,
    dependency_name TEXT,
    dependency_status TEXT NOT NULL DEFAULT 'unknown',
    maintenance_risk TEXT NOT NULL DEFAULT 'unknown',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (evaluation_id) REFERENCES github_repo_evaluations(evaluation_id)
);

CREATE TABLE IF NOT EXISTS github_repo_integration_candidates (
    candidate_id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL,
    component_name TEXT NOT NULL,
    candidate_type TEXT NOT NULL,
    overlap_status TEXT NOT NULL DEFAULT 'manual_review_required',
    recommended_strategy TEXT NOT NULL DEFAULT 'learn_pattern_only',
    approval_required INTEGER NOT NULL DEFAULT 1,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (evaluation_id) REFERENCES github_repo_evaluations(evaluation_id)
);

CREATE TABLE IF NOT EXISTS github_repo_pattern_references (
    pattern_reference_id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL,
    pattern_name TEXT NOT NULL,
    reference_status TEXT NOT NULL DEFAULT 'reference_only',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (evaluation_id) REFERENCES github_repo_evaluations(evaluation_id)
);

CREATE TABLE IF NOT EXISTS github_repo_adoption_decisions (
    adoption_decision_id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL,
    decision_class TEXT NOT NULL,
    decision_status TEXT NOT NULL DEFAULT 'pending_approval',
    rationale TEXT,
    approval_required INTEGER NOT NULL DEFAULT 1,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (evaluation_id) REFERENCES github_repo_evaluations(evaluation_id)
);

CREATE TABLE IF NOT EXISTS github_repo_attribution_records (
    attribution_record_id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL,
    attribution_status TEXT NOT NULL DEFAULT 'pending',
    license_ref TEXT,
    attribution_text TEXT,
    legal_review_required INTEGER NOT NULL DEFAULT 0,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (evaluation_id) REFERENCES github_repo_evaluations(evaluation_id)
);

CREATE INDEX IF NOT EXISTS idx_career_profiles_enabled ON career_profiles(enabled, privacy_scope);
CREATE INDEX IF NOT EXISTS idx_career_applications_status ON career_applications(profile_id, application_status);
CREATE INDEX IF NOT EXISTS idx_capability_center_component ON capability_center_records(component_type, component_id);
CREATE INDEX IF NOT EXISTS idx_agent_registry_enabled ON agent_registry_records(enabled, risk_level);
CREATE INDEX IF NOT EXISTS idx_github_repo_evaluations_repo ON github_repo_evaluations(owner_name, repo_name, integration_decision);
