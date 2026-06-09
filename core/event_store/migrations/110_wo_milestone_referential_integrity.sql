-- Migration 110: WO milestone referential integrity
--
-- The INNER JOIN added in migration 108's selector silently hides WOs whose
-- milestone_id is NULL or references a non-existent milestone row.  This
-- migration ensures every work order references a valid milestone before the
-- selector change lands on the live authority DB.
--
-- Step 1 — Create a 'Backlog' milestone (order_index 999) for each project
-- that has milestone-less WOs but no milestones at all.  UUID generated
-- inline using SQLite's randomblob() (available since 3.9).

INSERT INTO business_milestones
    (milestone_id, project_id, title, status, order_index, created_at, updated_at)
SELECT
    lower(hex(randomblob(4)))
        || '-' || lower(hex(randomblob(2)))
        || '-4'  || substr(lower(hex(randomblob(2))), 2)
        || '-'   || substr('89ab', abs(random()) % 4 + 1, 1)
                 || substr(lower(hex(randomblob(2))), 2)
        || '-'   || lower(hex(randomblob(6))),
    p.project_id,
    'Backlog',
    'created',
    999,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
FROM business_projects p
WHERE NOT EXISTS (
    SELECT 1 FROM business_milestones m WHERE m.project_id = p.project_id
)
AND EXISTS (
    SELECT 1 FROM business_work_orders wo
    LEFT JOIN business_milestones m2 ON wo.milestone_id = m2.milestone_id
    WHERE wo.project_id = p.project_id
      AND (wo.milestone_id IS NULL OR m2.milestone_id IS NULL)
);

-- Step 2 — Assign WOs with NULL milestone_id to the earliest valid milestone.
UPDATE business_work_orders
SET milestone_id = (
    SELECT m.milestone_id
    FROM business_milestones m
    WHERE m.project_id = business_work_orders.project_id
    ORDER BY m.order_index ASC, m.created_at ASC
    LIMIT 1
)
WHERE milestone_id IS NULL;

-- Step 3 — Assign WOs with a dangling (non-existent) milestone_id to the
-- earliest valid milestone.
UPDATE business_work_orders
SET milestone_id = (
    SELECT m.milestone_id
    FROM business_milestones m
    WHERE m.project_id = business_work_orders.project_id
    ORDER BY m.order_index ASC, m.created_at ASC
    LIMIT 1
)
WHERE milestone_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM business_milestones m
      WHERE m.milestone_id = business_work_orders.milestone_id
  );
