-- Migration 114: Set post_build_gate='independent_review' on cleanup and infrastructure
-- work order types so all subsequent WOs of those types require a passed review-verdict.json
-- before close is permitted.
UPDATE business_work_order_types
SET post_build_gate = 'independent_review'
WHERE type_id IN ('cleanup', 'infrastructure');
