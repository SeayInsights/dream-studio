-- Migration 157: business_work_orders.priority — what to pick up first
--
-- WHY. `ds work-order next` orders by created_at ASC, so the queue is FIFO. A defect
-- found by a review lane, or a red `main` found by the post-merge watcher, queues behind
-- every older work order — which is the opposite of what either finding means.
--
-- The policy already existed and had no mechanism. "Defect work orders execute before
-- normal milestone work orders" has been an operator rule carried in an agent's notes,
-- which is to say it held exactly as long as an agent remembered it. Three agents are
-- about to write to this queue — the review lanes before a push, the watcher after one,
-- and the session doing the building — and a rule that depends on recall is not a
-- handoff protocol.
--
-- THE VOCABULARY IS CLOSED, by CHECK constraint:
--
--   blocker   `main` is red, or a lane found a blocker-class defect. Ahead of everything.
--   defect    a regression, or a non-blocking lane finding. Ahead of planned work.
--   normal    planned work. The default, so nothing has to be classified to be created.
--   backlog   parked below planned work rather than deleted.
--
-- A CHECK rather than a convention because `--type` accepted any string for as long as it
-- existed and defaulted the unrecognised ones to `infrastructure`, so a typo became a work
-- order whose gates nothing could run. The same door is not left open twice.
--
-- WHY IT CANNOT BE FREELY CHOSEN, in the layer above: the watcher always writes `blocker`
-- (a red main is a fact, not a judgment) and a lane derives its level from its own
-- recorded precedent. An escape that costs nothing to claim becomes the norm — the same
-- reason `unenforced:` in the rule registry requires a twenty-character reason.
--
-- ADDITIVE ONLY: one column with a default on an existing table. No table is dropped, no
-- row is deleted, and no existing reader changes shape. Every row that exists takes
-- `normal`, which is what FIFO already meant for them.

ALTER TABLE business_work_orders
    ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'
    CHECK (priority IN ('blocker', 'defect', 'normal', 'backlog'));

-- The queue reads (priority, created_at) together; ordering by one without the other is
-- what this migration exists to stop.
CREATE INDEX IF NOT EXISTS idx_work_orders_priority_created
    ON business_work_orders (priority, created_at);
