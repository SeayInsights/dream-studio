-- Reverse of migration 157: drop business_work_orders.priority
--
-- Paired reverse under the R3 rollback regime (ROLLBACK_ENFORCED_FROM=154).
--
-- WHAT IS LOST. Every work order returns to the queue position it had before 157, which
-- is FIFO by created_at -- the ordering that made this column necessary. No work order is
-- deleted and no other field is touched; what goes is the answer to "pick this up first".
-- A blocker registered by the post-merge watcher becomes indistinguishable from a piece of
-- planned work filed the same day, which is the state this migration exists to end.
--
-- SQLite supports DROP COLUMN from 3.35 (2021), and the index must go first because it
-- names the column.

DROP INDEX IF EXISTS idx_work_orders_priority_created;

ALTER TABLE business_work_orders DROP COLUMN priority;
