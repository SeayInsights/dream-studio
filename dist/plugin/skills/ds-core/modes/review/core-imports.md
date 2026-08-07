# Review — Core Module Dependencies

This document tracks which core modules the review skill imports and how changes to those modules impact the skill.

## Imported Modules

### core/git.md
**Used for:**
- Reading git diffs for review
- Getting commit ranges
- Branch comparison

**Referenced in SKILL.md:**
- Diff analysis for code changes
- Commit history review

### core/orchestration.md
**Used for:**
- Spawning reviewer subagents
- Two-stage review pattern (spec then quality)
- Model selection for reviewers

**Referenced in SKILL.md:**
- Review loop implementation
- Parallel reviewer spawning for large changes

### core/format.md
**Used for:**
- Findings report format
- Review verdict structure

**Referenced in SKILL.md:**
- Output format specification
- Severity levels

## Impact Analysis

### If core/git.md changes:
**Affected sections:**
- Diff reading logic
- Commit analysis

**Action:** Review diff parsing in review SKILL.md

### If core/orchestration.md changes:
**Affected sections:**
- Reviewer spawning
- Two-stage review pattern
- Model selection

**Action:** HIGH IMPACT — review entire review SKILL.md, especially:
- Reviewer prompt templates
- Review loop logic

### If core/format.md changes:
**Affected sections:**
- Findings report format
- Verdict structure

**Action:** Update templates/output-formats/findings-report.md

## Maintenance Notes

**Last reviewed:** 2026-04-28
**Core module version compatibility:** All modules at v1.0

**Known issues:** None
