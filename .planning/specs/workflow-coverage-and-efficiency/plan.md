# Implementation Plan: Workflow Coverage, Token Efficiency & Feature Activation

**Date**: 2026-04-30 | **Spec**: `.planning/specs/workflow-coverage-and-efficiency/spec.md`
**Input**: Approved spec (B+C approach: chain-suggest + Python context efficiency layer)

## Summary

Build a Python context efficiency layer (5 scripts), add chain-suggest metadata to all 22 skill modes, create an on-skill-complete hook, extend the workflow engine with session caching and output compression, add pre-run cost gates, create 3 new workflows, and optimize 3 existing workflows.

## Technical Context

**Language/Version**: Python 3.14 (stdlib only — no pip deps)
**Primary Dependencies**: Existing hooks/lib/ modules (state.py, paths.py, studio_db.py, workflow_engine.py, workflow_cost.py)
**Storage**: `.sessions/<date>/` (session files), `~/.dream-studio/state/` (persistent state)
**Testing**: Manual verification via workflow runs + existing test patterns in tests/
**Target Platform**: Windows 11 (primary), cross-platform compatible (Unix paths handled)
**Constraints**: All scripts must fail gracefully — errors fall back to current behavior, never block skill execution

## Constitution Check

Verified against `.planning/CONSTITUTION.md`:
- Pack-based architecture: All changes follow pack structure (new hook in meta pack, metadata in skill SKILL.md files)
- No built-in overrides: No changes to EnterPlanMode, review, etc. routing
- Subagent-driven builds: Python scripts support the subagent pattern, don't replace it
- No forbidden patterns violated: No direct pushes, no co-authored-by, no wrangler deploy

## Project Structure

```text
hooks/lib/                          # Python scripts (5 new)
├── repo_context.py                 # NEW — project snapshot generator
├── context_compiler.py             # NEW — minimal prompt compiler
├── prompt_assembler.py             # NEW — cache-optimized prompt builder
├── findings_summarizer.py          # NEW — inter-node data compression
├── session_cache.py                # NEW — session file server
├── model_selector.py               # NEW — SQLite-driven model selection
├── workflow_engine.py              # MODIFY — add {{session:*}} + output_compress
├── workflow_cost.py                # MODIFY — add pre-run cost gate
├── workflow_state.py               # MODIFY — call repo_context on start
└── skill_metrics.py                # DELETE — dead code

packs/meta/hooks/
└── on-skill-complete.py            # NEW — chain-suggest advisory hook

skills/*/modes/*/SKILL.md           # MODIFY (22 files) — add chain_suggests frontmatter

workflows/                          # 3 new YAML workflows
├── audit-to-fix.yaml               # NEW
├── ui-feature.yaml                 # NEW
└── client-deliverable.yaml         # NEW

workflows/                          # 3 existing YAML optimizations
├── project-audit.yaml              # MODIFY — parallel regroup
├── optimize.yaml                   # MODIFY — short-circuit conditions
└── idea-to-pr.yaml                 # MODIFY — model tier downgrades
```

## Complexity Tracking

| Concern | Why Needed | Simpler Alternative Rejected Because |
|---------|------------|-------------------------------------|
| context_compiler.py parses SKILL.md sections | Need to extract only relevant sections per agent | Full SKILL.md is 500-1800 words — ~77% is boilerplate per agent |
| prompt_assembler.py enforces byte-identical prefix | Claude prompt cache needs identical prefixes for cache hits | Without this, every agent in a wave pays full cache-miss cost |
| {{session:*}} template syntax in workflow engine | Nodes re-read same session files (4-6x duplication) | Each Read tool call costs tokens for file content in context |
| model_selector.py queries SQLite | Historical success rates should drive model selection | Hardcoded model tiers waste money on simple tasks and fail on complex ones |

## Requirements Traceability

| Requirement | Description | Implemented By |
|-------------|-------------|----------------|
| SC-001 | Every skill has chain-suggest or workflow home | T002-T005 (metadata), T025-T030 (workflows) |
| SC-002 | Pre-run cost gate before workflow execution | T020 |
| SC-003 | >=50% token savings on subagent context | T008, T010, T012 |
| SC-004 | >=70% savings on inter-node findings | T007 |
| SC-005 | Dead code removed | T001 |
| SC-006 | on-skill-complete prints suggestions | T014 |
| SC-007 | 3 new P1 workflows created | T025, T026, T027 |
| SC-008 | Model auto-selection from SQLite | T009 |
| SC-009 | Polish in UI build pipeline | T026 (ui-feature.yaml) |
| SC-010 | repo_context.py verified on 2+ projects | T006 |
| SC-011 | Existing workflows optimized | T028, T029, T030 |
| SC-012 | workflow_engine.py supports session + compress | T016, T018 |
| SC-013 | Byte-identical static prefixes | T012 |

## Dependencies & Waves

```
Wave 1 (no deps):
  T001 ──────── dead code cleanup
  T002-T005 ─── chain-suggest metadata (parallel, different files)
  T006 ──────── repo_context.py
  T007 ──────── findings_summarizer.py
  T009 ──────── model_selector.py

Wave 2 (needs Wave 1):
  T008 ──────── context_compiler.py (needs T006: repo_context)
  T010-T013 ─── prompt_assembler.py (needs T008: context_compiler)
  T015 ──────── session_cache.py (standalone but logically Wave 2)
  T014 ──────── on-skill-complete hook (needs T002-T005: chain-suggest metadata)

Wave 3 (needs Wave 2):
  T016-T017 ─── workflow_engine.py changes (needs T007, T015)
  T018-T019 ─── workflow_state.py changes (needs T006)
  T020 ──────── pre-run cost gate (needs T009, T016)
  T021-T023 ─── build mode + orchestration updates (needs T010-T013)

Wave 4 (needs Wave 3):
  T025 ──────── audit-to-fix.yaml
  T026 ──────── ui-feature.yaml
  T027 ──────── client-deliverable.yaml
  T028-T030 ─── existing workflow optimizations
  T031 ──────── verification run
```

## Notes

- All Python scripts are stdlib-only — no pip install needed
- Every script must handle errors gracefully and fall back to current behavior
- Session files go in `.sessions/<YYYY-MM-DD>/` per existing convention
- Tests follow existing pattern in `tests/unit/` and `tests/integration/`
- Wave 1 tasks are safe to parallelize — each writes to distinct files
- Chain-suggest metadata is additive frontmatter — no SKILL.md behavior changes
