-- Reverse of migration 158: drop business_work_orders.blocked_from_status
--
-- Paired reverse under the R3 rollback regime (ROLLBACK_ENFORCED_FROM=154).
--
-- WHAT IS LOST. A work order blocked at the moment of rollback forgets the phase it was
-- blocked from, and unblock returns it to `in_progress` -- the behavior before 158, which
-- erased a review and a push for work blocked while waiting on CI. No work order is
-- deleted and no other field is touched. The blocked events keep `from_status` in their
-- payload, so re-applying 158 and replaying restores the column.
--
-- SQLite supports DROP COLUMN from 3.35 (2021). No index names the column.

ALTER TABLE business_work_orders DROP COLUMN blocked_from_status;
