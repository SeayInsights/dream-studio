-- Migration 108: Explicit work-order ordering — sequence_order + work_order_dependencies.
--
-- sequence_order (nullable, sparse 10/20/30): NULL means no explicit ordering;
-- NULLs sort last in the ready-set selector (ORDER BY sequence_order ASC NULLS LAST).
--
-- work_order_dependencies: directed dependency edges. An open dependency
-- (depends_on WO status != 'closed') blocks the dependent WO from the ready-set.

ALTER TABLE business_work_orders ADD COLUMN sequence_order INTEGER;

CREATE TABLE IF NOT EXISTS work_order_dependencies (
    work_order_id  TEXT NOT NULL REFERENCES business_work_orders(work_order_id),
    depends_on_id  TEXT NOT NULL REFERENCES business_work_orders(work_order_id),
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (work_order_id, depends_on_id)
);

CREATE INDEX IF NOT EXISTS idx_wo_dependencies_work_order
    ON work_order_dependencies (work_order_id);

CREATE INDEX IF NOT EXISTS idx_wo_dependencies_depends_on
    ON work_order_dependencies (depends_on_id);
