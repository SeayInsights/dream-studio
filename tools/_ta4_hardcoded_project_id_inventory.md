# TA4 — Hardcoded project_id Inventory

**Generated:** 2026-05-22  
**Status:** Remediation complete

## Scope

Searched for:
1. Literal UUID strings matching `[0-9a-f]{8}-[0-9a-f]{4}-…` in all production Python source (excluding `tests/`, `migrations/`)
2. Known operator project UUIDs: `a4befdce-bfb6-40ed-9e83-ace93edac44b` (dream-cmd), `29ff0914-b15a-4a84-8bc7-5619cc5240f6` (dream-studio)
3. Variable names: `DEFAULT_PROJECT_ID`, `MAIN_PROJECT`, `HARDCODED_PROJECT`, etc.
4. Config files: `.yaml`, `.toml`, `.env`, `.json`

## Findings

### Production Python source — 0 hardcoded project UUIDs

No UUID strings were found in any production `.py` file outside `tests/` and `migrations/`.

### Config / YAML / TOML files — 0 hardcoded project UUIDs

No UUID strings found in any config or settings file.

### Other files (non-production)

| File | Line | Value | Classification | Disposition |
|------|------|-------|----------------|-------------|
| `core/event_store/migrations/056_milestone_order_index.sql` | 14 | `a4befdce-bfb6-40ed-9e83-ace93edac44b` | Migration backfill — historical context | **Intentionally preserved** |
| `.dream-studio-project` | 3 | `29ff0914-b15a-4a84-8bc7-5619cc5240f6` | Runtime marker file, not source | **Not production source** |
| `DREAM-STUDIO-ROADMAP.md` | 186, 302 | `a4befdce-…` | Documentation | **Not production source** |
| `.audit/system-audit-2026-05-17.md` | 304, 464 | `a4befdce-…` | Audit record | **Not production source** |
| `.planning/` (5 files) | — | `a4befdce-…` | Planning files (gitignored) | **Not production source** |
| `tools/_ta3_marker_file_investigation.md` | 37, 49 | `a4befdce-…` | Investigation notes | **Not production source** |

### Migration 056 rationale (preserved)

`core/event_store/migrations/056_milestone_order_index.sql` backfills `order_index` for
a specific project whose milestones were inserted atomically (same `created_at`) — rowid
is the only reliable ordering signal for that specific historical dataset. The UUID is
necessary for correctness: applying the backfill to all projects would be wrong. This is
a legitimate migration artifact, not a runtime hardcode.

## SDLC Emitter Attribution Audit

All SDLC-domain event emitters were audited for `attribution_status` presence:

| File | Function | Event type | attribution_status | Status |
|------|----------|------------|--------------------|--------|
| `core/projects/mutations.py` | `register_project` | `project.created` | `"fully_attributed"` | ✓ |
| `core/projects/mutations.py` | `delete_project` | `project.deleted` | `"fully_attributed"` | ✓ |
| `core/projects/mutations.py` | `delete_project` | `task.deleted` | `"fully_attributed"` | ✓ |
| `core/milestones/mutations.py` | `create_milestone` | `milestone.created` | `"fully_attributed"` | ✓ |
| `core/work_orders/mutations.py` | `mark_task_done` | `task.completed` | `"fully_attributed"` | ✓ |
| `core/work_orders/mutations.py` | `block_work_order` | `work_order.blocked` | **missing** | ✗ → Fixed |
| `core/work_orders/mutations.py` | `add_tasks_from_file` | `task.created` | `"fully_attributed"` | ✓ |
| `core/work_orders/mutations.py` | `create_work_order` | `work_order.created` | `"fully_attributed"` | ✓ |
| `core/work_orders/mutations.py` | `create_task` | `task.created` | `"fully_attributed"` | ✓ |
| `core/work_orders/start.py` | `start_work_order` | `work_order.started` | `"fully_attributed"` | ✓ |
| `core/work_orders/close.py` | `close_work_order` | `gate.bypassed` | `"fully_attributed"` | ✓ |
| `core/work_orders/close.py` | `close_work_order` | `work_order.closed` | `"fully_attributed"` | ✓ |
| `core/skills/invocation.py` | `record_skill_invocation` | `skill.invoked` | conditional (fully_attributed / orphan) | ✓ |

### block_work_order remediation

**Problem:** `block_work_order` used a hand-built dict (not `CanonicalEventEnvelope`) and
the `trace` dict was missing `attribution_status`. The `project_id` is always known at
this call site (resolved from the DB), so the correct status is `"fully_attributed"`.

**Fix:** Converted to `CanonicalEventEnvelope` + added `attribution_status: "fully_attributed"`.

## Summary

- Genuine hardcodes requiring runtime replacement: **0**
- Migration artifacts preserved: **1**
- SDLC emitters fixed (missing attribution_status): **1** (`block_work_order`)
- envelope.py: `_validate_sdlc_event` added; wired into `to_dict()` (non-blocking)
