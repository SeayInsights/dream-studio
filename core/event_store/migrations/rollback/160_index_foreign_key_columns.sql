-- Rollback 160: drop the foreign-key column indexes (reverse of 160_index_foreign_key_columns.sql).
-- A reverse migration legitimately drops what its forward created. Only indexes are
-- removed, so no table or row is affected: lookups on these columns simply scan again.

DROP INDEX IF EXISTS idx_ai_usage_operational_records_accounting_profile_id;
DROP INDEX IF EXISTS idx_ai_usage_operational_records_adapter_id;
DROP INDEX IF EXISTS idx_ai_usage_operational_records_milestone_id;
DROP INDEX IF EXISTS idx_ai_usage_operational_records_task_id;
DROP INDEX IF EXISTS idx_ai_usage_operational_records_work_order_id;
DROP INDEX IF EXISTS idx_ds_friction_signals_extension_id;
DROP INDEX IF EXISTS idx_ds_friction_signals_project_id;
DROP INDEX IF EXISTS idx_ds_friction_signals_rule_id;
DROP INDEX IF EXISTS idx_ds_friction_signals_session_id;
DROP INDEX IF EXISTS idx_execution_events_adapter_id;
DROP INDEX IF EXISTS idx_execution_events_milestone_id;
DROP INDEX IF EXISTS idx_execution_events_parent_event_id;
DROP INDEX IF EXISTS idx_execution_events_task_id;
DROP INDEX IF EXISTS idx_guardrail_decisions_event_id;
DROP INDEX IF EXISTS idx_projection_retry_queue_event_id;
DROP INDEX IF EXISTS idx_raw_claude_code_events_adapter_id;
DROP INDEX IF EXISTS idx_readiness_events_work_order_id;
DROP INDEX IF EXISTS idx_research_evidence_records_event_id;
DROP INDEX IF EXISTS idx_research_evidence_records_milestone_id;
DROP INDEX IF EXISTS idx_research_evidence_records_task_id;
DROP INDEX IF EXISTS idx_scan_runs_previous_scan_id;
DROP INDEX IF EXISTS idx_security_events_work_order_id;
DROP INDEX IF EXISTS idx_validation_results_event_id;
DROP INDEX IF EXISTS idx_validation_results_milestone_id;
DROP INDEX IF EXISTS idx_validation_results_task_id;
