-- Migration 142: lean schema baseline (WO-SQUASH-BASELINE)
--
-- Operator-approved irreversible squash (approval 2026-07-03/2026-07-04,
-- WO 5fd84891-a329-48b8-b537-f0d4fc94d1a7). Collapses migrations 001-141 into
-- a single lean baseline. Evidence: .planning/audits/schema-keeplist-2026-07-03.md
-- (67 live tables / 57 logical, KEEP:67 RESURFACE:0 DROP:0 at audit time) plus the
-- migrations-127-141 drop wave that took studio.db from 137 -> 58 tables before this
-- squash landed, and the duplication review that preceded operator approval.
--
-- Regeneration method: a fresh temp-file DB was migrated through the full,
-- still-present 001-141 chain via core.config.sqlite_bootstrap.run_migrations(
-- conn, apply_unreleased=True). Every object in that DB's sqlite_master (tables,
-- indexes, views, triggers -- excluding sqlite_sequence and FTS5 shadow tables)
-- was re-emitted below in idempotent form (CREATE ... IF NOT EXISTS), tables then
-- indexes then views then triggers, preserving the original DDL text verbatim
-- apart from the added IF NOT EXISTS guard. DROP TABLE IF EXISTS / DROP VIEW IF
-- EXISTS statements for every tombstoned name run first so a historical DB at any
-- prior schema version sheds dead objects on its way to 142. See
-- tests/unit/schema_tombstones_data.py for the frozen tombstone registry and
-- docs/MIGRATION_AUTHORITY.md for the full migration-by-migration history that
-- this baseline supersedes (001-141 remain in git history; not in the working tree).
--
-- Historical-upgrade note: this migration guarantees (a) a fresh DB (applied=0)
-- ends up with exactly this schema, (b) a DB already at 141 is a no-op, and (c) a
-- DB at any older schema version applies without error and sheds tombstoned
-- tables/views. It does NOT replay column-level ALTER/RENAME transformations that
-- the original chain performed incrementally -- CREATE TABLE IF NOT EXISTS cannot
-- retrofit new columns onto a same-named table that predates them. The live
-- authority DB is at 141 (a no-op apply); this only matters for a hand-rolled or
-- very old out-of-band DB, which is not a supported upgrade path.

PRAGMA foreign_keys=OFF;

