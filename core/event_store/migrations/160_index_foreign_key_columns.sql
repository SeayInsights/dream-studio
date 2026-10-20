-- Migration 160: index every foreign-key column
--
-- WHY. The rule for this schema is that every table has a primary key and every column
-- that points at another table is indexed, so a join or a parent-side delete never scans
-- the child. Every table already had a primary key. 6 declared FOREIGN KEY columns and 19
-- more that name another table's key (milestone_id, task_id, adapter_id, session_id,
-- event_id, work_order_id and so on) had no index that leads with them. The convention
-- columns are not declared as FOREIGN KEYs, and SQLite cannot add that constraint without
-- rebuilding the table. An index does not depend on the parent table, so it can be added
-- safely now, including for the columns that point at more than one table.
--
-- SHAPE. A nullable column gets a PARTIAL index (WHERE col IS NOT NULL). On the live
-- database every one of these columns is entirely NULL (102,136 execution_events rows have
-- none of them set, and 606,239 of 606,240 raw_claude_code_events rows have no adapter_id),
-- so a full index would be written for nothing. SQLite uses a partial index for any lookup
-- of the form col = ?, which is what a join or a foreign-key check issues. A NOT NULL
-- column gets an ordinary index.
--
-- ADDITIVE ONLY. 25 CREATE INDEX IF NOT EXISTS statements, no table is rebuilt and no data
-- is touched, so this is safe to re-run. The paired rollback drops exactly these indexes.
-- tests/unit/test_schema_keys_and_foreign_key_indexes.py fails when a table lacks a primary
-- key or a foreign-key column lacks an index, so the next one is caught when it is added.

CREATE INDEX IF NOT EXISTS idx_ai_usage_operational_records_accounting_profile_id ON ai_usage_operational_records(accounting_profile_id) WHERE accounting_profile_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ai_usage_operational_records_adapter_id ON ai_usage_operational_records(adapter_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_operational_records_milestone_id ON ai_usage_operational_records(milestone_id) WHERE milestone_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ai_usage_operational_records_task_id ON ai_usage_operational_records(task_id) WHERE task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ai_usage_operational_records_work_order_id ON ai_usage_operational_records(work_order_id) WHERE work_order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ds_friction_signals_extension_id ON ds_friction_signals(extension_id) WHERE extension_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ds_friction_signals_project_id ON ds_friction_signals(project_id) WHERE project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ds_friction_signals_rule_id ON ds_friction_signals(rule_id) WHERE rule_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ds_friction_signals_session_id ON ds_friction_signals(session_id) WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_execution_events_adapter_id ON execution_events(adapter_id) WHERE adapter_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_execution_events_milestone_id ON execution_events(milestone_id) WHERE milestone_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_execution_events_parent_event_id ON execution_events(parent_event_id) WHERE parent_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_execution_events_task_id ON execution_events(task_id) WHERE task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_guardrail_decisions_event_id ON guardrail_decisions(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_projection_retry_queue_event_id ON projection_retry_queue(event_id);
CREATE INDEX IF NOT EXISTS idx_raw_claude_code_events_adapter_id ON raw_claude_code_events(adapter_id) WHERE adapter_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_readiness_events_work_order_id ON readiness_events(work_order_id) WHERE work_order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_research_evidence_records_event_id ON research_evidence_records(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_research_evidence_records_milestone_id ON research_evidence_records(milestone_id) WHERE milestone_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_research_evidence_records_task_id ON research_evidence_records(task_id) WHERE task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_scan_runs_previous_scan_id ON scan_runs(previous_scan_id) WHERE previous_scan_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_security_events_work_order_id ON security_events(work_order_id) WHERE work_order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_validation_results_event_id ON validation_results(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_validation_results_milestone_id ON validation_results(milestone_id) WHERE milestone_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_validation_results_task_id ON validation_results(task_id) WHERE task_id IS NOT NULL;
