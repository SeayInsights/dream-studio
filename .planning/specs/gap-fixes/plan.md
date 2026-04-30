# Gap Fixes — Implementation Plan
Date: 2026-04-29
Status: APPROVED

## Vision
Make dream-studio reliable out-of-box for anyone (even beginners), require no vocabulary knowledge, self-evolve with the user, and self-optimize its own internals over time.

## Scope
8 gaps identified in gap analysis. 23 tasks across 3 execution phases.

## Technical Context

### Architecture
- Hook handlers live in `packs/{pack}/hooks/{name}.py`
- `hooks/run.sh` dispatches by searching packs in order: core → quality → career → analyze → domains → meta
- Shared library: `hooks/lib/` (paths, state, audit, models, time_utils, etc.)
- Workflows: `workflows/*.yaml` — YAML DAG executed by Claude reading node commands
- Workflow engine state: `hooks/lib/workflow_engine.py` + `workflow_state.py`
- Config: `~/.dream-studio/config.json` — per-user persistent state
- Skill routing: `CLAUDE.md` routing table → `Skill` tool → `skills/{name}/SKILL.md`

### Key File Ownership
| Area | SSOT |
|---|---|
| Hook dispatch order | `hooks/run.sh` |
| Hook event registrations | `hooks/hooks.json` |
| Pack-level config | `~/.dream-studio/config.json` |
| Shared state read/write | `hooks/lib/state.py` |
| Audit log | `hooks/lib/audit.py` |
| Route-classify logic | `skills/coach/SKILL.md` |
| Workflow resume | `hooks/lib/workflow_engine.py` + `workflow_state.py` |

## Requirements

| TR-ID | Gap | Description | Priority |
|---|---|---|---|
| TR-G01 | GAP-1/8 | First-run hook fires once, collects Director profile, wires studio-onboard | must |
| TR-G02 | GAP-2 | Route-classify auto-invokes matched skill when confidence ≥ 0.8 | must |
| TR-G03 | GAP-5 | Pack-aware hook suppression + quiet_mode flag | should |
| TR-G04 | GAP-7 | skill_metrics wired into plugin-level hooks.json | should |
| TR-G05 | GAP-3 | Auto-lesson draft on debug completion + threshold escalation | should |
| TR-G06 | GAP-4 | self-audit workflow for dream-studio internals | could |
| TR-G07 | GAP-9 | validate-analysts CI/Makefile check | should |
| TR-G08 | GAP-6 | Workflow engine resume checkpoints survive context compaction | could |

## Architecture Decisions

**AD-1 — First-run uses sentinel file, not config key**
A sentinel file (`~/.dream-studio/state/.first-run-complete`) is simpler to check atomically and avoids race conditions with config.json reads. Config.json is written after questions are answered.

**AD-2 — route-classify auto-invoke is instruction-level (SKILL.md change), not code**
Route-classify runs inside Claude's context as a skill. The auto-invoke instruction tells Claude to call `Skill` tool directly when confidence ≥ 0.8. No Python needed.

**AD-3 — Pack-awareness via config, not filesystem detection**
`on-game-validate` already detects Godot projects via `detect_project()`. The new `pack_context.py` adds a config-level killswitch so users can explicitly disable domain hooks without removing the pack. These are complementary, not redundant.

**AD-4 — skill_metrics moves to a proper packs/meta handler**
The `.claude/settings.json` version is project-local only. A `packs/meta/hooks/on-skill-metrics.py` handler in `hooks/hooks.json` fires for all installed users. The settings.json entry becomes redundant and can be removed.

**AD-5 — Workflow resume in engine, not per-YAML-node**
Injecting resume logic into every YAML node's command would double each node's instructions and bloat context. `workflow_engine.py` saves/loads checkpoint state centrally — cleaner and maintainable.

## Execution Phases

### Phase 1 — New files and standalone changes (all parallelizable)
T001, T003, T004, T005, T007, T009, T011, T012, T013, T014, T015, T017, T018, T021

### Phase 2 — Wiring (depends on Phase 1 files)
T002 (→T001), T006 (→T005), T008 (→T007), T010 (→T011), T016 (→T015), T019 (→T018), T022 (→T021)

### Phase 3 — CI integration
T020 (→T019)