-- Tombstoned tables: dropped somewhere in the pre-squash chain and absent from
-- the fresh schema below. Must never resurface (operator directive, WO-TOMBSTONE-GUARD).
DROP TABLE IF EXISTS activity_log;
DROP TABLE IF EXISTS adapter_executions;
DROP TABLE IF EXISTS adapter_result_records;
DROP TABLE IF EXISTS agent_context_scope_policies;
DROP TABLE IF EXISTS agent_invocations;
DROP TABLE IF EXISTS agent_registry_records;
DROP TABLE IF EXISTS agent_result_records;
DROP TABLE IF EXISTS alert_history;
DROP TABLE IF EXISTS artifact_authority_records;
DROP TABLE IF EXISTS artifact_records;
DROP TABLE IF EXISTS authority_projection_records;
DROP TABLE IF EXISTS automation_checkpoints;
DROP TABLE IF EXISTS automation_log;
DROP TABLE IF EXISTS blocker_resolution_records;
DROP TABLE IF EXISTS canonical_events_legacy_backup;
DROP TABLE IF EXISTS capability_center_records;
DROP TABLE IF EXISTS career_application_events;
DROP TABLE IF EXISTS career_application_field_mappings;
DROP TABLE IF EXISTS career_applications;
DROP TABLE IF EXISTS career_browser_automation_runs;
DROP TABLE IF EXISTS career_case_studies;
DROP TABLE IF EXISTS career_cover_letter_versions;
DROP TABLE IF EXISTS career_evidence_refs;
DROP TABLE IF EXISTS career_interview_story_bank;
DROP TABLE IF EXISTS career_job_opportunities;
DROP TABLE IF EXISTS career_portfolio_artifacts;
DROP TABLE IF EXISTS career_profile_fields;
DROP TABLE IF EXISTS career_profiles;
DROP TABLE IF EXISTS career_resume_versions;
DROP TABLE IF EXISTS career_role_targets;
DROP TABLE IF EXISTS career_scorecards;
DROP TABLE IF EXISTS compliance_review_flags;
DROP TABLE IF EXISTS connector_ingestion_runs;
DROP TABLE IF EXISTS cor_skill_corrections;
DROP TABLE IF EXISTS dashboard_attention_items;
DROP TABLE IF EXISTS dashboard_authority_reconciliation_records;
DROP TABLE IF EXISTS decision_event_link;
DROP TABLE IF EXISTS decision_log;
DROP TABLE IF EXISTS decision_records;
DROP TABLE IF EXISTS demo_case_study_packets;
DROP TABLE IF EXISTS ds_design_briefs;
DROP TABLE IF EXISTS ds_documents;
DROP TABLE IF EXISTS ds_documents_fts;
DROP TABLE IF EXISTS ds_eval_runs;
DROP TABLE IF EXISTS ds_milestones;
DROP TABLE IF EXISTS ds_projects;
DROP TABLE IF EXISTS ds_tasks;
DROP TABLE IF EXISTS ds_technology_signals;
DROP TABLE IF EXISTS ds_work_order_types;
DROP TABLE IF EXISTS ds_work_orders;
DROP TABLE IF EXISTS execution_dependencies;
DROP TABLE IF EXISTS execution_event_links;
DROP TABLE IF EXISTS execution_nodes;
DROP TABLE IF EXISTS execution_outputs;
DROP TABLE IF EXISTS findings;
DROP TABLE IF EXISTS findings_current_status;
DROP TABLE IF EXISTS github_repo_adoption_decisions;
DROP TABLE IF EXISTS github_repo_attribution_records;
DROP TABLE IF EXISTS github_repo_dependency_findings;
DROP TABLE IF EXISTS github_repo_evaluations;
DROP TABLE IF EXISTS github_repo_integration_candidates;
DROP TABLE IF EXISTS github_repo_license_findings;
DROP TABLE IF EXISTS github_repo_pattern_references;
DROP TABLE IF EXISTS github_repo_security_findings;
DROP TABLE IF EXISTS guard_events;
DROP TABLE IF EXISTS guardrail_rules_audit;
DROP TABLE IF EXISTS hardening_candidate_records;
DROP TABLE IF EXISTS hook_eval_runs;
DROP TABLE IF EXISTS hook_executions;
DROP TABLE IF EXISTS hook_executions_new;
DROP TABLE IF EXISTS hook_findings;
DROP TABLE IF EXISTS hook_findings_new;
DROP TABLE IF EXISTS hook_invocations;
DROP TABLE IF EXISTS installer_distribution_checks;
DROP TABLE IF EXISTS learning_event_records;
DROP TABLE IF EXISTS legacy_canonical_event_import_map;
DROP TABLE IF EXISTS local_watch_schedule_records;
DROP TABLE IF EXISTS model_provider_profiles;
DROP TABLE IF EXISTS outcome_records;
DROP TABLE IF EXISTS pending_audits;
DROP TABLE IF EXISTS pi_analysis_runs;
DROP TABLE IF EXISTS pi_bugs;
DROP TABLE IF EXISTS pi_components;
DROP TABLE IF EXISTS pi_dependencies;
DROP TABLE IF EXISTS pi_improvements;
DROP TABLE IF EXISTS pi_violations;
DROP TABLE IF EXISTS pi_wave_tasks;
DROP TABLE IF EXISTS pi_waves;
DROP TABLE IF EXISTS policy_decision_records;
DROP TABLE IF EXISTS prd_amendment_records;
DROP TABLE IF EXISTS prd_assumptions;
DROP TABLE IF EXISTS prd_change_orders;
DROP TABLE IF EXISTS prd_documents;
DROP TABLE IF EXISTS prd_handoffs;
DROP TABLE IF EXISTS prd_intake_questions;
DROP TABLE IF EXISTS prd_intakes;
DROP TABLE IF EXISTS prd_notes;
DROP TABLE IF EXISTS prd_plans;
DROP TABLE IF EXISTS prd_requirements;
DROP TABLE IF EXISTS prd_route_reconciliation_records;
DROP TABLE IF EXISTS prd_sessions;
DROP TABLE IF EXISTS prd_specs;
DROP TABLE IF EXISTS prd_tasks;
DROP TABLE IF EXISTS prd_version_records;
DROP TABLE IF EXISTS privacy_redaction_export_records;
DROP TABLE IF EXISTS process_runs;
DROP TABLE IF EXISTS production_readiness_assessment_runs;
DROP TABLE IF EXISTS production_readiness_control_results;
DROP TABLE IF EXISTS production_readiness_findings;
DROP TABLE IF EXISTS production_readiness_remediation_work_orders;
DROP TABLE IF EXISTS production_readiness_skill_control_mappings;
DROP TABLE IF EXISTS proj_decision_patterns;
DROP TABLE IF EXISTS proj_security_summary;
DROP TABLE IF EXISTS proj_sessions;
DROP TABLE IF EXISTS proj_skill_stats;
DROP TABLE IF EXISTS proj_workflow_runs;
DROP TABLE IF EXISTS project_assumption_records;
DROP TABLE IF EXISTS project_change_order_records;
DROP TABLE IF EXISTS project_health_scorecards;
DROP TABLE IF EXISTS project_intake_questions;
DROP TABLE IF EXISTS project_intake_records;
DROP TABLE IF EXISTS project_milestone_records;
DROP TABLE IF EXISTS project_readiness_scorecards;
DROP TABLE IF EXISTS project_work_order_authority_records;
DROP TABLE IF EXISTS raw_planning_specs;
DROP TABLE IF EXISTS raw_pulse_snapshots;
DROP TABLE IF EXISTS raw_research;
DROP TABLE IF EXISTS raw_research_temp;
DROP TABLE IF EXISTS raw_specs;
DROP TABLE IF EXISTS raw_tasks;
DROP TABLE IF EXISTS raw_token_usage;
DROP TABLE IF EXISTS raw_workflow_nodes;
DROP TABLE IF EXISTS raw_workflow_nodes_bak071;
DROP TABLE IF EXISTS raw_workflow_nodes_temp;
DROP TABLE IF EXISTS raw_workflow_runs;
DROP TABLE IF EXISTS raw_workflow_runs_bak071;
DROP TABLE IF EXISTS raw_workflow_runs_temp;
DROP TABLE IF EXISTS reg_analyzed_repos;
DROP TABLE IF EXISTS reg_projects;
DROP TABLE IF EXISTS reg_repo_extractions;
DROP TABLE IF EXISTS reg_repo_research_links;
DROP TABLE IF EXISTS reg_research_sources;
DROP TABLE IF EXISTS reg_skill_deps;
DROP TABLE IF EXISTS reg_skills;
DROP TABLE IF EXISTS reg_workflows;
DROP TABLE IF EXISTS release_readiness_records;
DROP TABLE IF EXISTS research_cache_temp;
DROP TABLE IF EXISTS resolved_finding_links;
DROP TABLE IF EXISTS risk_mitigations;
DROP TABLE IF EXISTS risk_register;
DROP TABLE IF EXISTS route_decision_records;
DROP TABLE IF EXISTS scan_deltas;
DROP TABLE IF EXISTS sec_cve_matches;
DROP TABLE IF EXISTS sec_cve_matches_new;
DROP TABLE IF EXISTS sec_hook_checks;
DROP TABLE IF EXISTS sec_hook_checks_new;
DROP TABLE IF EXISTS sec_manual_reviews;
DROP TABLE IF EXISTS sec_manual_reviews_new;
DROP TABLE IF EXISTS sec_sarif_findings;
DROP TABLE IF EXISTS sec_sarif_findings_new;
DROP TABLE IF EXISTS session_tasks;
DROP TABLE IF EXISTS shared_context_packets;
DROP TABLE IF EXISTS skill_evaluation_runs;
DROP TABLE IF EXISTS skill_invocations;
DROP TABLE IF EXISTS sum_analytics_run;
DROP TABLE IF EXISTS sum_skill_summary;
DROP TABLE IF EXISTS task_attribution_records;
DROP TABLE IF EXISTS team_rollup_records;
DROP TABLE IF EXISTS telemetry_entity_registry;
DROP TABLE IF EXISTS telemetry_module_registry;
DROP TABLE IF EXISTS temp_fk_constraint;
DROP TABLE IF EXISTS token_usage_records;
DROP TABLE IF EXISTS tool_embeddings_cache;
DROP TABLE IF EXISTS tool_invocations;
DROP TABLE IF EXISTS tool_registry;
DROP TABLE IF EXISTS validation_failures;
DROP TABLE IF EXISTS workflow_agent_skill_mappings;
DROP TABLE IF EXISTS workflow_invocations;

-- Tombstoned views: retired by the chain's drop/recreate view-guard pattern
-- (migrations 029/039/040/062/081/088/089/099/102/103/112/118/129/131/137/140)
-- and not recreated in the final schema.
DROP VIEW IF EXISTS v_active_execution;
DROP VIEW IF EXISTS v_blocked_nodes;
DROP VIEW IF EXISTS v_completion_rate;
DROP VIEW IF EXISTS vw_activity_timeline;
DROP VIEW IF EXISTS vw_component_stats;
DROP VIEW IF EXISTS vw_graph_edges;
DROP VIEW IF EXISTS vw_hook_performance;
DROP VIEW IF EXISTS vw_prd_progress;
DROP VIEW IF EXISTS vw_project_readiness_latest;
DROP VIEW IF EXISTS vw_risk_hotspots;
DROP VIEW IF EXISTS vw_task_details;

-- Tables
CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS raw_skill_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT NOT NULL,
    invoked_at TEXT NOT NULL,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    success INTEGER NOT NULL,
    execution_time_s REAL
, project_id TEXT, session_id TEXT);
CREATE TABLE IF NOT EXISTS log_batch_imports (
    batch_id TEXT PRIMARY KEY,
    imported_at TEXT NOT NULL,
    row_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS raw_operational_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    project_slug TEXT NOT NULL,
    ci_status TEXT,
    open_prs INTEGER,
    stale_branches INTEGER,
    pending_drafts INTEGER,
    open_escalations INTEGER,
    captured_at TEXT NOT NULL,
    UNIQUE(snapshot_date, project_slug)
);
CREATE TABLE IF NOT EXISTS raw_approaches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,
    session_date TEXT NOT NULL,
    approach TEXT NOT NULL,
    outcome TEXT NOT NULL,
    context TEXT,
    why_worked TEXT,
    tokens_used INTEGER,
    duration_s REAL,
    model TEXT,
    captured_at TEXT NOT NULL
