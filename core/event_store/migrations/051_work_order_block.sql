-- Migration 051: Add block_reason column and extend ds_work_orders.status to include 'blocked'.
-- Uses ALTER TABLE ADD COLUMN (safe, no view re-validation) plus writable_schema to patch
-- the CHECK constraint in-place (no table recreation needed).
-- run_migrations applies this once; version tracking prevents re-run.

ALTER TABLE ds_work_orders ADD COLUMN block_reason TEXT;

PRAGMA writable_schema = ON;
UPDATE sqlite_master SET sql = REPLACE(
    sql,
    '''cancelled'')',
    '''cancelled'', ''blocked'')'
) WHERE type = 'table' AND name = 'ds_work_orders';
PRAGMA writable_schema = OFF;
