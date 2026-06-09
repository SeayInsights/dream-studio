-- Migration 109: Backfill sequence_order and work_order_dependencies.
--
-- sequence_order: sparse assignment (10, 20, 30…) per-milestone from created_at order.
-- WOs with no milestone (strays) are left NULL — the ready-set selector ignores them.
--
-- work_order_dependencies: seed known Clean-State Hardening ADR edges.
-- INSERT OR IGNORE is safe if either endpoint doesn't exist in this DB.

-- Assign sequence_order from created_at rank within each milestone (sparse * 10).
-- The correlated subcount gives rank 0-based; multiply by 10 for sparse spacing.
UPDATE business_work_orders
SET sequence_order = (
    SELECT COUNT(*) * 10 + 10
    FROM business_work_orders wo2
    WHERE wo2.milestone_id = business_work_orders.milestone_id
      AND wo2.created_at < business_work_orders.created_at
)
WHERE milestone_id IS NOT NULL
  AND sequence_order IS NULL;

-- Seed known dependency edges from the Clean-State Hardening ADR.
-- WO-Y (b582957c…) depends on WO-Q2 (d78040a9…).
INSERT OR IGNORE INTO work_order_dependencies (work_order_id, depends_on_id)
SELECT wo.work_order_id, dep.work_order_id
FROM business_work_orders wo, business_work_orders dep
WHERE wo.work_order_id LIKE 'b582957c%'
  AND dep.work_order_id LIKE 'd78040a9%';

-- WO-T2 (cbf06c32…) depends on WO-ORD (7e64870b…).
INSERT OR IGNORE INTO work_order_dependencies (work_order_id, depends_on_id)
SELECT wo.work_order_id, dep.work_order_id
FROM business_work_orders wo, business_work_orders dep
WHERE wo.work_order_id LIKE 'cbf06c32%'
  AND dep.work_order_id LIKE '7e64870b%';
