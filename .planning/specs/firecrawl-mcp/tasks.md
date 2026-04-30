# Tasks: Firecrawl MCP + Doc Alignment

**Input**: `.planning/specs/firecrawl-mcp/plan.md`, `spec.md`, `doc-audit.md`
**Prerequisites**: Approved spec, approved plan

---

## Phase 1: Debug Firecrawl MCP (Investigation)

**Purpose**: Identify why Firecrawl MCP tools don't appear in deferred tools list and fix

- [ ] T001 [US1] Debug Firecrawl MCP loading — check Claude Code MCP debug output, test server handshake, identify root cause
  - **File**: N/A (investigation)
  - **Acceptance**: Root cause identified and documented, or fix applied
  - **Depends on**: Nothing

- [ ] T002 [US1] Verify actual tool name prefix when Firecrawl loads (e.g., `mcp__firecrawl__*` vs `mcp__firecrawl-mcp__*`)
  - **File**: N/A (investigation — run `ToolSearch("firecrawl")`)
  - **Acceptance**: Verified prefix documented for use in subsequent tasks
  - **Depends on**: T001

**Checkpoint**: Firecrawl MCP loading understood. Verified tool prefix known. Proceed to doc edits.

---

## Phase 2: Web Access Module (FR-003, FR-004, FR-005, FR-009)

**Purpose**: Align web.md with verified Firecrawl MCP tool names and add new capabilities

- [ ] T003 [US1] [US3] Update `skills/core/web.md` — detection logic, tool names, add search/extract/map sections, update capability matrix
  - **File**: `skills/core/web.md`
  - **Acceptance**: Detection checks use verified prefix; capability matrix has Search and Extract rows; scraper-mcp remains Tier 2
  - **Depends on**: T002

---

## Phase 3: Tool Registry + Reference Docs (FR-006, FR-008, FR-010)

**Purpose**: Update tool metadata and setup skill to reflect MCP server approach

- [ ] T004 [P] [US2] Update `skills/setup/tool-registry.yml` — change Firecrawl entry from `pip install firecrawl-py` to MCP server detection
  - **File**: `skills/setup/tool-registry.yml`
  - **Acceptance**: detect_command checks MCP server availability; install_command references npm; what_it_unlocks is current
  - **Depends on**: T002

- [ ] T005 [P] [US2] Update `docs/tool-reference.md` — Firecrawl entry with MCP server install, verify, and skill benefit table
  - **File**: `docs/tool-reference.md`
  - **Acceptance**: Install shows MCP server config; verify step checks deferred tools or npx; no reference to `firecrawl --version`
  - **Depends on**: T002

- [ ] T006 [P] [US4] Update setup wizard and JIT SKILL.md to detect existing MCP config instead of offering pip install
  - **Files**: `skills/setup/modes/wizard/SKILL.md`, `skills/setup/modes/jit/SKILL.md`
  - **Acceptance**: Wizard detects `firecrawl` key in `mcpServers` config; JIT checks MCP config before offering install
  - **Depends on**: T002

**Checkpoint**: All Firecrawl-specific docs aligned. Tool registry accurate.

---

## Phase 4: README + Stale Doc Fixes (FR-007 + doc audit)

**Purpose**: Update README and fix stale documentation items

- [ ] T007 [US2] Update `README.md` — Full Profile Firecrawl section (MCP server config) + add MCP Servers subsection to setup profiles
  - **File**: `README.md`
  - **Acceptance**: Full Profile shows MCP server JSON config; MCP Servers subsection lists firecrawl + scraper-mcp with purpose
  - **Depends on**: T002

- [ ] T008 [P] Rewrite `STRUCTURE.md` to match current pack-based directory layout (`skills/<pack>/modes/<mode>/`)
  - **File**: `STRUCTURE.md`
  - **Acceptance**: Directory tree matches `ls -R skills/`; no references to flat skill paths
  - **Depends on**: Nothing

- [ ] T009 [P] Fix `CONTRIBUTING.md` branch prefix — `feature/` → `feat/`
  - **File**: `CONTRIBUTING.md`
  - **Acceptance**: All branch prefix references match CLAUDE.md convention (`feat/`, `fix/`, `chore/`)
  - **Depends on**: Nothing

- [ ] T010 [P] Create `.github/PULL_REQUEST_TEMPLATE.md` from CONTRIBUTING.md checklist
  - **File**: `.github/PULL_REQUEST_TEMPLATE.md` (new)
  - **Acceptance**: Template includes PR checklist items from CONTRIBUTING.md; auto-populates on `gh pr create`
  - **Depends on**: Nothing

- [ ] T011 [P] Verify CHANGELOG.md has entries for PRs #46 (onboarding) and #48 (workflow coverage)
  - **File**: `CHANGELOG.md`
  - **Acceptance**: Both PRs have entries under appropriate version section; add if missing
  - **Depends on**: Nothing

**Checkpoint**: All documentation current and consistent.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1** (Debug): No dependencies — start immediately
- **Phase 2** (web.md): Depends on T002 (need verified tool prefix)
- **Phase 3** (Registry/Docs): Depends on T002 (need verified tool prefix)
- **Phase 4** (README/Stale): T007 depends on T002; T008-T011 have no dependencies

### Parallel Opportunities

```
Phase 1:  T001 → T002
                    ↓
Phase 2:          T003
Phase 3:          T004 [P] T005 [P] T006
Phase 4:          T007
                  T008 [P] T009 [P] T010 [P] T011  ← independent, can start immediately
```

**Wave 1** (immediate): T001
**Wave 2** (after T001): T002 + T008 + T009 + T010 + T011
**Wave 3** (after T002): T003 + T004 + T005 + T006 + T007

### Commit Strategy

1. **Commit 1**: T008 + T009 + T010 + T011 — `docs: fix stale structure, branch prefix, add PR template`
2. **Commit 2**: T003 + T004 + T005 + T006 — `feat: align Firecrawl MCP detection and tool docs`
3. **Commit 3**: T007 — `docs: update README setup profiles with MCP server config`

---

## Summary

| Task | Phase | Parallel | File(s) | Est |
|---|---|---|---|---|
| T001 | 1 | — | N/A | 15m |
| T002 | 1 | — | N/A | 5m |
| T003 | 2 | — | web.md | 20m |
| T004 | 3 | P | tool-registry.yml | 10m |
| T005 | 3 | P | tool-reference.md | 15m |
| T006 | 3 | P | wizard + jit SKILL.md | 15m |
| T007 | 4 | — | README.md | 20m |
| T008 | 4 | P | STRUCTURE.md | 25m |
| T009 | 4 | P | CONTRIBUTING.md | 2m |
| T010 | 4 | P | PR template (new) | 10m |
| T011 | 4 | P | CHANGELOG.md | 5m |
| **Total** | | | **10 files** | **~2.5h** |
