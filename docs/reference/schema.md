# Dream Studio Schema Reference

Complete catalog of all tables in `~/.dream-studio/state/studio.db`.

**Authority:** SQLite at `~/.dream-studio/state/studio.db`  
**Access:** `core/event_store/studio_db.py` — WAL mode, `PRAGMA foreign_keys = ON`  
**Migrations:** `core/event_store/migrations/` — 107 total, append-only convention  
**Current version:** checked via `ds validate`

---

## Project Spine ERD

```
business_projects (1)
  ├── (N) business_milestones
  │         └── (N) business_work_orders
  │                   ├── (1) business_work_order_types  [lookup]
  │                   └── (N) business_tasks
  ├── (N) business_design_briefs
  └── (N) business_work_order_preflights  [via work orders]
```

---

## SDLC Authority Tables

### `business_projects`
Project registry. One row per Dream Studio project.

| Column | Type | Notes |
|--------|------|-------|
| `project_id` | TEXT PK | UUID |
| `name` | TEXT NOT NULL | Display name |
| `description` | TEXT | Optional |
| `status` | TEXT | `active` / `paused` / `deleted` |
| `project_path` | TEXT | Resolved absolute path to repo |
| `created_at` | TEXT | ISO 8601 UTC |
| `updated_at` | TEXT | ISO 8601 UTC |

Active project: `WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1`

---

### `business_milestones`
Milestone definitions. Groups work orders under a deliverable boundary.

| Column | Type | Notes |
|--------|------|-------|
| `milestone_id` | TEXT PK | UUID |
| `project_id` | TEXT | FK → business_projects |
| `title` | TEXT NOT NULL | |
| `description` | TEXT | |
| `status` | TEXT | `pending` / `active` / `complete` / `deleted` |
| `order_index` | INTEGER | Sort order |
| `due_date` | TEXT | Optional ISO date |
| `stage_gate_json` | TEXT | JSON gate definitions |
| `validation_expectations_json` | TEXT | |
| `security_readiness_checks_json` | TEXT | |
| `created_at` | TEXT | |
| `updated_at` | TEXT | |
| `source_event_id` | TEXT | Canonical event that created this row |
| `last_event_id` | TEXT | Most recent event applied |

---

### `business_work_orders`
Atomic work units. Populated by event projection from `business_canonical_events`.

| Column | Type | Notes |
|--------|------|-------|
| `work_order_id` | TEXT PK | UUID |
| `project_id` | TEXT | FK → business_projects |
| `milestone_id` | TEXT | FK → business_milestones |
| `title` | TEXT | |
| `description` | TEXT | |
| `work_order_type` | TEXT | FK → business_work_order_types |
| `status` | TEXT | `created` / `in_progress` / `blocked` / `closed` |
| `created_at` | TEXT | |
| `started_at` | TEXT | |
| `closed_at` | TEXT | |
| `blocked_at` | TEXT | |
| `block_reason` | TEXT | |
| `source_event_id` | TEXT | |
| `last_event_id` | TEXT | |
| `last_updated_at` | TEXT | |

---

### `business_tasks`
Tasks within a work order.

| Column | Type | Notes |
|--------|------|-------|
| `task_id` | TEXT PK | UUID |
| `work_order_id` | TEXT | FK → business_work_orders |
| `project_id` | TEXT | FK → business_projects |
| `title` | TEXT NOT NULL | |
| `description` | TEXT | |
| `status` | TEXT | `pending` / `complete` / `deleted` |
| `created_at` | TEXT NOT NULL | |
| `updated_at` | TEXT NOT NULL | |
| `source_event_id` | TEXT | |
| `last_event_id` | TEXT | |

---

### `business_work_order_types`
Lookup table. Defines 10 canonical work order type contracts.

