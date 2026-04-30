# Implementation Plan: Repo Integration — 4 External Repos → dream-studio

**Date**: 2026-04-29 | **Spec**: `.planning/specs/repo-integration/`  
**Input**: Research analysis from think phase (conversation context)

## Summary

Extract proven patterns from 4 external repos (impeccable, mattpocock/skills, OpenSpec, next-browser) and integrate them into dream-studio as additive enrichments. No existing logic is overwritten — every change slots into the existing pack structure, file conventions, and directory patterns already established.

**Rule**: All changes are additive only. Read existing file → append/extend → never replace.

## Technical Context

**Language/Version**: Markdown, YAML  
**Primary Dependencies**: None — pure content files  
**Storage**: File system under `C:\Users\Dannis Seay\builds\dream-studio\`  
**Testing**: Manual — open each modified file, verify additive section present, verify no existing content removed  
**Target Platform**: dream-studio skill runtime (Claude Code)  
**Project Type**: skill/domain-doc  
**Performance Goals**: N/A  
**Constraints**: Additive only. Never overwrite. Each task = one commit.

## Constitution Check

- All 3 project memory files exist (CLAUDE.md, CONSTITUTION.md, GOTCHAS.md) ✓
- Changes follow existing pack/skill/domain directory conventions ✓
- No new packs being created — enriching existing ones ✓
- All foreign content adapted to dream-studio idiom (not copy-pasted raw) ✓

## Project Structure

### Documentation (this feature)

```text
.planning/specs/repo-integration/
├── plan.md              # This file
└── tasks.md             # Task breakdown
```

### Files Being Modified or Created

```text
# Phase A — New reference files
skills/design/references/
├── typography.md              (NEW — from impeccable)
├── color-and-contrast.md      (NEW — from impeccable)
├── spatial-design.md          (NEW — from impeccable)
├── motion-design.md           (NEW — from impeccable)
├── interaction-design.md      (NEW — from impeccable)
├── responsive-design.md       (NEW — from impeccable)
├── ux-writing.md              (NEW — from impeccable)
└── anti-patterns.md           (NEW — from impeccable, expanded)

skills/domains/design/
├── motion-design.yml          (NEW)
├── interaction-design.yml     (NEW)
├── ux-writing.yml             (NEW)
├── anti-patterns.yml          (NEW)
├── typography-standards.yml   (UPDATE — enrich existing)
└── color-standards.yml        (UPDATE — enrich existing)

# Phase B — New templates/checklists/analysts
skills/think/templates/
├── design-template.md         (NEW — architecture artifact)
└── spec-template.md           (UPDATE — add PRD acceptance criteria)

skills/plan/templates/
└── tasks-template.md          (UPDATE — add owner + estimate fields)

skills/build/templates/agent-prompts/
└── tdd-loop.md                (NEW — TDD red→green→refactor prompt)

skills/harden/templates/       (dir does not exist — create it)
└── context-template.md        (NEW — CONTEXT.md domain vocab template)

skills/ship/templates/
└── archive-stamp-template.md  (NEW — spec archive record)

skills/polish/checklists/
└── design-anti-patterns.yml   (NEW — 24 anti-patterns checklist)

skills/coach/analysts/
└── zoom-out.yml               (NEW — "solving the right problem?" analyst)

