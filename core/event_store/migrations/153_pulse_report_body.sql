-- Migration 153: raw_operational_snapshots — add report_body (WO-FILESDB-C4B S4)
--
-- The full pulse report markdown currently lives only on disk (meta/pulse-<date>.md);
-- raw_operational_snapshots stored just the derived counts. This adds a nullable
-- report_body TEXT so the FULL pulse body is captured in the authority (operator
-- decision: keep the full body, not a truncated/derived summary). C4B-5 then drops the
-- disk pulse-<date>.md write.
--
-- Additive, non-destructive: a plain ADD COLUMN (no rebuild — no CHECK/PK change), so
-- existing rows keep report_body=NULL. raw_operational_snapshots is a REAL live table
-- (migration 142); 153 stays unreleased (.released_version 152) so it applies to
-- fresh-install / CI schema until `ds migrate activate` releases it. insert_operational_snapshot
-- feature-detects the column so the live DB keeps writing snapshots (sans body) pre-release.

ALTER TABLE raw_operational_snapshots ADD COLUMN report_body TEXT;
