# Security Scan — WO-C Post-wave orphan & rot sweep

**Date:** 2026-06-06
**Changed files (code):**
- control/execution/workflow/learning.py (deleted)
- projections/core/email/*.py (deleted — 5 files)
- projections/core/notifications/dispatcher.py (deleted)
- projections/generators/__init__.py (deleted)
- projections/frontend/integrate_improvements.py (deleted)
- projections/tests/test_alerts.py (deleted — uncollected test dir)
- projections/tests/test_email.py (deleted — uncollected test dir)
- tests/unit/test_career_ops_capability_agent_github.py (deleted)
- interfaces/cli/check_schema.py (deleted — vestigial debug script)
- interfaces/cli/merge_databases.py (deleted — vestigial TA-004 migration script)
- .claude/CLAUDE.md (removed ds-career routing row)
- .claude/skills/ds-setup/tool-registry.yml (removed ds-career firecrawl entry)
- core/module_contracts.py (removed 3 dead test file refs from validation_tests)
- pyproject.toml (removed python-pptx>=0.6.21 and openpyxl>=3.1.0)
- requirements.txt (removed stale projections/ml comment)

## Findings: NONE

### What was changed

All changes are DELETIONS or SUBTRACTIONS. No new code paths, no new input surfaces, no new
external calls, no new trust boundaries.

### control/execution/workflow/learning.py (deleted)
- Zero importers confirmed (grep across all .py files). Historical performance tracker with no
  callers since the Wave 2+ cleanup runs. Deletion creates no new attack surface.

### projections/core/email/ (deleted, 5 files)
- Only imported by self (example_usage.py, test_import.py) and projections/tests/test_email.py
  (in uncollected test directory). No production routes or CLI commands import this. Deletion
  creates no new attack surface.

### projections/core/notifications/dispatcher.py (deleted)
- Only imported by projections/tests/test_alerts.py (uncollected test directory). No production
  routes import this. Deletion creates no new attack surface.

### projections/generators/__init__.py (deleted)
- Empty stub package. Zero importers. No attack surface.

### projections/frontend/integrate_improvements.py (deleted)
- No production routes import this. Reads a missing file (hooks_improved.html) that doesn't exist.
  Zero importers. No attack surface.

### check_schema.py and merge_databases.py (deleted)
- One-off TA-004 diagnostic/migration scripts. automation_checkpoints and automation_log tables
  were dropped in migration 101. These scripts are now vestigial. Deletion is net reduction
  of executable surface.

### .claude/CLAUDE.md, tool-registry.yml (config edits)
- Removed dead routing entries for ds-career (deleted in Wave 2). Config-only changes; no code
  execution paths affected.

### core/module_contracts.py (edit)
- Removed 3 entries of the deleted test file from validation_tests lists. No module boundary,
  owned_tables, or maturity level changed. Net reduction.

### pyproject.toml (edit)
- Removed python-pptx and openpyxl from dependencies. These libraries had zero importers after
  projections/exporters/ was cleared. Reducing dependencies reduces supply-chain attack surface.

### requirements.txt (edit)
- Removed stale comment referencing deleted projections/ml/. Comment-only change.
