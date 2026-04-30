# Tasks: Platform Intelligence — Persistence, Registry, Self-Calibration

**Spec**: `.planning/specs/platform-intelligence/spec.md`
**Plan**: `.planning/specs/platform-intelligence/plan.md`
**Branch base**: `main` (commit ca61341)

---

## Phase 1A — feat/studio-db-schema (PR ≤ 120 lines)

**Purpose**: Create `studio_db.py` — the single DB writer. Schema init, library API, CLI. No callers yet.

- [ ] T001 Create `hooks/lib/studio_db.py` with full schema init, library functions, and CLI

  **Files**: `hooks/lib/studio_db.py` (new)

  **What to build**:
  - `_connect(db_path)` → opens connection with `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`, creates all tables + view on first run
  - Tables: `raw_workflow_runs`, `raw_workflow_nodes`, `raw_skill_telemetry`, `cor_skill_corrections`, `sum_skill_summary`, `log_batch_imports`
  - View: `effective_skill_runs` (COALESCE correction over heuristic)
  - Library functions: `archive_workflow(run_key, wf_dict)`, `last_run(workflow_name) -> dict|None`, `run_count(workflow_name) -> int`, `import_buffer(buffer_path) -> int`, `rebuild_summaries()`, `rolling_window_prune()`, `skill_correct(telemetry_id, success, reason)`
  - `import_buffer`: compute SHA256 of buffer content as `batch_id`; check `log_batch_imports` first; if exists → return 0 (idempotent); else INSERT all rows + INSERT log row in one transaction
  - `rebuild_summaries`: `DELETE FROM sum_skill_summary` + `INSERT INTO sum_skill_summary SELECT ... FROM effective_skill_runs WHERE skill_name IN (SELECT skill_name FROM raw_skill_telemetry GROUP BY skill_name HAVING COUNT(*) >= 5) ORDER BY id DESC LIMIT 30 GROUP BY skill_name` — all in one transaction
  - CLI subcommands: `archive-workflow <run_key> <json>`, `skill-correct <telemetry_id> success|failure [--reason TEXT]`, `import-and-rebuild` (calls `import_buffer` then `rebuild_summaries`)
  - All functions wrapped in try/except — never raises to caller; returns 0/None on error

  **Acceptance**: `py -3.12 hooks/lib/studio_db.py --help` prints subcommand list; `py -3.12 -c "from lib.studio_db import _connect; c = _connect(); print('ok')"` from hooks/ dir prints `ok`; all 6 tables + 1 view present in schema.

---

- [ ] T002 Add tests for `studio_db.py`

  **Files**: `tests/unit/test_studio_db.py` (new)

  **Depends on**: T001

  **Tests to write** (tmp_path fixture for DB path):
  - `test_schema_creates_all_tables`: connect, query `sqlite_master`, assert all 6 tables + 1 view present
  - `test_archive_workflow_round_trip`: archive a synthetic wf_dict, call `last_run("test")`, assert status + finished_at returned
  - `test_last_run_returns_none_when_absent`: `last_run("nonexistent")` → None, no exception
  - `test_import_buffer_idempotent`: write 3 rows to buffer, import twice, assert `raw_skill_telemetry` count = 3 (not 6)
  - `test_import_buffer_batch_logged`: after import, `log_batch_imports` has one row with correct row_count
  - `test_skill_correct_inserts_correction`: insert telemetry row, call `skill_correct(id, 0, "wrong")`, query `effective_skill_runs` → `success=0`, `signal_source='corrected'`
  - `test_rebuild_summaries_self_heals`: corrupt `sum_skill_summary` with wrong data, call `rebuild_summaries()`, assert correct values restored
  - `test_graceful_on_bad_db_path`: call all library functions with a read-only path, assert returns 0/None without raising

  **Acceptance**: `py -3.12 -m pytest tests/unit/test_studio_db.py -q` — 8 passed, 0 failed.

---

## Phase 1B — feat/studio-db-wiring (PR ≤ 120 lines)

**Purpose**: Wire `workflow_state.py` to archive completed/aborted runs and prune JSON. Depends on Phase 1A merged.

- [ ] T003 Wire `workflow_state.py` to archive terminal workflows to `studio.db`

  **Files**: `hooks/lib/workflow_state.py` (modify)

  **Depends on**: T001 merged to main

  **What to change**:
  - Add `from lib.studio_db import archive_workflow as _archive_workflow` (guarded try/except import, `_DB_AVAILABLE` flag)
  - In `cmd_update`: after `_write_state(data)`, if new status is in `{"completed", "completed_with_failures"}` and `_DB_AVAILABLE`: call `_archive_workflow(args.key, wf)`, then `del data["active_workflows"][args.key]`, `_write_state(data)`
  - In `cmd_abort`: same pattern — archive then delete from JSON after setting `wf["status"] = "aborted"`
  - Add `rolling_window_prune()` call in on-pulse (add import to `packs/meta/hooks/on-pulse.py`)

  **Acceptance**: Run `make test` — all existing tests pass. After manually running a test workflow to completion, `workflows.json` no longer contains the terminal entry; running `py -3.12 hooks/lib/studio_db.py` CLI with `last_run` equivalent confirms the archived row exists.

