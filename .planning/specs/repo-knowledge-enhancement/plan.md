# Implementation Plan: Repo Knowledge Enhancement

**Date**: 2026-04-29 | **Spec**: `.planning/specs/repo-knowledge-enhancement/plan.md`  
**Input**: Analysis of 11 GitHub repos across Power BI and visual builder domains

## Summary

Enhance dream-studio's `client-work` and `dashboard-dev` skills with knowledge extracted from 11 curated GitHub repos. Fixes one critical bug (TMDL indentation rule is backwards), adds substantial Power BI reference depth, upgrades three skills with mandatory checklist gates and anti-patterns tables, and adds a new canvas-patterns reference for DreamySuite work.

## Technical Context

**Language/Version**: Markdown (skill reference files)  
**Primary Dependencies**: None — documentation-only changes  
**Storage**: Plugin cache files + source repo  
**Testing**: Manual — invoke affected skills after changes and verify routing/behavior  
**Target Platform**: Claude Code plugin system  
**Project Type**: skill/domain-doc  
**Performance Goals**: N/A  
**Constraints**: All changes must be backward-compatible with existing skill routing  
**Scale/Scope**: 5 file edits, 2 new files, 7 tasks total

## Constitution Check

*GATE: Must pass before implementation.*

- ✅ No new skills — only enriching existing reference files
- ✅ No changes to routing tables or CLAUDE.md
- ✅ No structural changes to plugin — additive only
- ✅ Changes confined to known SSOT files per skill
- ✅ Blast radius: 7 files, all in `client-work/`, `domains/bi/`, `build/`, `debug/`, `dashboard-dev/` — no cross-skill contamination

## Project Structure

### Documentation (this feature)

```text
.planning/specs/repo-knowledge-enhancement/
├── plan.md          ← this file
├── tasks.md         ← task breakdown
└── traceability.yaml
```

### Source Files Being Changed

```text
# Plugin cache (where Claude Code reads from):
C:\Users\Dannis Seay\.claude\plugins\cache\dream-studio\dream-studio\0.2.0\skills\

client-work/
├── SKILL.md                          ← T004 (checklist gates + anti-patterns)
└── powerbi/
    ├── pbip-format.md                ← T001 (CRITICAL BUG FIX + TMDL rules)
    └── tmdl-authoring.md             ← T002 (NEW FILE)

domains/bi/
└── dax-patterns.md                   ← T003 (major expansion)

build/
└── SKILL.md                          ← T005 (STOP gate + anti-patterns table)

debug/
└── SKILL.md                          ← T006 (anti-patterns table)

dashboard-dev/
└── canvas-patterns.md                ← T007 (NEW FILE)
```

## Requirements Traceability

| Requirement ID | Description | Source Repos | Implemented By |
|---|---|---|---|
| FR-001 | Fix TMDL indentation bug (spaces → tabs) | d7rocket/PowerBI-Skill | T001 |
| FR-002 | Add full TMDL syntax rules to pbip-format | pbip-demo, d7rocket | T001 |
| FR-003 | Create tmdl-authoring.md reference file | pbip-demo, pbip-documenter, pbip-lineage-explorer, superstore-pbip | T002 |
| FR-004 | Expand dax-patterns.md with annotated patterns | world-university-ranking, superstore-pbip, agentic-powerbi | T003 |
| FR-005 | Add STOP checklist gates to client-work/SKILL.md | wix/skills, d7rocket | T004 |
| FR-006 | Add anti-patterns tables to build + debug skills | wix/skills | T005, T006 |
| FR-007 | Create canvas-patterns.md for DreamySuite | Webstudio, Frappe Builder, GrapesJS, VvvebJs | T007 |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Plugin cache edits lost on plugin reinstall | Medium | Also push changes to source repo at builds/dream-studio |
| TMDL rule change breaks existing workflows | Low | Rule is a bug fix — current rule actively breaks TMDL; new rule is correct |
| Anti-patterns tables add friction to skill flow | Low | Tables are reference-only; they don't add steps to the execution path |
| canvas-patterns.md orphaned if dashboard-dev skill doesn't import it | Low | Add import line to dashboard-dev/SKILL.md in T007 |

## Execution Order

```
Phase 1 (sequential — bug fix first):
  T001 → fix pbip-format.md

Phase 2 (parallel — different files, no shared state):
  T002 [P] → new tmdl-authoring.md
  T003 [P] → expand dax-patterns.md

Phase 3 (parallel — all different files):
  T004 [P] → update client-work/SKILL.md
  T005 [P] → update build/SKILL.md
  T006 [P] → update debug/SKILL.md
  T007 [P] → new canvas-patterns.md
```

## Success Metrics

- [ ] `pbip-format.md` says tabs, never spaces (FR-001 closed)
- [ ] A TMDL snippet written following the new rules opens in Power BI Desktop without parse errors
- [ ] `tmdl-authoring.md` exists and is imported by `client-work/SKILL.md`
- [ ] `dax-patterns.md` contains VAR-before-CALCULATE, ALL vs ALLSELECTED, AVERAGEX composite, QoQ REMOVEFILTERS+DATEADD patterns with explanations
- [ ] `client-work/SKILL.md` has a mandatory 4-item checklist with STOP gate before any Power BI build
- [ ] `build/SKILL.md` anti-patterns section is in ❌/✅ table format
- [ ] `debug/SKILL.md` anti-patterns section is in ❌/✅ table format
- [ ] `canvas-patterns.md` exists under `dashboard-dev/` and covers all 7 patterns from the visual builder analysis

## dream-studio Integration

**Skill Flow**: think → **plan** → build → review → verify → ship

**Output Location**: `.planning/specs/repo-knowledge-enhancement/`

**Next Steps**:
1. Review this plan and tasks.md with Director for approval
2. Run `dream-studio:build` with tasks.md
3. Execute T001 first (bug fix), then Phase 2 + Phase 3 in parallel waves
