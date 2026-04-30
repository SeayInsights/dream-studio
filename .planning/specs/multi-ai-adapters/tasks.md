# Tasks: Multi-AI Adapter Build System

**Input**: `.planning/specs/multi-ai-adapters/plan.md` (required), `spec.md` (required)
**Prerequisites**: plan.md approved by Director
**Tests**: Not included in v1 — adapter output is verified by manual smoke test after build

**Organization**: Tasks are grouped by user story so each story's adapter can be implemented and validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story this task belongs to
- Exact file paths included in every task description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffolding and configuration that all three adapters depend on. Must be complete before any adapter work begins.

- [ ] T001 Create `scripts/adapters_config.yml` — platform registry with entries for `cursor`, `copilot`, and `system-prompt` (each entry: `name`, `template`, `output_path`, `include_domains` flag)
- [ ] T002 Create `scripts/adapter_templates/` directory with `README.md` — document the three required fields every template must expose (skill_name, triggers, workflow_steps) and the one-template-one-config-entry contract (SC-005)
- [ ] T003 Write `scripts/build_adapters.py` core extraction layer — implement `discover_skills()` (glob `skills/*/modes/*/SKILL.md`), `parse_skill(path)` (extract frontmatter triggers, description, workflow steps from body), and `load_gotchas(skill_dir)` (parse `gotchas.yml` avoid entries; return empty list if missing or empty) — SKILL.md files must not be modified (FR-002, FR-003, FR-009)

**Checkpoint**: Extraction layer ready — `discover_skills()` returns correct count, `parse_skill()` returns structured data for one skill

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build runner, logging, token estimation, and entry points that all three adapter generators call.

**Note**: T003 (Phase 1) must be complete before this phase begins. T004–T007 share no files and can run in parallel after T003.

- [ ] T004 [P] Write `scripts/build_adapters.py` Jinja2 render engine — implement `render_adapter(platform_cfg, skills, domains)` that loads the correct `.j2` template from `scripts/adapter_templates/`, renders it with the extracted skill data, and writes to `dist/adapters/<platform>/` (creates subdirs as needed); depends on T003
- [ ] T005 [P] Write `scripts/build_adapters.py` domain loader — implement `load_domains()` to glob `skills/domains/**/*.md` and `skills/domains/**/*.yml`, read content, skip malformed YAML with logged error (edge case FR-011); depends on T003
- [ ] T006 [P] Write `scripts/build_adapters.py` token estimator — implement `estimate_tokens(text)` using `len(text) // 4` approximation with optional `tiktoken` import fallback; implement truncation logic (gotchas first, then workflow step summaries) for system-prompt budget enforcement (FR-012, SC-003); depends on T003
- [ ] T007 Write `scripts/build_adapters.py` CLI entry point — implement `main()` with `argparse`: `--platform <name>` flag for partial rebuild (FR-007), full logging output (skills processed count, skipped list with reasons, output files written, token estimate per adapter) (FR-008), reads `scripts/adapters_config.yml` to determine which platforms to build; depends on T004, T005, T006

**Checkpoint**: `py scripts/build_adapters.py --help` runs without error; `py scripts/build_adapters.py --platform cursor` exits gracefully (even if templates not yet written)

---

## Phase 3: User Story 1 — Cursor Adapter (Priority: P1) — MVP

**Goal**: Cursor users get a `.cursorrules` file with all skill trigger keywords, pipeline routing, and top gotchas.

**Independent Test**: Delete `dist/adapters/cursor/`. Run `make adapters`. Verify `dist/adapters/cursor/.cursorrules` exists and contains trigger keywords from at least 35 skills (SC-002) and at least 3 gotchas from `skills/core/modes/build/gotchas.yml`.

### Implementation for User Story 1

- [ ] T008 [P] [US1] Create `scripts/adapter_templates/cursor.j2` — Jinja2 template that renders Cursor XML `<rule>` blocks: one block per skill with `<description>` (skill name), `<globs>` (all file types), and `<instructions>` (trigger keywords + numbered workflow steps); gotchas rendered as `<avoid>` sub-elements; omit gotchas block if list is empty (edge case)
- [ ] T009 [US1] Add `make adapters` target to `Makefile` — target calls `py scripts/build_adapters.py`; also add `make adapters PLATFORM=cursor` shorthand; depends on T007

**Checkpoint**: `make adapters` produces `dist/adapters/cursor/.cursorrules`; file contains `<rule>` XML blocks; grep for 5 known skill trigger keywords returns matches

---

## Phase 4: User Story 2 — Copilot Adapter (Priority: P2)

**Goal**: Copilot users get a `.github/copilot-instructions.md` with Power Platform domain knowledge, security gotchas, and workflow routing.

**Independent Test**: Run `make adapters`. Verify `dist/adapters/copilot/.github/copilot-instructions.md` exists and contains DAX pattern content sourced from `skills/domains/powerbi/`.

### Implementation for User Story 2

- [ ] T010 [P] [US2] Create `scripts/adapter_templates/copilot.j2` — Jinja2 template that renders flat markdown: H2 section per skill with trigger keywords as a bullet list and workflow steps as a numbered list; H2 `Domain Knowledge` section rendered from domain files when `include_domains: true` in config; omit empty gotchas sections (edge case)
- [ ] T011 [US2] Smoke-test Copilot adapter output — run `py scripts/build_adapters.py --platform copilot` and verify `dist/adapters/copilot/.github/copilot-instructions.md` exists, contains `## ` headings for at least 10 skills, and contains domain content from `skills/domains/powerbi/`; log any skills skipped due to missing frontmatter triggers; depends on T010, T007