---

## Phase 2 — feat/workflow-registry (PR ≤ 120 lines)

**Purpose**: Workflow discovery. Depends on Phase 1A merged (needs `last_run`, `run_count`).

- [ ] T004 Create `hooks/lib/workflow_registry.py` with `list_workflows` and `format_registry_table`

  **Files**: `hooks/lib/workflow_registry.py` (new)

  **Depends on**: T001 merged to main

  **What to build**:
  - `list_workflows(workflows_dir: Path) -> list[dict]`: scan `*.yaml`, for each: parse `name` (fallback: stem), `description` (fallback: `"(no description)"`), sum `estimated_tokens` from nodes (None if no node has the field), call `last_run(name)` + `run_count(name)` from `studio_db`
  - `format_registry_table(workflows: list[dict]) -> str`: box-drawing table with columns: Name (20), Description (35), Est. Tokens (12), Last Run (12), Runs (5); `—` for missing token estimates; "never" for null last_run; relative time ("2h ago", "yesterday", "3d ago") for last_run timestamps
  - All try/except guarded — returns empty list / empty string on any error

  **Acceptance**: `py -3.12 -c "from lib.workflow_registry import list_workflows, format_registry_table; from pathlib import Path; print(format_registry_table(list_workflows(Path('workflows'))))"` from hooks/ dir prints a table with all 15 workflows.

---

- [ ] T005 [P] Add `make workflows` target and tests for workflow_registry

  **Files**: `Makefile` (modify), `tests/unit/test_workflow_registry.py` (new)

  **Depends on**: T004

  **Makefile addition**:
  ```makefile
  workflows:
      $(PYTHON) -c "import sys; sys.path.insert(0,'hooks'); from lib.workflow_registry import list_workflows, format_registry_table; from pathlib import Path; print(format_registry_table(list_workflows(Path('workflows'))))"
  ```

  **Tests**:
  - `test_list_workflows_finds_all_yamls`: tmp_path with 3 synthetic workflow YAMLs → list returns 3 entries
  - `test_list_workflows_fallback_no_name`: YAML without `name:` field → entry uses filename stem
  - `test_list_workflows_no_estimated_tokens`: YAML with nodes but no `estimated_tokens` → `estimated_tokens` is None
  - `test_format_table_marks_unestimated`: format_registry_table on entry with None estimated_tokens → `—` appears in output
  - `test_format_table_shows_never_for_no_runs`: entry with `last_run=None, run_count=0` → "never" in output

  **Acceptance**: `py -3.12 -m pytest tests/unit/test_workflow_registry.py -q` — 5 passed; `make workflows` runs in < 2s.

---

- [ ] T006 Update workflow skill preamble to show registry when no workflow name given

  **Files**: `skills/workflow/SKILL.md` (modify)

  **Depends on**: T004

  **What to change**: In the skill's "when no workflow name is provided" section, add instruction to call `format_registry_table(list_workflows(Path("workflows")))` and print the result before prompting the user to choose. Add import pattern (same as T004's CLI call, using subprocess or inline Python).

  **Acceptance**: Invoking `workflow:` with no argument shows the registry table in the response before asking which workflow to run.

---

## Phase 3A — feat/skill-calibration-capture (PR ≤ 120 lines)

**Purpose**: Stop hook capture + correction CLI. Depends on Phase 1A merged.

- [ ] T007 Extend `on-quality-score.py` to detect skill + append JSONL buffer

  **Files**: `packs/meta/hooks/on-quality-score.py` (modify)

  **Depends on**: T001 merged to main

  **What to add** (after existing quality-score logic, in its own try/except block):
  - Parse Stop payload from stdin (or env) — extract `tool_use` list
  - Find any `Skill` tool call where `name` starts with `dream-studio:` → extract skill name (strip prefix)
  - If no skill found: return (session had no skill invocation)
  - Apply success heuristic to payload's last assistant message: failure keywords = `["error", "traceback", "failed", "exception", "cannot", "unable to", "not found"]` (case-insensitive); `success = 1` if none present
  - Extract `model`, `input_tokens`, `output_tokens` from payload if available
  - Append one JSON line to `state_dir() / "telemetry-buffer.jsonl"` using `open(..., "a")`:
    `{"skill_name": ..., "invoked_at": ISO-8601, "model": ..., "input_tokens": ..., "output_tokens": ..., "success": 0|1, "execution_time_s": null}`
  - Entire block wrapped in try/except — hook exits 0 on any error

  **Acceptance**: After a session that used `dream-studio:build`, `telemetry-buffer.jsonl` contains one JSON line with `skill_name: "build"` and a valid `success` value.

---

