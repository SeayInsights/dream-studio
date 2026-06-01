-- Migration 089: Rename security_scan_runs and security_findings to reflect their
-- actual scope (all-skill data, not security-only).
--
-- Background: security_scan_runs was created in migration 085 for the brownfield
-- security scan pipeline. Migration 087 added skill_id to generalize it to all
-- quality skills (code-quality, testing, types-deps, database). The table now holds
-- scans across all five quality skills keyed by skill_id.
-- security_findings similarly holds findings from all skills via rule_id prefix.
--
-- This rename is cosmetic correctness: the table names should reflect their actual scope.

PRAGMA foreign_keys = OFF;

-- ── 1. Rename primary tables ──────────────────────────────────────────────────
ALTER TABLE security_scan_runs RENAME TO scan_runs;
ALTER TABLE security_findings RENAME TO findings;

-- ── 2. Rename dependent tables that reference these names ─────────────────────
-- security_scan_deltas references security_findings; rename it too
ALTER TABLE security_scan_deltas RENAME TO scan_deltas;

-- ── 3. Re-create indexes with new names (SQLite does not auto-rename indexes) ──
-- Drop old indexes (they still point to the old table names in SQLite's schema)
DROP INDEX IF EXISTS idx_security_findings_project;
DROP INDEX IF EXISTS idx_security_findings_rule;
DROP INDEX IF EXISTS idx_security_findings_hash;
DROP INDEX IF EXISTS idx_security_findings_scan;
DROP INDEX IF EXISTS idx_security_scan_runs_project;
DROP INDEX IF EXISTS idx_security_scan_runs_skill;
DROP INDEX IF EXISTS idx_scan_deltas_scan;

-- Re-create with new table names
CREATE INDEX IF NOT EXISTS idx_findings_project ON findings(project_id, severity, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_findings_rule ON findings(project_id, rule_id, status);
CREATE INDEX IF NOT EXISTS idx_findings_hash ON findings(finding_hash) WHERE finding_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_findings_scan ON findings(scan_id, severity);
CREATE INDEX IF NOT EXISTS idx_scan_runs_project ON scan_runs(project_id, skill_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_runs_skill ON scan_runs(project_id, skill_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_deltas_scan ON scan_deltas(scan_id);

PRAGMA foreign_keys = ON;
