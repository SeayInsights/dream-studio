-- Migration 037: Execution telemetry traceability spine
-- Adds local-first execution telemetry, module registry, attribution facts,
-- dashboard attention, and authority projection records.

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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (parent_event_id) REFERENCES execution_events(event_id)
);

CREATE TABLE IF NOT EXISTS process_runs (
    process_run_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    run_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT,
    route_id TEXT,
    summary TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS telemetry_module_registry (
    module_id TEXT PRIMARY KEY,
    module_name TEXT NOT NULL,
    module_type TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    execution_mode TEXT NOT NULL DEFAULT 'local',
    docker_profile TEXT,
    owns_tables_json TEXT NOT NULL DEFAULT '[]',
    emits_event_types_json TEXT NOT NULL DEFAULT '[]',
    dashboard_cards_json TEXT NOT NULL DEFAULT '[]',
    health_status TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS telemetry_entity_registry (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    canonical_key TEXT NOT NULL,
    module_id TEXT,
    project_scope TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (module_id) REFERENCES telemetry_module_registry(module_id)
);

CREATE TABLE IF NOT EXISTS agent_invocations (
    invocation_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    purpose TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
);

CREATE TABLE IF NOT EXISTS skill_invocations (
    invocation_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    skill_id TEXT NOT NULL,
    status TEXT NOT NULL,
    purpose TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
);

CREATE TABLE IF NOT EXISTS workflow_invocations (
    invocation_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    workflow_id TEXT NOT NULL,
    status TEXT NOT NULL,
    purpose TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
);

CREATE TABLE IF NOT EXISTS hook_invocations (
    invocation_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    hook_id TEXT NOT NULL,
    status TEXT NOT NULL,
    prevented_risky_action INTEGER NOT NULL DEFAULT 0,
    purpose TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
);

CREATE TABLE IF NOT EXISTS tool_invocations (
    invocation_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    tool_id TEXT NOT NULL,
    status TEXT NOT NULL,
    purpose TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
);

CREATE TABLE IF NOT EXISTS token_usage_records (
    token_usage_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    agent_id TEXT,
    skill_id TEXT,
    workflow_id TEXT,
    hook_id TEXT,
    model_id TEXT,
    provider TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost REAL NOT NULL DEFAULT 0,  -- db-005-suppress: original REAL type; corrected to NUMERIC(20,8) in migration 081
    purpose TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS security_findings (
    finding_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    scan_id TEXT,
    process_run_id TEXT,
    severity TEXT NOT NULL,
    category TEXT,
    rule_id TEXT,
    file_path TEXT,
    start_line INTEGER,
    end_line INTEGER,
    description TEXT NOT NULL,
    recommendation TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    introduced_by_agent_id TEXT,
    introduced_by_skill_id TEXT,
    introduced_by_workflow_id TEXT,
    introduced_by_hook_id TEXT,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS decision_records (
    decision_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    decision_type TEXT NOT NULL,
    decision_status TEXT NOT NULL,
    selected_option TEXT,
    rationale TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
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

CREATE TABLE IF NOT EXISTS blocker_resolution_records (
    blocker_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    blocker_class TEXT NOT NULL,
    route_class TEXT NOT NULL,
    confidence TEXT NOT NULL,
    resolution_status TEXT NOT NULL,
    prompt_required INTEGER NOT NULL DEFAULT 0,
    dashboard_approval_required INTEGER NOT NULL DEFAULT 0,
    rationale TEXT,
    research_refs_json TEXT NOT NULL DEFAULT '[]',
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

CREATE TABLE IF NOT EXISTS artifact_records (
    artifact_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    artifact_path TEXT NOT NULL,
    artifact_role TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL,
    source_authority TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
);

CREATE TABLE IF NOT EXISTS outcome_records (
    outcome_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    outcome_type TEXT NOT NULL,
    outcome_status TEXT NOT NULL,
    summary TEXT,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
);

CREATE TABLE IF NOT EXISTS route_decision_records (
    route_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    route_decision TEXT NOT NULL,
    handoff_required INTEGER NOT NULL DEFAULT 0,
    operator_action_required INTEGER NOT NULL DEFAULT 0,
    prompt_required INTEGER NOT NULL DEFAULT 0,
    next_stage_gate TEXT,
    next_milestone TEXT,
    recommended_next_work_order TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
);

CREATE TABLE IF NOT EXISTS dashboard_attention_items (
    attention_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    attention_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    action_required INTEGER NOT NULL DEFAULT 0,
    operator_action_required INTEGER NOT NULL DEFAULT 0,
    prompt_required INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
);

CREATE TABLE IF NOT EXISTS authority_projection_records (
    projection_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    event_id TEXT,
    projection_domain TEXT NOT NULL,
    source_authority TEXT NOT NULL,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    lifecycle_status TEXT NOT NULL,
    authority_role TEXT NOT NULL,
    derived_fields_json TEXT NOT NULL DEFAULT '{}',
    confidence TEXT NOT NULL DEFAULT 'unknown',
    stale_superseded_json TEXT NOT NULL DEFAULT '{}',
    stop_gate_implications_json TEXT NOT NULL DEFAULT '[]',
    validation_requirements_json TEXT NOT NULL DEFAULT '[]',
    dashboard_readiness_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (event_id) REFERENCES execution_events(event_id)
);

CREATE INDEX IF NOT EXISTS idx_execution_events_scope ON execution_events(project_id, milestone_id, task_id);
CREATE INDEX IF NOT EXISTS idx_execution_events_process ON execution_events(process_run_id);
CREATE INDEX IF NOT EXISTS idx_process_runs_scope ON process_runs(project_id, milestone_id, task_id);
CREATE INDEX IF NOT EXISTS idx_modules_type_enabled ON telemetry_module_registry(module_type, enabled);
CREATE INDEX IF NOT EXISTS idx_entities_module ON telemetry_entity_registry(module_id);
CREATE INDEX IF NOT EXISTS idx_agent_invocations_scope ON agent_invocations(project_id, milestone_id, task_id, agent_id);
CREATE INDEX IF NOT EXISTS idx_skill_invocations_scope ON skill_invocations(project_id, milestone_id, task_id, skill_id);
CREATE INDEX IF NOT EXISTS idx_workflow_invocations_scope ON workflow_invocations(project_id, milestone_id, task_id, workflow_id);
CREATE INDEX IF NOT EXISTS idx_hook_invocations_scope ON hook_invocations(project_id, milestone_id, task_id, hook_id);
CREATE INDEX IF NOT EXISTS idx_tool_invocations_scope ON tool_invocations(project_id, milestone_id, task_id, tool_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_scope ON token_usage_records(project_id, milestone_id, task_id, agent_id, skill_id, workflow_id, hook_id, model_id);
CREATE INDEX IF NOT EXISTS idx_security_findings_scope ON security_findings(project_id, milestone_id, task_id, severity);
CREATE INDEX IF NOT EXISTS idx_security_findings_file ON security_findings(project_id, file_path, severity);
CREATE INDEX IF NOT EXISTS idx_decision_records_scope ON decision_records(project_id, milestone_id, task_id);
CREATE INDEX IF NOT EXISTS idx_research_records_scope ON research_evidence_records(project_id, milestone_id, task_id);
CREATE INDEX IF NOT EXISTS idx_blocker_records_scope ON blocker_resolution_records(project_id, milestone_id, task_id, route_class);
CREATE INDEX IF NOT EXISTS idx_validation_results_scope ON validation_results(project_id, milestone_id, task_id, status);
CREATE INDEX IF NOT EXISTS idx_artifact_records_scope ON artifact_records(project_id, milestone_id, task_id, lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_outcome_records_scope ON outcome_records(project_id, milestone_id, task_id, outcome_status);
CREATE INDEX IF NOT EXISTS idx_route_records_scope ON route_decision_records(project_id, milestone_id, task_id, route_decision);
CREATE INDEX IF NOT EXISTS idx_attention_items_scope ON dashboard_attention_items(project_id, milestone_id, task_id, status);
CREATE INDEX IF NOT EXISTS idx_authority_projection_scope ON authority_projection_records(project_id, milestone_id, task_id, projection_domain);
