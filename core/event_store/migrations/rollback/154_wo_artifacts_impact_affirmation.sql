-- Rollback of migration 154: restore the pre-154 artifact-kind allowlist.
--
-- Reverses 154 by rebuilding business_work_order_artifacts with the original CHECK
-- (without 'impact_affirmation'). Any impact-affirmation rows are dropped by the rebuild
-- (they cannot exist under the restored CHECK) — impact affirmations are advisory ceremony
-- records, not authority, so losing them on a rollback is acceptable. Additive-safe: no
-- other table is touched. Mirror of 154 with the extended kind removed.

PRAGMA foreign_keys=OFF;

CREATE TABLE business_work_order_artifacts_r154 (
    work_order_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN (
        'api_contract', 'security_scan', 'design_audit', 'review_verdict', 'context',
        'operator_decision', 'decision_request', 'escalation', 'report', 'eval'
    )),
    instance_key TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (work_order_id, kind, instance_key)
);

INSERT INTO business_work_order_artifacts_r154
    (work_order_id, kind, instance_key, content, created_at, updated_at)
    SELECT work_order_id, kind, instance_key, content, created_at, updated_at
    FROM business_work_order_artifacts
    WHERE kind <> 'impact_affirmation';

DROP TABLE business_work_order_artifacts;
ALTER TABLE business_work_order_artifacts_r154 RENAME TO business_work_order_artifacts;

CREATE INDEX IF NOT EXISTS idx_wo_artifacts_wo
    ON business_work_order_artifacts(work_order_id);

PRAGMA foreign_keys=ON;
