# Gap Fixes — Task List
Date: 2026-04-29

---

## Phase 1 — New files and standalone changes
All tasks in this phase are independent and can run in parallel.

### T001 [P] Create on-first-run.py handler
- Implements: TR-G01
- Files: `packs/meta/hooks/on-first-run.py`
- Depends on: none
- What: New hook handler. On UserPromptSubmit, check for sentinel `~/.dream-studio/state/.first-run-complete`. If absent: print welcome banner, prompt for director_name / domain / primary_use, write answers to `~/.dream-studio/config.json` (merging, not overwriting), create sentinel file. Exit 0 always — never block the session.
- Acceptance: Running the hook with no sentinel produces a populated config.json and creates the sentinel. Running it again is a no-op.

### T003 [P] Update README Quick Start — studio-onboard
- Implements: TR-G01
- Files: `README.md`
- Depends on: none
- What: Add `workflow: run studio-onboard` as the first command in the Quick Start section with a one-line description: "Run once after install — audits your setup and customizes dream-studio to your project."
- Acceptance: Quick Start section shows studio-onboard as step 1 before any other command.

### T004 [P] Update coach SKILL.md — route-classify auto-invoke
- Implements: TR-G02
- Files: `skills/coach/SKILL.md`
- Depends on: none
- What: In the `route-classify` mode section, add instruction: "After classifying, if the top match has confidence ≥ 0.8, invoke it immediately via the Skill tool (do not just name it). If confidence < 0.8, present the top 3 matches with scores and ask the Director to confirm before invoking."
- Acceptance: The SKILL.md route-classify section contains the ≥ 0.8 auto-invoke rule and the < 0.8 confirmation fallback.

### T005 [P] Create hooks/lib/pack_context.py
- Implements: TR-G03
- Files: `hooks/lib/pack_context.py`
- Depends on: none
- What: New library module. `is_pack_active(pack_name: str) -> bool` — reads `active_packs` list from `~/.dream-studio/config.json` via `state.read_config()`. Returns True if the list is empty (default: all packs active) or if `pack_name` is in the list. Returns False only when the list is non-empty and the pack is absent.
- Acceptance: `is_pack_active("domains")` returns True when active_packs is [] or ["domains"]; False when active_packs is ["core", "quality"].

### T007 [P] Add quiet_mode support to hooks/lib/state.py
- Implements: TR-G03
- Files: `hooks/lib/state.py`
- Depends on: none
- What: Add `get_quiet_mode() -> int` (reads `quiet_mode` int from config, default 0) and `set_quiet_mode(turns: int) -> None` (writes to config). Convention: quiet_mode=0 means normal; quiet_mode=N means suppress advisory hooks for N more turns, decrement each turn.
- Acceptance: `set_quiet_mode(3)` writes to config; `get_quiet_mode()` returns 3; calling again returns 2 after one decrement.

### T009 [P] Add effectiveness_score field to hooks/lib/audit.py
- Implements: TR-G03
- Files: `hooks/lib/audit.py`
- Depends on: none
- What: Add optional `effectiveness_score: float | None` param to the audit record append function (default None). When provided, include it in the JSONL record. This scaffolds hook effectiveness tracking without requiring any hook to use it yet.
- Acceptance: Audit records with `effectiveness_score=0.8` include the field in the written JSONL line.

### T011 [P] Create packs/meta/hooks/on-skill-metrics.py
- Implements: TR-G04
- Files: `packs/meta/hooks/on-skill-metrics.py`
- Depends on: none
- What: New PostToolUse handler for Skill tool invocations. Reads payload from stdin, extracts `tool_input.skill` (or `tool_input.name`). Calls `hooks/lib/skill_metrics.py` logic inline (import and call `main()` equivalent with extracted skill name and model). Exits 0 always.
- Acceptance: Handler correctly extracts skill name from stdin payload and appends a record to `~/.dream-studio/state/skill-usage.jsonl`.

### T012 [P] Update README — plugin install note for settings.json hooks
- Implements: TR-G04
- Files: `README.md`
- Depends on: none
- What: In the Installation section, add a note: "After installing, merge the hooks from `.claude/settings.json` in this repo into your global `~/.claude/settings.json` to enable skill metrics and guard hooks." Link to the relevant section of the Development Workflow section.
- Acceptance: Installation section has the merge note with file path reference.