| Type | Post-build gate | Notes |
|------|----------------|-------|
| `ui_component` | design_brief_locked | Reusable UI element |
| `ui_page` | design_brief_locked | Complete screen/view |
| `api_endpoint` | api_contract_exists | Backend route |
| `authentication` | all_tests_pass | Auth/session/OAuth |
| `saas_feature` | design_brief_locked, api_contract_exists | Cross-cutting feature |
| `data_pipeline` | all_tests_pass | ETL/ingestion/batch |
| `game_mechanic` | all_tests_pass | Gameplay rule |
| `deployment` | — | CI/CD/containers |
| `infrastructure` | — | Schema/cloud/network |
| `documentation` | — | Docs/ADRs/references |

---

### `business_design_briefs`
Design specifications. Must be locked before UI work begins.

| Column | Type | Notes |
|--------|------|-------|
| `brief_id` | TEXT PK | UUID |
| `project_id` | TEXT | FK → business_projects |
| `status` | TEXT | `draft` / `locked` |
| `design_system` | TEXT | One of 5 design systems |
| `content` | TEXT | JSON blob |
| `created_at` | TEXT | |
| `updated_at` | TEXT | |

Design system values: `tech-minimal`, `editorial-modern`, `brutalist-bold`, `playful-rounded`, `executive-clean`

---

## Canonical Event Tables

### `business_canonical_events`
Business-domain events (SDLC, security, document lifecycle). Source for all SDLC projections.

| Column | Type | Notes |
|--------|------|-------|
| `event_id` | TEXT PK | UUID |
| `received_at` | TEXT | Ingest timestamp |
| `event_type` | TEXT NOT NULL | e.g., `work_order.created` |
| `event_timestamp` | TEXT NOT NULL | Emission timestamp |
| `schema_version` | INTEGER | Default 1 |
| `trace` | JSON | `{domain, project_id, milestone_id, work_order_id, task_id}` |
| `payload` | JSON | Event-specific data |
| `correlation_id` | TEXT | Cross-event correlation |
| `project_id` | TEXT | Denormalized from trace |
| `milestone_id` | TEXT | Denormalized from trace |
| `work_order_id` | TEXT | Denormalized from trace |
| `task_id` | TEXT | Denormalized from trace |
| `severity` | TEXT | `info` / `warn` / `error` |
| `source` | TEXT | Default `ingestor` |

---

### `ai_canonical_events`
AI-domain events (skill invocations, session lifecycle, token accounting).

| Column | Type | Notes |
|--------|------|-------|
| `event_id` | TEXT PK | |
| `event_type` | TEXT NOT NULL | e.g., `skill.invoked` |
| `event_timestamp` | TEXT NOT NULL | |
| `session_id` | TEXT | |
| `skill_id` | TEXT | |
| `workflow_id` | TEXT | |
| `agent_id` | TEXT | |
| `hook_id` | TEXT | |
| `model_id` | TEXT | |
| `trace` | JSON | |
| `payload` | JSON | |
| `severity` | TEXT | |

---

### `raw_claude_code_events`
Raw pre-normalization event archive. Written before dual-canonical split. Kept for full-fidelity replay.

---

## Projection Infrastructure

### `projection_state`
Cursor state for each registered projection.

| Column | Type | Notes |
|--------|------|-------|
| `projection_name` | TEXT PK | |
| `last_processed_business_event_id` | TEXT | Last consumed business event |
| `last_processed_ai_event_id` | TEXT | Last consumed AI event |
| `last_run_at` | TEXT | |
| `events_processed_total` | INTEGER | |
| `events_failed_total` | INTEGER | |

### `projection_retry_queue`
Transient failure backlog for projection retry.

### `projection_dead_letter`
Events that exhausted all retries. Operator resolves manually via `ds projection dead-letter resolve`.

### `projection_checkpoints`
Legacy checkpoint table preserved for backward compatibility.

---

## Preflight & Findings

### `preflight_events`
Append-only findings spine for work orders. AD-6 emit-only pattern.

