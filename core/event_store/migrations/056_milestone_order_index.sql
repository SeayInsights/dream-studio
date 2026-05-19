ALTER TABLE ds_milestones
ADD COLUMN order_index INTEGER DEFAULT 0;

-- Backfill order_index for Dream Command using rowid as insertion order proxy.
-- All milestones for this project were inserted atomically (same created_at),
-- so rowid is the only reliable ordering signal.
UPDATE ds_milestones
SET order_index = (
    SELECT COUNT(*)
    FROM ds_milestones m2
    WHERE m2.project_id = ds_milestones.project_id
    AND m2.rowid < ds_milestones.rowid
)
WHERE project_id = 'a4befdce-bfb6-40ed-9e83-ace93edac44b';
