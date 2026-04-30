# Feature Specification: Platform Intelligence — Persistence, Registry, Self-Calibration

**Topic Directory**: `.planning/specs/platform-intelligence/`
**Created**: 2026-04-29
**Status**: Approved — proceeding to plan
**Scope**: Items 4–6 of the Grade-A competitive gap list — three coupled deliverables sharing one SQLite backend

---

## Dependency Graph

```
Item 4 — studio.db schema + workflow archive
    └─► Item 5 — Workflow registry (needs last_run from Item 4)
              └─► Item 6 — Self-calibrating skill loop (shares DB, correction layer)
```

Each item is independently shippable. Build in order.

---

## Current State

- `workflow_state.py` persists to `workflows.json` (JSON, not in-memory — but grows unbounded)
- No cross-session query: can't ask "how many times has hotfix.yaml run?"
- 15 YAML files in `workflows/` — no discovery mechanism
- `skills/*/metadata.yml` has `quality_metrics` block — all zeroed, never updated
- `on-quality-score.py` scores code quality on Stop — does not capture skill-level telemetry

---

## Core Architecture — Five Patterns Applied Across All Items

### Pattern 1: Append-Only Fact Tables (never UPDATE, never DELETE except scheduled pruning)
Fact rows record what happened. A failed INSERT leaves previous data intact because nothing was overwritten. Corruption risk is structural, not just operational.

### Pattern 2: Correction Layer (override wrong data without mutating history)
When a heuristic produces a wrong signal, the Director inserts a correction record. A SQL view (`effective_skill_runs`) returns `COALESCE(correction.success, telemetry.success)` — corrections win automatically in all downstream queries. The original record and the correction are both preserved. Correcting a correction: insert another correction.

### Pattern 3: Rebuild-Safe Summaries (DELETE + INSERT in one transaction per pulse)
`sum_skill_summary` is the only mutable table. On every pulse: `DELETE FROM sum_skill_summary` + `INSERT INTO sum_skill_summary SELECT ... GROUP BY skill_name` — in one transaction. A mid-write crash rolls back; the previous summary survives. Self-healing from fact tables on next pulse.

### Pattern 4: Idempotent Batch Import (batch_import_log prevents duplicate ingestion)
A crash mid-import leaves the JSONL buffer partially consumed. On retry, without a commit log, rows get double-counted and `times_used` inflates silently. The fix: each import batch gets a `batch_id` (SHA256 of buffer content + timestamp). The import transaction inserts all telemetry rows AND one row into `log_batch_imports` atomically. On retry, `batch_id` already exists → skip. Import is idempotent regardless of how many times it retries.

### Pattern 5: Table-Name Prefixes as Schema-Isolation Signal
SQLite has no schemas. Prefixes make blast radius readable at a glance and enforce the contract via grep:

| Prefix | Meaning | Contract |
|--------|---------|----------|
| `raw_` | Append-only fact tables | Never UPDATE or DELETE (except scheduled pruning) |
| `cor_` | Correction/override layer | Append-only; never mutates `raw_` rows |
| `sum_` | Rebuild-safe summaries | DELETE + INSERT in one transaction per pulse only |
| `log_` | Import audit trail | Append-only; checked before each import for idempotency |

### Write Path Decoupling (Stop hook → JSONL buffer → on-pulse → DB)
The Stop hook fires at session end. Touching SQLite there means lock acquisition and possible contention. Instead:
- **Stop hook**: appends one JSON line to `telemetry-buffer.jsonl` (~0.5ms, no DB).
- **on-pulse**: calls `import_buffer()` → commits → calls `rebuild_summaries()`. These two steps are always orchestrated together. If `import_buffer()` fails, `rebuild_summaries()` does not run — summaries never reflect a partial import.

The Stop hook can never block due to DB state. The pulse is the only SQLite writer for telemetry.

---

## Full Schema

