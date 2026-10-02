-- Migration 159: profile layer — business_profiles (switchable operating-context identity)
--
-- WHY. Dream Studio runs across multiple real-world engagements (today: SeayInsights and
-- Fulcrum, more to come) that each want their own Claude Code config directory and,
-- eventually, their own MCP client identity -- but all share ONE Dream Studio authority
-- rather than separate installs: the whole point of a shared authority is seeing
-- everything across identities in one place, with attribution (the client layer,
-- migration 155) distinguishing them. There was no "which identity am I operating as
-- right now" concept to switch -- the only related field (`ds project state`'s
-- active_client_id) is DERIVED from whichever project happens to be active, not an
-- independent settable thing. "Active project" (what work) and "active profile" (which
-- identity) are orthogonal, parallel concepts, and both can be active independently.
--
-- A profile belongs to a client (business_clients) -- many profiles may share a client.
-- profile_id is a UUID (matching business_projects/business_milestones/
-- business_work_orders/business_tasks's dominant convention) rather than a human slug
-- like business_clients uses: clients are a small curated seed set, profiles are
-- user-created, and `name` already carries the human-readable label. status mirrors
-- business_projects.status's active|paused singleton-style column (switching displaces
-- the previous active row; core/profiles/mutations.py::switch_active_profile).
--
-- claude_config_dir / mcp_client_name are stored and UNUSED by this migration --
-- deliberately. Wiring claude_config_root() (core/config/paths.py) to prefer the active
-- profile's claude_config_dir, and building an MCP client identity registry keyed by
-- mcp_client_name, are both separate follow-ups once their own concurrent work lands;
-- this migration only reserves the columns.
--
-- ADDITIVE ONLY: one new table + one index. No existing table touched, no row rewritten,
-- no reader shape changed. No seed rows -- unlike business_clients, a fresh install has
-- zero profiles until an operator creates one.
--
-- Release-guarded by .released_version: this affects fresh-install / CI schema until an
-- operator runs `ds migrate activate`. Paired reverse migration at
-- rollback/159_profile_layer.sql.

CREATE TABLE IF NOT EXISTS business_profiles (
    profile_id        TEXT PRIMARY KEY,
    client_id         TEXT NOT NULL REFERENCES business_clients(client_id),
    name              TEXT NOT NULL,
    claude_config_dir TEXT,
    mcp_client_name   TEXT,
    status            TEXT NOT NULL DEFAULT 'active',   -- active | paused | archived
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_business_profiles_client ON business_profiles(client_id);
