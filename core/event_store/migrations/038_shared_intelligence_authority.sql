-- Migration 038: Shared intelligence SQLite authority foundation
-- Adds canonical structured records for artifacts, learning, adapters,
-- model/provider profiles, context packets, normalized adapter results, and
-- capability routing. Files remain human-readable exports unless a record here
-- explicitly marks them as authority exports.

CREATE TABLE IF NOT EXISTS artifact_authority_records (
    record_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    source_path TEXT,
    source_hash TEXT,
    authority_status TEXT NOT NULL DEFAULT 'canonical',
    file_is_export INTEGER NOT NULL DEFAULT 1,
    human_export_path TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    supersedes_record_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (record_type IN (
        'work_order',
        'handoff',
        'continuation_packet',
        'evidence_summary',
        'report',
        'route_decision',
        'release_packet',
        'cleanup_cutover_record',
        'operator_decision',
        'other'
    )),
    CHECK (authority_status IN ('canonical', 'superseded', 'draft', 'export_only', 'rejected')),
    FOREIGN KEY (supersedes_record_id) REFERENCES artifact_authority_records(record_id)
);

CREATE TABLE IF NOT EXISTS learning_event_records (
    learning_event_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    component_type TEXT,
    component_id TEXT,
    event_class TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    summary TEXT NOT NULL,
    observed_pattern TEXT,
    root_cause TEXT,
    remediation_hint TEXT,
    recurrence_key TEXT,
    promotion_status TEXT NOT NULL DEFAULT 'observed',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (event_class IN (
        'skill_gap',
        'workflow_gap',
        'hook_gap',
        'workaround',
        'failed_assumption',
        'operator_correction',
        'validation_failure',
        'route_mistake',
        'successful_hardening',
        'adapter_gap',
        'model_provider_gap',
        'other'
    )),
    CHECK (promotion_status IN (
        'observed',
        'candidate',
        'promoted_to_rule',
        'promoted_to_skill',
        'promoted_to_workflow',
        'promoted_to_hook',
        'promoted_to_adapter_policy',
        'dashboard_attention',
        'operator_approval_required',
        'rejected'
    ))
);

CREATE TABLE IF NOT EXISTS hardening_candidate_records (
    candidate_id TEXT PRIMARY KEY,
    learning_event_id TEXT,
    component_type TEXT NOT NULL,
    component_id TEXT NOT NULL,
    current_version TEXT,
    proposed_version TEXT,
    hardening_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    validation_plan_json TEXT NOT NULL DEFAULT '[]',
    recurrence_check_json TEXT NOT NULL DEFAULT '{}',
    rollback_plan TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (component_type IN ('skill', 'workflow', 'hook', 'adapter', 'model_provider', 'tool', 'agent', 'other')),
    CHECK (status IN ('candidate', 'approved_for_rehearsal', 'validated', 'promoted', 'rejected', 'deferred')),
    FOREIGN KEY (learning_event_id) REFERENCES learning_event_records(learning_event_id)
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

CREATE TABLE IF NOT EXISTS model_provider_profiles (
    model_profile_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    capability_tags_json TEXT NOT NULL DEFAULT '[]',
    context_limit_tokens INTEGER,
    cost_profile_json TEXT NOT NULL DEFAULT '{}',
    token_behavior_json TEXT NOT NULL DEFAULT '{}',
    output_quality_json TEXT NOT NULL DEFAULT '{}',
    failure_modes_json TEXT NOT NULL DEFAULT '[]',
    best_use_patterns_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (provider, model_id)
);

CREATE TABLE IF NOT EXISTS shared_context_packets (
    packet_id TEXT PRIMARY KEY,
    adapter_id TEXT NOT NULL,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    packet_type TEXT NOT NULL,
    packet_status TEXT NOT NULL DEFAULT 'generated',
    source_authority TEXT NOT NULL DEFAULT 'sqlite',
    model_private_memory_required INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (packet_status IN ('generated', 'used', 'superseded', 'rejected')),
    CHECK (model_private_memory_required = 0),
    FOREIGN KEY (adapter_id) REFERENCES adapter_authority_profiles(adapter_id)
);

CREATE TABLE IF NOT EXISTS adapter_result_records (
    result_id TEXT PRIMARY KEY,
    adapter_id TEXT NOT NULL,
    packet_id TEXT,
    project_id TEXT,
    milestone_id TEXT,
    task_id TEXT,
    process_run_id TEXT,
    result_type TEXT NOT NULL,
    normalized_status TEXT NOT NULL,
    decision_refs_json TEXT NOT NULL DEFAULT '[]',
    code_change_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    validation_refs_json TEXT NOT NULL DEFAULT '[]',
    research_refs_json TEXT NOT NULL DEFAULT '[]',
    risk_refs_json TEXT NOT NULL DEFAULT '[]',
    artifact_refs_json TEXT NOT NULL DEFAULT '[]',
    outcome_refs_json TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (adapter_id) REFERENCES adapter_authority_profiles(adapter_id),
    FOREIGN KEY (packet_id) REFERENCES shared_context_packets(packet_id)
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

CREATE INDEX IF NOT EXISTS idx_artifact_authority_scope ON artifact_authority_records(project_id, milestone_id, task_id, record_type);
CREATE INDEX IF NOT EXISTS idx_learning_events_component ON learning_event_records(component_type, component_id, event_class);
CREATE INDEX IF NOT EXISTS idx_learning_events_scope ON learning_event_records(project_id, milestone_id, task_id);
CREATE INDEX IF NOT EXISTS idx_hardening_component ON hardening_candidate_records(component_type, component_id, status);
CREATE INDEX IF NOT EXISTS idx_context_packets_adapter ON shared_context_packets(adapter_id, project_id, milestone_id, task_id);
CREATE INDEX IF NOT EXISTS idx_adapter_results_scope ON adapter_result_records(adapter_id, project_id, milestone_id, task_id, result_type);
CREATE INDEX IF NOT EXISTS idx_capability_routes_scope ON capability_route_records(project_id, milestone_id, task_id, task_class);