```sql
-- Set on every connection open:
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

-- raw_: append-only fact tables (never UPDATE, never DELETE except pruning)

CREATE TABLE IF NOT EXISTS raw_workflow_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key     TEXT NOT NULL UNIQUE,
    workflow    TEXT NOT NULL,
    yaml_path   TEXT NOT NULL,
    status      TEXT NOT NULL,            -- completed | completed_with_failures | aborted
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    node_count  INTEGER,
    nodes_done  INTEGER
);

CREATE TABLE IF NOT EXISTS raw_workflow_nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key     TEXT NOT NULL REFERENCES raw_workflow_runs(run_key),
    node_id     TEXT NOT NULL,
    status      TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT,
    duration_s  REAL,
    output      TEXT
);

CREATE TABLE IF NOT EXISTS raw_skill_telemetry (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name       TEXT NOT NULL,
    invoked_at       TEXT NOT NULL,
    model            TEXT,
    input_tokens     INTEGER,
    output_tokens    INTEGER,
    success          INTEGER NOT NULL,    -- heuristic: 1=success, 0=failure
    execution_time_s REAL
);

-- cor_: correction layer (append-only; overrides heuristic without mutating raw_)

CREATE TABLE IF NOT EXISTS cor_skill_corrections (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    telemetry_id      INTEGER NOT NULL REFERENCES raw_skill_telemetry(id),
    corrected_success INTEGER NOT NULL,
    reason            TEXT,
    corrected_at      TEXT NOT NULL
);

-- sum_: rebuild-safe summaries (DELETE + INSERT in one transaction per pulse)

CREATE TABLE IF NOT EXISTS sum_skill_summary (
    skill_name        TEXT PRIMARY KEY,
    times_used        INTEGER,
    success_rate      REAL,
    avg_input_tokens  REAL,
    avg_output_tokens REAL,
    avg_exec_time_s   REAL,
    last_success      TEXT,
    last_failure      TEXT,
    updated_at        TEXT
);

-- log_: import audit trail (idempotency guard for JSONL batch imports)

CREATE TABLE IF NOT EXISTS log_batch_imports (
    batch_id    TEXT PRIMARY KEY,         -- SHA256 of buffer content + timestamp
    imported_at TEXT NOT NULL,
    row_count   INTEGER NOT NULL
);

-- View: corrections win over heuristic signals in all downstream queries

CREATE VIEW IF NOT EXISTS effective_skill_runs AS
SELECT
    t.id,
    t.skill_name,
    t.invoked_at,
    COALESCE(c.corrected_success, t.success) AS success,
    CASE WHEN c.id IS NOT NULL THEN 'corrected' ELSE 'heuristic' END AS signal_source,
    t.input_tokens,
    t.output_tokens,
    t.execution_time_s
FROM raw_skill_telemetry t
LEFT JOIN cor_skill_corrections c ON c.telemetry_id = t.id;
```

---

## Item 4 — SQLite Workflow State Persistence

### Problem
`workflows.json` grows unbounded: every completed/aborted workflow stays in the dict forever. No cross-session query capability. Item 5 (registry) needs "last run per workflow" — impossible from JSON without a full scan.

### Approaches

**Option A — Augment JSON with SQLite archive (recommended)**
Keep `workflows.json` for active workflow state (proven, zero-risk hot path). When a workflow reaches terminal status (completed/completed_with_failures/aborted), archive it to `studio.db` and prune the JSON entry. `workflows.json` then only ever contains in-flight runs.

- Pros: Zero blast radius to existing execution path; DB adds only what JSON can't do (indexable history, cross-session query)
- Cons: Two state sources (JSON for active, SQLite for history) — minor mental model cost

**Option B — Full SQLite migration (replace JSON)**
Replace `workflows.json` entirely. `workflow_state.py` rewrites its I/O layer to `sqlite3`.

- Pros: Single source of truth
- Cons: High blast radius — touches every command in `workflow_state.py`; risk of subtle regression in the proven locking/serialization path; all tests need DB setup/teardown

**Option C — Keep JSON + SQLite for metrics only**
Don't touch workflow persistence. Add SQLite only for telemetry and registry reads YAML directly.

- Pros: Minimal blast radius
- Cons: Registry can't show last-run without JSON scan; Items 5 and 6 have no shared infrastructure

**Recommendation: Option A** — augment, don't replace.

### Functional Requirements
- **FR-P01**: `hooks/lib/studio_db.py` MUST initialize `studio.db` in `state_dir()` on first connection, running schema migrations. Zero new deps (stdlib `sqlite3`). WAL mode set on every connection open.
- **FR-P02**: `studio_db.py` MUST expose `archive_workflow(run_key, wf_dict)` — inserts into `workflow_runs` + `workflow_nodes` in one transaction.
- **FR-P03**: `workflow_state.py` `cmd_update` (terminal status) and `cmd_abort` MUST call `archive_workflow`, then remove the key from `workflows.json`.
- **FR-P04**: `studio_db.py` MUST expose `last_run(workflow_name) -> dict | None` and `run_count(workflow_name) -> int` — used by Item 5.
- **FR-P05**: All `studio_db` functions MUST wrap every DB operation in try/except — OSError and sqlite3.Error are caught, logged to stderr, and return gracefully. Never raises to caller.
- **FR-P06**: On-pulse MUST prune `workflow_runs` and `workflow_nodes` rows where `finished_at < 90 days ago`.

