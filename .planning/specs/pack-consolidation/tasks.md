# Pack Consolidation — Tasks

## Phase 1: Scaffolding

### T001 — Create pack router template
**Files:** `skills/templates/pack-router-template.md`
**Depends:** none
**Acceptance:** Template file exists with frontmatter pattern (name, description, argument-hint, user_invocable, args) and mode dispatch table structure. Can be copied and filled in for each pack.

---

## Phase 2: Pack Migrations
Each task creates one pack. All 6 are independent — can run in parallel [P].

### T002 [P] — Migrate core pack (9 modes)
**Files:**
- CREATE `skills/core/SKILL.md` (router)
- CREATE `skills/core/modes/` directory
- MOVE `skills/think/` → `skills/core/modes/think/`
- MOVE `skills/plan/` → `skills/core/modes/plan/`
- MOVE `skills/build/` → `skills/core/modes/build/`
- MOVE `skills/review/` → `skills/core/modes/review/`
- MOVE `skills/verify/` → `skills/core/modes/verify/`
- MOVE `skills/ship/` → `skills/core/modes/ship/`
- MOVE `skills/handoff/` → `skills/core/modes/handoff/`
- MOVE `skills/recap/` → `skills/core/modes/recap/`
- MOVE `skills/explain/` → `skills/core/modes/explain/`
**Depends:** T001
**Note:** `skills/core/` already has shared modules (git.md, format.md, etc.). The new SKILL.md and modes/ directory coexist alongside them. Do NOT move or rename the shared modules.
**Acceptance:** `skills/core/SKILL.md` is a router with 9 modes. All 9 mode directories exist under `modes/` with their full content. No orphan directories at `skills/think/`, `skills/plan/`, etc. Shared modules at `skills/core/git.md` etc. remain untouched.

### T003 [P] — Migrate quality pack (7 modes)
**Files:**
- CREATE `skills/quality/SKILL.md` (router)
- CREATE `skills/quality/modes/` directory
- MOVE `skills/debug/` → `skills/quality/modes/debug/`
- MOVE `skills/polish/` → `skills/quality/modes/polish/`
- MOVE `skills/harden/` → `skills/quality/modes/harden/`
- MOVE `skills/secure/` → `skills/quality/modes/secure/`
- MOVE `skills/structure-audit/` → `skills/quality/modes/structure-audit/`
- MOVE `skills/learn/` → `skills/quality/modes/learn/`
- MOVE `skills/coach/` → `skills/quality/modes/coach/`
**Depends:** T001
**Acceptance:** `skills/quality/SKILL.md` is a router with 7 modes. All 7 mode directories exist under `modes/`. No orphan directories at top level.

### T004 [P] — Migrate career pack (6 modes)
**Files:**
- CREATE `skills/career/SKILL.md` (router)
- CREATE `skills/career/modes/` directory
- MOVE `skills/career-ops/` → `skills/career/modes/ops/`
- MOVE `skills/career-scan/` → `skills/career/modes/scan/`
- MOVE `skills/career-evaluate/` → `skills/career/modes/evaluate/`
- MOVE `skills/career-apply/` → `skills/career/modes/apply/`
- MOVE `skills/career-track/` → `skills/career/modes/track/`
- MOVE `skills/career-pdf/` → `skills/career/modes/pdf/`
**Depends:** T001
**Note:** Mode names drop the `career-` prefix since the pack name provides namespace.
**Acceptance:** Router with 6 modes. No orphan `skills/career-*` directories at top level.

### T005 [P] — Migrate security pack (7 modes)
**Files:**
- CREATE `skills/security/SKILL.md` (router)
- CREATE `skills/security/modes/` directory
- MOVE `skills/scan/` → `skills/security/modes/scan/`
- MOVE `skills/dast/` → `skills/security/modes/dast/`
- MOVE `skills/binary-scan/` → `skills/security/modes/binary-scan/`
- MOVE `skills/mitigate/` → `skills/security/modes/mitigate/`
- MOVE `skills/comply/` → `skills/security/modes/comply/`
- MOVE `skills/netcompat/` → `skills/security/modes/netcompat/`
- MOVE `skills/security-dashboard/` → `skills/security/modes/dashboard/`
**Depends:** T001
**Note:** `security-dashboard` shortens to `dashboard` — pack name provides namespace.
**Acceptance:** Router with 7 modes. No orphan directories.

### T006 [P] — Migrate analyze pack (2 modes)
**Files:**
- BACKUP existing `skills/analyze/SKILL.md` content
- MOVE existing analyze skill content → `skills/analyze/modes/multi/`
  - Move: SKILL.md, config.yml, gotchas.yml, metadata.yml, changelog.md
  - Keep in place: `analysts/` directory (shared across modes), `modes.yml`
