# Tasks: dream-studio Onboarding

**Input**: Design documents from `.planning/specs/onboarding/`
**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create skill directory structure at `skills/setup/` with SKILL.md, skill.ts, modes/ subdirectory

**Acceptance**: Directory structure exists with placeholder files

---

- [x] T002 [P] Create tool registry at `skills/setup/tool-registry.yml` with metadata for 6 tools (gh, firecrawl, playwright, npm, python, node)

**Acceptance**: YAML file contains: name, description, detect_command (per-platform), install_command (per-platform), what_it_unlocks, docs_url for each tool

---

- [x] T003 [P] Define setup preferences JSON schema at `.dream-studio/setup-prefs.json` with fields: onboarding_path (wizard/as-needed/read-docs), first_run_complete (bool), tools (per-tool state: installed/skipped/never)

**Acceptance**: JSON schema documented in plan.md, example file created

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 [US1] Implement first-run detection logic in `skills/setup/skill.ts` — checks if `.dream-studio/setup-prefs.json` exists, if not triggers first-run prompt

**Acceptance**: Function `isFirstRun()` returns true when setup-prefs.json missing, false when it exists

---

- [x] T005 [US1] Create first-run prompt in `skills/setup/skill.ts` — displays "First time using dream-studio! Run full setup wizard, or prompt as-needed when skills need tools? [wizard/as-needed/read-docs]" and captures user choice

**Acceptance**: Prompt appears on first skill invocation, user can select one of three choices, selection is returned

---

- [x] T006 [US1] Implement preference save/load functions in `skills/setup/skill.ts` — `savePreference(path, toolStates)`, `loadPreference()` — reads/writes `.dream-studio/setup-prefs.json`

**Acceptance**: Functions correctly write and read JSON file with schema from T003

---

- [x] T007 [P] [US5] Create core module `skills/core/web.md` with fallback logic: (1) detect if Firecrawl installed, (2) if yes use Firecrawl, (3) if no use scraper-mcp if available, (4) else use WebSearch/WebFetch

**Acceptance**: Markdown file documents detection logic + fallback chain, includes code examples for skill integration

---

- [x] T008 [P] [US5] Update core module `skills/core/git.md` to add gh CLI detection logic: (1) detect if `gh` command exists, (2) if yes use `gh`, (3) if no prompt user for manual GitHub ops or use GitHub API fallback

**Acceptance**: git.md includes new "gh CLI Detection" section with fallback instructions

---

- [x] T009 [US5] Create core module `skills/core/setup.md` with functions: `detectTool(toolName)` (cross-platform detection using `which`/`where`), `getToolStatus(toolName)` (returns installed/missing/partial), `shouldPromptForTool(toolName)` (checks user preferences)

**Acceptance**: Markdown file documents detection functions with Windows/Mac/Linux command differences

---

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 + 5 (Priority: P1) 🎯 MVP

**Goal**: Skills work immediately with zero setup via fallbacks + first-run prompt

**Independent Test**: Clone dream-studio fresh, run `dream-studio:core think`, verify: (1) first-run prompt appears, (2) select any option, (3) skill completes successfully using fallbacks

**Note**: User Stories 1 and 5 are fully implemented in Phase 2 (Foundational) since they're prerequisites for all other work. This phase is complete when Phase 2 is done.

**Checkpoint**: At this point, new users can use dream-studio with zero setup (fallback mode)

---

## Phase 4: User Story 2 (Priority: P2) - Setup Wizard

**Goal**: Interactive wizard detects tools, guides installation

**Independent Test**: Run `dream-studio:setup` on clean machine, verify: (1) detects all 6 tools as missing, (2) offers install for each, (3) shows what each unlocks

### Implementation for User Story 2

- [x] T010 [US2] Write `skills/setup/SKILL.md` with three modes: wizard (full setup), status (show current state), jit (just-in-time prompts)

**Acceptance**: SKILL.md documents all three modes with trigger keywords, examples, and integration instructions

---