### Success Criteria
- **SC-P01**: After a hotfix workflow completes, `studio.db` contains its run + node rows; `workflows.json` no longer contains that key.
- **SC-P02**: `last_run("hotfix")` returns the correct result without scanning `workflows.json`.
- **SC-P03**: All existing `workflow_state.py` tests pass (zero regression).
- **SC-P04**: `workflows.json` active-workflows dict never contains terminal-status entries after this change.

### User Stories

**P1 — Completed workflows don't accumulate in JSON**
- Given: `hotfix` workflow reaches `completed`
- When: `cmd_update` sets the terminal node
- Then: Archived to `studio.db`; removed from `workflows.json`

**P2 — Cross-session last-run query**
- Given: `fix-issue` ran 3 sessions ago (different Claude Code process)
- When: `last_run("fix-issue")` called
- Then: Returns `{"status": "completed", "finished_at": "2026-04-29T..."}` from SQLite

---

## Item 5 — Workflow Registry

### Problem
15 workflow YAMLs exist. Users must know filenames to use them. The `workflow:` skill asks for a name without showing what's available. No descriptions, no last-run info, no cost estimates visible at a glance.

### Approaches

**Option A — Dynamic scan + DB enrichment (recommended)**
At list time: scan `workflows/*.yaml`, read `name`/`description` from each file, join with `studio.db` for `last_run` + `run_count`, pull `estimated_tokens` from nodes via `workflow_cost.py`. Format as a table. Zero schema changes to YAML.

- Pros: Always current; auto-discovers new files; last-run from DB; cost from existing infrastructure
- Cons: Scans all YAML files at list time (15 files, < 50ms, negligible)

**Option B — Dedicated registry YAML**
A `workflows/registry.yaml` manually listing all workflows.

- Pros: Single file
- Cons: Dual-SSOT footgun — same problem we just fixed with routing table

**Option C — README table only**
- Cons: Doesn't solve in-session discovery

**Recommendation: Option A**

### New module: `hooks/lib/workflow_registry.py`
```python
def list_workflows(workflows_dir: Path) -> list[dict]:
    # Scan *.yaml, enrich with last_run + run_count + estimated_tokens
    # Returns: [{name, description, yaml_path, estimated_tokens, last_run, run_count}]

def format_registry_table(workflows: list[dict]) -> str:
    # Box-drawing table: Name | Description | Est. Tokens | Last Run | Runs
```

### Functional Requirements
- **FR-R01**: `workflow_registry.py` MUST scan `workflows/*.yaml` and return enriched metadata dicts. Zero new deps.
- **FR-R02**: Each entry MUST include: `name`, `description`, `yaml_path`, `estimated_tokens` (summed from nodes, `None` if absent), `last_run` (from `studio_db.last_run`, `None` if never), `run_count`.
- **FR-R03**: `format_registry_table` MUST produce a human-readable box-drawing table.
- **FR-R04**: `make workflows` MUST print the registry table to stdout in < 1 second.
- **FR-R05**: The `workflow:` skill MUST display the registry table as a preamble when no workflow name is provided.
- **FR-R06**: A YAML without `name`/`description` MUST still appear using the filename stem and `(no description)`.

### Success Criteria
- **SC-R01**: `make workflows` lists all 15 workflows with description, cost, and last-run in < 1 second.
- **SC-R02**: A new `workflows/my-flow.yaml` auto-appears without any registration step.
- **SC-R03**: Estimated tokens column shows `—` (not `0`) when no node has `estimated_tokens`.

### User Stories

**P1 — Browse workflows in-session**
- Given: 15 workflow files; hotfix ran 2 hours ago
- When: `workflow: list` invoked
- Then: Table shows all 15; hotfix shows "2h ago" in Last Run column

**P2 — New workflow auto-appears**
- When: `workflows/my-pipeline.yaml` added with `name:` and `description:`
- Then: Appears in `make workflows` immediately (no `make install` needed)

---

## Item 6 — Self-Calibrating Skill Loop

### Problem
`quality_metrics` in every skill's `metadata.yml` is permanently zero. No feedback loop exists: a skill failing 40% of the time looks identical to one failing 0%. The Director has no signal for which skills need maintenance or which are reliably performing.

### Approaches

**Option A — JSONL buffer capture (Stop) + pulse rollup (recommended)**
Stop hook appends one JSON line to `telemetry-buffer.jsonl` (< 1ms, no DB). on-pulse batch-imports the buffer into `skill_telemetry`, rebuilds `skill_summary`, writes corrected metrics back to `metadata.yml` atomically, rotates the buffer.

