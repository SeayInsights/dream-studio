-- Migration 103: Drop entire prd_* cluster (WO-F)
--
-- AD-10 decision: business_projects IS what PRD was.
-- All prd_* tables are retired. Views, junction tables, and root table
-- are dropped in FK dependency order.
--
-- Migration 083 created canonical_events; migration 102 is its terminal
-- transformation. This migration is the terminal transformation for the
-- prd_* cluster (created in migrations 012 and 047).

PRAGMA foreign_keys = OFF;

-- Drop dependent views first (referencing prd_documents/prd_tasks)
DROP VIEW IF EXISTS vw_prd_progress;
DROP VIEW IF EXISTS vw_task_details;

-- Drop junction table
DROP TABLE IF EXISTS session_tasks;

-- Drop leaf tables (FK → prd_documents, prd_sessions, prd_tasks)
DROP TABLE IF EXISTS prd_handoffs;
DROP TABLE IF EXISTS prd_sessions;
DROP TABLE IF EXISTS prd_tasks;
DROP TABLE IF EXISTS prd_plans;

-- Drop root table
DROP TABLE IF EXISTS prd_documents;

-- Drop remaining prd_* tables (no FK dependencies on other prd_* tables)
DROP TABLE IF EXISTS prd_version_records;
DROP TABLE IF EXISTS prd_amendment_records;
DROP TABLE IF EXISTS prd_route_reconciliation_records;

PRAGMA foreign_keys = ON;
