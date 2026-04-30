# Tasks: Grade-A Upgrade — Memory, CI, Token Efficiency

**Input**: `.planning/specs/grade-a-upgrade/spec.md`, `.planning/specs/grade-a-upgrade/plan.md`
**Branches**: `feat/p0-setup` (PR 1, standalone) | `feat/grade-a-upgrade` (PR 2, three sequenced commits)
**Base commit**: b729ecf (v0.10.0)

---

## Phase 0: Branch Setup

- [x] T000 Create branches `feat/p0-setup` and `feat/grade-a-upgrade` from main

  **Acceptance**: Both branches exist locally; `git log --oneline -1` on each shows b729ecf

---

## PR 1: feat/p0-setup — First-Run Setup Experience

> Ship order: this PR merges before `feat/grade-a-upgrade` is started

### Phase 1 — P0 Setup [SC-S01, SC-S02, SC-S03]

**Goal**: One command fully configures a cold clone in <2 min  
**Independent test**: Clone to a temp dir → `py scripts/setup.py` → all checklist lines print ✓ → re-run → idempotent

- [x] T001 Create `scripts/setup.py`:
  - Check Python ≥3.11; print readable error with minimum version if not met (FR-S01)
  - Create `.venv/` if absent; `pip install -r requirements.txt` into it (FR-S02)
  - Non-destructive settings.json merge — read `~/.claude/settings.json`, add only keys absent in `hooks` array; never overwrite existing user keys (FR-S03)
  - Create `~/.claude/projects/.../memory/` dir if absent; write starter `MEMORY.md` if not present (FR-S04)
  - Print ✓/✗ checklist summary at end; exit 0 if all pass, 1 if any fail (FR-S07)

  **Acceptance**: `py scripts/setup.py` on a clean clone prints ≥5 checklist lines and exits 0; re-running is idempotent (no errors, same output)

- [x] T002 [P] Create `install.ps1` — check execution policy, call `py scripts/setup.py`, exit with same code (FR-S06)

  **Acceptance**: `.\install.ps1` on Windows delegates to setup.py and exits with the same code
  **Depends on**: T001

- [x] T003 [P] Create `install.sh` — `#!/usr/bin/env bash`, call `python3 scripts/setup.py`, exit with same code

  **Acceptance**: `bash install.sh` delegates to setup.py and exits with the same code
  **Depends on**: T001

- [x] T004 Add `setup` target to `Makefile` → calls `py -3.12 scripts/setup.py` (FR-S05)

  **Acceptance**: `make setup` runs without error and prints checklist summary
  **Depends on**: T001

**Checkpoint — PR 1 ready**: T001–T004 committed, CI green, push `feat/p0-setup`, open PR

---

## PR 2: feat/grade-a-upgrade — Three Upgrades

> Branch from main **after** PR 1 is merged

### Phase 2 — Upgrade 3: Token Benchmark [SC-T01–SC-T04]

**Goal**: Per-category overhead measured; numbers published in docs/  
**Independent test**: `py scripts/benchmark_tokens.py --run-label test` → creates token-benchmark.md with per-category table

- [ ] T005 Extend `packs/meta/hooks/on-token-log.py` — add `hook_output_bytes` and `hook_overhead_est` to log row; read from payload if present, default to `0` if absent; existing rows without these fields still parse correctly (FR-T02)

  **Acceptance**: Handler exits 0; new rows include both columns; old rows with missing columns don't break log parsing

- [ ] T006 Create `scripts/benchmark_tokens.py` — `--run-label STR` arg reads token-log.md, groups by run label, computes per-category overhead delta (hooks, routing table, memories, skills), writes `~/.dream-studio/meta/token-benchmark.md` with per-category table; `--publish` flag copies report to `docs/token-overhead.md` (FR-T01, FR-T03, FR-T06)

  **Acceptance**: `py scripts/benchmark_tokens.py --run-label test` creates token-benchmark.md with ≥3 category rows; `--publish` creates/updates `docs/token-overhead.md`
  **Depends on**: T005 (needs extended log format)

