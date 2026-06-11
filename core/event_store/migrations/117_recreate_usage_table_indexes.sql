-- Migration 117: Recreate the usage-table indexes migration 081 dropped.
--
-- Background (issue #264, found during WO-DEBT-I, executed under WO-IDX-RECREATE):
--   Migration 081 rebuilt token_usage_records and ai_usage_operational_records
--   via the table-reconstruction pattern (CREATE _new + INSERT...SELECT + DROP +
--   RENAME) to convert REAL cost columns to NUMERIC(20,8). DROP TABLE removed
--   the tables' indexes, and 081 recreated only the views — not the indexes.
--   Every DB at schema version >= 81 is therefore missing:
--     - idx_token_usage_scope            (created by migration 037)
--     - idx_ai_usage_operational_scope   (created by migration 043)
--     - idx_ai_usage_operational_process (created by migration 043)
--   Not a swallow-handler casualty: the DROP legitimately removed them and no
--   later statement attempted recreation.
--
-- DDL below matches the original definitions from migrations 037 and 043
-- verbatim. IF NOT EXISTS keeps this a no-op on any DB that somehow has them
-- (e.g. a pre-081 DB that never ran the reconstruction).

CREATE INDEX IF NOT EXISTS idx_token_usage_scope
ON token_usage_records(project_id, milestone_id, task_id, agent_id, skill_id, workflow_id, hook_id, model_id);

CREATE INDEX IF NOT EXISTS idx_ai_usage_operational_scope
ON ai_usage_operational_records(project_id, milestone_id, task_id, work_order_id, adapter_id);

CREATE INDEX IF NOT EXISTS idx_ai_usage_operational_process
ON ai_usage_operational_records(process_run_id, adapter_id, model_id);
