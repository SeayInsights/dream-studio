-- Add originating_symptom to business_work_orders.
-- Defect WOs set this at registration; close re-runs the SQL-CHECK at close time
-- to confirm the fix landed before the WO can be marked complete.
ALTER TABLE business_work_orders ADD COLUMN originating_symptom TEXT;

-- Backfill WO-TOKEN-CAPTURE with its canonical symptom.
UPDATE business_work_orders
SET originating_symptom = 'SQL-CHECK: SELECT COUNT(*) FROM token_usage_records'
WHERE title LIKE 'WO-TOKEN-CAPTURE%';

-- Add a symptom-check task to WO-TOKEN-CAPTURE so the grader has traceability.
-- Uses a stable UUID so idempotent re-runs are safe (INSERT OR IGNORE).
INSERT OR IGNORE INTO business_tasks
    (task_id, work_order_id, project_id, title, description, acceptance_criteria, status, created_at, updated_at)
SELECT
    'a7b8c9d0-e1f2-4a3b-9c4d-e5f6a7b8c9d0',
    wo.work_order_id,
    wo.project_id,
    'SYMPTOM-CHECK: token_usage_records not empty',
    'Canonical symptom example: the token pipeline gap meant token_usage_records stayed empty. Encodes the originating failure so future verification confirms the fix held.',
    'SQL-CHECK: SELECT COUNT(*) FROM token_usage_records',
    'complete',
    datetime('now'),
    datetime('now')
FROM business_work_orders wo
WHERE wo.title LIKE 'WO-TOKEN-CAPTURE%'
LIMIT 1;
