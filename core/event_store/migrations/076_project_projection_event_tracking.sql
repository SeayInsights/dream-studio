-- Phase 18.2.5: Add projection event-tracking columns to business_projects.
--
-- Adds source_event_id and last_event_id columns, matching the pattern from
-- migrations 072 (business_tasks), 073 (business_milestones), and 074
-- (business_design_briefs).
--
-- source_event_id: event_id of the project.created event that created this row.
-- last_event_id:   event_id of the most-recently applied canonical event.
--
-- Both are nullable; NULL means the row predates event sourcing (migration 077
-- backfills them for existing rows).

ALTER TABLE business_projects ADD COLUMN source_event_id TEXT;
ALTER TABLE business_projects ADD COLUMN last_event_id TEXT;
