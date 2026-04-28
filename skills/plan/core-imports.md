# Plan — Core Module Dependencies

This document tracks which core modules the plan skill imports and how changes to those modules impact the skill.

## Imported Modules

### core/orchestration.md
**Used for:**
- Subagent spawning for complex spec analysis
- Model selection

**Referenced in SKILL.md:**
- Spec analysis for large/complex specs
- Dependency graph generation

### core/format.md
**Used for:**
- Plan output format
- Task structure guidelines

**Referenced in SKILL.md:**
- Plan file format specifications
- Task template structure

## Impact Analysis

### If core/orchestration.md changes:
**Affected sections:**
- Spec analysis patterns
- Model selection for planning agents

**Action:** Review plan SKILL.md analysis section

### If core/format.md changes:
**Affected sections:**
- Plan file format
- Task structure

**Action:** HIGH IMPACT — review plan output format, update templates/output-formats/plan-format.md

## Maintenance Notes

**Last reviewed:** 2026-04-28
**Core module version compatibility:** All modules at v1.0

**Known issues:** None
