-- Migration 106: Drop redundant per-type invocation tables.
--
-- All rows in these tables are covered 1:1 by execution_events (verified in WO-R
-- investigation: 0 rows have data absent from execution_events). The write path
-- in emitters.py no longer dual-writes to these tables as of this migration.
-- Readers have been repointed to execution_events filtered by component column.

DROP TABLE IF EXISTS skill_invocations;
DROP TABLE IF EXISTS agent_invocations;
DROP TABLE IF EXISTS workflow_invocations;
DROP TABLE IF EXISTS hook_invocations;
DROP TABLE IF EXISTS tool_invocations;
