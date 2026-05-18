# Dream Studio Schema Reference

## Overview

Dream Studio's authority database is a SQLite file at `~/.dream-studio/state/studio.db`. It is managed entirely through migrations stored in `core/event_store/migrations/`. The schema is append-only by convention — migrations add tables, columns, and indexes but never drop them. The current schema version is **54 applied migrations**.

All reads and writes go through `core/event_store/studio_db.py` using WAL mode for concurrent access safety.

---

## Table Glossary

### `canonical_events`
The core event log. Every significant action in Dream Studio (skill invocations, work order transitions, gate evaluations) produces a canonical event. Primary key is `event_id` (UUID). Events are append-only and carry an envelope with `project_id`, `adapter_id`, and `invocation_mode`. Used for traceability and replay.

### `ds_projects`
Project registry. One row per Dream Studio project. Primary key is `project_id` (UUID). Fields include `name`, `description`, `status` (active/inactive), and timestamps. The active project is resolved by querying `WHERE status = 'active' ORDER BY updated_at DESC`. Used by all SDLC operations to scope records.

### `ds_milestones`
Milestone definitions within a project. Each milestone groups related work orders under a deliverable boundary. Primary key is `milestone_id` (UUID). Foreign key to `ds_projects.project_id`. Fields include `title`, `description`, `status`, and `due_date`.

### `ds_work_orders`
Work order records — the atomic unit of executable work. Each work order has a bounded module, task list, and gate requirements. Primary key is `work_order_id` (UUID). Foreign keys to `ds_milestones.milestone_id` and `ds_work_order_types.type_id`. Fields include `title`, `status` (open/in_progress/complete/blocked), `work_order_type`, and timestamps.

### `ds_tasks`
Individual tasks within a work order. Primary key is `task_id` (UUID). Foreign key to `ds_work_orders.work_order_id`. Fields include `title`, `status` (pending/complete), and `sequence` (ordering). Task completion is tracked via `ds work-order task-done`.

### `ds_work_order_types`
Lookup table defining work order type contracts. Each type specifies `post_build_gate` (pipe-separated gate names that must pass before close) and `module_boundary` defaults. Predefined types: `infrastructure`, `api_endpoint`, `ui_component`, `ui_page`, `data_pipeline`, `saas_feature`, `deployment`.

### `ds_design_briefs`
Design briefs for projects. A design brief captures visual language, design system, component requirements, and anti-slop criteria before implementation begins. Primary key is `brief_id` (UUID). Foreign key to `ds_projects.project_id`. Fields include `status` (draft/locked), `design_system`, and a JSON `content` blob. Briefs must be locked (human-approved) before UI work orders can start.

### `reg_projects`
Registry for cross-project skill invocations. Tracks which projects have been registered with which skills for portfolio-level intelligence.

### `reg_skills`
Skill usage registry. One row per skill invocation, recording `skill_id`, `mode`, `project_id`, `timestamp`, and outcome. Used by the analytics dashboard and coach routing.

### `reg_gotchas`
Known failure patterns and their fixes. Each gotcha has a stable `gotcha_id` (hash of the normalized error message), `skill_id`, `severity`, `title`, `context`, and `fix`. Populated by `ds memory ingest-sessions` and manual lesson capture. Used to surface warnings before a developer hits a known failure.

### `raw_lessons`
Unstructured learning records captured during sessions. Used as a staging area before promotion to `reg_gotchas` or knowledge base entries.

### `ds_documents`
Architectural documents tracked by Dream Studio. Fields include `doc_type` (architecture_decision, constitution, etc.), `title`, `content` (NULL for session-harvested docs to avoid storing raw content), and `source_path`. Used to build a document index across projects.

### `execution_events`
Fine-grained execution telemetry. Each hook invocation, skill load, and tool call produces an execution event. Used by the telemetry dashboard and the `on-skill-metrics` hook.

### `security_findings`
Security scan results stored by the `ds-security` pack. Each finding has a severity, category, rule ID, and remediation status. Used by the executive security dashboard.

---

## Project Spine ERD

```
ds_projects (1)
  ├── (N) ds_milestones
  │         └── (N) ds_work_orders
  │                   ├── (1) ds_work_order_types  [lookup]
  │                   └── (N) ds_tasks
  └── (N) ds_design_briefs
```

Cardinality:
- One project → many milestones
- One milestone → many work orders
- One work order → one type (lookup)
- One work order → many tasks
- One project → many design briefs (typically one per project)

---

## Event Envelope Fields

Every canonical event carries a `CanonicalEventEnvelope` with these fields:

| Field | Always populated | Notes |
|-------|-----------------|-------|
| `event_id` | Yes | UUID generated at emit time |
| `event_type` | Yes | String identifier (e.g., `skill_invoked`, `work_order_started`) |
| `project_id` | When available | Resolved from active project in DB; NULL for system events |
| `adapter_id` | Yes | Always `"claude"` for Claude Code sessions |
| `invocation_mode` | Yes | One of: `interactive`, `batch`, `hook`, `cli` |
| `timestamp` | Yes | ISO 8601 UTC |
| `payload` | Yes | JSON blob with event-specific data |
| `session_id` | When available | Claude Code session identifier |

`invocation_mode` values:
- `interactive` — user-initiated from Claude Code chat
- `batch` — running as part of a workflow or batch operation
- `hook` — triggered by a Claude Code hook (UserPromptSubmit, Stop, etc.)
- `cli` — triggered directly from the `ds` CLI