### T013 [P] Remove redundant skill_metrics hook from .claude/settings.json
- Implements: TR-G04
- Files: `.claude/settings.json`
- Depends on: none
- What: Remove the PostToolUse Skill matcher hook that calls `skill_metrics.py` directly. This becomes redundant once T010 wires it into `hooks/hooks.json` at plugin level. Keep the PreToolUse guard hooks (force-push, wrangler deploy, main push protection).
- Acceptance: `.claude/settings.json` PostToolUse section is empty or removed; PreToolUse guards remain intact.

### T014 [P] Update debug SKILL.md — mandatory auto-lesson capture
- Implements: TR-G05
- Files: `skills/debug/SKILL.md`
- Depends on: none
- What: Change the learn invocation from optional suggestion ("invoke learn: to capture it") to mandatory: "After any debug session that required ≥ 3 hypothesis iterations OR revealed a reusable pattern, invoke `learn:` before closing the session. This is not optional — draft lessons are the input to dream-studio's self-improvement loop." Also add: after the fix is committed and the GitHub issue is created, always invoke `learn:` with the debug log summary as input.
- Acceptance: Debug SKILL.md Step 6 states learn invocation as mandatory with the ≥3 iteration threshold.

### T015 [P] Create hooks/lib/lesson_threshold.py
- Implements: TR-G05
- Files: `hooks/lib/lesson_threshold.py`
- Depends on: none
- What: `get_escalation_candidates(threshold: int = 3) -> list[dict]`. Reads `~/.dream-studio/state/skill-usage.jsonl` and `meta/draft-lessons/` directory. Counts how many draft lessons reference each skill. Returns list of `{skill, lesson_count, lesson_files}` for skills where lesson_count ≥ threshold. These are candidates for Director review and skill update.
- Acceptance: Given 4 draft lesson files referencing "debug", returns debug with lesson_count=4 when threshold=3.

### T017 [P] Create workflows/self-audit.yaml
- Implements: TR-G06
- Files: `workflows/self-audit.yaml`
- Depends on: none
- What: New workflow with nodes: (1) `collect-signal` — reads `~/.dream-studio/state/skill-usage.jsonl`, `audit.jsonl`, and `skills/dream-studio-catalog.md`; (2) `audit-hooks` — finds hooks with zero audit entries in last 30 days (noise candidates); (3) `audit-routing` — reads CLAUDE.md trigger table, cross-references with skill-usage.jsonl for triggers that never matched; (4) `audit-skill-size` — checks each SKILL.md word count, flags any exceeding 800 words; (5) `audit-gotchas` — finds gotcha IDs appearing in 3+ different skills' gotchas.yml (candidates to promote to core module); (6) `synthesize` — produces ranked self-audit report to `~/.dream-studio/state/self-audit-YYYY-MM-DD.md`.
- Acceptance: Workflow YAML is valid, has all 6 nodes with correct depends_on chains, and synthesize node produces a ranked report.

### T018 [P] Create scripts/validate_analysts.py
- Implements: TR-G07
- Files: `scripts/validate_analysts.py`
- Depends on: none
- What: Script that (1) reads all `skills/*/metadata.yml` to collect the canonical skill name list; (2) reads `skills/coach/analysts/route-classifier.yml` and any other analyst YAMLs for skill references; (3) diffs: skills present in metadata but absent from analyst coverage; (4) exits 1 with diff output if any skills are uncovered; exits 0 if all skills are covered. Print: "PASS: all N skills covered" or "FAIL: N skills missing from analyst coverage: [list]".
- Acceptance: Adding a new skill metadata.yml without updating route-classifier.yml causes the script to exit 1.

### T021 [P] Add resume checkpoints to workflow_engine.py + workflow_state.py
- Implements: TR-G08
- Files: `hooks/lib/workflow_engine.py`, `hooks/lib/workflow_state.py`
- Depends on: none
- What: In `workflow_state.py`, add `completed_nodes: list[str]`, `last_completed_node: str | None`, and `resume_from: str | None` fields to the state schema. In `workflow_engine.py`, after each node completes successfully, write `completed_nodes` to checkpoint at `~/.dream-studio/state/workflow-{name}-checkpoint.json`. On workflow start, if checkpoint exists and `resume_from` is set, skip nodes already in `completed_nodes`. Checkpoint is cleared on workflow completion or abort.
- Acceptance: A workflow interrupted after node 3 of 8 resumes from node 4 when re-invoked; completed nodes are not re-run.

