# Build — Core Module Dependencies

This document tracks which core modules the build skill imports and how changes to those modules impact the skill.

## Imported Modules

### core/git.md
**Used for:**
- Commit formatting with task references
- Reading git diffs for review
- Branch operations

**Referenced in SKILL.md:**
- Step 2.5: Commit with TR-IDs
- Commit message format

### core/traceability.md
**Used for:**
- TR-ID validation before updates
- Updating commit references in traceability.yaml
- Checking if traceability tracking is enabled

**Referenced in SKILL.md:**
- Step 2.6: Update traceability (conditional)

### core/quality.md
**Used for:**
- Running build commands
- Executing tests
- Linting and validation

**Referenced in SKILL.md:**
- Verification after implementation
- Pre-commit checks

### core/orchestration.md
**Used for:**
- Subagent spawning patterns
- Model selection (Haiku/Sonnet/Opus)
- Review loop pattern
- Implementer prompt template
- Handling agent responses (DONE, BLOCKED, etc.)

**Referenced in SKILL.md:**
- Step 1: Dependency analysis
- Step 2: Execute each task
- Step 2.2: Handle implementer response
- Step 2.3-2.4: Review loops
- Implementer prompt template section

### core/format.md
**Used for:**
- Checkpoint format (output after every 3 tasks)
- Task progress reporting

**Referenced in SKILL.md:**
- Step 3: Checkpoint

## Impact Analysis

### If core/git.md changes:
**Affected sections:**
- Step 2.5 (Commit formatting)
- May need to update commit message template

**Action:** Review build SKILL.md Step 2.5 and verify commit format still works

### If core/traceability.md changes:
**Affected sections:**
- Step 2.6 (TR-ID updates)
- Conditional traceability logic

**Action:** Review build SKILL.md Step 2.6 validation and update logic

### If core/quality.md changes:
**Affected sections:**
- Build/test execution patterns
- Pre-commit validation

**Action:** Review quality gates in build process

### If core/orchestration.md changes:
**Affected sections:**
- Step 1 (dependency analysis)
- Step 2.1 (implementer dispatch)
- Step 2.2 (response handling)
- Step 2.3-2.4 (review loops)
- Model selection table

**Action:** HIGH IMPACT — review entire build SKILL.md, especially:
- Subagent spawning logic
- Review loop implementation
- Model selection guidelines

### If core/format.md changes:
**Affected sections:**
- Step 3 (checkpoint output)

**Action:** Review checkpoint format in build SKILL.md

## Maintenance Notes

**Last reviewed:** 2026-04-28
**Core module version compatibility:** All modules at v1.0

**Known issues:** None
