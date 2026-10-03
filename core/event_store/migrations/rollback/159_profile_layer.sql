-- Rollback 159: remove the profile layer (reverse of 159_profile_layer.sql).
-- A reverse migration legitimately drops what its forward created; it is exempt from the
-- forward-migration DROP-safety gate. Order: index, then the table.
--
-- WHAT IS LOST. Every row in business_profiles (profile identity: name, client_id,
-- claude_config_dir, mcp_client_name, status) is dropped. No other table references
-- business_profiles, so nothing else is affected. Re-applying 159 recreates the empty
-- table; profile rows themselves are not recoverable from any other table since they
-- were never event-sourced into a replayable projection in this change set.

DROP INDEX IF EXISTS idx_business_profiles_client;
DROP TABLE IF EXISTS business_profiles;