- [x] T011 [US2] Implement status command in `skills/setup/modes/status.md` — reads tool-registry.yml, runs detectTool() for each, outputs table: Tool | Status | What It Unlocks | Install Command

**Acceptance**: Running `dream-studio:setup status` displays formatted table with correct detection for all tools

---

- [x] T012 [US2] Implement wizard mode in `skills/setup/modes/wizard.md` — (1) detect all tools, (2) for each missing tool show what it unlocks, (3) prompt "Install X? [y/n/skip]", (4) if yes run install command, (5) verify post-install, (6) save state to setup-prefs.json

**Acceptance**: Wizard completes successfully, partially installing some tools, saving progress to setup-prefs.json

---

- [x] T013 [US2] Add tool-specific detection logic in `skills/setup/skill.ts` — per-tool functions: `detectGh()`, `detectFirecrawl()`, `detectPlaywright()` with platform-specific commands (Windows: `where`, Unix: `which`) and version verification (`--version` check)

**Acceptance**: Each detection function returns {installed: bool, version: string|null, path: string|null}

---

- [x] T014 [US2] Add Firecrawl auth flow in wizard mode — if Firecrawl installed but no API key, prompt user: "Firecrawl needs API key. Open browser to authenticate? [y/n]", if yes run browser auth flow from Firecrawl skill.md

**Acceptance**: Wizard detects partial Firecrawl install, offers auth flow, saves API key to .env or setup-prefs.json

---

**Checkpoint**: At this point, User Story 2 (wizard) should be fully functional and testable independently

---

## Phase 5: User Story 3 (Priority: P2) - Just-In-Time Prompts

**Goal**: Progressive enhancement via JIT prompts when skills need missing tools

**Independent Test**: Choose "as-needed" on first run, invoke web scraping skill, verify: (1) prompt appears "This skill works better with Firecrawl. Install now? [y/n/never]", (2) choice is saved

### Implementation for User Story 3

- [x] T015 [US3] Implement JIT prompt mode in `skills/setup/modes/jit.md` — function `promptForTool(toolName)` checks if already prompted (from setup-prefs.json), if not displays prompt, captures choice, saves to preferences

**Acceptance**: JIT prompt appears once per tool, "never" choice prevents future prompts

---

- [x] T016 [US3] Add per-tool "never ask" preference tracking in setup-prefs.json — extend schema with `tools.<toolName>.never_prompt: bool`

**Acceptance**: setup-prefs.json schema updated, preferences saved correctly after "never" selection

---

- [x] T017 [US3] Update `skills/core/web.md` to integrate JIT prompt — before falling back to WebSearch, check if user preference is "as-needed", if yes call `promptForTool('firecrawl')`, if user approves install then retry with Firecrawl

**Acceptance**: web.md fallback logic includes JIT prompt step, only fires when user chose "as-needed" path

---

**Checkpoint**: At this point, User Stories 2 AND 3 should both work independently

---

## Phase 6: User Story 4 (Priority: P3) - README Documentation

**Goal**: Manual setup path for "read first" users

**Independent Test**: Follow README "Standard" profile instructions, run `dream-studio:setup status`, verify gh and basic tools show as installed

### Implementation for User Story 4

- [x] T018 [US4] Write README setup section with three profiles: **Minimal** (nothing to install, skills use fallbacks), **Standard** (gh CLI + npm/python/node), **Full** (everything: gh + Firecrawl + Playwright)

**Acceptance**: README includes per-platform install commands for each profile, explains what each unlocks

---

- [x] T019 [P] [US4] Add per-tool documentation in README — for each of 6 tools: what it is, why you'd want it, which skills benefit, install command (Windows/Mac/Linux), verification command

**Acceptance**: README has table or sections for all 6 tools with complete documentation

---

- [x] T020 [US4] Add "If using Cursor/Copilot" note in README — placeholder for future adapter integration, points to (future) `adapters/README.md`

**Acceptance**: README includes note: "Using Cursor or Copilot? After setup, run `make adapters` to generate platform-specific config."

---