| Column | Type | Notes |
|--------|------|-------|
| `event_id` | TEXT PK | UUID |
| `work_order_id` | TEXT | |
| `finding_type` | TEXT | `blocking` / `advisory` / `info` |
| `severity` | TEXT | `critical` / `high` / `medium` / `low` |
| `category` | TEXT | e.g., `security`, `format`, `test` |
| `message` | TEXT | Human-readable finding |
| `emitted_at` | TEXT | |
| `gate_name` | TEXT | Gate that produced this finding |
| `source` | TEXT | |

### `business_work_order_preflights`
Projection-populated read model for preflight findings (from preflight_events).

---

## Telemetry & Analytics

### `execution_events`
Fine-grained execution telemetry spine. One row per skill invocation, hook fire, or tool call.

| Column | Type | Notes |
|--------|------|-------|
| `event_id` | TEXT PK | |
| `project_id` | TEXT | |
| `skill_id` | TEXT | |
| `workflow_id` | TEXT | |
| `session_id` | TEXT | |
| `hook_id` | TEXT | |
| `outcome_status` | TEXT | `success` / `error` / `timeout` |
| `model_id` | TEXT | |
| `duration_ms` | INTEGER | |
| `emitted_at` | TEXT | |

### `token_usage_records`
Per-turn token accounting.

| Column | Type | Notes |
|--------|------|-------|
| `record_id` | TEXT PK | |
| `session_id` | TEXT | |
| `project_id` | TEXT | |
| `input_tokens` | INTEGER | |
| `output_tokens` | INTEGER | |
| `cache_read_tokens` | INTEGER | Added migration 105 |
| `model_id` | TEXT | |
| `recorded_at` | TEXT | |

### `reg_skills`
Skill usage registry. One row per invocation.

### `reg_gotchas`
Known failure patterns. Stable `gotcha_id` (hash of normalized error), `severity`, `title`, `context`, `fix`.

### `raw_lessons`
Unstructured learning records before promotion to gotchas.

### `ds_documents`
Document index. `doc_type`, `title`, `source_path`, `content` (NULL for large docs).

---

## Security

### `security_findings` (via `sec_*` tables)
Security scan results from `ds-security` pack.

| Column | Type | Notes |
|--------|------|-------|
| `finding_id` | TEXT PK | |
| `severity` | TEXT | |
| `category` | TEXT | |
| `rule_id` | TEXT | SARIF rule reference |
| `remediation_status` | TEXT | `open` / `resolved` / `accepted_risk` |
| `project_id` | TEXT | |
| `scan_run_id` | TEXT | |
| `created_at` | TEXT | |

---

## Behavioral Evals

### `ds_eval_runs`
Behavioral eval evidence with baseline tracking.

| Column | Type | Notes |
|--------|------|-------|
| `run_id` | TEXT PK | UUID |
| `eval_id` | TEXT | |
| `skill_id` | TEXT | |
| `passed` | INTEGER | Boolean (0/1) |
| `total_score` | REAL | 0.0–1.0 |
| `skill_versions_snapshot` | TEXT | JSON |
| `run_at` | TEXT | |

---

## Migration History (key milestones)

| Range | Phase | Tables introduced |
|-------|-------|------------------|
| 001–020 | Foundation | raw_workflow_runs, raw_skill_telemetry, raw_pulse_snapshots, security findings |
| 021–050 | Authority | execution_events, process_runs, telemetry_module_registry, business_work_order_types, business_design_briefs |
| 051–084 | SDLC + Projections | business_work_orders (069), business_projects/milestones/tasks (070), canonical_events (083) |
| 085–100 | Dual-Canonical | business_canonical_events, ai_canonical_events, projection_state, projection_retry_queue, projection_dead_letter |
| 101–107 | Hardening | ds_eval_runs (104), token cache_read_tokens (105), preflight_events + business_work_order_preflights (107) |

---

## Cross-references

- Migration files: `core/event_store/migrations/`
- DB access: `core/event_store/studio_db.py`, `core/config/database.py`
- Event types: [`docs/reference/events.md`](events.md)
- Projection engine: `core/projections/`
