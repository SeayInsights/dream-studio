-- Migration: Analytics Views
-- Created: 2026-05-06
-- Track B Phase 2: SQL Views Creation
-- Purpose: Create view layer for analytics package (zero Python aggregation)

-- View 1: Security Summary (unified findings from multiple sources)
-- TB-005: Implemented - combines SARIF, CVE, manual reviews, and hook checks
DROP VIEW IF EXISTS vw_security_summary;
CREATE VIEW vw_security_summary AS

-- SARIF findings (static analysis results)
SELECT
    'sarif' AS source_type,
    CAST(sarif_finding_id AS TEXT) AS finding_id,
    scan_tool AS tool,
    severity,
    file_path,
    line_number,
    message,
    status,
    created_at
FROM sec_sarif_findings

UNION ALL

-- CVE matches (dependency vulnerabilities)
SELECT
    'cve' AS source_type,
    CAST(cve_match_id AS TEXT) AS finding_id,
    'CVE Scanner' AS tool,
    severity,
    package_name AS file_path,
    NULL AS line_number,
    description AS message,
    status,
    created_at
FROM sec_cve_matches

UNION ALL

-- Manual security reviews
SELECT
    'manual' AS source_type,
    CAST(review_id AS TEXT) AS finding_id,
    'Manual Review' AS tool,
    risk_level AS severity,
    NULL AS file_path,
    NULL AS line_number,
    findings AS message,
    status,
    created_at
FROM sec_manual_reviews

UNION ALL

-- Hook-based security checks
SELECT
    'hook_check' AS source_type,
    CAST(hook_check_id AS TEXT) AS finding_id,
    check_type AS tool,
    CASE check_result
        WHEN 'failed' THEN 'error'
        WHEN 'warning' THEN 'warning'
        ELSE 'info'
    END AS severity,
    NULL AS file_path,
    NULL AS line_number,
    details AS message,
    check_result AS status,
    created_at
FROM sec_hook_checks

ORDER BY created_at DESC;

-- View 2: Activity Timeline (chronological event feed)
-- TB-006: Implemented - chronological feed of all activity events
DROP VIEW IF EXISTS vw_activity_timeline;
CREATE VIEW vw_activity_timeline AS
SELECT
    activity_id,
    activity_type,
    event_timestamp,
    severity,
    stream_type,
    stream_id,
    json_extract(event_data, '$.summary') AS summary
FROM activity_log
ORDER BY event_timestamp DESC;

-- View 3: Risk Hotspots (files with most findings)
-- TB-007: Implemented - aggregates open findings by file path
DROP VIEW IF EXISTS vw_risk_hotspots;
CREATE VIEW vw_risk_hotspots AS
SELECT
    file_path,
    COUNT(*) AS finding_count,
    MAX(severity) AS max_severity,
    GROUP_CONCAT(DISTINCT scan_tool) AS tools
FROM sec_sarif_findings
WHERE status = 'open'
  AND file_path IS NOT NULL
GROUP BY file_path
HAVING finding_count >= 3
ORDER BY finding_count DESC;

-- View 4: Hook Performance (execution stats)
-- TB-008: Implemented - aggregates hook execution metrics
DROP VIEW IF EXISTS vw_hook_performance;
CREATE VIEW vw_hook_performance AS
SELECT
    hook_name,
    COUNT(*) AS execution_count,
    AVG(duration_ms) AS avg_duration_ms,
    MAX(duration_ms) AS max_duration_ms,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failure_count
FROM hook_executions
GROUP BY hook_name
ORDER BY avg_duration_ms DESC;

-- View 5: Guardrail Decisions (block/allow history)
-- TB-008: Implemented - guardrail enforcement audit trail
DROP VIEW IF EXISTS vw_guardrail_decisions;
CREATE VIEW vw_guardrail_decisions AS
SELECT
    gd.decision_id,
    gd.rule_id,
    gd.decision,
    gd.event_id,
    al.activity_type,
    al.event_timestamp,
    gd.reason
FROM guardrail_decisions gd
JOIN activity_log al ON gd.event_id = al.activity_id
ORDER BY al.event_timestamp DESC;