**Checkpoint**: All user stories should now be independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T021 [P] Add wizard cancellation handling — if user exits mid-wizard, save partial progress, next wizard run resumes from last completed tool

**Acceptance**: Cancel wizard after 2 tools installed, re-run wizard, verify it skips installed tools and continues

---

- [x] T022 [P] Add version mismatch warnings in status command — if tool installed but version is outdated (from tool-registry.yml min_version), show warning with upgrade command

**Acceptance**: Status command shows "(outdated, upgrade with: ...)" for tools with old versions

---

- [x] T023 Cross-platform testing verification — test on Windows, Mac, Linux: (1) first-run detection, (2) tool detection, (3) wizard install commands

**Acceptance**: All three platforms complete wizard successfully, status command shows correct state

---

- [x] T024 Error handling for missing .dream-studio directory — if `.dream-studio/` doesn't exist when saving preferences, create it automatically

**Acceptance**: First-run on system without `.dream-studio/` creates directory + setup-prefs.json

---

- [x] T025 [P] Update `skills/dream-studio-catalog.md` to add setup skill entry with status, version, description

**Acceptance**: Catalog includes setup skill with correct metadata

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories 1+5 (Phase 3)**: Implemented in Phase 2 - no additional tasks
- **User Story 2 (Phase 4)**: Depends on Foundational (Phase 2)
- **User Story 3 (Phase 5)**: Depends on Foundational (Phase 2) + User Story 2 (Phase 4) for JIT prompt integration
- **User Story 4 (Phase 6)**: Depends on User Story 2 (Phase 4) for status command reference
- **Polish (Phase 7)**: Depends on all user stories being complete

### Task Dependencies Within Phases

**Phase 1 (Setup)**:
- T001 → all other tasks (need directory structure first)
- T002, T003 can run in parallel after T001

**Phase 2 (Foundational)**:
- T004, T005 → T006 (detection and prompt before save/load)
- T007, T008, T009 can run in parallel (different files)
- T006 must complete before any user story work (all stories save preferences)

**Phase 4 (Wizard)**:
- T010 → T011, T012 (SKILL.md before modes)
- T011, T013 can run in parallel
- T012 → T014 (wizard mode before auth flow)

**Phase 5 (JIT)**:
- T015 → T016 (prompt logic before preference schema extension)
- T016 → T017 (schema updated before web.md integration)

**Phase 6 (README)**:
- T018, T019 can run in parallel
- T020 independent (can run anytime)

### Parallel Opportunities

- Phase 1: T002, T003 after T001
- Phase 2: T007, T008, T009 in parallel (different files)
- Phase 4: T011, T013 in parallel
- Phase 6: T018, T019 in parallel
- Phase 7: T021, T022, T025 in parallel

---

## Implementation Strategy

### MVP First (User Stories 1 + 5 Only - Fallback Mode)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (includes US1 + US5)
3. **STOP and VALIDATE**: Test first-run prompt + fallback mode
4. This is MVP — skills work with zero setup

### Incremental Delivery

1. MVP (Phases 1-3) → Test first-run + fallbacks
2. Add Phase 4 (Wizard) → Test full setup path
3. Add Phase 5 (JIT) → Test progressive enhancement
4. Add Phase 6 (README) → Test manual setup
5. Add Phase 7 (Polish) → Cross-platform verification

### Parallel Team Strategy

With multiple developers:

1. Team completes Phases 1-2 together (Foundation)
2. Once Foundational is done:
   - Developer A: Phase 4 (Wizard)
   - Developer B: Phase 5 (JIT)
   - Developer C: Phase 6 (README)
3. Phases complete and integrate independently

---

## dream-studio Integration

**Execution via**: `dream-studio:build` skill

**Task Tracking**: Use TaskCreate/TaskUpdate to track progress

**Checkpoints**: Pause at each checkpoint to verify independently

**Commit Strategy**: Commit after each task or logical group

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Phase 2 (Foundational) includes US1 + US5 since they're prerequisites
- US1 and US5 have no separate implementation phase — they're built into Foundation
