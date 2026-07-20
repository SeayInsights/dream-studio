-- Migration 152: business_work_order_artifacts — add instance_key + extend kinds (WO-FILESDB-C1)
--
-- Foundation for the FILESDB disk->table completion milestone. Rebuilds the artifacts table to:
--   (a) add a nullable-by-default `instance_key` (DEFAULT '') so multi-instance artifacts fit —
--       specifically the ~15 eval stages, stored as kind='eval' + instance_key=<eval_type>; and
--   (b) extend the `kind` CHECK for the artifact types the C2-C5 work orders move off disk
--       (operator_decision, decision_request, escalation, report, eval).
--
-- SQLite cannot ALTER a CHECK constraint or a PRIMARY KEY, so this is a
-- create-copy-drop-rename rebuild. Existing rows migrate with instance_key=''
-- (singletons). Additive: no data lost, no other table touched.
--
-- business_work_order_artifacts is a REAL live table (migration 144), currently unreleased
-- (.released_version 143); this rebuild only affects fresh-install/CI schema until release.

PRAGMA foreign_keys=OFF;

CREATE TABLE business_work_order_artifacts_new (
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

INSERT INTO business_work_order_artifacts_new
    (work_order_id, kind, instance_key, content, created_at, updated_at)
    SELECT work_order_id, kind, '', content, created_at, updated_at
    FROM business_work_order_artifacts;

DROP TABLE business_work_order_artifacts;
ALTER TABLE business_work_order_artifacts_new RENAME TO business_work_order_artifacts;

CREATE INDEX IF NOT EXISTS idx_wo_artifacts_wo
    ON business_work_order_artifacts(work_order_id);

PRAGMA foreign_keys=ON;
