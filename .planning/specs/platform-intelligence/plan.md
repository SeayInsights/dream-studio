# Implementation Plan: Platform Intelligence — Persistence, Registry, Self-Calibration

**Date**: 2026-04-29 | **Spec**: `.planning/specs/platform-intelligence/spec.md`

## Summary

Build a SQLite-backed analytics backend (`studio.db`) shared across three features: workflow run archival (Item 4), workflow discovery registry (Item 5), and self-calibrating skill telemetry loop (Item 6). The DB uses prefixed tables to enforce data contracts by naming convention; a JSONL buffer decouples the Stop hook from all DB writes; a correction table lets the Director override bad heuristic signals without mutating history.

## Technical Context

**Language/Version**: Python 3.12 (stdlib only — zero new pip dependencies)
**Primary Dependencies**: `sqlite3` (stdlib), `hashlib` (stdlib), `pathlib` (stdlib)
**Storage**: `~/.dream-studio/state/studio.db` (WAL mode), `telemetry-buffer.jsonl` (append-only flat file)
**Testing**: pytest, existing test suite (388 tests, must stay green)
**Target Platform**: Windows / macOS / Linux (all hook paths must be cross-platform)
**Performance Goals**: Stop hook adds < 5ms; JSONL import completes in < 200ms for 500 rows; `make workflows` output in < 1s
**Constraints**: Zero new pip dependencies; all hooks exit 0 on any error; PR ≤ 120 lines each

## Architecture Decisions (locked)

### Table prefix contract
| Prefix | Contract |
|--------|----------|
| `raw_` | Append-only. Never UPDATE or DELETE except scheduled pruning. |
| `cor_` | Correction-only. Append-only. Never mutates `raw_` rows. |
| `sum_` | Rebuild-safe. DELETE + INSERT in one transaction per pulse. |
| `log_` | Audit trail. Append-only. Checked before each import for idempotency. |

### Write path
```
Stop hook → telemetry-buffer.jsonl (O_APPEND, ~0.5ms, no DB)
on-pulse  → import_buffer() → [commit] → rebuild_summaries()
              (these two steps always orchestrated together)
```

### studio_db.py dual role
Both a **library** (imported by on-pulse, workflow_state.py) and a **CLI** (called by hooks via subprocess with retry). Same pattern as `workflow_state.py`.

### Idempotent import
Each JSONL batch gets a `batch_id` (SHA256 of file content). Import transaction: INSERT all telemetry rows + INSERT one `log_batch_imports` row atomically. On retry: if `batch_id` exists → skip.

### Correction layer
`cor_skill_corrections` references `raw_skill_telemetry(id)`. View `effective_skill_runs` applies `COALESCE(correction, original)`. Rollup queries this view — corrections propagate without re-running anything.

### Rebuild-safe summary
`sum_skill_summary` is `DELETE + INSERT` in one transaction per pulse. Self-heals from `raw_skill_telemetry` + `cor_skill_corrections` on every run.

## Project Structure

```
hooks/lib/
├── studio_db.py          ← NEW: schema, CLI, library functions
├── workflow_registry.py  ← NEW: list_workflows, format_registry_table
└── (workflow_state.py)   ← MODIFIED: archive on terminal status

packs/meta/hooks/
├── on-quality-score.py   ← MODIFIED: JSONL buffer append
└── on-pulse.py           ← MODIFIED: import_buffer + rebuild_summaries + metadata write

state/ (runtime, not in repo)
├── studio.db             ← NEW: WAL-mode SQLite
└── telemetry-buffer.jsonl ← NEW: Stop hook capture buffer

tests/unit/
├── test_studio_db.py     ← NEW
├── test_workflow_registry.py ← NEW
└── test_skill_calibration.py ← NEW
```

## Phase Breakdown

### Phase 1 — feat/studio-db (Items 4 foundation)
Two PRs due to 120-line constraint:
- **PR A**: `studio_db.py` — schema init + library functions + CLI
- **PR B**: `workflow_state.py` wiring — archive on terminal + prune JSON

### Phase 2 — feat/workflow-registry (Item 5)
One PR: `workflow_registry.py` + `make workflows` + skill preamble + tests

### Phase 3 — feat/skill-calibration (Item 6)
Two PRs due to 120-line constraint:
- **PR A**: Stop hook buffer append + `skill-correct` CLI
- **PR B**: on-pulse import + rebuild + metadata write + Skill Health report + tests

## Risk Register

| Risk | Mitigation |
|------|-----------|
| DB corruption | WAL + append-only raw_ tables; failed INSERT leaves previous data intact |
| Stop hook latency | JSONL buffer — Stop hook never touches DB |
| Duplicate import on retry | `log_batch_imports` idempotency guard (SHA256 batch_id) |
| Wrong heuristic signal | `cor_skill_corrections` correction table + COALESCE view |
| sum_ corruption | Self-healing: rebuilt from raw_ on every pulse |
| metadata.yml write race | Single writer (on-pulse only) + atomic rename |
| Unbounded DB growth | Rolling 100-row window per skill; raw_workflow_runs pruned > 90 days |
