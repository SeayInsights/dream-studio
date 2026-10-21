-- Reverse of migration 161: drop security_events.confidence / coverage / limitations
--
-- Paired reverse under the R3 rollback regime (ROLLBACK_ENFORCED_FROM=154).
--
-- WHAT IS LOST. The three values recorded on findings since 161 are discarded; those
-- findings read as confidence "unknown", coverage "unknown", limitations "not recorded",
-- which is how every finding read before 161. No row is deleted and no other column is
-- touched. The finding.recorded events on the spool carry the same values for
-- observability, but nothing replays security_events from them, so the values are not
-- recoverable by re-applying 161.
--
-- SQLite supports DROP COLUMN from 3.35 (2021). Each column's CHECK is its own, and no
-- index or view names these columns (the findings status view selects *).

ALTER TABLE security_events DROP COLUMN limitations;
ALTER TABLE security_events DROP COLUMN coverage;
ALTER TABLE security_events DROP COLUMN confidence;
