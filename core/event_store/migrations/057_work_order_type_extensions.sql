-- Slice 8c: extend ds_work_order_types with workflow routing and gate resolution.
--
-- ALTER TABLE is safe to replay — run_migrations silently skips
-- "duplicate column name" errors on existing databases.

ALTER TABLE ds_work_order_types ADD COLUMN workflow_template TEXT;
ALTER TABLE ds_work_order_types ADD COLUMN precondition_skill TEXT;
ALTER TABLE ds_work_order_types ADD COLUMN task_generator TEXT;
ALTER TABLE ds_work_order_types ADD COLUMN resolution_instructions TEXT;

UPDATE ds_work_order_types SET
  workflow_template = 'ui-feature',
  precondition_skill = 'ds-website:discover',
  task_generator = 'ds-core:plan',
  resolution_instructions = 'Fill design brief fields and lock before building.'
WHERE type_id IN ('ui_component', 'ui_page');

UPDATE ds_work_order_types SET
  workflow_template = 'idea-to-pr',
  task_generator = 'ds-core:plan'
WHERE type_id IN ('api_endpoint', 'saas_feature', 'data_pipeline', 'authentication', 'infrastructure');

UPDATE ds_work_order_types SET
  workflow_template = 'game-feature',
  task_generator = 'ds-core:plan'
WHERE type_id = 'game_mechanic';

UPDATE ds_work_order_types SET
  task_generator = 'ds-core:plan'
WHERE type_id = 'documentation';
