-- Slice 5b/5e: work_order_type routing key for the SDLC pipeline.
--
-- run_migrations silently skips "duplicate column name" errors, so the
-- ALTER TABLE is safe to replay.  INSERT OR IGNORE guards the type rows
-- so bootstrap on an existing DB with partial data is also safe.

ALTER TABLE ds_work_orders ADD COLUMN work_order_type TEXT;

CREATE TABLE IF NOT EXISTS ds_work_order_types (
    type_id         TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    pre_build_gate  TEXT,
    build_executor  TEXT,
    post_build_gate TEXT
);

INSERT OR IGNORE INTO ds_work_order_types VALUES
  ('ui_component',   'UI Component',    'design_brief_locked',
   'fullstack:frontend', 'design_critique'),
  ('ui_page',        'UI Page',         'design_brief_locked',
   'website:page',       'design_critique'),
  ('api_endpoint',   'API Endpoint',    'api_contract_exists',
   'fullstack:backend',  'security_scan'),
  ('authentication', 'Authentication',  'api_contract_and_security_review',
   'fullstack:backend',  'security_scan'),
  ('saas_feature',   'SaaS Feature',    'api_contract_exists',
   'saas-build',         'security_scan'),
  ('data_pipeline',  'Data Pipeline',   NULL,
   'fullstack:backend',  'security_scan'),
  ('game_mechanic',  'Game Mechanic',   'spec_approved',
   'game-dev',           'game_validate'),
  ('deployment',     'Deployment',      'all_tests_pass',
   'devops-engineer',    'security_scan'),
  ('infrastructure', 'Infrastructure',  NULL,
   'devops-engineer',    'security_scan'),
  ('documentation',  'Documentation',   NULL,
   'core:build',         NULL);