- [ ] T007 [P] Create `docs/token-overhead.md` stub — title, methodology note, "Run `py scripts/benchmark_tokens.py --publish` to regenerate" instruction (FR-T06 stub)

  **Acceptance**: File exists at `docs/token-overhead.md` with a methodology section and regeneration instruction

- [ ] T008 Update `README.md` — add "Token Overhead" section (after Features) linking to `docs/token-overhead.md` and one-sentence methodology description (FR-T04)

  **Acceptance**: README contains a Token Overhead heading with a link to `docs/token-overhead.md`
  **Depends on**: T007 (link target must exist first)

**Commit A**: `feat: token benchmark instrumentation and benchmark script (Upgrade 3)`

---

### Phase 3 — Upgrade 2: CI Gate [SC-C01–SC-C04]

**Goal**: PRs blocked on any check failure; `make ci-gate` matches CI behavior  
**Independent test**: Break a lint rule → `make ci-gate` → exits 1 → JSON shows lint check `"passed": false`

- [ ] T009 Create `scripts/ci_gate.py` — sequentially runs `make test`, `make lint`, `make fmt --check`, `make security`; captures stdout/stderr per check; prints `{"status": "pass|fail", "checks": [{"name": str, "passed": bool, "output": str}]}` to stdout; exits 0 all pass / 1 any fail; if `ANTHROPIC_API_KEY` set, runs `claude --print "review: check PR for regressions"` as advisory step appended to output (non-blocking) (FR-C01, FR-C02, FR-C06)

  **Acceptance**: `py scripts/ci_gate.py` on current repo exits 0 with valid JSON; introducing a deliberate lint error causes exit 1 with the lint check marked `"passed": false`

- [ ] T010 [P] Update `.github/workflows/ci.yml` — add `ci-gate` job: `runs-on: ubuntu-latest`, Python 3.12, install dev deps, run `py scripts/ci_gate.py`; job name must be `ci-gate` (exact string required for branch protection rule) (FR-C03, FR-C06)

  **Acceptance**: ci.yml has a job named `ci-gate` that calls `py scripts/ci_gate.py`; existing `test` and `audit` jobs unchanged
  **Depends on**: T009

- [ ] T011 [P] Add `ci-gate` target to `Makefile` → `py -3.12 scripts/ci_gate.py` (FR-C04)

  **Acceptance**: `make ci-gate` invokes the script and exits with the same code as direct invocation
  **Depends on**: T009

- [ ] T012 [P] Create `.claude/hooks/pre-push` — bash script: calls `make ci-gate`; on non-zero exit prints `[dream-studio] CI gate failed — push blocked` and exits 1; top of file includes install instructions comment: `# Install: cp .claude/hooks/pre-push .git/hooks/pre-push && chmod +x .git/hooks/pre-push` (FR-C05)

  **Acceptance**: File exists and is executable; running it when `make ci-gate` would fail exits 1 with the advisory message
  **Depends on**: T011 (pre-push delegates to `make ci-gate`)

**Commit B**: `feat: CI gate script and pre-push hook (Upgrade 2)`

---

### Phase 4 — Upgrade 1: Memory Retrieval [SC-M01–SC-M05]

**Goal**: Top-5 relevant memories injected on prompt; MEMORY.md never truncates; pulse shows memory health  
**Independent test**: Create 10 .md files with distinct topics in a temp memory dir → `from hooks.lib.memory_search import MemorySearch; results = MemorySearch(tmp_dir).search("Power BI DAX")` → Power BI files rank top, unrelated files absent

