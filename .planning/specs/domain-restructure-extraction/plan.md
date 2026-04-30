# Implementation Plan: Domain Restructure + Repo Knowledge Extraction

**Date**: 2026-04-29 | **Spec**: Director-approved in session

## Summary

Two workstreams in sequence: (1) collapse the siloed `domains/bi/` into `domains/powerbi/` as a single open Power BI domain any skill can reference, deduplicating `client-work/powerbi/` in the process; (2) add three new domain files from Batch 2+3 repo analysis — dimensional modeling, UI component library, and web animation patterns.

## Technical Context

**Project Type**: domain-doc / skill architecture  
**Language/Version**: Markdown, YAML  
**Storage**: File system  
**Target Platform**: dream-studio skill system  
**Constraints**: PR <120 lines per PR; deliver as 2 PRs; no Co-Authored-By commits

## Constitution Check

- Enforces SSOT principle: one canonical location per domain, no duplicates
- Removes `client-work` content silo — Power BI knowledge becomes broadly referenceable
- `client-work/SKILL.md` updated atomically after all moves — no broken import window
- New saas-build files are additive; no existing skill is modified

## Project Structure

### Planning

```text
.planning/specs/domain-restructure-extraction/
├── plan.md      ← this file
└── tasks.md     ← task breakdown
```

### Affected Files

```text
# Moves into domains/powerbi/
skills/domains/bi/dax-patterns.md            → skills/domains/powerbi/dax-patterns.md
skills/domains/bi/m-query-patterns.md        → skills/domains/powerbi/m-query-patterns.md
skills/client-work/powerbi/tmdl-authoring.md → skills/domains/powerbi/tmdl-authoring.md
skills/client-work/powerbi/pbip-format.md    → skills/domains/powerbi/pbip-format.md
skills/client-work/powerbi/design-hacks.yml  → skills/domains/powerbi/design-hacks.yml

# Deletes (dupes / renamed)
skills/client-work/powerbi/accessibility-checklist.yml  ← exact dupe of domains/powerbi/ copy
skills/client-work/powerbi/storytelling-framework.yml   ← rename canonical in-place

# Rename in domains/powerbi/
skills/domains/powerbi/storytelling-patterns.yml → skills/domains/powerbi/storytelling-framework.yml

# Retire
skills/domains/bi/   ← empty after moves, delete

# Import update
skills/client-work/SKILL.md

# New files
skills/domains/data/data-modeling.md
skills/domains/saas-build/component-library.md
skills/domains/saas-build/animation-patterns.md

# Registry update
skills/domains/ingest-log.yml
```

## Requirements Traceability

| Requirement ID | Description | Implemented By |
|---------------|-------------|----------------|
| TR-001 | All Power BI knowledge lives in `domains/powerbi/`; `domains/bi/` retired | T002–T009 |
| TR-002 | `client-work/SKILL.md` imports updated to `domains/powerbi/` | T010 |
| TR-003 | No duplicate files across domain and client-work directories | T007, T008 |
| TR-004 | `domains/data/data-modeling.md` created with all 7 dimensional modeling patterns | T013 |
| TR-005 | `domains/saas-build/component-library.md` created with Mage-UI patterns | T014 |
| TR-006 | `domains/saas-build/animation-patterns.md` created with meet-ui + GSAP patterns | T015 |
| TR-007 | `ingest-log.yml` updated with all Batch 2+3 repos | T016 |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| SKILL.md imports broken between move and update | High | T010 runs only after all moves (T002–T008) complete |
| `saas-build/` directory doesn't exist yet | Medium | T014 creates dir + file; T015 depends on T014 |
| PR2 line count exceeds 120 (doc content) | Low | Split into PR2a (data) + PR2b (saas-build) if needed at build time |

## Success Metrics

- [ ] `domains/bi/` directory does not exist
- [ ] `domains/powerbi/` contains 8 files (was 3)
- [ ] `client-work/powerbi/` no longer exists or is empty
- [ ] All `client-work/SKILL.md` imports resolve to `domains/powerbi/`
- [ ] `domains/data/data-modeling.md` exists with 7 sections
- [ ] `domains/saas-build/component-library.md` exists
- [ ] `domains/saas-build/animation-patterns.md` exists
- [ ] `ingest-log.yml` contains entries for all 6 newly analyzed repos
