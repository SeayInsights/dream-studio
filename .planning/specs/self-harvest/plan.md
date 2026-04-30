# Implementation Plan: Self-Harvest

**Date**: 2026-04-29 | **Spec**: `.planning/specs/self-harvest/spec.md`

## Summary

Extend the existing `learn` skill with a `harvest` mode that scans historical session files, draft lessons, and gotchas to extract reusable patterns. Add auto-draft hooks to `recap` and `handoff` so learnings are captured at session end without Director intervention. All output goes to `meta/draft-lessons/` first — nothing writes to skill files without explicit approval.

Also promotes the 5 stale draft lessons from April 19 as the first concrete harvest run.

## Technical Context

**Language/Version**: Markdown + YAML (no code)
**Primary Dependencies**: Existing dream-studio skill infrastructure (`learn`, `recap`, `handoff`, `meta/`)
**Storage**: File system — `skills/*/SKILL.md`, `skills/*/gotchas.yml`, `meta/draft-lessons/`, `meta/lessons/`
**Testing**: Manual verification — trigger `learn: harvest`, confirm draft appears; trigger recap, confirm auto-draft appears
**Target Platform**: dream-studio local skill directory
**Project Type**: skill-doc update
**Performance Goals**: Harvest completes < 10 min on ~25 session files (SC-004)
**Constraints**: Never write to `skills/*/gotchas.yml` without Director approval in-conversation (FR-008)
**Scale/Scope**: 4 SKILL.md files, 5 gotchas.yml files, 5 draft lesson promotions, 1 archive batch

## Constitution Check

No `.planning/CONSTITUTION.md` exists in dream-studio. No conflicts to surface. Proceed.

## Project Structure

```text
.planning/specs/self-harvest/
├── spec.md           # Approved
├── plan.md           # This file
└── tasks.md          # Task breakdown

skills/learn/
├── SKILL.md          # MODIFIED — harvest mode added
└── gotchas.yml       # MODIFIED — anti-bloat rules added

skills/recap/
└── SKILL.md          # MODIFIED — auto-draft step added

skills/handoff/
└── SKILL.md          # MODIFIED — auto-draft step added

skills/secure/
└── gotchas.yml       # MODIFIED — 2 entries added

skills/review/
└── gotchas.yml       # MODIFIED — 1 entry added

skills/ship/
└── gotchas.yml       # MODIFIED — 3 entries added

skills/build/
└── gotchas.yml       # MODIFIED — 1 entry added

meta/draft-lessons/   # SOURCE — 5 files promoted then archived
meta/lessons/         # TARGET — 5 files moved here after promotion
```

## Requirements Traceability

| Requirement ID | Description | Implemented By |
|---|---|---|
| FR-001 | harvest scans .sessions, draft-lessons, gotchas, memory feedback | T002 |
| FR-002 | dedup check against existing gotchas before drafting | T001, T002 |
| FR-003 | only draft lessons with ≥2 source confirmations | T002 |
| FR-004 | harvest never writes directly to skill files | T001, T002 |
| FR-005 | cap at 5 new draft lessons per harvest run | T001, T002 |
| FR-006 | recap and handoff auto-create draft on correction/blocker | T003, T004 |
| FR-007 | auto-harvested drafts flagged `Source: auto-harvest` | T002, T003, T004 |
| FR-008 | promotion to gotchas.yml requires Director approval | T005, T006, T007, T008 |

## Draft Lesson → Target Gotchas Mapping

| Draft File | Target Skill Gotchas |
|---|---|
| `2026-04-19-verify-before-fixing-audit.md` | `secure/gotchas.yml` |
| `2026-04-19-never-downgrade-lint-rules.md` | `ship/gotchas.yml`, `build/gotchas.yml` |
| `2026-04-19-validate-locally-before-push.md` | `ship/gotchas.yml` |
| `2026-04-19-verify-ci-steps-exist.md` | `ship/gotchas.yml` |
| `2026-04-19-audit-reports-need-resolution-tracking.md` | `secure/gotchas.yml`, `review/gotchas.yml` |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Harvest scan grows too broad over time | Medium — noise creeps in | Enforce ≤5 cap and ≥2-source rule in learn/gotchas.yml |
| Auto-draft in recap adds overhead to every session end | Low — slow recap | Scan is text-only, no file writes unless pattern found. Cost: seconds |
| Director skips approval and promotion accumulates | Medium — drafts go stale again | learn/SKILL.md documents the promotion flow explicitly; SC-001 tracks this |

## Success Metrics

- [ ] `learn: harvest` trigger documented in learn/SKILL.md with all 4 scan sources
- [ ] learn/gotchas.yml has anti-bloat rules (dedup, cap, no-auto-promote)
- [ ] recap/SKILL.md has auto-draft step
- [ ] handoff/SKILL.md has auto-draft step
- [ ] All 5 draft lessons promoted to correct gotchas.yml files (SC-002)
- [ ] All 5 draft lesson files archived to meta/lessons/ with status: PROMOTED

## Build Execution Model

**Wave 1 [parallel]**: T001, T002, T003, T004 — each owns a distinct file, no conflicts
**Wave 2 [parallel, Director approval required]**: T005, T006, T007, T008 — each owns a distinct gotchas.yml
**Wave 3 [sequential]**: T009 — archive; depends on all Wave 2 promotions complete

Wave 2 tasks each present their draft content and target file to the Director before writing. Explicit approval required per task.
