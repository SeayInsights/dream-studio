-- Rollback 155: remove the client layer (reverse of 155_client_layer.sql).
-- A reverse migration legitimately drops what its forward created; it is exempt from the
-- forward-migration DROP-safety gate. Order: index, then the FK column, then the table.

DROP INDEX IF EXISTS idx_business_projects_client;
ALTER TABLE business_projects DROP COLUMN client_id;
DROP TABLE IF EXISTS business_clients;
