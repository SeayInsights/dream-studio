-- Migration 158: business_work_orders.blocked_from_status — the phase unblock returns to
--
-- WHY. Work orders now move through their phases in a fixed order: created ->
-- in_progress -> in_review -> pushed -> ci_issues -> closed, with ci_issues the only
-- phase that may be skipped. A work order can be blocked from any open phase, and
-- unblock sent every one of them to `in_progress`. A work order blocked while `pushed`,
-- waiting for CI, came back at `in_progress`: its review and its push erased, and the
-- watcher -- which looks for work at `pushed` -- would never find it again.
--
-- So block records where it came from, and unblock returns there. The row holds it
-- rather than the event history alone because unblock must answer at the moment it runs,
-- and the spool is ingested on its own schedule; the blocked event carries the same
-- value as `from_status`, so a replay rebuilds the column from history.
--
-- THE VOCABULARY IS CLOSED, by CHECK: the five open phases, or NULL for a work order
-- that is not blocked (and for one blocked before this column existed, which unblock
-- returns to `in_progress`, as it always did).
--
-- ADDITIVE ONLY: one nullable column on an existing table. No table is dropped, no row is
-- deleted, and no existing reader changes shape.

ALTER TABLE business_work_orders
    ADD COLUMN blocked_from_status TEXT
    CHECK (
        blocked_from_status IS NULL
        OR blocked_from_status IN ('created', 'in_progress', 'in_review', 'pushed', 'ci_issues')
    );
