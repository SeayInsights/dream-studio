# Implementation Plan: dream-studio Improvements

**Date**: 2026-04-28 | **Branch**: `feat/dream-studio-improvements`
**Spec**: Approved integration spec — conversation 2026-04-28

---

## Summary

Backfill 7 external patterns (LangGraph JSON contracts, AutoGen routing fallback, LangGraph
conditional branching, Aider repo-map, SWE-agent red-green, Devin per-task checkpoint, Claude
prompt caching) across 16 target files in the dream-studio skill system. Concurrently deliver
2 missing skills (explain, metrics hook) and 2 mandate fixes (debug→issue, pipeline gate).

---

## Technical Context

**Language/Version**: Markdown (skill files), YAML (config/workflows/analysts), Python 3.x (metrics script)
**Primary Dependencies**: None external — edits to existing plain-text skill files
**Storage**: File system (`.planning/`, `skills/`, `workflows/`, `hooks/lib/`, `.claude/`)
**Testing**: Manual smoke-test.md runs + catalog regeneration (`py generate-catalog.py`)
**Target Platform**: Claude Code plugin (Windows / macOS / Linux)
**Project Type**: Skill / plugin configuration
**Constraints**: No breaking changes to any existing skill's public interface; all changes additive or replacement-in-place
**Scale/Scope**: 26 tasks across 16 files + 4 new files

---

## Constitution Check

No `.planning/CONSTITUTION.md` exists for this project. Architectural invariants sourced from STRUCTURE.md and REGISTRY.md:

- **SSOT rule**: Core modules own shared patterns; skills reference, don't duplicate
- **File ownership**: One task per file modification; no parallel agents on same file
- **Additive first**: New sections augment existing; wholesale rewrites only when required
- **Registry must stay accurate**: Any new core module requires REGISTRY.md update
- **No public interface breaks**: `DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT` signals are consumed by existing workflows — JSON schema must be backward-compatible or workflows updated simultaneously

**Interface compatibility decision**: JSON schema is a REPLACEMENT in orchestration.md. The `fix-issue.yaml` and `idea-to-pr.yaml` workflows use `{{node.output}}` template syntax and parse node output as text, not JSON. The new JSON schema will be the authoritative pattern for new dispatches; existing workflows use command: nodes that produce free-text, not skill agent contracts, so no collision.

---

## Project Structure

### Planning documents (this feature)

```text
.planning/specs/dream-studio-improvements/
├── plan.md         ← this file
├── tasks.md        ← task breakdown
└── traceability.yaml ← TR-ID registry
```

### Files being modified

```text
skills/core/
├── orchestration.md    ← T004, T012, T017
├── format.md           ← T008
├── repo-map.md         ← T007 (NEW)
└── REGISTRY.md         ← T007

skills/build/
├── SKILL.md            ← T005, T013, T014, T015, T026
└── config.yml          ← T009

skills/review/
└── SKILL.md            ← T006

skills/debug/
└── SKILL.md            ← T018, T025

skills/verify/
└── SKILL.md            ← T019

skills/explain/          ← T003 (NEW directory + 5 files)
├── SKILL.md
├── metadata.yml
├── gotchas.yml
├── config.yml
└── changelog.md

skills/coach/
├── SKILL.md            ← T022
├── modes.yml           ← T024
└── analysts/
    └── route-classifier.yml  ← T023 (NEW)

workflows/
├── idea-to-pr.yaml     ← T010
└── fix-issue.yaml      ← T002, T020

hooks/lib/
└── skill_metrics.py    ← T011 (NEW)

builds/dream-studio/CLAUDE.md  ← T003 (routing), T021
builds/dream-studio/.claude/settings.json  ← T016 (PostToolUse hook)
```

---

## Dependency Graph

Sequential chains within shared files:

```
core/orchestration.md:  T004 → T012 → T017
build/SKILL.md:         T005 → T013 → T014 → T015 → T026
fix-issue.yaml:         T002 → T020
debug/SKILL.md:         T018 → T025
coach chain:            T022 → T023 → T024
metrics chain:          T011 → T016
```

Cross-file dependencies:

