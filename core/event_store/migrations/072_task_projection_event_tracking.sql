-- Add event tracking columns to business_tasks for projection idempotency.
-- Phase 18.2.3: TaskProjection uses source_event_id / last_event_id to
-- implement the same idempotency contract as WorkOrderProjection.
ALTER TABLE business_tasks ADD COLUMN source_event_id TEXT;
ALTER TABLE business_tasks ADD COLUMN last_event_id TEXT;