- [ ] T008 Add `skill-correct` subcommand to `workflow_state.py`

  **Files**: `hooks/lib/workflow_state.py` (modify)

  **Depends on**: T001 merged to main, T007

  **What to add**:
  - New subcommand: `skill-correct <telemetry_id> <success> [--reason TEXT]`
  - Calls `studio_db.skill_correct(telemetry_id, success_int, reason)` which inserts to `cor_skill_corrections`
  - Prints: `[studio_db] Correction recorded: telemetry_id={id} → success={val}`

  **Acceptance**: `py -3.12 hooks/lib/workflow_state.py skill-correct 1 success --reason "test"` inserts a row to `cor_skill_corrections`; `py -3.12 hooks/lib/workflow_state.py skill-correct --help` shows usage.

---

## Phase 3B — feat/skill-calibration-pulse (PR ≤ 120 lines)

**Purpose**: Pulse import, summary rebuild, metadata write, health report. Depends on Phase 3A merged.

- [ ] T009 Extend `on-pulse.py` to import buffer + rebuild summaries + write metadata.yml

  **Files**: `packs/meta/hooks/on-pulse.py` (modify)

  **Depends on**: T007 merged to main

  **What to add** (new `_run_skill_calibration()` function, called inside `generate_pulse()`):
  - Call `studio_db.import_buffer(buffer_path)` → if 0 rows imported and buffer empty: skip rebuild
  - Call `studio_db.rebuild_summaries()` (always after import, never independently)
  - Call `studio_db.rolling_window_prune()` (keep last 100 rows per skill)
  - For each skill in `sum_skill_summary` with `times_used >= 5`: read `skills/<name>/metadata.yml`, update `quality_metrics` block, write atomically via temp+rename
  - Entire block in try/except — never raises

  **Acceptance**: After 5+ skill invocations are in `raw_skill_telemetry`, running on-pulse updates `skills/build/metadata.yml` `quality_metrics` with non-zero values.

---

- [ ] T010 Add Skill Health section to pulse report

  **Files**: `packs/meta/hooks/on-pulse.py` (modify)

  **Depends on**: T009

  **What to add** (inside `generate_pulse()` report string):
  - Query `sum_skill_summary` for all skills with `times_used >= 5`
  - For each: print `✓ <name> — <times_used> uses, <success_rate*100:.0f>% success, avg <avg_input_tokens+avg_output_tokens:.0f> tokens`
  - Flag skills with `success_rate < 0.70` as `⚠` instead of `✓`; append `(ids: ...)` showing the most recent 3 `raw_skill_telemetry` IDs where `success=0` (for `skill-correct` reference)
  - If no skills have ≥ 5 runs: print `Skill Health: insufficient data (< 5 runs per skill)`

  **Acceptance**: Pulse report output contains a "Skill Health:" section; a skill with mocked `success_rate=0.60` shows `⚠` with telemetry IDs.

---

- [ ] T011 Add tests for skill calibration

  **Files**: `tests/unit/test_skill_calibration.py` (new)

  **Depends on**: T009, T010

  **Tests**:
  - `test_buffer_import_populates_telemetry`: write 3-line JSONL buffer, call `import_buffer`, assert `raw_skill_telemetry` count = 3
  - `test_import_idempotent_on_retry`: import same buffer twice, assert count still = 3
  - `test_rebuild_summaries_uses_effective_view`: insert telemetry row (success=0), insert correction (success=1), rebuild, assert `sum_skill_summary.success_rate = 1.0`
  - `test_atomic_metadata_write_leaves_no_tmp_on_success`: run metadata write, assert `.yml.tmp` does not exist after
  - `test_skill_health_flags_below_threshold`: mock `sum_skill_summary` with `success_rate=0.60`, call health formatter, assert `⚠` in output
  - `test_rolling_window_prune_keeps_100_per_skill`: insert 110 rows for one skill, call `rolling_window_prune`, assert count = 100

  **Acceptance**: `py -3.12 -m pytest tests/unit/test_skill_calibration.py -q` — 6 passed; full suite still 388+ passed.

---

## Summary Table

| ID | Task | Phase | PR | Est. Size | Depends On |
|----|------|-------|----|-----------|------------|
| T001 | `studio_db.py` — schema + library + CLI | 1A | A | L | — |
| T002 | Tests for `studio_db.py` | 1A | A | M | T001 |
| T003 | Wire `workflow_state.py` — archive on terminal | 1B | B | S | T001 merged |
| T004 | `workflow_registry.py` — list + format | 2 | C | M | T001 merged |
| T005 | `make workflows` + registry tests | 2 | C | S | T004 |
| T006 | Workflow skill preamble update | 2 | C | S | T004 |
| T007 | `on-quality-score.py` — JSONL buffer append | 3A | D | S | T001 merged |
| T008 | `skill-correct` CLI subcommand | 3A | D | S | T001 merged, T007 |
| T009 | `on-pulse.py` — import + rebuild + metadata write | 3B | E | M | T007 merged |
| T010 | Pulse Skill Health section | 3B | E | S | T009 |
| T011 | Tests for skill calibration | 3B | E | M | T009, T010 |

**S** = < 30 lines | **M** = 30–80 lines | **L** = 80–120 lines

### Wave execution (parallel opportunities)
- T001 + T002 sequential (same file)
- T003, T004, T007, T008 can all start once T001 is merged (different files — parallel branches)
- T005, T006 parallel after T004
- T009, T010, T011 sequential (same file chain)
