# Ship — Core Module Dependencies

This document tracks which core modules the ship skill imports and how changes to those modules impact the skill.

## Imported Modules

### core/quality.md
**Used for:**
- Running build command
- Executing tests
- Running linters (ESLint, TypeScript)
- Bundle analysis

**Referenced in SKILL.md:**
- Phase 1: Audit (technical checks)
- Phase 4: Test (unit/regression tests)

### core/git.md
**Used for:**
- Checking current branch
- Verifying clean working tree
- Reading recent changes

**Referenced in SKILL.md:**
- Pre-deploy safety checks
- Change analysis

### core/orchestration.md
**Used for:**
- Spawning audit agents for different phases
- Model selection for analysis

**Referenced in SKILL.md:**
- Phase-based audit execution
- Parallel audit agents

### core/format.md
**Used for:**
- Ship report format
- Gate decision structure

**Referenced in SKILL.md:**
- Output format specification
- Gate status indicators

## Impact Analysis

### If core/quality.md changes:
**Affected sections:**
- Phase 1: Audit technical checks
- Phase 4: Test execution
- Build/lint commands

**Action:** HIGH IMPACT — review ship SKILL.md audit phases

### If core/git.md changes:
**Affected sections:**
- Pre-deploy git checks
- Change analysis

**Action:** Review ship safety checks

### If core/orchestration.md changes:
**Affected sections:**
- Audit agent spawning
- Parallel phase execution

**Action:** Review ship audit orchestration

### If core/format.md changes:
**Affected sections:**
- Ship report format
- Gate decision output

**Action:** Update ship report templates

## Maintenance Notes

**Last reviewed:** 2026-04-28
**Core module version compatibility:** All modules at v1.0

**Known issues:** None
