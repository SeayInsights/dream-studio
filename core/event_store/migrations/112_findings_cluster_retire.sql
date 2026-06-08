-- Migration 112: Migrate findings cluster → security_events spine; drop retired tables.
--
-- Precondition: migration 111 created security_events + readiness_events + findings_current_status.
--
-- Live-data migrations:
--   findings              (15 rows) → security_events as finding.recorded events
--   resolved_finding_links (2 rows) → security_events as finding.resolved events
--
-- Empty drops (no data loss):
--   sec_sarif_findings, sec_cve_matches, sec_manual_reviews
--   scan_deltas, resolved_finding_links, findings
--   production_readiness_assessment_runs, production_readiness_control_results
--   production_readiness_findings, production_readiness_remediation_work_orders
--   production_readiness_skill_control_mappings
--
-- vw_security_summary is rebuilt to read from security_events + findings_current_status.

PRAGMA foreign_keys = ON;

-- ── 1. Migrate findings → security_events ────────────────────────────────────

INSERT OR IGNORE INTO security_events (
    event_id, parent_event_id, event_kind, correlation_id,
    project_id, work_order_id, scanner_type,
    cwe_id, owasp_category, cve_id,
    file_path, line_number, vuln_class, exploitability,
    severity, title, body, created_at
)
SELECT
    finding_id,                            -- preserve original ID
    NULL,                                  -- no parent (root finding events)
    'finding.recorded',
    process_run_id,                        -- correlation_id ← process_run_id
    project_id,
    NULL,                                  -- work_order_id not on findings
    NULL,                                  -- scanner_type not on findings
    NULL,                                  -- cwe_id not on findings
    NULL,                                  -- owasp_category not on findings
    NULL,                                  -- cve_id not on findings
    file_path,
    start_line,
    category,                              -- vuln_class ← category
    severity,                              -- exploitability ← severity (best approximation)
    severity,
    description,                           -- title ← description (first 200 chars max)
    CASE WHEN recommendation IS NOT NULL
         THEN recommendation ELSE NULL END,
    created_at
FROM findings;

-- ── 2. Migrate resolved_finding_links → security_events as finding.resolved events

INSERT OR IGNORE INTO security_events (
    event_id, parent_event_id, event_kind, correlation_id,
    project_id, body, created_at
)
SELECT
    link_id,
    prev_finding_id,                       -- parent_event_id points to the original finding
    'finding.resolved',
    NULL,
    project_id,
    verdict,                               -- body carries the verdict ('same_edited', etc.)
    adjudicated_at                         -- created_at in security_events ← adjudicated_at
FROM resolved_finding_links;

-- ── 3. Rebuild findings_current_status from migrated spine rows ───────────────
-- (FindingsProjection.fold_spine() handles ongoing updates; this seeds it once.)

INSERT OR REPLACE INTO findings_current_status (
    finding_id, project_id, work_order_id, severity, title,
    file_path, line_number, scanner_type,
    current_status, last_status_event_id, created_at, updated_at
)
SELECT
    se.event_id,
    se.project_id,
    se.work_order_id,
    se.severity,
    se.title,
    se.file_path,
    se.line_number,
    se.scanner_type,
    COALESCE((
        SELECT CASE
            WHEN s2.event_kind = 'finding.resolved' THEN 'resolved'
            ELSE COALESCE(s2.body, 'open')
        END
        FROM security_events s2
        WHERE s2.parent_event_id = se.event_id
          AND s2.event_kind IN ('finding.status_changed', 'finding.resolved')
        ORDER BY s2.created_at DESC
        LIMIT 1
    ), 'open'),
    (
        SELECT s2.event_id
        FROM security_events s2
        WHERE s2.parent_event_id = se.event_id
          AND s2.event_kind IN ('finding.status_changed', 'finding.resolved')
        ORDER BY s2.created_at DESC
        LIMIT 1
    ),
    se.created_at,
    se.created_at
FROM security_events se
WHERE se.event_kind = 'finding.recorded';

-- ── 4. Drop the vw_security_summary that references retired tables ─────────────

DROP VIEW IF EXISTS vw_security_summary;

-- ── 5. Drop retired empty tables ──────────────────────────────────────────────

DROP TABLE IF EXISTS sec_sarif_findings;
DROP TABLE IF EXISTS sec_cve_matches;
DROP TABLE IF EXISTS sec_manual_reviews;
DROP TABLE IF EXISTS scan_deltas;
DROP TABLE IF EXISTS resolved_finding_links;

-- Drop production_readiness cluster (all empty)
DROP TABLE IF EXISTS production_readiness_skill_control_mappings;
DROP TABLE IF EXISTS production_readiness_remediation_work_orders;
DROP TABLE IF EXISTS production_readiness_findings;
DROP TABLE IF EXISTS production_readiness_control_results;
DROP TABLE IF EXISTS production_readiness_assessment_runs;

-- Drop findings last (FK source for resolved_finding_links already dropped above)
DROP TABLE IF EXISTS findings;

-- ── 6. Rebuild vw_security_summary over the new spine ────────────────────────

CREATE VIEW IF NOT EXISTS vw_security_summary AS
SELECT
    'spine' AS source_type,
    fcs.finding_id,
    COALESCE(fcs.scanner_type, 'unknown') AS tool,
    fcs.severity,
    fcs.file_path,
    fcs.line_number,
    (SELECT se.title FROM security_events se WHERE se.event_id = fcs.finding_id) AS message,
    fcs.current_status AS status,
    fcs.created_at
FROM findings_current_status fcs
ORDER BY fcs.created_at DESC;