```
T005 depends T004   (build/SKILL.md references orchestration.md JSON schema)
T006 depends T004   (review/SKILL.md mirrors orchestration.md analyst pattern)
T012 depends T004, T007  (orchestration.md repo-map field needs repo-map.md to exist)
T013 depends T005, T007  (build/SKILL.md Step 0 needs repo-map.md + T005 already modified file)
T014 depends T008, T013  (checkpoint format needs format.md updated + T013 already modified build)
T015 depends T014        (worktree section follows checkpoint section in build/SKILL.md)
T016 depends T011        (settings.json hook calls skill_metrics.py — script must exist first)
T017 depends T012        (pipeline gate goes in orchestration.md after repo-map field)
T020 depends T002, T018  (write-failing-test node needs T002's fix-issue.yaml mods + T018's debug output JSON)
T023 depends T022        (analyst file references mode defined in T022)
T024 depends T023        (modes.yml entry references analyst file from T023)
T025 depends T018        (auto-learn suggestion appended to debug Step 1.5 context)
T026 depends T015        (auto-learn note appended to checkpoint section touched in T015)
```

---

## Wave Execution Plan

| Wave | Tasks (parallel within wave) | Gate |
|------|------------------------------|------|
| 1 | T001 | Branch created |
| 2 | T002 [P], T003 [P], T004, T007 [P], T008 [P], T009 [P], T010 [P], T011 [P] | T004 complete before Wave 3 |
| 3 | T005 [P], T006 [P] | Both complete before Wave 4 |
| 4 | T012, T013 (different files — run [P]) | Both complete before Wave 5 |
| 5 | T014 | Complete before Wave 6 |
| 6 | T015, T016 [P], T017 [P], T018 [P], T019 [P], T021 [P], T022 [P] | All complete before Wave 7 |
| 7 | T020 [P], T023 [P], T025 [P], T026 [P] | All complete before Wave 8 |
| 8 | T024 | Plan complete |

Note: Wave 2 has T004 as sequential within the wave (no other task touches orchestration.md in Wave 2, so T004 can run alongside the [P] tasks). T004 is listed without [P] marker only to signal it's the Wave 2 bottleneck for Wave 3.

---

## Requirements

| ID | Description | Priority | Tasks |
|----|-------------|----------|-------|
| TR-001 | fix-issue.yaml has unconditional create-issue node after diagnose | must | T002 |
| TR-002 | explain skill exists; routing covers it | must | T003 |
| TR-003 | orchestration.md + build + review use JSON agent schema | must | T004, T005, T006 |
| TR-004 | orchestration.md + build enforce static-before-dynamic prompt ordering | must | T004, T005 |
| TR-005 | idea-to-pr.yaml has security branch; fix-issue.yaml has write-failing-test node | should | T010, T020 |
| TR-006 | repo-map.md exists; orchestration.md references it; build/SKILL.md generates on Step 0 | should | T007, T012, T013 |
| TR-007 | format.md has task-level checkpoint; build uses it per-task; config threshold=1 | should | T008, T009, T014 |
| TR-008 | build parallel dispatch uses isolation:worktree | should | T015 |
| TR-009 | orchestration.md has pipeline gate pattern | could | T017 |
| TR-010 | skill_metrics.py exists; settings.json has PostToolUse hook | could | T011, T016 |
| TR-011 | debug has Step 1.5; verify has red-green section; fix-issue has conditional test node | could | T018, T019, T020 |
| TR-012 | CLAUDE.md routing fallback; coach route-classify mode + analyst + modes.yml | could | T021, T022, T023, T024 |
| TR-013 | debug Step 6 + build checkpoint suggest learn: | could | T025, T026 |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| JSON schema breaks existing workflow node parsing | Low | High | Workflows use `command:` blocks with free-text output — they don't consume skill agent JSON. No collision. |
| orchestration.md changes break 6 dependent skills | Medium | High | Changes are additive (new sections). Existing text preserved. Run catalog after to verify. |
| settings.json hook fires on all projects globally | Medium | Medium | Scope hook to dream-studio plugin directory check in skill_metrics.py — no-op if not in a dream-studio session. |
| explain skill triggers overlap with other skills | Low | Low | "explain:" is distinct. Route table is keyword-first; ambiguous prompts go to coach fallback anyway. |
| Worktree isolation changes agent output paths | Low | Medium | Claude Code cleans worktree automatically if no changes. Existing review steps read git diff which works across worktrees. |

---

## Success Criteria

- [ ] All 26 tasks committed on `feat/dream-studio-improvements`
- [ ] `py generate-catalog.py` runs clean (no errors, catalog updated)
- [ ] `py hooks/lib/skill_metrics.py` runs without error
- [ ] orchestration.md implementer template has JSON schema block visible in file
- [ ] explain skill directory has all 5 required files
- [ ] fix-issue.yaml has create-issue node visible before plan-fix
- [ ] coach/modes.yml has route-classify entry
- [ ] No existing skill smoke tests broken (manual check of build + review)