- [x] T013 Create `hooks/lib/memory_search.py` — COMPLETE (built during coverage campaign, PR #32)
  - MemorySearch class with FTS5 index, refresh_if_stale, search, archive_stale — all implemented

- [x] T014 [P] Create `tests/unit/test_memory_search.py` — COMPLETE (9 tests, all passing in PR #32)

- [x] T015 [P] Create `packs/meta/hooks/on-memory-retrieve.py` — COMPLETE (built during PR #32)

- [x] T016 Update `hooks/hooks.json` — COMPLETE (on-memory-retrieve in UserPromptSubmit chain, PR #32)

- [x] T017 Extend `packs/meta/hooks/on-pulse.py` — COMPLETE (collect_memory_stats() implemented, PR #32)

**Commit C**: DONE — merged in coverage campaign PR #32 (commit 5a0518e)

---

## Phase 5: PR Finalization

- [x] T018 Push `feat/p0-setup`, open PR → main — COMPLETE

- [x] T019 Grade-A memory stack shipped — COMPLETE via coverage campaign PRs #29–#32

---

## Phase 6: Competitive Gap Closure — Three New Items

> **Context**: Competitive analysis (2026-04-29) identified three remaining gaps.
> Branch from main (commit 5a0518e). All items are independent — no cross-item dependencies.
> Build order: Item 1 → Item 2 → Item 3 (smallest delta first).

---

### Item 1 — FTS5 Memory Completion (2 remaining gaps)

> archive_stale() exists and is tested but is never called automatically.
> MEMORY.md is not pruned when files are moved to archive/.
> SC-M02 (count cap at 90) is not enforced.

**Goal**: Archival runs automatically; MEMORY.md stays consistent; active count never exceeds 90  
**PR**: `feat/memory-archive-wiring`  
**Size estimate**: ~60 lines across 2 files

- [ ] T020 Extend `hooks/lib/memory_search.py` with two new methods:

  **`prune_memory_md(archived_paths: list[Path]) -> int`**
  - Reads MEMORY.md, removes lines whose `](filename.md)` reference matches any path in archived_paths
  - Returns count of lines removed
  - Defensive: if MEMORY.md absent or malformed, exits silently (never raises)

  **`enforce_limit(max_active: int = 90) -> int`**
  - Queries memory_meta for files with `last_accessed > 0`, orders by `last_accessed ASC`
  - Calls `archive_stale()` in batches until active count ≤ max_active
  - Returns count archived
  - Files with `last_accessed == 0` (never searched) are exempt — they were never a hit

  Add tests to `tests/unit/test_memory_search.py`:
  - `test_prune_memory_md_removes_archived_entries` — write MEMORY.md with 3 entries, archive 1, assert line removed
  - `test_prune_memory_md_tolerates_missing_file` — assert no exception when MEMORY.md absent
  - `test_enforce_limit_archives_oldest_first` — create 95 files with old last_accessed, assert count drops to ≤90
  - `test_enforce_limit_skips_never_accessed` — files with last_accessed=0 must not be archived

  **Acceptance**: All 4 new tests pass; existing 9 tests unchanged  
  **File ownership**: `hooks/lib/memory_search.py`, `tests/unit/test_memory_search.py`

- [ ] T021 Wire T020's methods into `packs/meta/hooks/on-pulse.py`

  In `generate_pulse()`, after `collect_memory_stats()`:
  1. Call `MemorySearch(mem_dir).archive_stale(days=90)` → capture archived paths
  2. Call `.prune_memory_md(archived_paths)` → keeps MEMORY.md consistent
  3. Call `.enforce_limit(max_active=90)` → cap active count
  4. If any archival occurred, print `[on-pulse] Archived N stale memories → memory/archive/`

  Guard: if mem_dir does not exist, skip block silently.

  **Acceptance**: After a pulse run with 95+ active memories (last_accessed set to 100d ago in tests), archive/ contains the overflow files and MEMORY.md no longer references them  
  **File ownership**: `packs/meta/hooks/on-pulse.py`  
  **Depends on**: T020

**Commit**: `fix: wire memory archive + MEMORY.md pruning into on-pulse (FR-M05, SC-M02)`

---

### Item 2 — Workflow Cost Estimates (4 tasks)

> No existing code. First-in-category capability — no competitor estimates token cost pre-run.
> Target: backwards-compatible optional field, human-readable terminal output before first wave.

**Goal**: `estimated_tokens` per node in workflow YAML; pre-run summary prints before execution  
**PR**: `feat/workflow-cost-estimates`  
**Size estimate**: ~120 lines across 3 files + 2 workflow YAML updates

- [ ] T022 [P] Add `estimated_tokens` optional field to workflow YAML schema

  In `hooks/lib/workflow_validate.py`, add `estimated_tokens` to the per-node optional fields.
  Validation rule: integer ≥ 0 if present; absent is valid (no default injected).
  Existing workflows without the field must continue to validate and run unchanged.

  **Acceptance**: `hotfix.yaml` (no field) validates; a YAML with `estimated_tokens: 500` on a node validates; `estimated_tokens: -1` fails validation  
  **File ownership**: `hooks/lib/workflow_validate.py`

- [ ] T025 [P] Add `estimated_tokens` to sample workflows

  Update `workflows/hotfix.yaml` and `workflows/fix-issue.yaml`:
  - Each node gets a realistic `estimated_tokens` value (debug: 2000, build: 3000, verify: 1500, ship: 1000)
  - Add a comment above the field: `# Estimated prompt + completion tokens for this node`

  **Acceptance**: Both YAML files pass `make validate-analysts` (or equivalent schema check); field values are plausible (not 0)  
  **File ownership**: `workflows/hotfix.yaml`, `workflows/fix-issue.yaml`  
  **Note**: T025 can be done in parallel with T022, T023

- [ ] T023 Create `hooks/lib/workflow_cost.py` + tests

  **`estimate_workflow_cost(workflow_data: dict) -> dict`**
  - Iterates `workflow_data["nodes"]`
  - Sums `estimated_tokens` fields; tracks which nodes lack the field
  - Returns:
    ```python
    {
      "total_estimated": int,   # sum of all estimated_tokens values
      "node_count": int,        # total nodes
      "estimated_count": int,   # nodes with estimated_tokens present
      "unestimated_count": int, # nodes without it
      "nodes": [{"id": str, "estimated_tokens": int | None}, ...]
    }
    ```

  **`format_cost_summary(cost_dict: dict) -> str`**
  - Returns a human-readable pre-run table, e.g.:
    ```
    ┌─ Workflow Cost Estimate ──────────────────┐
    │  debug          2,000 tokens              │
    │  build          3,000 tokens              │
    │  verify         1,500 tokens    (2 nodes unestimated)
    │  ─────────────────────────────            │
    │  Total:         6,500 tokens est.         │
    └───────────────────────────────────────────┘
    ```

  Create `tests/unit/test_workflow_cost.py`:
  - `test_estimate_sums_all_nodes` — 3 nodes with known values → correct total
  - `test_estimate_handles_missing_field` — node without estimated_tokens → unestimated_count=1, no KeyError
  - `test_estimate_empty_workflow` — 0 nodes → total 0, no crash
  - `test_format_summary_contains_total` — assert "Total" in output
  - `test_format_summary_marks_unestimated` — assert unestimated count shows in output when > 0

  **Acceptance**: 5 tests pass; `estimate_workflow_cost({})` returns a valid dict without raising  
  **File ownership**: `hooks/lib/workflow_cost.py`, `tests/unit/test_workflow_cost.py`  
  **Depends on**: T022 (schema must accept the field before testing round-trip validation)

- [ ] T024 Wire pre-run cost summary into `hooks/lib/workflow_state.py`

  Find the workflow run/start entry point in workflow_state.py (where first wave dispatch begins).
  Before dispatching the first wave:
  1. Call `estimate_workflow_cost(parsed_workflow)` from workflow_cost.py
  2. Call `format_cost_summary(cost_dict)`
  3. Print the formatted summary to stdout with `flush=True`
  4. If workflow has 0 estimated nodes (all unestimated), print a one-line note instead:
     `[workflow] No token estimates — add estimated_tokens to nodes for a pre-run cost summary`

  Guard: import inside try/except; if workflow_cost.py fails to import, skip silently.

  **Acceptance**: Running a workflow with estimated_tokens on nodes prints the cost table before the first skill invocation; running without any estimated_tokens prints the one-line note; existing workflow behavior (DAG execution, state tracking) is unchanged  
  **File ownership**: `hooks/lib/workflow_state.py`  
  **Depends on**: T023

**Commit**: `feat: workflow cost estimates with pre-run token summary`

---

### Item 3 — Routing Table Auto-Registration (3 tasks)

> 38 skills already have metadata.yml with triggers: []. Generator + sentinel markers eliminate
> the dual-SSOT footgun. Triggers populated for 9 core skills now; generator falls back to
> description field parsing for any skill where triggers: [] is still empty.

**Goal**: `make install` regenerates routing table in CLAUDE.md from metadata.yml — idempotent, preserves surrounding content  
**PR**: `feat/routing-auto-registration`  
**Size estimate**: ~150 lines across 1 new script + 9 metadata.yml updates + Makefile + CLAUDE.md sentinels

- [ ] T026 [P] Add sentinel markers to routing table section in `CLAUDE.md`

  Wrap the existing "### Build Pipeline" routing table block with:
  ```markdown
  <!-- BEGIN AUTO-ROUTING -->
  ...existing routing tables...
  <!-- END AUTO-ROUTING -->
  ```
  Position: directly inside the `## Skill Routing` section, wrapping only the tables (not the intro paragraph or the Routing Fallback note below).

  **Acceptance**: CLAUDE.md is valid markdown; section above and below sentinels is unchanged; sentinels appear as comments (invisible in rendered markdown)  
  **File ownership**: `CLAUDE.md`

- [ ] T027 [P] Create `scripts/generate_routing.py` + tests + Makefile target

  **Generator logic:**
  1. Glob all `skills/*/metadata.yml` files
  2. For each skill: load `name`, `triggers`, `description`, `pack` fields
  3. If `triggers` is non-empty, use those as routing keywords
  4. Else, extract trigger text from `description` field using pattern: `` `trigger_text:` `` or `Trigger on `keyword:`` → parse to keyword list
  5. Group skills by `pack` (core, quality, security, domain, meta, etc.)
  6. Generate a routing table in the format matching the existing CLAUDE.md tables
  7. Read CLAUDE.md, replace content between `<!-- BEGIN AUTO-ROUTING -->` and `<!-- END AUTO-ROUTING -->` with generated table
  8. Write back — everything outside the sentinel block is preserved byte-for-byte

  **Idempotency contract**: Running twice produces identical file content.  
  **Graceful degradation**: Skills with no `metadata.yml` → silently skipped. Skills with `triggers: []` and no parseable triggers in description → silently omitted from table (no error).

  Add `install` target to Makefile:
  ```makefile
  install:
      $(PYTHON) scripts/generate_routing.py
  ```

  Create `tests/unit/test_generate_routing.py`:
  - `test_generates_table_from_triggers` — mock 2 skills with non-empty triggers, assert both appear in output
  - `test_falls_back_to_description_parsing` — skill with triggers: [], description has trigger text → appears in output
  - `test_skips_skill_without_metadata` — a skills/ subdir with no metadata.yml → no error, not in output
  - `test_idempotent` — run generator twice on same CLAUDE.md → byte-identical output
  - `test_preserves_content_outside_sentinels` — content before BEGIN and after END marker unchanged

  **Acceptance**: 5 tests pass; `py scripts/generate_routing.py` runs without error on current repo  
  **File ownership**: `scripts/generate_routing.py`, `tests/unit/test_generate_routing.py`, `Makefile`

- [ ] T028 Populate `triggers` arrays in 9 core skills

  Update `skills/{build,plan,review,debug,think,verify,ship,handoff,recap}/metadata.yml`:
  - Set `triggers` to the canonical keywords from that skill's SKILL.md or CLAUDE.md routing table
  - Examples:
    - debug: `[debug:, diagnose:]`
    - build: `["build:", "execute plan:"]`
    - plan: `["plan:", "/plan"]`
    - review: `["review:", "review code", "review PR:"]`

  These 9 skills cover the core build pipeline and session management. Remaining 29 skills rely on the description-field fallback (T027) until their metadata is populated in a follow-up.

  **Acceptance**: `py scripts/generate_routing.py` produces a routing table containing all 9 skills; `make install` is idempotent when run a second time  
  **File ownership**: `skills/{9 skills}/metadata.yml`  
  **Note**: T028 can be done in parallel with T026 and T027 (distinct file sets)

**Commit**: `feat: routing table auto-registration via metadata.yml (make install)`

---

## Phase 7: PR Finalization

- [ ] T029 Open PR `feat/memory-archive-wiring` (Item 1) — T020-T021

  **Acceptance**: CI green; `make test` passes; PR ≤ 60 lines; no regressions

- [ ] T030 Open PR `feat/workflow-cost-estimates` (Item 2) — T022-T025

  **Acceptance**: CI green; 5 new tests pass; existing workflow integration tests pass

- [ ] T031 Open PR `feat/routing-auto-registration` (Item 3) — T026-T028

  **Acceptance**: CI green; `make install` idempotent; 5 new tests pass; CLAUDE.md routing table regenerated correctly

---

## Dependencies & Execution Order

### Phase Dependencies

| Phase | Blocks | Notes |
|---|---|---|
| T000 (branches) | All others | Create both branches first |
| Phase 1 (P0 Setup) | PR 2 start | PR 1 must merge before feat/grade-a-upgrade branches from main |
| Phase 2 (Token Benchmark) | Phase 3+4 ordering | Commit A before B; B before C |
| Phase 3 (CI Gate) | Phase 4 (same PR) | Commit B before C |
| Phase 4 (Memory) | T018/T019 | All commits before PR |

### Within-Phase Parallel Groups

| Phase | Parallel group | Tasks |
|---|---|---|
| Phase 1 | After T001 complete | T002 [P] T003 |
| Phase 2 | After T005+T006 complete | T007 [P] (independent of T006; needed for T008) |
| Phase 3 | After T009 complete | T010 [P] T011 [P] T012 |
| Phase 4 | After T013 complete | T014 [P] T015 |
| Phase 4 | After T014+T015 complete | T016 [P] T017 |

### File Ownership (no cross-task conflicts)

| File | Owner |
|---|---|
| `scripts/setup.py` | T001 |
| `install.ps1` | T002 |
| `install.sh` | T003 |
| `Makefile` (setup target) | T004 |
| `packs/meta/hooks/on-token-log.py` | T005 |
| `scripts/benchmark_tokens.py` | T006 |
| `docs/token-overhead.md` | T007 |
| `README.md` | T008 |
| `scripts/ci_gate.py` | T009 |
| `.github/workflows/ci.yml` | T010 |
| `Makefile` (ci-gate target) | T011 — different PR than T004, no conflict |
| `.claude/hooks/pre-push` | T012 |
| `hooks/lib/memory_search.py` | T013 |
| `tests/unit/test_memory_search.py` | T014 |
| `packs/meta/hooks/on-memory-retrieve.py` | T015 |
| `hooks/hooks.json` | T016 |
| `packs/meta/hooks/on-pulse.py` | T017 |

No two tasks in the same wave write to the same file. ✓
