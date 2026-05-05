-- Migration 010: Workflow Learning System - Project Intelligence Wave 6

-- Add workflow execution tracking columns to reg_workflows
ALTER TABLE reg_workflows ADD COLUMN chain TEXT;
ALTER TABLE reg_workflows ADD COLUMN success_count INTEGER DEFAULT 0;
ALTER TABLE reg_workflows ADD COLUMN total_count INTEGER DEFAULT 0;
ALTER TABLE reg_workflows ADD COLUMN created_at TEXT;

-- Create index for performance when querying by success rate
CREATE INDEX IF NOT EXISTS idx_workflows_success_rate
ON reg_workflows(success_count, total_count)
WHERE total_count > 0;

-- Create index for filtering by category
CREATE INDEX IF NOT EXISTS idx_workflows_category_success
ON reg_workflows(category, success_count, total_count);
