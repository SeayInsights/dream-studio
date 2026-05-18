-- Migration 054: Add anti_slop_passed to post_build_gate for UI work order types (Slice 7c).
-- Pipe-separated gate list: all gates must pass before a UI work order can close.

UPDATE ds_work_order_types
SET post_build_gate = 'design_critique|anti_slop_passed'
WHERE type_id IN ('ui_component', 'ui_page');