- Pros: Stop hook adds ~0ms overhead; DB write only happens on pulse schedule; buffer is human-readable and inspectable
- Cons: Telemetry is eventually consistent (delay between capture and DB import = pulse interval)

**Option B — Synchronous DB write in Stop hook**
Stop hook writes directly to `skill_telemetry` in SQLite.

- Pros: Immediately queryable
- Cons: DB lock acquisition at session end adds 10–50ms; contention if pulse runs simultaneously

**Option C — Token-log analysis only, no metadata.yml updates**
Build a `scripts/skill_report.py` that reads `studio.db` on demand.

- Cons: Doesn't close the feedback loop — metadata.yml stays frozen, skills can't self-describe health

**Recommendation: Option A** — JSONL buffer for zero-latency capture, pulse for batch import.

### Success signal heuristic
The Stop payload includes the session's final assistant message. Failure indicators (case-insensitive): `error`, `traceback`, `failed`, `exception`, `cannot`, `unable to`, `not found`. If none: `success=True`. Produces ~85% accuracy — rolling 30-run averages are meaningful over 10+ runs. Wrong signals are correctable via `skill-correct` CLI.

### Correction CLI
```
py -3.12 hooks/lib/workflow_state.py skill-correct <telemetry_id> success
py -3.12 hooks/lib/workflow_state.py skill-correct <telemetry_id> failure --reason "heuristic missed retry"
```
The telemetry ID is visible in the pulse skill-health table. Inserting a correction appends to `skill_corrections` — original row is never mutated.

### How `effective_skill_runs` view works
```sql
-- Corrections win over heuristic signals automatically:
SELECT COALESCE(c.corrected_success, t.success) AS success
FROM skill_telemetry t
LEFT JOIN skill_corrections c ON c.telemetry_id = t.id
```
Rolling 30-run rollup queries this view — corrections propagate instantly.

### Pulse rollup (rebuild-safe)
```sql
-- All in one transaction — atomic, self-healing:
DELETE FROM skill_summary;
INSERT INTO skill_summary
    SELECT skill_name,
           COUNT(*) as times_used,
           AVG(success) as success_rate,
           AVG(input_tokens) as avg_input_tokens,
           AVG(output_tokens) as avg_output_tokens,
           AVG(execution_time_s) as avg_exec_time_s,
           MAX(CASE WHEN success=1 THEN invoked_at END) as last_success,
           MAX(CASE WHEN success=0 THEN invoked_at END) as last_failure,
           datetime('now') as updated_at
    FROM (SELECT * FROM effective_skill_runs
          WHERE skill_name IN (
              SELECT skill_name FROM skill_telemetry
              GROUP BY skill_name HAVING COUNT(*) >= 5)
          ORDER BY invoked_at DESC LIMIT 30)
    GROUP BY skill_name;
```

### metadata.yml atomic write
```python
tmp = metadata_path.with_suffix(".yml.tmp")
tmp.write_text(updated_yaml, encoding="utf-8")
tmp.rename(metadata_path)  # atomic on all platforms
```
If the process crashes before rename, `.yml.tmp` is left behind — on-pulse detects and cleans it up.

### Functional Requirements
- **FR-S01**: `on-quality-score.py` MUST detect which dream-studio skill ran (from Stop payload tool_use list), apply success heuristic, append one JSON line to `state_dir() / "telemetry-buffer.jsonl"` using O_APPEND (atomic on POSIX; on Windows: open with `"a"` mode).
- **FR-S02**: on-pulse MUST: read the buffer, batch-INSERT all rows into `skill_telemetry` in one transaction, then rotate the buffer (rename to `.jsonl.bak`, then create new empty file).
- **FR-S03**: on-pulse MUST rebuild `skill_summary` (DELETE + INSERT in one transaction) from `effective_skill_runs`, using last 30 rows per skill.
- **FR-S04**: on-pulse MUST write updated `quality_metrics` back to each skill's `metadata.yml` atomically (write-to-temp, rename). Only for skills with ≥ 5 recorded runs.
- **FR-S05**: Pulse report MUST include a "Skill Health" section flagging skills with `success_rate < 0.70` as ⚠ degraded. Each flagged skill shows the most recent telemetry IDs for correction reference.
- **FR-S06**: `workflow_state.py` MUST expose a `skill-correct <telemetry_id> success|failure [--reason TEXT]` subcommand that inserts to `skill_corrections`. Never updates `skill_telemetry`.
- **FR-S07**: All DB and file operations in Stop hook path MUST be wrapped in try/except — hook exits 0 on any error.
- **FR-S08**: `rolling_window_prune()` in `studio_db.py` MUST keep last 100 rows per skill in `skill_telemetry` (delete older rows when count exceeds 100). Runs in on-pulse.

