-- Migration 144: business_work_order_artifacts — WO ceremony artifacts in the authority
-- (WO-FILESDB-P1, files-in-database directive 2026-07-07)
--
-- WO close/verify artifacts (api-contract.md, security-scan.md, design-audit.md,
-- review-verdict.json, context.md) were written to .planning/work-orders/<id>/ on
-- disk and read back from there by the close gates. The files-in-database directive
-- moves them into the authority so the ceremony no longer depends on loose files.
--
-- The close/verify gates read DB-or-disk (disk fallback retained during transition),
-- so this table can sit dormant (unreleased) on the live authority DB until the
-- operator runs `ds migrate activate`; fresh installs and CI apply it immediately.

CREATE TABLE IF NOT EXISTS business_work_order_artifacts (
    work_order_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN (
        'api_contract', 'security_scan', 'design_audit', 'review_verdict', 'context'
    )),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (work_order_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_wo_artifacts_wo
    ON business_work_order_artifacts(work_order_id);