- CREATE new `skills/analyze/SKILL.md` (router, replaces old one)
- MOVE `skills/domain-re/` → `skills/analyze/modes/domain-re/`
**Depends:** T001
**Note:** The `analysts/` directory stays at `skills/analyze/analysts/` since both modes reference it. The `modes.yml` file stays at pack level for analyst configuration.
**Acceptance:** Router with 2 modes (multi, domain-re). `analysts/` accessible from both modes. No orphan `skills/domain-re/` directory.

### T007 [P] — Migrate domains pack (6 modes)
**Files:**
- CREATE `skills/domains/SKILL.md` (router)
- CREATE `skills/domains/modes/` directory
- MOVE `skills/game-dev/` → `skills/domains/modes/game-dev/`
- MOVE `skills/saas-build/` → `skills/domains/modes/saas-build/`
- MOVE `skills/mcp-build/` → `skills/domains/modes/mcp-build/`
- MOVE `skills/dashboard-dev/` → `skills/domains/modes/dashboard-dev/`
- MOVE `skills/client-work/` → `skills/domains/modes/client-work/`
- MOVE `skills/design/` → `skills/domains/modes/design/`
**Depends:** T001
**Note:** `skills/domains/` already has reference data directories (powerbi/, data/, etc.). These stay in place alongside the new SKILL.md and modes/.
**Acceptance:** Router with 6 modes. Existing reference data untouched. No orphan directories.

---

## Phase 3: Configuration Updates

### T008 — Update packs.yaml and plugin.json
**Files:**
- EDIT `packs.yaml` — update skill lists to reflect pack names, add explain to core
- EDIT `.claude-plugin/plugin.json` — bump version to 0.3.0, update description
**Depends:** T002-T007
**Acceptance:** packs.yaml lists 7 packs with correct mode references. plugin.json shows version 0.3.0.

### T009 — Update project CLAUDE.md routing table
**Files:**
- EDIT `CLAUDE.md` — replace 35-row routing table with 7-row pack-based table
**Depends:** T008
**Acceptance:** Routing table has 7 entries (one per pack). Each entry lists all trigger keywords for all modes in that pack. `<!-- BEGIN AUTO-ROUTING -->` / `<!-- END AUTO-ROUTING -->` markers preserved.

### T010 — Update sync-cache.ps1
**Files:**
- EDIT `scripts/sync-cache.ps1` — ensure it handles nested modes/ directories correctly
**Depends:** T002-T007
**Acceptance:** Running sync-cache.ps1 copies all pack directories (including modes/ subdirectories) to the plugin cache. Verify with `ls` of cache after run.

---

## Phase 4: External Updates

### T011 — Update user's global CLAUDE.md
**Files:**
- EDIT `~/.claude/CLAUDE.md` — update routing table to use pack:mode invocation pattern
**Depends:** T009
**Acceptance:** Global routing table matches project CLAUDE.md. All `dream-studio:<old-skill>` references replaced with `dream-studio:<pack>` + mode argument.

### T012 — Update README.md with new invocation examples
**Files:**
- EDIT `README.md` — document pack-based invocation, explain mode dispatch
**Depends:** T009
**Acceptance:** README shows correct invocation examples for each pack. Includes "Getting Started" section showing how modes work.

---

## Phase 5: Verification

### T013 — Reinstall plugin and verify discovery
**Steps:**
1. Run sync-cache.ps1 or `claude plugins install file://...`
2. Start new Claude Code session
3. Check available skills list — should show exactly 7 dream-studio skills
4. Verify no old skill names appear (no dream-studio:think, dream-studio:debug, etc.)
**Depends:** T010, T011
**Acceptance:** All 7 pack skills visible in available skills list. Total dream-studio description budget < 600 chars.

### T014 — Smoke test mode dispatch
**Steps:**
1. Invoke each pack with explicit mode: `/dream-studio:core think`, `/dream-studio:quality debug`, etc.
2. Invoke each pack without mode, using trigger keywords: "think: should we use React?" → should route to core/think
3. Verify the correct mode's SKILL.md content loads in each case
**Depends:** T013
**Acceptance:** All modes dispatch correctly via explicit argument AND keyword inference.

---

## Summary

| Phase | Tasks | Parallel? | Est. files changed |
|---|---|---|---|
| 1 Scaffolding | T001 | — | 1 |
| 2 Migrations | T002-T007 | yes [P] | ~37 directories moved |
| 3 Config | T008-T010 | sequential | 4 |
| 4 External | T011-T012 | yes [P] | 2 |
| 5 Verify | T013-T014 | sequential | 0 |
| **Total** | **14 tasks** | | |
