-- Add event tracking columns to business_design_briefs for projection idempotency.
-- Phase 18.2.4: DesignBriefProjection uses source_event_id / last_event_id to
-- implement the same idempotency contract as TaskProjection / MilestoneProjection.
ALTER TABLE business_design_briefs ADD COLUMN source_event_id TEXT;
ALTER TABLE business_design_briefs ADD COLUMN last_event_id TEXT;
