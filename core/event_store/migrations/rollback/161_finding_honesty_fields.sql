-- Reverse of migration 161: drop security_events.confidence / coverage / limitations
--
-- Paired reverse under the R3 rollback regime (ROLLBACK_ENFORCED_FROM=154).
--
-- WHAT IS LOST. The three values recorded on findings since 161 are discarded; those
-- findings read as confidence "unknown", coverage "unknown", limitations "not recorded",
-- which is how every finding read before 161. No row is deleted and no other column is
-- touched. The values are not recoverable from the spool either: record_finding's spool
-- emission does not run (issue #910), and emit_security_finding's security.finding.logged
-- event carries them for observability only, with nothing that replays security_events
-- from it. Re-applying 161 therefore restores the columns, not the values.
--
-- SQLite supports DROP COLUMN from 3.35 (2021). Each column's CHECK is its own, and no
-- index or view names these columns.

ALTER TABLE security_events DROP COLUMN limitations;
ALTER TABLE security_events DROP COLUMN coverage;
ALTER TABLE security_events DROP COLUMN confidence;