, project_id TEXT, session_id TEXT);
CREATE TABLE IF NOT EXISTS reg_gotchas (
    gotcha_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    context TEXT,
    fix TEXT,
    keywords TEXT,
    discovered TEXT,
    times_hit INTEGER DEFAULT 0,
    last_hit TEXT,
    PRIMARY KEY (gotcha_id, skill_id)
);
CREATE TABLE IF NOT EXISTS raw_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    confidence TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'draft',
    title TEXT NOT NULL,
    what_happened TEXT,
    lesson TEXT,
    evidence TEXT,
    promoted_to TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT
, activity_id INTEGER, task_id TEXT, prd_id TEXT, skill_id TEXT);
CREATE TABLE IF NOT EXISTS raw_sentinels (
    sentinel_key TEXT PRIMARY KEY,
    sentinel_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts_gotchas USING fts5(
    gotcha_id, title, context, fix, keywords,
    content=reg_gotchas, content_rowid=rowid
);
CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id TEXT PRIMARY KEY,
    rule_name TEXT NOT NULL,
    metric_path TEXT NOT NULL,      -- Path to metric being monitored (e.g., 'skill.success_rate', 'api.latency_p95')
    condition TEXT NOT NULL,         -- Comparison operator: 'gt', 'lt', 'eq', 'gte', 'lte'
    threshold REAL,                  -- Threshold value to trigger alert
    severity TEXT,                   -- Alert severity: 'info', 'warning', 'critical'
    enabled BOOLEAN DEFAULT 1        -- Whether rule is active
);
CREATE TABLE IF NOT EXISTS memory_entries (
    memory_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSON,
    importance REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    last_accessed TEXT,
    access_count INTEGER NOT NULL DEFAULT 0,
    tags TEXT,
    project TEXT,
    skill TEXT
, source_type TEXT DEFAULT 'unknown', source_id TEXT, lifecycle_state TEXT DEFAULT 'ACTIVE', confidence REAL, provenance JSON, lineage JSON, relationships JSON, updated_at TEXT, intelligence_surfaced_at TEXT, source_repo_id TEXT, tainted INTEGER NOT NULL DEFAULT 0, taint_reason TEXT, taint_timestamp TEXT);
CREATE TABLE IF NOT EXISTS audit_runs (
    audit_id TEXT PRIMARY KEY,  -- e.g., 'AUDIT-SEC-20260506-001', 'AUDIT-QUAL-20260506-002'
    activity_id INTEGER,  -- FK to activity_log (hub) - nullable for standalone audits
    audit_type TEXT NOT NULL CHECK(audit_type IN ('code_quality', 'security', 'performance', 'architecture', 'compliance')),
    audit_scope TEXT NOT NULL CHECK(audit_scope IN ('project', 'prd', 'task', 'skill', 'file', 'function')),
    target_id TEXT NOT NULL,  -- e.g., 'dream-studio', 'PRD-001', 'T-042', 'core.py'
    target_type TEXT NOT NULL CHECK(target_type IN ('project', 'prd', 'task', 'skill', 'file', 'function', 'module')),
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed', 'cancelled')) DEFAULT 'running',
    findings_count INTEGER DEFAULT 0,
    critical_count INTEGER DEFAULT 0,
    high_count INTEGER DEFAULT 0,
    medium_count INTEGER DEFAULT 0,
    low_count INTEGER DEFAULT 0,
    report_path TEXT,  -- Path to detailed report file (e.g., '.dream-studio/reports/audit/AUDIT-SEC-20260506-001.md')
    summary TEXT,  -- Brief summary of findings (e.g., "3 critical XSS vulnerabilities, 5 missing input validations")
    started_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),  -- ISO8601
    completed_at TEXT,  -- ISO8601, nullable until completed
    duration_s REAL,  -- Duration in seconds, calculated on completion
    FOREIGN KEY (activity_id) REFERENCES activity_log(activity_id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS guardrail_decisions (
    decision_id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    event_id TEXT,
    action TEXT NOT NULL CHECK (action IN ('allow', 'block', 'require_approval', 'advisory')),
    message TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    metadata TEXT
);
-- memory_fts: standalone FTS5 table (no content= sync), managed by
-- FTS5MemoryRetriever. This is a PROJECTION (rebuildable) index over
-- memory_entries, not authoritative data (originally migration 033).
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    memory_id UNINDEXED,
    content,
    category,
    tags
);
CREATE TABLE IF NOT EXISTS execution_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    event_name TEXT NOT NULL,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    parent_event_id TEXT,
    actor_type TEXT,
    actor_id TEXT,
    agent_id TEXT,
    skill_id TEXT,
    workflow_id TEXT,
    hook_id TEXT,
    tool_id TEXT,
    model_id TEXT,
    adapter_id TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    outcome_status TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), _built_from_event_id TEXT,
    FOREIGN KEY (parent_event_id) REFERENCES execution_events(event_id)
);
CREATE TABLE IF NOT EXISTS research_evidence_records (
    research_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    question TEXT NOT NULL,
    decision_class TEXT NOT NULL,
    confidence TEXT NOT NULL,
    sources_json TEXT NOT NULL DEFAULT '[]',
    source_summary TEXT,
    decision_impact TEXT,
    operator_verification_required INTEGER NOT NULL DEFAULT 0,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
);
CREATE TABLE IF NOT EXISTS validation_results (
    validation_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    validation_type TEXT NOT NULL,
    status TEXT NOT NULL,
    command TEXT,
    scope TEXT,
    summary TEXT,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
);
CREATE TABLE IF NOT EXISTS adapter_authority_profiles (
    adapter_id TEXT PRIMARY KEY,
    adapter_type TEXT NOT NULL,
    adapter_name TEXT NOT NULL,
    authority_role TEXT NOT NULL DEFAULT 'projection',
    owns_source_of_truth INTEGER NOT NULL DEFAULT 0,
    config_projection_path TEXT,
    supported_context_packets_json TEXT NOT NULL DEFAULT '[]',
    supported_result_types_json TEXT NOT NULL DEFAULT '[]',
    stale_detection_policy_json TEXT NOT NULL DEFAULT '{}',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (adapter_type IN ('claude', 'codex', 'cursor', 'copilot', 'chatgpt', 'mcp', 'local_model', 'shell', 'other')),
    CHECK (authority_role IN ('projection', 'executor', 'reviewer', 'observer')),
    CHECK (owns_source_of_truth = 0)
);
CREATE TABLE IF NOT EXISTS capability_route_records (
    capability_route_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    task_class TEXT NOT NULL,
    selected_adapter_id TEXT,
    selected_model_profile_id TEXT,
    route_basis_json TEXT NOT NULL DEFAULT '{}',
    risk_level TEXT NOT NULL DEFAULT 'medium',
    cost_sensitivity TEXT NOT NULL DEFAULT 'medium',
    validation_required INTEGER NOT NULL DEFAULT 1,
    operator_approval_required INTEGER NOT NULL DEFAULT 0,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (selected_adapter_id) REFERENCES adapter_authority_profiles(adapter_id),
    FOREIGN KEY (selected_model_profile_id) REFERENCES model_provider_profiles(model_profile_id)
);
CREATE TABLE IF NOT EXISTS ai_adapter_accounting_profiles (
    profile_id TEXT PRIMARY KEY,
    adapter_id TEXT NOT NULL,
    provider TEXT,
    model_id TEXT,
    configuration_label TEXT NOT NULL,
    billing_mode TEXT NOT NULL,
    token_visibility TEXT NOT NULL,
    cost_visibility TEXT NOT NULL,
    usage_source TEXT NOT NULL,
    cost_source TEXT NOT NULL DEFAULT 'unavailable',
    confidence TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (billing_mode IN (
        'subscription_plan',
        'plan_allowance',
        'token_metered',
        'api_metered',
        'credit_metered',
        'enterprise_contract',
        'unknown',
        'unavailable'
    )),
    CHECK (token_visibility IN ('exact', 'partial', 'estimated', 'unavailable')),
    CHECK (cost_visibility IN (
        'exact',
        'provider_reported',
        'estimated',
        'allocated_subscription_cost',
        'unavailable',
        'unknown'
    )),
    CHECK (usage_source IN (
        'provider_metadata',
        'provider_usage_export',
        'local_telemetry',
        'plan_usage_panel',
        'manual_config',
        'unavailable'
    )),
    CHECK (cost_source IN (
        'provider_metadata',
        'provider_usage_export',
        'billing_api',
        'plan_allocation_config',
        'local_estimate',
        'unavailable',
        'unknown'
    )),
    CHECK (confidence IN ('high', 'medium', 'low', 'unknown')),
    CHECK (active IN (0, 1)),
    FOREIGN KEY (adapter_id) REFERENCES adapter_authority_profiles(adapter_id)
);
CREATE TABLE IF NOT EXISTS raw_claude_code_events (
    event_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    event_type TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    source_payload TEXT NOT NULL DEFAULT '{}',
    session_id TEXT,
    project_id TEXT,
    workflow_id TEXT,
    skill_id TEXT,
    agent_id TEXT,
    hook_id TEXT,
    tool_id TEXT,
    model_id TEXT,
    adapter_id TEXT,
    correlation_id TEXT
);
CREATE TABLE IF NOT EXISTS business_canonical_events (
    event_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    event_type TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    trace JSON NOT NULL DEFAULT '{}',
    payload JSON NOT NULL DEFAULT '{}',
    correlation_id TEXT,
    project_id TEXT,
    milestone_id TEXT,
    work_order_id TEXT,
    task_id TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    source TEXT NOT NULL DEFAULT 'ingestor'
);
CREATE TABLE IF NOT EXISTS ai_canonical_events (
    event_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    event_type TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    trace JSON NOT NULL DEFAULT '{}',
    payload JSON NOT NULL DEFAULT '{}',
    correlation_id TEXT,
    session_id TEXT,
    skill_id TEXT,
    workflow_id TEXT,
    agent_id TEXT,
    hook_id TEXT,
    model_id TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    source TEXT NOT NULL DEFAULT 'ingestor'
);
CREATE TABLE IF NOT EXISTS projection_state (
    projection_name TEXT PRIMARY KEY,
    last_processed_business_event_id TEXT,
    last_processed_ai_event_id TEXT,
    last_run_at TEXT,
    events_processed_total INTEGER NOT NULL DEFAULT 0,
    events_failed_total INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS projection_dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    event_source TEXT NOT NULL CHECK (event_source IN ('business', 'ai')),
    projection_name TEXT NOT NULL,
    error_message TEXT,
    error_traceback TEXT,
    failed_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_retry_at TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'resolved', 'ignored'))
);
CREATE TABLE IF NOT EXISTS projection_retry_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    event_source TEXT NOT NULL CHECK (event_source IN ('business', 'ai')),
    projection_name TEXT NOT NULL,
    next_retry_at TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS business_work_orders (
    work_order_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    created_at TEXT,
    started_at TEXT,
    closed_at TEXT,
    blocked_at TEXT,
    unblocked_at TEXT,
    block_reason TEXT,
    source_event_id TEXT,
    last_event_id TEXT,
    last_updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
, description TEXT, work_order_type TEXT, updated_at TEXT, sequence_order INTEGER, originating_symptom TEXT, verify_status TEXT, verify_score REAL, verified_at TEXT);
CREATE TABLE IF NOT EXISTS business_projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
, source_event_id TEXT, last_event_id TEXT, project_path TEXT, total_sessions INTEGER NOT NULL DEFAULT 0, total_tokens INTEGER NOT NULL DEFAULT 0, last_session_at TEXT, detected_stack TEXT, stack_json TEXT, vision_statement TEXT);
CREATE TABLE IF NOT EXISTS business_milestones (
    milestone_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES business_projects(project_id),
    title TEXT NOT NULL,
    description TEXT,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    order_index INTEGER DEFAULT 0,
    stage_gate_json TEXT,
    validation_expectations_json TEXT,
    security_readiness_checks_json TEXT
, source_event_id TEXT, last_event_id TEXT);
CREATE TABLE IF NOT EXISTS business_work_order_types (
    type_id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    pre_build_gate TEXT,
    build_executor TEXT,
    post_build_gate TEXT,
    workflow_template TEXT,
    precondition_skill TEXT,
    task_generator TEXT,
    resolution_instructions TEXT
);
CREATE TABLE IF NOT EXISTS business_tasks (
    task_id TEXT PRIMARY KEY,
    work_order_id TEXT NOT NULL REFERENCES business_work_orders(work_order_id),
    project_id TEXT NOT NULL REFERENCES business_projects(project_id),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
, source_event_id TEXT, last_event_id TEXT, acceptance_criteria TEXT);
CREATE TABLE IF NOT EXISTS business_design_briefs (
    brief_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES business_projects(project_id),
    status TEXT NOT NULL DEFAULT 'draft',
    purpose TEXT,
    audience TEXT,
    tone TEXT,
    design_system TEXT,
    font_pairing TEXT,
    brand_tokens TEXT,
    raw_output TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
, source_event_id TEXT, last_event_id TEXT);
CREATE TABLE IF NOT EXISTS "scan_runs" (
    scan_id      TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES business_projects(project_id),
    is_baseline  INTEGER NOT NULL DEFAULT 0 CHECK(is_baseline IN (0, 1)),
    scope        TEXT NOT NULL DEFAULT 'full_repo',  -- full_repo | changed | sample
    target_path  TEXT,
    tool_versions_json TEXT NOT NULL DEFAULT '{}',   -- {"gitleaks": "8.x", "bandit": "1.x", ...}
    findings_count    INTEGER NOT NULL DEFAULT 0,
    critical_count    INTEGER NOT NULL DEFAULT 0,
    high_count        INTEGER NOT NULL DEFAULT 0,
    medium_count      INTEGER NOT NULL DEFAULT 0,
    low_count         INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'running'
                      CHECK(status IN ('running', 'completed', 'failed')),
    started_at   TEXT NOT NULL,
    completed_at TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now','utc'))
, previous_scan_id TEXT
    REFERENCES "scan_runs"(scan_id), skill_id TEXT NOT NULL DEFAULT 'security');
