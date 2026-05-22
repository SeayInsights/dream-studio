-- Phase 18.0 C3: Remove test fixture contamination from ds_projects
--
-- Background: pytest runs that pre-dated or bypassed the guard_real_homedir
-- autouse fixture wrote test fixture rows directly into the production
-- studio.db. These rows are identifiable by their names matching known test
-- factory patterns used in tests/unit/test_project*.py.
--
-- Real projects kept:
--   - "Dream Studio"  (the primary development project)
--   - "Dream Command" (the active build project)
--
-- Deleted names (all are factory-generated test identifiers):
--   - "My Project"          (repeated 5 times, tests/unit/test_project*.py)
--   - "Programmatic Project" (repeated 5 times, tests/unit/test_project*.py)
--   - "API Project"         (repeated 5 times, tests/unit/test_project*.py)
--   - "TA0 Verification Test" (explicit TA0 test fixture)
--   - "TA0 E2E Verify"       (explicit TA0 test fixture)
--
-- Idempotency: DELETE WHERE is safe to re-run; rows matching these names
-- after this migration runs are new contamination, not residual.
--
-- Audit: 25 rows before → 2 rows after (Dream Studio, Dream Command).

DELETE FROM ds_projects
WHERE name IN (
    'My Project',
    'Programmatic Project',
    'API Project',
    'TA0 Verification Test',
    'TA0 E2E Verify'
);
