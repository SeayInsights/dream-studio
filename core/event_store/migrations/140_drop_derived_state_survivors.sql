-- Migration 140: Drop derived-state SQLite survivors (WO dff23cb0)
--
-- findings_current_status (security_events status projection) and
-- sum_skill_summary (raw_skill_telemetry rollup) are both pure derived
-- state — every column is reconstructable from their source tables. Retire
-- the persisted copies; compute the same aggregations at read time instead
-- (see core/findings/current_status.py::FINDINGS_CURRENT_STATUS_SQL and
-- core/event_store/studio_db.py::get_skill_summaries).
--
-- findings_current_status:
--   * 15 rows (operator authority, verified 2026-07-04), pure fold_spine()
--     upsert output over security_events (finding.recorded /
--     finding.status_changed / finding.resolved). FindingsProjection
--     (core/projections/findings_projection.py) was the sole writer;
--     deleted. Every reader across core/security/lifecycle.py,
--     core/analytics/aggregate_metrics.py, core/projects/{delta,intake}.py,
--     projections/scoring/engine.py, projections/api/routes/{project_detail,
--     project_list,project_security,security}.py,
--     projections/api/lib/{project_helpers,security_helpers}.py, and
--     core/telemetry/{read_models,execution_spine,dashboard_freshness}.py
--     repointed to derive current_status from security_events at read time.
--   * vw_security_summary (migration 112) is a live SQLite VIEW that read
--     FROM findings_current_status — rebuilt below to read directly from
--     security_events using the identical status-derivation logic (latest
--     finding.status_changed / finding.resolved event body per finding,
--     else 'open').
--   * No FOREIGN KEY references findings_current_status from any other table.
--
-- sum_skill_summary:
--   * 2 rows (operator authority, verified 2026-07-04), pure rebuild_summaries()
--     rollup over raw_skill_telemetry (via the effective_skill_runs view).
--     rebuild_summaries() was the sole writer; deleted.
--     get_skill_summaries() now computes the identical aggregation live.
--   * No FOREIGN KEY, no VIEW references sum_skill_summary.
--
-- Evidence this is safely droppable (operator duplication review, 2026-07-04,
-- operator-approved pre-squash removal):
--   * grepped core/event_store/migrations/ for "REFERENCES findings_current_status("
--     and "REFERENCES sum_skill_summary(" — no hits.
--   * grepped for CREATE VIEW bodies referencing either table — only
--     vw_security_summary (migration 112) touches findings_current_status;
--     rebuilt below over security_events directly. No view touches
--     sum_skill_summary.
--
-- Result: 62 - 2 = 60 tables (fresh bootstrap_database() count of
-- sqlite_master tables excluding sqlite_%, measured 2026-07-04).
-- Reviewed: 2026-07-04 (WO dff23cb0-950f-4607-bb30-e1a353a6f8ba)

DROP VIEW IF EXISTS vw_security_summary;

DROP INDEX IF EXISTS idx_findings_current_status_project;
DROP INDEX IF EXISTS idx_findings_current_status_severity;
DROP TABLE IF EXISTS findings_current_status;

DROP TABLE IF EXISTS sum_skill_summary;

-- Rebuild vw_security_summary over security_events directly (same shape as
-- migration 112's version, minus the findings_current_status intermediary).
-- current_status derivation matches FindingsProjection.fold_spine() exactly:
-- the latest finding.status_changed / finding.resolved event body for a
-- finding (split on ':', trimmed), else 'open'.
CREATE VIEW IF NOT EXISTS vw_security_summary AS
SELECT
    'spine' AS source_type,
    r.event_id AS finding_id,
    COALESCE(r.scanner_type, 'unknown') AS tool,
    r.severity,
    r.file_path,
    r.line_number,
    r.title AS message,
    CASE
        WHEN ls.body IS NULL THEN 'open'
        ELSE TRIM(
            CASE WHEN INSTR(ls.body, ':') > 0
                 THEN SUBSTR(ls.body, 1, INSTR(ls.body, ':') - 1)
                 ELSE ls.body
            END
        )
    END AS status,
    r.created_at
FROM (
    SELECT * FROM security_events WHERE event_kind = 'finding.recorded'
) r
LEFT JOIN (
    SELECT parent_event_id, body, event_id, created_at,
           ROW_NUMBER() OVER (
               PARTITION BY parent_event_id ORDER BY created_at DESC, event_id DESC
           ) AS rn
    FROM security_events
    WHERE event_kind IN ('finding.status_changed', 'finding.resolved')
) ls ON ls.parent_event_id = r.event_id AND ls.rn = 1
ORDER BY r.created_at DESC;