# Phase C — SKILL.md updates (12 files)
skills/think/SKILL.md          (UPDATE)
skills/plan/SKILL.md           (UPDATE)
skills/build/SKILL.md          (UPDATE)
skills/debug/SKILL.md          (UPDATE)
skills/verify/SKILL.md         (UPDATE)
skills/ship/SKILL.md           (UPDATE)
skills/harden/SKILL.md         (UPDATE)
skills/design/SKILL.md         (UPDATE)
skills/polish/SKILL.md         (UPDATE)
skills/coach/SKILL.md          (UPDATE)
skills/workflow/SKILL.md       (UPDATE)
skills/mcp-build/SKILL.md      (UPDATE)
```

## Source Mapping

| Source Repo | Pattern Extracted | dream-studio Target |
|---|---|---|
| pbakaus/impeccable | 7 reference modules (typography, color, spatial, motion, interaction, responsive, ux-writing) | skills/design/references/ |
| pbakaus/impeccable | 24 anti-pattern list | skills/design/references/anti-patterns.md + skills/polish/checklists/design-anti-patterns.yml |
| pbakaus/impeccable | CLI detect tool | skills/verify/SKILL.md (Web/SaaS domain block) |
| pbakaus/impeccable | /critique, /animate command modes | skills/design/SKILL.md |
| mattpocock/skills | grill-me structured questioning | skills/think/SKILL.md Step 1 |
| mattpocock/skills | grill-with-docs docs-interrogation | skills/think/SKILL.md Step 1 |
| mattpocock/skills | to-prd PRD acceptance criteria | skills/think/templates/spec-template.md |
| mattpocock/skills | tdd loop (red→green→refactor) | skills/build/SKILL.md + tdd-loop.md template |
| mattpocock/skills | triage severity classification | skills/debug/SKILL.md Step 0.5 |
| mattpocock/skills | to-issues GitHub issue generation | skills/plan/SKILL.md |
| mattpocock/skills | CONTEXT.md shared domain vocabulary | skills/harden/SKILL.md + context-template.md |
| mattpocock/skills | zoom-out scope check | skills/coach/SKILL.md + zoom-out.yml |
| mattpocock/skills | caveman compressed comms | skills/workflow/SKILL.md |
| mattpocock/skills | owner+estimate task format | skills/plan/templates/tasks-template.md |
| Fission-AI/OpenSpec | design.md architecture artifact | skills/think/SKILL.md + design-template.md |
| Fission-AI/OpenSpec | spec archive pattern | skills/ship/SKILL.md + archive-stamp-template.md |
| vercel-labs/next-browser | React errors/snapshot/network debug | skills/debug/SKILL.md |
| vercel-labs/next-browser | snapshot/a11y/profile/interaction verify | skills/verify/SKILL.md |
| vercel-labs/next-browser | CWV check at ship gate | skills/ship/SKILL.md |
| vercel-labs/next-browser | CLI-to-skill bridge pattern | skills/mcp-build/SKILL.md |

## Dependency Order

```
Phase A (reference files) ──────────────────────────────────┐
Phase B (templates/checklists)  ────────────────────────────┤
                                                             ↓
                                              Phase C (SKILL.md updates)
```

Phase C tasks reference the files created in A and B.
All Phase A tasks are independent of each other (different files).
All Phase B tasks are independent of each other (different files).
Phase C Wave 1 (think, plan, build, debug) independent of Wave 2 and 3.
Phase C Wave 2 (verify, ship, harden, design) independent of Wave 3.
Phase C Wave 3 (polish, coach, workflow, mcp-build) independent of previous waves.
Waves 1/2/3 within Phase C can actually all run in parallel (all different files).

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Impeccable repo content changes between research and build | Low | Fetch from raw.githubusercontent.com at build time, adapt to dream-studio idiom |
| SKILL.md update accidentally removes existing content | High | Read file first, append only, diff check before commit |
| harden/templates/ dir missing | Low | Build agent creates dir before writing file |

## Success Metrics

- [ ] 8 new files created in `skills/design/references/`
- [ ] 6 domain files created/updated in `skills/domains/design/`
- [ ] 9 template/checklist/analyst files created or updated
- [ ] 12 SKILL.md files updated with additive sections
- [ ] Zero existing content removed from any file
- [ ] All new files follow dream-studio YAML/Markdown conventions

## dream-studio Integration

**Skill Flow**: think → plan → **build** → verify

**Next Steps**:
1. Run `dream-studio:build` with tasks.md
2. Execute Phase A wave in parallel (8+4+2 tasks)
3. Execute Phase B wave in parallel (8 tasks)
4. Execute Phase C in 3 sub-waves (4+4+4 tasks)
