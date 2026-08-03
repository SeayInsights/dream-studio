-- Migration 154: business_work_order_artifacts — register the impact_affirmation kind (R5)
--
-- R5 stores the change-impact affirmation as a WO ceremony artifact
-- (kind='impact_affirmation'): an explicit record of which impact classes
-- (auth/contract/migration/changelog) a change touches, required by the
-- change_impact_affirmed universal close gate. SQLite cannot ALTER a CHECK
-- constraint, so this is the standard create-copy-drop-rename rebuild that extends
-- the kind allowlist (mirrors migration 152). Additive: no data lost, no other table
-- touched. business_work_order_artifacts is release-guarded (.released_version 153),
-- so this only affects fresh-install/CI schema until release.

PRAGMA foreign_keys=OFF;

CREATE TABLE business_work_order_artifacts_m154 (
    work_order_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN (
        'api_contract', 'security_scan', 'design_audit', 'review_verdict', 'context',
        'operator_decision', 'decision_request', 'escalation', 'report', 'eval',
        'impact_affirmation'
    )),
    instance_key TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (work_order_id, kind, instance_key)
);

INSERT INTO business_work_order_artifacts_m154
    (work_order_id, kind, instance_key, content, created_at, updated_at)
    SELECT work_order_id, kind, instance_key, content, created_at, updated_at
    FROM business_work_order_artifacts;

DROP TABLE business_work_order_artifacts;
ALTER TABLE business_work_order_artifacts_m154 RENAME TO business_work_order_artifacts;

CREATE INDEX IF NOT EXISTS idx_wo_artifacts_wo
    ON business_work_order_artifacts(work_order_id);

PRAGMA foreign_keys=ON;
