-- Migration 134: business_work_orders verification columns (WO-DBA-EVAL-DECISION T1)
--
-- Target architecture: verification verdicts attach to the business entity they
-- certify instead of living only in the ds_eval_runs side table + the
-- review-verdict.json file. The columns carry the SUMMARY (status/score/when);
-- the full grader detail stays in the work_order.verified canonical event
-- (emitted by core/work_orders/verify.py from migration 135 onward).
--
-- verify_status: 'passed' | 'failed' | 'unreviewable' | NULL (never verified)
-- verify_score:  composite score 0.0-1.0 from the independent review
-- verified_at:   ISO-8601 UTC timestamp of the most recent verification

ALTER TABLE business_work_orders ADD COLUMN verify_status TEXT;
ALTER TABLE business_work_orders ADD COLUMN verify_score REAL;
ALTER TABLE business_work_orders ADD COLUMN verified_at TEXT;
