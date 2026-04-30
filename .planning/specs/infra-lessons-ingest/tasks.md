# Tasks: Infrastructure, Lesson Harvest, Repo-Ingest Workflow
**Date:** 2026-04-29
**Plan:** .planning/specs/infra-lessons-ingest/plan.md

---

## Phase 1 — Config Fixes (TR-001, TR-005)

### T001 — Fix global config.json
**Implements:** TR-001
**Files:** `~/.dream-studio/config.json`
**Depends on:** none
**Acceptance:** config.json contains director_name, claude_memory_path, schema_version=1, github_repo preserved

### T002 — Set harvest.projects_root in learn/config.yml
**Implements:** TR-001
**Files:** `skills/learn/config.yml`
**Depends on:** none  
**Acceptance:** `harvest.projects_root` set to `C:\Users\Dannis Seay\builds`; `extra_paths` set to `["C:\\Users\\Dannis Seay\\dannis-naomi"]`

**[P with T001]** — different files, no dependency

### T003 — Create ARCHITECTURE.md documenting packs/ vs skills/
**Implements:** TR-005
**Files:** `ARCHITECTURE.md` (new, dream-studio root)
**Depends on:** none
**Acceptance:** ARCHITECTURE.md explains: packs/ = Python hook runtime (do not edit without testing), skills/ = Claude guidance loaded by on-skill-load.py, their relationship, and how adding a new skill requires both layers

**[P with T001, T002]**

---

## Phase 2 — Lesson Triage (TR-002)

### T004 — Dedup check: do gotchas already capture high-context pattern?
**Implements:** TR-002
**Files:** `skills/build/gotchas.yml`, `skills/debug/gotchas.yml`, `skills/plan/gotchas.yml` (read only)
**Depends on:** none
**Acceptance:** Confirm whether "proactively compact/checkpoint when context approaches 75%" already exists in any gotchas.yml; record finding for T005

**[P with Phase 1 tasks]**

### T005 — Bulk reject 22 draft lessons
**Implements:** TR-002
**Files:** 18 `handoff-*` + 4 `theme-sonnet-*` files in `~/.dream-studio/meta/draft-lessons/`
**Depends on:** T004
**Acceptance:** All 22 moved to `~/.dream-studio/meta/lessons/` with `Status: REJECTED` prepended; no content modified

### T006 — Evaluate and promote/reject the 4 high-context theme lessons
**Implements:** TR-002
**Files:** 4 `theme-high-context-*` in draft-lessons/; optionally build/debug/plan gotchas.yml
**Depends on:** T004, T005
**Acceptance:**
- If dedup check (T004) shows the pattern IS already in gotchas → move all 4 to lessons/ as REJECTED
- If NOT in gotchas → add one new entry to `skills/build/gotchas.yml` best_practices: "If context approaches 75%, /compact before starting the next task group"; move all 4 to lessons/ as PROMOTED

---

## Phase 3 — Repo-Ingest Workflow (TR-003, TR-004)

### T007 — Create ingest-log.yml schema
**Implements:** TR-004
**Files:** `skills/domains/ingest-log.yml` (new)
**Depends on:** none
**Acceptance:** File contains YAML schema with fields: repo_name, url, stars, domain, commit_or_date_analyzed, files_touched, refresh_due, notes; plus entries for each existing domain YAML (backfill with analysis date 2026-04-28 and refresh_due 2026-10-28)

**[P with Phase 1 and 2 tasks that don't share files]**

### T008 — Build `workflow: repo-ingest` node in workflow/SKILL.md
**Implements:** TR-003
**Files:** `skills/workflow/SKILL.md`
**Depends on:** T007
**Acceptance:** workflow/SKILL.md contains a `repo-ingest` node section with:
  - Trigger: `workflow: repo-ingest <url-or-path>`
  - 5-step process (domain detect → pattern extract → YAML write → ingest-log entry → refresh flag)
  - Domain routing table (how to pick the right YAML)
  - Anti-bloat rules (dedup before writing, ≤10 patterns per run)
  - Output: updated domain YAML + ingest-log.yml entry

---

## Phase 4 — Skill Depth Policy (TR-006)

### T009 — Update STRUCTURE.md with JIT enrichment policy
**Implements:** TR-006
**Files:** `skills/STRUCTURE.md`
**Depends on:** none
**Acceptance:** STRUCTURE.md contains a "Skill Depth Policy" section stating: enrich on first real use only; learn + repo-ingest are the ongoing depth builders; sprint enrichment is explicitly prohibited

**[P with Phase 3]**

### T010 — Fix polish/SKILL.md to reference its checklists
**Implements:** TR-006
**Files:** `skills/polish/SKILL.md`
**Depends on:** none
**Acceptance:** Steps section in SKILL.md explicitly references `checklists/` directory; at minimum names the 4 available checklists (web-design.yml, fluent-design-compliance.yml, material-design-compliance.yml, data-viz-accessibility.yml)

**[P with T009]**

### T011 — Add "JIT enrichment pending" notice to thin skills
**Implements:** TR-006
**Files:** `skills/mcp-build/SKILL.md`, `skills/dashboard-dev/SKILL.md`, `skills/saas-build/SKILL.md`
**Depends on:** none
**Acceptance:** Each gets a `## Depth Status` section at bottom: "This skill enriches JIT — examples and gotchas will be added from the first real build that uses it."

**[P with T009, T010]** — different files

---

## Summary

| Task | Implements | Phase | Parallel? | Effort |
|------|-----------|-------|-----------|--------|
| T001 | TR-001 | 1 | P with T002, T003 | 5 min |
| T002 | TR-001 | 1 | P with T001, T003 | 5 min |
| T003 | TR-005 | 1 | P with T001, T002 | 15 min |
| T004 | TR-002 | 2 | P with Phase 1 | 5 min |
| T005 | TR-002 | 2 | after T004 | 10 min |
| T006 | TR-002 | 2 | after T004, T005 | 10 min |
| T007 | TR-004 | 3 | P with Phase 1-2 non-conflicting | 20 min |
| T008 | TR-003 | 3 | after T007 | 30 min |
| T009 | TR-006 | 4 | P with T010, T011 | 10 min |
| T010 | TR-006 | 4 | P with T009, T011 | 10 min |
| T011 | TR-006 | 4 | P with T009, T010 | 10 min |

**Total: ~2 hours. No tasks share files within the same wave.**

---

## Execution waves

**Wave 1 (parallel):** T001, T002, T003, T004, T007
**Wave 2 (parallel):** T005 (after T004), T008 (after T007), T009, T010, T011
**Wave 3 (sequential):** T006 (after T005)