CREATE TABLE IF NOT EXISTS "raw_sessions" (
    session_id TEXT PRIMARY KEY,
    project_id TEXT,
    topic TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_s REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    tasks_completed INTEGER DEFAULT 0,
    pipeline_phase TEXT,
    handoff_consumed INTEGER DEFAULT 0,
    outcome TEXT
);
CREATE TABLE IF NOT EXISTS "raw_handoffs" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES raw_sessions(session_id),
    project_id TEXT,
    topic TEXT NOT NULL,
    plan_path TEXT,
    pipeline_phase TEXT,
    current_task_id TEXT,
    current_task_name TEXT,
    tasks_completed INTEGER,
    tasks_total INTEGER,
    branch TEXT,
    last_commit TEXT,
    working TEXT,
    broken TEXT,
    pending_decisions TEXT,
    active_files TEXT,
    next_action TEXT,
    lessons_json TEXT,
    gotchas_hit TEXT,
    approaches_json TEXT,
    created_at TEXT NOT NULL
, file_id TEXT, checksum TEXT);
CREATE TABLE IF NOT EXISTS ds_eval_baselines (
    eval_id TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0.0',
    baseline_score REAL NOT NULL,
    last_run_score REAL,
    last_run_at TEXT,
    regression_flag INTEGER NOT NULL DEFAULT 0 CHECK(regression_flag IN (0, 1)),
    regression_threshold REAL NOT NULL DEFAULT 0.10,
    run_count INTEGER NOT NULL DEFAULT 0,
    last_updated_at TEXT NOT NULL DEFAULT (datetime('now')), label TEXT DEFAULT NULL,
    PRIMARY KEY (eval_id, version)
);
CREATE TABLE IF NOT EXISTS ds_workflow_pattern_signals (
    pattern_id TEXT PRIMARY KEY,
    project_id TEXT,
    pattern_type TEXT NOT NULL CHECK(pattern_type IN (
        'post_completion', 'pre_close', 'always_paired'
    )),
    skill_a TEXT NOT NULL,
    skill_b TEXT,                           -- NULL for post_completion and pre_close
    co_occurrence_count INTEGER NOT NULL DEFAULT 0,
    total_sessions INTEGER NOT NULL DEFAULT 1,
    confidence_score REAL NOT NULL
        CHECK(confidence_score >= 0.0 AND confidence_score <= 1.0),
    suppressed INTEGER NOT NULL DEFAULT 0 CHECK(suppressed IN (0, 1)),
    suppressed_at TEXT,
    last_observed_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS ds_user_extensions (
    extension_id            TEXT PRIMARY KEY,
    skill_id                TEXT NOT NULL,  -- canonical skill being extended (e.g., 'ds-quality:security')
    extension_type          TEXT NOT NULL CHECK(extension_type IN (
                                'example', 'gap_filler', 'threshold_override',
                                'option_override', 'mode_addition', 'trigger_alias'
                            )),
    content                 TEXT NOT NULL,  -- JSON or markdown; type-specific structure
    source_signal           TEXT,           -- 'friction' | 'pattern' | 'manual' | 'eval_gap'
    compiled_from           TEXT,           -- JSON refs: WO IDs, session IDs, or signal IDs
    status                  TEXT NOT NULL DEFAULT 'proposed' CHECK(status IN (
                                'proposed', 'experimental', 'active',
                                'suppressed', 'rejected', 'deprecated'
                            )),
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    last_validated_at       TEXT,           -- when retroactive validation last ran
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
    user_confirmed_at       TEXT,           -- NULL = not yet confirmed
    user_confirmed_by       TEXT,           -- operator ID who confirmed
    suppressed_reason       TEXT            -- required when status='suppressed'
, validation_detail TEXT);
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
    classified_as   TEXT CHECK(classified_as IS NULL OR classified_as IN (
                        'capability', 'personalization', 'onboarding'
                    )),
    classified_at   TEXT,
    extension_id    TEXT
, classification_confidence REAL, classification_reason TEXT, classification_skipped INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS preflight_events (
    event_id        TEXT PRIMARY KEY,
    parent_event_id TEXT REFERENCES preflight_events(event_id),
    work_order_id   TEXT NOT NULL,
    correlation_id  TEXT,
    event_kind      TEXT NOT NULL CHECK (event_kind IN ('preflight.created', 'preflight.status_changed')),
    finding_type    TEXT CHECK (finding_type IN ('blast_radius', 'impact', 'risk', 'spec_reference', 'dependency')),
    source          TEXT,
    severity        TEXT CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info')),
    summary         TEXT,
    body            TEXT,
    author_type     TEXT,
    status          TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS business_work_order_preflights (
    finding_id          TEXT PRIMARY KEY,
    work_order_id       TEXT NOT NULL,
    correlation_id      TEXT,
    finding_type        TEXT,
    source              TEXT,
    severity            TEXT,
    summary             TEXT,
    body                TEXT,
    author_type         TEXT,
    status              TEXT NOT NULL DEFAULT 'open',
    last_status_event_id TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS work_order_dependencies (
    work_order_id  TEXT NOT NULL REFERENCES business_work_orders(work_order_id),
    depends_on_id  TEXT NOT NULL REFERENCES business_work_orders(work_order_id),
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (work_order_id, depends_on_id)
);
CREATE TABLE IF NOT EXISTS security_events (
    event_id          TEXT PRIMARY KEY,
    parent_event_id   TEXT REFERENCES security_events(event_id),
    event_kind        TEXT NOT NULL,    -- finding.recorded | finding.status_changed | finding.resolved | scan_run.started
    correlation_id    TEXT,             -- → ai_canonical_events skill run that produced it
    project_id        TEXT,
    work_order_id     TEXT,
    scanner_type      TEXT,             -- SAST | DAST | SCA | secrets
    cwe_id            TEXT,
    owasp_category    TEXT,
    cve_id            TEXT,
    file_path         TEXT,
    line_number       INTEGER,
    vuln_class        TEXT,             -- injection | auth | crypto | ...
    exploitability    TEXT,             -- critical | high | medium | low | info
    severity          TEXT,             -- critical | high | medium | low | info
    title             TEXT,
    body              TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);
CREATE TABLE IF NOT EXISTS readiness_events (
    event_id          TEXT PRIMARY KEY,
    parent_event_id   TEXT REFERENCES readiness_events(event_id),
    event_kind        TEXT NOT NULL,    -- assessment.started | control_result.recorded | control_result.status_changed | assessment.closed
    correlation_id    TEXT,             -- → ai_canonical_events skill run that produced it
    project_id        TEXT,
    work_order_id     TEXT,
    framework         TEXT,             -- SOC2 | NIST | ISO27001 | custom
    control_id        TEXT,
    result            TEXT,             -- pass | fail | na | incomplete
    evidence          TEXT,
    remediation_wo    TEXT,             -- → business_work_orders(work_order_id)
    title             TEXT,
    body              TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);
CREATE TABLE IF NOT EXISTS "research_cache" (
    cache_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    focus_areas TEXT,
    sources TEXT,
    findings TEXT,
    confidence_score REAL,
    triangulation_score REAL,
    activity_id INTEGER,
    prd_id TEXT,
    task_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT
);
CREATE TABLE IF NOT EXISTS eval_registry (
    eval_id        TEXT PRIMARY KEY,
    target_type    TEXT NOT NULL CHECK(target_type IN ('skill','hook','workflow','agent')),
    target_id      TEXT NOT NULL,
    rubric_score   INTEGER,
    last_run_at    TEXT,
    last_run_id    TEXT,
    baseline_run_id TEXT,
    friction_flag  INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
, friction_signal_count INTEGER NOT NULL DEFAULT 0, friction_threshold INTEGER NOT NULL DEFAULT 3, pending_rerun INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS ds_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS ds_escalations (
    work_order_id TEXT PRIMARY KEY,
    escalation_level INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    designated_executor TEXT,
    last_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS "ai_usage_operational_records" (
    usage_record_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    work_order_id TEXT,
    process_run_id TEXT,
    adapter_id TEXT NOT NULL,
    provider TEXT,
    model_id TEXT,
    accounting_profile_id TEXT,
    token_usage_id TEXT,
    billing_mode TEXT NOT NULL DEFAULT 'unknown',
    token_visibility TEXT NOT NULL DEFAULT 'unavailable',
    cost_visibility TEXT NOT NULL DEFAULT 'unknown',
    usage_source TEXT NOT NULL DEFAULT 'local_telemetry',
    cost_source TEXT NOT NULL DEFAULT 'unknown',
    confidence TEXT NOT NULL DEFAULT 'unknown',
    input_tokens INTEGER,
    output_tokens INTEGER,
    cached_tokens INTEGER,
    total_tokens INTEGER,
    cost_amount NUMERIC(20, 8),
    cost_currency TEXT,
    run_count INTEGER NOT NULL DEFAULT 1,
    files_touched_json TEXT NOT NULL DEFAULT '[]',
    commands_run_json TEXT NOT NULL DEFAULT '[]',
    validation_result TEXT,
    pr_result_outcome TEXT,
    success INTEGER,
    failure_reason TEXT,
    rework_needed INTEGER,
    security_findings_json TEXT NOT NULL DEFAULT '[]',
    readiness_findings_json TEXT NOT NULL DEFAULT '[]',
    duration_ms INTEGER,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (billing_mode IN (
        'subscription_plan', 'plan_allowance', 'token_metered', 'api_metered',
        'credit_metered', 'enterprise_contract', 'unknown', 'unavailable'
    )),
    CHECK (token_visibility IN ('exact', 'partial', 'estimated', 'unavailable')),
    CHECK (cost_visibility IN (
        'exact', 'provider_reported', 'estimated', 'allocated_subscription_cost',
        'unavailable', 'unknown'
    )),
    CHECK (usage_source IN (
        'provider_metadata', 'provider_usage_export', 'local_telemetry',
        'plan_usage_panel', 'manual_config', 'unavailable'
    )),
    CHECK (cost_source IN (
        'provider_metadata', 'provider_usage_export', 'billing_api',
        'plan_allocation_config', 'local_estimate', 'unavailable', 'unknown'
    )),
    CHECK (confidence IN ('high', 'medium', 'low', 'unknown')),
    CHECK (success IN (0, 1) OR success IS NULL),
    CHECK (rework_needed IN (0, 1) OR rework_needed IS NULL),
    FOREIGN KEY (adapter_id) REFERENCES adapter_authority_profiles(adapter_id),
    FOREIGN KEY (accounting_profile_id)
        REFERENCES ai_adapter_accounting_profiles(profile_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_approaches_skill ON raw_approaches(skill_id, outcome);
CREATE INDEX IF NOT EXISTS idx_approaches_captured ON raw_approaches(captured_at);
CREATE INDEX IF NOT EXISTS idx_telemetry_skill ON raw_skill_telemetry(skill_name, invoked_at);
CREATE INDEX IF NOT EXISTS idx_gotchas_skill ON reg_gotchas(skill_id);
CREATE INDEX IF NOT EXISTS idx_gotchas_discovered ON reg_gotchas(discovered);
CREATE INDEX IF NOT EXISTS idx_opsnapshots_project ON raw_operational_snapshots(project_slug, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_lessons_status ON raw_lessons(status);
CREATE INDEX IF NOT EXISTS idx_lessons_source ON raw_lessons(source);
CREATE INDEX IF NOT EXISTS idx_sentinels_type ON raw_sentinels(sentinel_type);
CREATE INDEX IF NOT EXISTS idx_approaches_project ON raw_approaches(project_id);
CREATE INDEX IF NOT EXISTS idx_approaches_session ON raw_approaches(session_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_project ON raw_skill_telemetry(project_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_session ON raw_skill_telemetry(session_id);
CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled, severity);
CREATE INDEX IF NOT EXISTS idx_memory_source
ON memory_entries(source);
CREATE INDEX IF NOT EXISTS idx_memory_category
ON memory_entries(category);
CREATE INDEX IF NOT EXISTS idx_memory_project
ON memory_entries(project);
CREATE INDEX IF NOT EXISTS idx_memory_importance
ON memory_entries(importance DESC);
CREATE INDEX IF NOT EXISTS idx_lessons_activity
ON raw_lessons(activity_id);
CREATE INDEX IF NOT EXISTS idx_lessons_task
ON raw_lessons(task_id);
CREATE INDEX IF NOT EXISTS idx_lessons_prd
ON raw_lessons(prd_id);
CREATE INDEX IF NOT EXISTS idx_lessons_skill
ON raw_lessons(skill_id);
CREATE INDEX IF NOT EXISTS idx_lessons_activity_status
ON raw_lessons(activity_id, status);
CREATE INDEX IF NOT EXISTS idx_lessons_task_confidence
ON raw_lessons(task_id, confidence);
CREATE INDEX IF NOT EXISTS idx_audit_target
ON audit_runs(target_id, target_type);
CREATE INDEX IF NOT EXISTS idx_audit_type_status
ON audit_runs(audit_type, status);
CREATE INDEX IF NOT EXISTS idx_audit_started
ON audit_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_severity
ON audit_runs(critical_count DESC, high_count DESC)
WHERE status = 'completed';
CREATE INDEX IF NOT EXISTS idx_guardrail_decisions_rule_id ON guardrail_decisions(rule_id);
CREATE INDEX IF NOT EXISTS idx_guardrail_decisions_evaluated_at ON guardrail_decisions(evaluated_at);
CREATE INDEX IF NOT EXISTS idx_guardrail_decisions_action ON guardrail_decisions(action);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_provenance
ON memory_entries(source_type, source_id) WHERE source_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_memory_lifecycle
ON memory_entries(lifecycle_state);
CREATE INDEX IF NOT EXISTS idx_execution_events_scope ON execution_events(project_id, milestone_id, task_id);
CREATE INDEX IF NOT EXISTS idx_execution_events_process ON execution_events(process_run_id);
CREATE INDEX IF NOT EXISTS idx_research_records_scope ON research_evidence_records(project_id, milestone_id, task_id);
CREATE INDEX IF NOT EXISTS idx_validation_results_scope ON validation_results(project_id, milestone_id, task_id, status);
CREATE INDEX IF NOT EXISTS idx_capability_routes_scope ON capability_route_records(project_id, milestone_id, task_id, task_class);
CREATE INDEX IF NOT EXISTS idx_ai_accounting_profiles_adapter
ON ai_adapter_accounting_profiles(adapter_id, provider, model_id, active);
CREATE INDEX IF NOT EXISTS idx_execution_events_canonical_link
    ON execution_events(_built_from_event_id)
    WHERE _built_from_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_cce_session_id   ON raw_claude_code_events(session_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_project_id   ON raw_claude_code_events(project_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_workflow_id  ON raw_claude_code_events(workflow_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_skill_id     ON raw_claude_code_events(skill_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_agent_id     ON raw_claude_code_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_hook_id      ON raw_claude_code_events(hook_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_tool_id      ON raw_claude_code_events(tool_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_correlation_id ON raw_claude_code_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_event_type    ON raw_claude_code_events(event_type);
CREATE INDEX IF NOT EXISTS idx_raw_cce_received_at   ON raw_claude_code_events(received_at);
CREATE INDEX IF NOT EXISTS idx_raw_cce_event_timestamp ON raw_claude_code_events(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_cce_project_time ON raw_claude_code_events(project_id, received_at);
CREATE INDEX IF NOT EXISTS idx_raw_cce_type_time ON raw_claude_code_events(event_type, received_at);
CREATE INDEX IF NOT EXISTS idx_raw_cce_session_type ON raw_claude_code_events(session_id, event_type);
CREATE INDEX IF NOT EXISTS idx_bce_correlation_id  ON business_canonical_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_bce_event_type      ON business_canonical_events(event_type);
CREATE INDEX IF NOT EXISTS idx_bce_event_timestamp ON business_canonical_events(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_bce_received_at     ON business_canonical_events(received_at);
CREATE INDEX IF NOT EXISTS idx_bce_project_id      ON business_canonical_events(project_id);
CREATE INDEX IF NOT EXISTS idx_bce_milestone_id    ON business_canonical_events(milestone_id);
CREATE INDEX IF NOT EXISTS idx_bce_work_order_id   ON business_canonical_events(work_order_id);
CREATE INDEX IF NOT EXISTS idx_bce_task_id         ON business_canonical_events(task_id);
CREATE INDEX IF NOT EXISTS idx_bce_project_time ON business_canonical_events(project_id, event_timestamp);
CREATE INDEX IF NOT EXISTS idx_bce_type_time    ON business_canonical_events(event_type, event_timestamp);
CREATE INDEX IF NOT EXISTS idx_bce_project_type ON business_canonical_events(project_id, event_type);
CREATE INDEX IF NOT EXISTS idx_ace_correlation_id  ON ai_canonical_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_ace_event_type      ON ai_canonical_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ace_event_timestamp ON ai_canonical_events(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_ace_received_at     ON ai_canonical_events(received_at);
CREATE INDEX IF NOT EXISTS idx_ace_session_id      ON ai_canonical_events(session_id);
CREATE INDEX IF NOT EXISTS idx_ace_skill_id        ON ai_canonical_events(skill_id);
CREATE INDEX IF NOT EXISTS idx_ace_workflow_id     ON ai_canonical_events(workflow_id);
CREATE INDEX IF NOT EXISTS idx_ace_agent_id        ON ai_canonical_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_ace_hook_id         ON ai_canonical_events(hook_id);
CREATE INDEX IF NOT EXISTS idx_ace_model_id        ON ai_canonical_events(model_id);
CREATE INDEX IF NOT EXISTS idx_ace_session_time ON ai_canonical_events(session_id, event_timestamp);
CREATE INDEX IF NOT EXISTS idx_ace_type_time    ON ai_canonical_events(event_type, event_timestamp);
CREATE INDEX IF NOT EXISTS idx_ace_skill_time   ON ai_canonical_events(skill_id, event_timestamp);
CREATE INDEX IF NOT EXISTS idx_ace_workflow_time ON ai_canonical_events(workflow_id, event_timestamp);
CREATE INDEX IF NOT EXISTS idx_pdl_projection_name
    ON projection_dead_letter(projection_name);
CREATE INDEX IF NOT EXISTS idx_pdl_failed_at
    ON projection_dead_letter(failed_at);
CREATE INDEX IF NOT EXISTS idx_pdl_status
    ON projection_dead_letter(status);
CREATE INDEX IF NOT EXISTS idx_pdl_event_id
    ON projection_dead_letter(event_id);
CREATE INDEX IF NOT EXISTS idx_prq_next_retry_at
    ON projection_retry_queue(next_retry_at);
CREATE INDEX IF NOT EXISTS idx_prq_projection_name
    ON projection_retry_queue(projection_name);
CREATE INDEX IF NOT EXISTS idx_bwo_project_id
    ON business_work_orders(project_id);
CREATE INDEX IF NOT EXISTS idx_bwo_milestone_id
    ON business_work_orders(milestone_id);
CREATE INDEX IF NOT EXISTS idx_bwo_status
    ON business_work_orders(status);
CREATE INDEX IF NOT EXISTS idx_bwo_created_at
    ON business_work_orders(created_at);
CREATE INDEX IF NOT EXISTS idx_bwo_last_updated_at
    ON business_work_orders(last_updated_at);
CREATE INDEX IF NOT EXISTS idx_bwo_project_status
    ON business_work_orders(project_id, status);
CREATE INDEX IF NOT EXISTS idx_business_milestones_project ON business_milestones(project_id);
CREATE INDEX IF NOT EXISTS idx_bwo_type ON business_work_orders(work_order_type);
CREATE INDEX IF NOT EXISTS idx_business_tasks_project    ON business_tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_business_tasks_work_order ON business_tasks(work_order_id);
CREATE INDEX IF NOT EXISTS idx_business_design_briefs_project ON business_design_briefs(project_id);
CREATE INDEX IF NOT EXISTS idx_memory_intelligence_surfaced
ON memory_entries(intelligence_surfaced_at)
WHERE intelligence_surfaced_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_business_projects_last_session
ON business_projects(last_session_at DESC);
CREATE INDEX IF NOT EXISTS idx_business_projects_path
ON business_projects(project_path);
CREATE INDEX IF NOT EXISTS idx_business_projects_stack
ON business_projects(detected_stack);
CREATE INDEX IF NOT EXISTS idx_security_scan_runs_baseline
ON "scan_runs"(project_id, is_baseline);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON raw_sessions(project_id, started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON raw_sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_handoffs_session ON raw_handoffs(session_id);
CREATE INDEX IF NOT EXISTS idx_handoffs_project ON raw_handoffs(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_scan_runs_project ON scan_runs(project_id, skill_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_runs_skill ON scan_runs(project_id, skill_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_tainted
ON memory_entries(tainted, project) WHERE tainted = 1;
CREATE INDEX IF NOT EXISTS idx_memory_source_repo
ON memory_entries(source_repo_id) WHERE source_repo_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_eval_baselines_regression
    ON ds_eval_baselines(regression_flag)
    WHERE regression_flag = 1;
CREATE INDEX IF NOT EXISTS idx_workflow_patterns_project
    ON ds_workflow_pattern_signals(project_id, confidence_score DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_patterns_phase19
    ON ds_workflow_pattern_signals(confidence_score, suppressed)
    WHERE suppressed = 0;
CREATE INDEX IF NOT EXISTS idx_eval_baselines_label
    ON ds_eval_baselines(label)
    WHERE label IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_extensions_skill_status
    ON ds_user_extensions(skill_id, status);
CREATE INDEX IF NOT EXISTS idx_extensions_decision6
    ON ds_user_extensions(status, past_wo_count, current_eval_score)
    WHERE status = 'experimental';
CREATE INDEX IF NOT EXISTS idx_extensions_active
    ON ds_user_extensions(skill_id)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_friction_signals_skill
    ON ds_friction_signals(skill_id)
    WHERE skill_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_friction_signals_unclassified
    ON ds_friction_signals(created_at)
    WHERE classified_as IS NULL;
CREATE INDEX IF NOT EXISTS idx_friction_signals_type
    ON ds_friction_signals(signal_type, created_at);
CREATE INDEX IF NOT EXISTS idx_friction_classified_ready
    ON ds_friction_signals(classified_as, classification_confidence)
    WHERE classified_as IS NOT NULL AND classification_skipped = 0 AND extension_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_preflight_events_work_order
    ON preflight_events (work_order_id, event_kind, created_at);
CREATE INDEX IF NOT EXISTS idx_preflight_events_parent
    ON preflight_events (parent_event_id)
    WHERE parent_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_wo_preflights_work_order
    ON business_work_order_preflights (work_order_id, severity, status);
CREATE INDEX IF NOT EXISTS idx_wo_dependencies_work_order
    ON work_order_dependencies (work_order_id);
CREATE INDEX IF NOT EXISTS idx_wo_dependencies_depends_on
    ON work_order_dependencies (depends_on_id);
CREATE INDEX IF NOT EXISTS idx_security_events_project
ON security_events(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_events_parent
ON security_events(parent_event_id);
CREATE INDEX IF NOT EXISTS idx_security_events_kind
ON security_events(event_kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_events_severity
ON security_events(project_id, severity, event_kind);
CREATE INDEX IF NOT EXISTS idx_readiness_events_project
ON readiness_events(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_readiness_events_parent
ON readiness_events(parent_event_id);
CREATE INDEX IF NOT EXISTS idx_readiness_events_kind
ON readiness_events(event_kind, project_id);
CREATE INDEX IF NOT EXISTS idx_research_cache_prd ON research_cache(prd_id);
CREATE INDEX IF NOT EXISTS idx_research_cache_task ON research_cache(task_id);
CREATE INDEX IF NOT EXISTS idx_research_cache_activity ON research_cache(activity_id);
CREATE INDEX IF NOT EXISTS idx_eval_registry_target ON eval_registry(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_eval_registry_last_run ON eval_registry(last_run_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_operational_scope
ON ai_usage_operational_records(project_id, milestone_id, task_id, work_order_id, adapter_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_operational_process
ON ai_usage_operational_records(process_run_id, adapter_id, model_id);

-- Views
CREATE VIEW IF NOT EXISTS canonical_events AS
    SELECT
        event_id,
        event_type,
        event_timestamp                       AS timestamp,
        trace,
        severity,
        payload,
        NULL                                  AS actor,
        NULL                                  AS confidence_score,
        NULL                                  AS source_type,
        0                                     AS raw_prompt_retained,
        0                                     AS raw_tool_output_retained,
        schema_version,
        received_at                           AS created_at,
        NULL                                  AS invocation_mode
    FROM business_canonical_events
    UNION
    SELECT
        event_id,
        event_type,
        event_timestamp                       AS timestamp,
        trace,
        severity,
        payload,
        NULL                                  AS actor,
        NULL                                  AS confidence_score,
        NULL                                  AS source_type,
        0                                     AS raw_prompt_retained,
        0                                     AS raw_tool_output_retained,
        schema_version,
        received_at                           AS created_at,
        NULL                                  AS invocation_mode
    FROM ai_canonical_events;
CREATE VIEW IF NOT EXISTS effective_skill_runs AS
SELECT
    t.id,
    t.skill_name,
    t.invoked_at,
    t.success AS success,
    'heuristic' AS signal_source,
    t.input_tokens,
    t.output_tokens,
    t.execution_time_s
FROM raw_skill_telemetry t;
CREATE VIEW IF NOT EXISTS vw_approach_patterns AS
SELECT
    skill_id,
    approach,
    COUNT(*) AS times_tried,
    SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes,
    ROUND(
        CAST(SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS REAL)
        / COUNT(*) * 100, 1
    ) AS success_pct,
    CAST(AVG(tokens_used) AS INTEGER) AS avg_tokens,
    ROUND(AVG(duration_s), 1) AS avg_duration
FROM raw_approaches
GROUP BY skill_id, approach
HAVING COUNT(*) >= 2;
CREATE VIEW IF NOT EXISTS vw_guardrail_decisions AS
SELECT
    decision_id,
    rule_id,
    action AS decision,
    event_id,
    evaluated_at AS event_timestamp,
    message AS reason
FROM guardrail_decisions
ORDER BY evaluated_at DESC;
CREATE VIEW IF NOT EXISTS vw_security_summary AS
SELECT
    'spine' AS source_type,
    r.event_id AS finding_id,
    COALESCE(r.scanner_type, 'unknown') AS tool,
    r.severity,
    r.file_path,
    r.line_number,
    r.title AS message,
    CASE
        WHEN ls.body IS NULL THEN 'open'
        ELSE TRIM(
            CASE WHEN INSTR(ls.body, ':') > 0
                 THEN SUBSTR(ls.body, 1, INSTR(ls.body, ':') - 1)
                 ELSE ls.body
            END
        )
    END AS status,
    r.created_at
FROM (
    SELECT * FROM security_events WHERE event_kind = 'finding.recorded'
) r
LEFT JOIN (
    SELECT parent_event_id, body, event_id, created_at,
           ROW_NUMBER() OVER (
               PARTITION BY parent_event_id ORDER BY created_at DESC, event_id DESC
           ) AS rn
    FROM security_events
    WHERE event_kind IN ('finding.status_changed', 'finding.resolved')
) ls ON ls.parent_event_id = r.event_id AND ls.rn = 1
ORDER BY r.created_at DESC;

-- Triggers
CREATE TRIGGER IF NOT EXISTS trg_gotchas_ai AFTER INSERT ON reg_gotchas BEGIN
    INSERT INTO fts_gotchas(rowid, gotcha_id, title, context, fix, keywords)
    VALUES (new.rowid, new.gotcha_id, new.title, new.context, new.fix, new.keywords);
END;
CREATE TRIGGER IF NOT EXISTS trg_gotchas_ad AFTER DELETE ON reg_gotchas BEGIN
    INSERT INTO fts_gotchas(fts_gotchas, rowid, gotcha_id, title, context, fix, keywords)
    VALUES ('delete', old.rowid, old.gotcha_id, old.title, old.context, old.fix, old.keywords);
END;
CREATE TRIGGER IF NOT EXISTS trg_gotchas_au AFTER UPDATE ON reg_gotchas BEGIN
    INSERT INTO fts_gotchas(fts_gotchas, rowid, gotcha_id, title, context, fix, keywords)
    VALUES ('delete', old.rowid, old.gotcha_id, old.title, old.context, old.fix, old.keywords);
    INSERT INTO fts_gotchas(rowid, gotcha_id, title, context, fix, keywords)
    VALUES (new.rowid, new.gotcha_id, new.title, new.context, new.fix, new.keywords);
END;
CREATE TRIGGER IF NOT EXISTS memory_entries_fts_insert
AFTER INSERT ON memory_entries
BEGIN
    INSERT INTO memory_fts(memory_id, content, category, tags)
    VALUES (new.memory_id, new.content, new.category, COALESCE(new.tags, ''));
END;
CREATE TRIGGER IF NOT EXISTS memory_entries_fts_update
AFTER UPDATE ON memory_entries
BEGIN
    DELETE FROM memory_fts WHERE memory_id = old.memory_id;
    INSERT INTO memory_fts(memory_id, content, category, tags)
    VALUES (new.memory_id, new.content, new.category, COALESCE(new.tags, ''));
END;
CREATE TRIGGER IF NOT EXISTS memory_entries_fts_delete
AFTER DELETE ON memory_entries
BEGIN
    DELETE FROM memory_fts WHERE memory_id = old.memory_id;
END;

PRAGMA foreign_keys=ON;
