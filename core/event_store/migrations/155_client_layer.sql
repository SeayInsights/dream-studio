-- Migration 155: client layer — business_clients + business_projects.client_id
-- (Attribution Coherence Phase 2)
--
-- Adds a CLIENT layer above projects (client -> many projects) so separate engagements for one
-- client stop collapsing into a single project. ADDITIVE ONLY: a new table, a new nullable FK
-- column, an index, and three seed clients (SeayInsights, Fulcrum, Hypershift) as reference data.
-- No table is dropped and no row is deleted, so there is no DROP-safety concern.
--
-- business_projects.client_id is NULLABLE; existing project rows are assigned a client by
-- core/clients/backfill.py::backfill_project_clients (fulcrum/hypershift by name-or-path, else
-- SeayInsights) at activation time — fresh installs have no projects to backfill. SeayInsights is
-- the default client for new work.
--
-- Release-guarded by .released_version (154): this affects fresh-install / CI schema until an
-- operator runs `ds migrate activate` to bump the sentinel. Paired reverse migration lives at
-- rollback/155_client_layer.sql.

CREATE TABLE IF NOT EXISTS business_clients (
    client_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'active',   -- active | archived | deleted
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

ALTER TABLE business_projects ADD COLUMN client_id TEXT REFERENCES business_clients(client_id);

CREATE INDEX IF NOT EXISTS idx_business_projects_client ON business_projects(client_id);

-- Seed clients (reference data; present on fresh + live). Stable slug ids so they are
-- deterministic and human-readable. INSERT OR IGNORE keeps this idempotent on re-apply.
INSERT OR IGNORE INTO business_clients (client_id, name, description) VALUES
    ('seayinsights', 'SeayInsights', 'Default client: SeayInsights internal + product work'),
    ('fulcrum',      'Fulcrum',      'FulcrumDefense engagement'),
    ('hypershift',   'Hypershift',   'Hypershift engagement');