### Success Criteria
- **SC-S01**: After 5 `dream-studio:build` invocations, `skills/build/metadata.yml` shows non-zero `times_used` and `success_rate`.
- **SC-S02**: Pulse report flags any skill below 70% success rate with ⚠ and the telemetry IDs of failure rows.
- **SC-S03**: `metadata.yml` write is atomic — a crash mid-write leaves the original file intact, `.yml.tmp` cleaned up on next pulse.
- **SC-S04**: Stop hook adds < 5ms to session end (JSONL append only, no DB).
- **SC-S05**: After Director runs `skill-correct <id> success`, the next pulse's rollup reflects the correction without re-running anything.

### User Stories

**P1 — Skills report live health**
- Given: 8 mcp-build invocations, 3 heuristic failures
- When: pulse runs
- Then: Pulse shows `⚠ mcp-build — 8 uses, 62% success (ids: 14, 17, 21)` — Director can inspect and correct

**P2 — Correct a wrong heuristic signal**
- Given: `skill-correct 14 success --reason "error was in user input, not skill"` run
- When: Next pulse runs
- Then: mcp-build success_rate recalculated using corrected row; metadata.yml updated; ⚠ may clear if rate now ≥ 70%

**P3 — Bad metadata.yml write doesn't corrupt skill**
- Given: Pulse crashes mid-write (power failure, process kill)
- When: Next pulse runs
- Then: `.yml.tmp` detected and cleaned; original `metadata.yml` unchanged; rollup reruns cleanly

---

## Risk Residual (after architectural mitigations)

| Risk | Residual risk | Why it's acceptable |
|------|--------------|---------------------|
| DB corruption | Very low | WAL + append-only facts; no UPDATE means nothing to half-write |
| Stop hook latency | Eliminated | JSONL buffer; DB never touched in Stop path |
| Wrong heuristic signals | Low | Correction table available; rolling 30-run avg smooths 1–2 bad signals |
| metadata.yml race | Very low | Single writer (only on-pulse); atomic rename means readers never see partial |
| skill_summary corruption | Self-healing | Rebuilt from facts on every pulse; next pulse recovers automatically |
| DB unbounded growth | Low | Rolling 100-row window per skill; workflow_runs pruned > 90 days |

---

## Implementation Phases

```
Phase 1 — feat/studio-db  (Items 4 foundation)
  T001: hooks/lib/studio_db.py — schema init (WAL, all tables + view), archive_workflow,
        last_run, run_count, record_skill_invocations (batch from buffer),
        rolling_window_prune, skill_correct
  T002: workflow_state.py — wire archive_workflow on terminal status + prune JSON entry
  T003: Tests — archive round-trip, last_run, graceful on error, correction insert

Phase 2 — feat/workflow-registry  (Item 5, depends on Phase 1)
  T004: hooks/lib/workflow_registry.py — list_workflows, format_registry_table
  T005: make workflows target; tests (list, auto-discover, format)
  T006: workflow skill preamble — show registry when no name given

Phase 3 — feat/skill-calibration  (Item 6, depends on Phase 1)
  T007: on-quality-score.py — skill detection + heuristic + JSONL buffer append
  T008: on-pulse.py — buffer import + skill_summary rebuild + metadata.yml atomic write
  T009: workflow_state.py — skill-correct subcommand
  T010: Pulse report — Skill Health section with ⚠ flags + telemetry IDs
  T011: Tests — buffer import, rebuild-safe summary, atomic write, correction propagation
```

---

## Assumptions

- `studio.db` lives at `paths.state_dir() / "studio.db"` (same dir as `workflows.json`)
- `telemetry-buffer.jsonl` lives at `paths.state_dir() / "telemetry-buffer.jsonl"`
- Skill detection uses the Stop payload's `tool_use` list; if `Skill` tool was called with a dream-studio skill name, that's the invoked skill for this session
- PR size limit (120 lines) requires splitting Phase 1 into studio_db.py creation + workflow_state wiring as separate PRs
- on-pulse is the **only** process that writes to `skill_summary` and `metadata.yml` — no concurrent writers

---

**Spec path**: `.planning/specs/platform-intelligence/spec.md`
Waiting for Director approval before plan.