**Checkpoint**: `dist/adapters/copilot/.github/copilot-instructions.md` present; file passes a manual spot-check for DAX patterns section

---

## Phase 5: User Story 3 — System-Prompt Adapter (Priority: P3)

**Goal**: `dist/adapters/system-prompt/system-prompt.md` — injectable into any LLM, under 8,000 tokens, covering all skills and domain knowledge.

**Independent Test**: Run `make adapters`. Verify `dist/adapters/system-prompt/system-prompt.md` exists, is under 8,000 tokens (`estimate_tokens()` value logged), and contains content from at least 10 distinct skills.

### Implementation for User Story 3

- [ ] T012 [P] [US3] Create `scripts/adapter_templates/system-prompt.j2` — Jinja2 template that renders a single dense markdown document: routing table (skill → triggers), per-skill workflow steps, all gotchas, domain knowledge appendix; template exposes truncation hooks so `estimate_tokens()` can trim gotchas then workflow summaries if 8K budget exceeded (FR-006, FR-011, SC-003)
- [ ] T013 [US3] Smoke-test system-prompt adapter output — run `py scripts/build_adapters.py --platform system-prompt` and verify: file exists, logged token estimate is < 8,000, content spans ≥ 10 skills; verify `--platform system-prompt` only regenerates that adapter (partial rebuild, FR-007); depends on T012, T007

**Checkpoint**: System-prompt adapter present; token estimate < 8,000 in build log; partial rebuild flag works

---

## Phase 6: Polish and Cross-Cutting Concerns

**Purpose**: Gitignore, requirements, and template authoring guide — shared concerns that don't belong to any single story.

- [ ] T014 [P] Add `dist/` to `.gitignore` — append `dist/` entry to `.gitignore` (or create file if absent); verify `git status` shows `dist/adapters/` as ignored after running `make adapters`
- [ ] T015 [P] Add `Jinja2>=3.1` and `PyYAML>=6.0` to `requirements.txt` — append both entries; note optional `tiktoken` in a comment for precise token counting

**Checkpoint**: `git status` shows no untracked `dist/` files after a full `make adapters` run; `pip install -r requirements.txt` succeeds

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately; T001 and T002 are parallel
- **Phase 2 (Foundational)**: Depends on T003 completion; T004, T005, T006 are parallel; T007 depends on all three
- **Phase 3 (US1)**: T008 depends on T004 (render engine); T009 depends on T007 (CLI entry point)
- **Phase 4 (US2)**: T010 depends on T004; T011 depends on T010 and T007
- **Phase 5 (US3)**: T012 depends on T004, T005, T006; T013 depends on T012 and T007
- **Phase 6 (Polish)**: T014 and T015 are parallel; no blocking dependencies; run alongside or after Phase 3

### File Ownership (no two tasks share a write target)

| File | Owner Task |
|------|------------|
| `scripts/adapters_config.yml` | T001 |
| `scripts/adapter_templates/README.md` | T002 |
| `scripts/build_adapters.py` | T003, T004, T005, T006, T007 (sequential) |
| `scripts/adapter_templates/cursor.j2` | T008 |
| `Makefile` | T009 |
| `scripts/adapter_templates/copilot.j2` | T010 |
| `scripts/adapter_templates/system-prompt.j2` | T012 |
| `.gitignore` | T014 |
| `requirements.txt` | T015 |

> Note: `build_adapters.py` is written across T003–T007 but all are sequential (each depends on the prior). No race condition.

### Parallel Opportunities

**Phase 1**: T001 [P] and T002 [P] can run together (different files)
**Phase 2**: T004, T005, T006 can run together after T003 completes
**Phase 3 & Phase 6**: T008 [P] and T014 [P] and T015 [P] can run together after T007 completes
**Phase 4**: T010 [P] can run alongside T008/T014/T015 (different file)
**Phase 5**: T012 [P] can run alongside T008/T010/T014/T015 (different file)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (T001, T002, T003)
2. Complete Phase 2 (T004, T005, T006, T007)
3. Complete T008 and T009 (Cursor adapter)
4. Complete T014, T015 (gitignore + requirements)
5. **STOP and VALIDATE**: `make adapters` produces `.cursorrules` with ≥35 skill triggers
6. Demo to Director before continuing to P2 and P3

### Incremental Delivery

1. Phase 1 + Phase 2 → build runner ready
2. Phase 3 → Cursor adapter (MVP, US1 complete)
3. Phase 4 → Copilot adapter (US2 complete)
4. Phase 5 → System-prompt adapter (US3 complete)
5. Phase 6 → Gitignore + requirements (hardening)

---

## Notes

- [P] tasks = different files, no shared write targets — safe for parallel execution
- Each phase checkpoint is a natural commit boundary
- `build_adapters.py` is built across T003–T007 in strict sequence — each task appends a distinct function group; no two tasks write the same function
- Edge cases (missing frontmatter, empty gotchas, malformed YAML) are handled at the extraction layer (T003, T005) — templates never receive None or empty structures
- `dist/` must be gitignored (T014) before any adapter is committed to the repo
