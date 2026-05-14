# Verify — Core Module Dependencies

This document tracks which core modules the verify skill imports and how changes to those modules impact the skill.

## Imported Modules

### core/quality.md
**Used for:**
- Running tests
- Executing build/dev servers
- Running linters and validators

**Referenced in SKILL.md:**
- Test execution patterns
- Quality checks

### core/format.md
**Used for:**
- Verification report format
- Evidence documentation structure

**Referenced in SKILL.md:**
- Output format specification
- Evidence file organization

## Impact Analysis

### If core/quality.md changes:
**Affected sections:**
- Test execution logic
- Build/dev server startup
- Quality checks

**Action:** Review verify SKILL.md test execution patterns

### If core/format.md changes:
**Affected sections:**
- Verification report format
- Evidence structure

**Action:** Update verification report templates

## Maintenance Notes

**Last reviewed:** 2026-04-28
**Core module version compatibility:** All modules at v1.0

**Known issues:** None
