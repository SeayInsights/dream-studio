# Core Module Registry

Tracks which skills use which core modules for impact analysis.

## Purpose

Before changing a core module, check this registry to see which skills will be affected.

## Module Usage Map

### core/git.md
**Used by:** build, review, verify, ship, plan, handoff, recap

**Patterns:**
- Commit formatting
- Branch operations
- Diff reading
- PR checking

**Change impact:** 7 skills affected

---

### core/traceability.md
**Used by:** plan, build, verify

**Patterns:**
- Check traceability.yaml existence
- Validate traceability file
- Update TR-IDs with commits/tests
- Status tracking

**Change impact:** 3 skills affected

---

### core/quality.md
**Used by:** review, ship, verify, build

**Patterns:**
- Build commands
- Test execution
- Linting
- Accessibility checks
- Performance metrics

**Change impact:** 4 skills affected

---

### core/orchestration.md
**Used by:** build, review, secure, think, analyze, career-ops

**Patterns:**
- Subagent spawning (parallel/sequential)
- Model selection logic
- Result collection
- Review loops

**Change impact:** 6 skills affected

---

### core/format.md
**Used by:** ALL SKILLS

**Patterns:**
- Markdown tables
- Checkbox lists
- Severity tags
- Verdict statements
- Evidence format

**Change impact:** All skills affected (use extreme caution)

---

### core/repo-map.md
**Used by:** build

**Patterns:**
- Compact symbol map generation (find + grep)
- Pre-inline into subagent context as static prefix
- Enables structural awareness without full file reads

**Change impact:** 1 skill affected (build)

---

### core/web.md
**Used by:** career-scan, career-ops, analyze, security-dast, domains-client-work (research phase)

**Patterns:**
- Web access fallback chain (Firecrawl → scraper-mcp → WebSearch/WebFetch)
- Tool detection logic
- Silent degradation (TR-014)
- Capability matrix for tool selection

**Change impact:** 5 skills affected

---

## External Subagent Dependencies

Skills that dispatch non-standard subagent types (outside the Haiku/Sonnet/Opus set):

| Skill | Subagent type | Dispatch trigger |
|-------|--------------|-----------------|
| client-work | `bi-developer` | Any `.pbip`/`.tmdl` work, DAX debugging, M-query errors, Dataverse schema changes, RLS implementation |

**Impact:** If the `bi-developer` agent type is unavailable or slow, client-work will fail silently on Power BI deep work. Always verify agent availability before dispatching client-work on complex Power BI tasks.

---

## Skills by Module Count

| Skill | Modules Used | Core Modules |
|-------|--------------|--------------|
| build | 5 | git, traceability, quality, orchestration, format |
| review | 4 | git, quality, orchestration, format |
| verify | 4 | git, traceability, quality, format |
| ship | 3 | git, quality, format |
| plan | 3 | git, traceability, format |
| secure | 3 | git, orchestration, format |
| think | 2 | orchestration, format |
| analyze | 2 | orchestration, format |
| handoff | 2 | git, format |
| recap | 2 | git, format |

## Update Instructions

When creating a new skill:
1. Add module imports to skill's SKILL.md under `## Imports` section
2. Update this registry with the new skill in relevant module sections
3. Update "Skills by Module Count" table

When refactoring an existing skill:
1. Update `## Imports` section in SKILL.md
2. Update this registry to reflect new module usage

When modifying a core module:
1. Check this registry for affected skills
2. Test each affected skill after the change
3. Update module version/changelog if needed

## Version History

- **2026-04-29**: Enforcement + gap closure
  - Added "External Subagent Dependencies" section (client-work → bi-developer)
  - All 37 SKILL.md files received "Before you start" preload block
  - debug/build got project GOTCHAS.md/CONSTITUTION.md step-0 check
  - think got CONSTITUTION.md check in Step 1 (Clarify)
  - harden now scaffolds CLAUDE.md + CONSTITUTION.md + GOTCHAS.md first
  - Global ~/.claude/CLAUDE.md routing table expanded to cover all 37 skills
  - sync-cache.ps1 created; all 37 skills synced to plugin cache

- **2026-04-28**: Architecture enhancement Phase 2
  - Added metadata.yml, gotchas.yml, config.yml to all 37 skills
  - Created skill catalog with auto-generation
  - Enriched core 5 skills (build, plan, review, verify, ship) with:
    - Examples (simple + complex)
    - Templates (agent prompts + output formats)
    - Smoke tests
    - Core-imports.md (impact analysis)
  - Added changelog.md to all skills
  - Skills now tracked: 37 total
  
- **2026-04-27**: Initial registry created during modularization refactor
  - Core modules extracted: git, traceability, quality, orchestration, format
  - 10 skills tracked (build, review, verify, ship, plan, secure, think, analyze, handoff, recap)
