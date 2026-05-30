-- Migration 087: Add skill_id to security_scan_runs (generalizing to any quality skill)
--
-- security_scan_runs was created in migration 085 for security scans specifically.
-- Code-quality and other quality skills use the same findings table (security_findings,
-- differentiated by rule_id prefix: sec-* = security, cq-* = code-quality, etc.)
-- and the same scan-run tracking. Adding skill_id lets callers distinguish which
-- skill produced each scan run.
--
-- Default 'security' preserves all existing rows (all prior scans were security).
-- Code-quality scans write 'code-quality'; future skills use their own skill_id.

ALTER TABLE security_scan_runs ADD COLUMN
    skill_id TEXT NOT NULL DEFAULT 'security';

CREATE INDEX IF NOT EXISTS idx_security_scan_runs_skill
ON security_scan_runs(project_id, skill_id, started_at DESC);