---

## Phase 2 — Wiring (run after Phase 1 completes)

### T002 Add on-first-run to hooks/hooks.json
- Implements: TR-G01
- Files: `hooks/hooks.json`
- Depends on: T001
- What: Add `on-first-run` as the **first** hook in the `UserPromptSubmit` array (before `on-milestone-start`). This ensures it fires before any other hook on every prompt until first-run is complete.
- Acceptance: hooks.json UserPromptSubmit array starts with on-first-run.

### T006 Add pack_context guard to on-game-validate.py
- Implements: TR-G03
- Files: `packs/domains/hooks/on-game-validate.py`
- Depends on: T005
- What: Import `pack_context` from lib. At the top of `main()`, after the existing early-exit guards, add: `if not pack_context.is_pack_active("domains"): return`. This gives users a config-level killswitch independent of the file-system Godot project detection.
- Acceptance: With `active_packs: ["core", "quality"]` in config, on-game-validate exits immediately without running any checks.

### T008 Add quiet_mode check to on-pulse.py
- Implements: TR-G03
- Files: `packs/meta/hooks/on-pulse.py`
- Depends on: T007
- What: Import `state.get_quiet_mode` and `state.set_quiet_mode`. At the top of `main()`, after the existing cooldown check: if `get_quiet_mode() > 0`, call `set_quiet_mode(get_quiet_mode() - 1)` and return. This suppresses the pulse for N turns when the user sets quiet_mode.
- Acceptance: With quiet_mode=2, on-pulse returns without output on next two runs; on third run it fires normally.

### T010 Add on-skill-metrics to hooks/hooks.json
- Implements: TR-G04
- Files: `hooks/hooks.json`
- Depends on: T011
- What: Add a new PostToolUse entry with `matcher: "Skill"` that calls `on-skill-metrics` handler. Place it after the existing Edit|Write PostToolUse block.
- Acceptance: hooks.json has a Skill-matched PostToolUse entry for on-skill-metrics.

### T016 Update on-meta-review.py — lesson threshold escalation
- Implements: TR-G05
- Files: `packs/meta/hooks/on-meta-review.py`
- Depends on: T015
- What: Import `lesson_threshold.get_escalation_candidates`. After the existing draft-lessons check, call `get_escalation_candidates(threshold=3)`. For each candidate returned, print: "⚠️ [skill] has [N] draft lessons — consider a skill update. Run: learn: promote [skill]". This surfaces skills that are accumulating lessons without being updated.
- Acceptance: With 3+ debug draft lessons, on-meta-review prints the escalation message for the debug skill.

### T019 Update Makefile — add validate-analysts target
- Implements: TR-G07
- Files: `Makefile`
- Depends on: T018
- What: Add `validate-analysts` target: `py scripts/validate_analysts.py`. Add it to the `all` or `check` composite target if one exists, or document it standalone.
- Acceptance: `make validate-analysts` runs the script and exits 0 on a fully-covered skill list.

### T022 Update workflows/fix-issue.yaml — use engine resume
- Implements: TR-G08
- Files: `workflows/fix-issue.yaml`
- Depends on: T021
- What: No node-level changes needed — T021 adds resume support at the engine level. However, update the workflow's `description` field to note that it supports resume: "Resume-safe: if interrupted, re-run to continue from last completed node." Also verify `on_failure` handling is compatible with the new checkpoint clearing.
- Acceptance: fix-issue.yaml description mentions resume support; on_failure: abort clears the checkpoint.

---

## Phase 3 — CI integration

### T020 Update .github/workflows/ci.yml — validate-analysts step
- Implements: TR-G07
- Files: `.github/workflows/ci.yml`
- Depends on: T019
- What: Add a `validate-analysts` step to the CI matrix that runs `make validate-analysts`. Place it after the `lint` step.
- Acceptance: CI YAML has a validate-analysts step; the step uses the same Python matrix as existing steps.

---

## Summary

| Phase | Tasks | Can Parallelize |
|---|---|---|
| Phase 1 | T001, T003–T005, T007, T009, T011–T015, T017–T018, T021 | All |
| Phase 2 | T002, T006, T008, T010, T016, T019, T022 | All (different files) |
| Phase 3 | T020 | Single |

**Total:** 23 tasks · 8 requirements · 3 waves
