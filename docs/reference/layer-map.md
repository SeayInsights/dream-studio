# System Layer Map

**Status:** CURRENT  
**Last reviewed:** 2026-06-07 (WO-P)

---

## Layer Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ADAPTER LAYER                                                               │
│  Claude Code adapter (.claude/ hooks, skills, CLAUDE.md projections)         │
│  Entry points: hooks/git/pre-push, hooks/context-threshold, hooks/session   │
│  Projection: .claude/CLAUDE.md (generated from canonical/adapter_authority)  │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ invokes via function call (not subprocess)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CONTROL LAYER                                                               │
│  Skills: canonical/skills/ (routed by ds-* skill pack names)                 │
│  Workflows: canonical/workflows/ (YAML manifests, e.g. pre-push.yaml)        │
│  Gates: core/gates/ (pre_push.py, skill_sync_source.py, migration_risk.py)  │
│  Work orders: core/work_orders/ (start.py, close.py, task management)       │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ reads and writes via
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  AUTHORITY LAYER                                                             │
│  SQLite DB: ~/.dream-studio/state/studio.db                                  │
│  Canonical events: business_canonical_events, ai_canonical_events            │
│  Business state: business_projects, business_milestones, business_work_orders│
│  Token tracking: token_usage_records (with cache_read_tokens, migration 105) │
│  Eval records: ds_eval_baselines, ds_eval_runs                               │
│  Spool buffer: ~/.dream-studio/spool/*.json                                  │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ projected into
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PROJECTION LAYER                                                            │
│  Dashboard API: projections/api/ (FastAPI routes + Pydantic models)          │
│  Collectors: projections/core/collectors/ (TokenCollector, etc.)             │
│  Queries: projections/api/queries/ (token_attribution, etc.)                 │
│  Read models: computed from canonical events, no raw DB writes               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Modules by Layer

### Adapter Layer

| Module | Purpose |
|--------|---------|
| `hooks/git/pre-push` | Git hook: calls `py core/gates/pre_push.py` |
| `hooks/context-threshold` | Context limit hook: triggers re-projection |
| `hooks/session-start`, `hooks/session-end` | Session lifecycle events |
| `.claude/CLAUDE.md` | Claude Code adapter projection (generated) |
| `canonical/skills/` | Skill spec files (referenced by ds-* packs) |

### Control Layer

| Module | Purpose |
|--------|---------|
| `core/gates/pre_push.py` | Pre-push gate runner; two-tier (blocking/advisory) |
| `core/gates/skill_sync_source.py` | A4/A5 enforcement block regression check |
| `core/gates/migration_risk.py` | SQL/migration change risk classifier |
| `core/work_orders/start.py` | Work order start: loads context, sets boundary |
| `core/work_orders/close.py` | Work order close: checks post-build gates |
| `core/work_orders/task.py` | Task lifecycle management |
| `core/eval/runner.py` | Behavioral eval runner (deterministic, WO-N2) |
| `core/eval/schema.py` | EvalCase, EvalResult, MatchResult dataclasses |
| `core/eval/matcher.py` | Event-trace matcher for deterministic scoring |
| `core/pricing/claude_models.py` | Token cost computation (`compute_cost()`) |

### Authority Layer

| Table/File | Purpose |
|------------|---------|
| `business_canonical_events` | Business-domain event authority |
| `ai_canonical_events` | AI-domain event authority (token.consumed, etc.) |
| `canonical_events` | Compat VIEW (UNION of both authority tables) |
| `business_projects` | Project registry |
| `business_milestones` | Milestone tracking |
| `business_work_orders` | Work order lifecycle state |
| `business_tasks` | Task completion tracking |
| `token_usage_records` | Token telemetry (with cache_read_tokens) |
| `ds_eval_baselines` | Eval baseline scores per eval_id/version |
| `ds_eval_runs` | Per-run eval evidence and regression history |
| `reg_gotchas` | Known-failure patterns from gate and debug runs |

### Projection Layer

| Module | Purpose |
|--------|---------|
| `projections/api/routes/metrics.py` | Dashboard token metrics endpoint |
| `projections/api/routes/intelligence.py` | Token intelligence endpoint |
| `projections/api/queries/token_attribution.py` | Canonical token metric queries |
| `projections/core/collectors/token_collector.py` | Token metrics from token_usage_records |
| `projections/core/collectors/authority_sources.py` | SQL subquery builders with fallbacks |

---

## Dependency Rules (Hard Constraints)

1. **Adapters never write to authority tables.** Hooks emit events via spool only.
2. **Projections are read-only.** No projection module writes to canonical event tables.
3. **CLI commands are the designated writer for business state** (projects, milestones, work orders, tasks).
4. **The ingestor is the sole writer to authority event tables.** No direct INSERT to `business_canonical_events` or `ai_canonical_events` from other code.
5. **Skills route through function calls, not subprocess `py -m interfaces.cli.ds`.** The A4/A5 enforcement block is the canonical reference.

---

## Per-API Quick Reference

### `core/gates/pre_push.py`

```python
run_pre_push_gates(
    manifest_path: Path | None = None,
    repo_root: Path | None = None,
    stop_on_first_failure: bool = True,
    emit_events: bool = True,
) -> PrePushReport
```

- **Reads:** `canonical/workflows/pre-push.yaml`
- **Writes (spool):** `gate.pre_push.failed` events for each failed blocking gate
- **Returns:** `PrePushReport` with `overall_passed`, `failed_gates`, `advisory_warnings`

### `core/pricing/claude_models.py`

```python
compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float  # USD
```

- **Reads:** `CLAUDE_MODEL_PRICING` dict (hardcoded pricing table)
- **Writes:** nothing
- **Normalization:** strips date suffixes (`claude-haiku-4-5-20251001` → `claude-haiku-4-5`)

### `projections/api/queries/token_attribution.canonical_token_metrics()`

```python
canonical_token_metrics(days: int) -> dict
```

- **Reads:** `canonical_events` (compat view) for `token.consumed` events
- **Writes:** nothing
- **Returns:** `{total_tokens, input_tokens, output_tokens, cache_hits, total_cost_usd, by_model, by_project, timeline, ...}`

### `projections/core/collectors/authority_sources.token_usage_sql()`

```python
token_usage_sql(conn: sqlite3.Connection) -> str | None
```

- **Reads:** `PRAGMA table_info("token_usage_records")` to detect available columns
- **Returns:** SQL subquery string with `_column_or_literal()` fallbacks for optional columns
- **Fallbacks:** `adapter_id → NULL`, `cache_read_tokens → 0` (pre-migration 105 DBs)
