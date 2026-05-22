# Finding: reg_projects / ds_projects Dual Store (TA0d)

**Discovered:** 2026-05-22 during TA5 dashboard testing
**Severity:** Data correctness — `/api/v1/projects` returns `total: 0` despite populated `ds_projects`

## Symptom

`GET /api/v1/projects` returns:

```json
{"total": 0, "projects": []}
```

The `ds_projects` table has active projects (Dream Studio, Dream Command, etc.).

## Root Cause

The projects endpoint reads from `reg_projects`, not `ds_projects`.
These are two parallel project stores that have drifted out of sync:

- `ds_projects` — the canonical project authority used by the CLI, work orders, milestones, and all SDLC operations
- `reg_projects` — an older project registry table; now stale relative to `ds_projects`

## Impact

- `/api/v1/projects` always returns empty
- Any dashboard surface that shows project totals reads from the wrong store
- `by_project` breakdowns on the tokens endpoint use project UUIDs from `ds_projects`; there is no resolution path to human-readable project names without joining to `ds_projects`

## Resolution (future workstream: TA0d)

Options:
1. Repoint the `/api/v1/projects` endpoint to `ds_projects`
2. Reconcile `reg_projects` as a view or alias over `ds_projects`
3. Deprecate `reg_projects` entirely

**Decision gate:** Requires audit of all `reg_projects` read sites before switching.

## Scope of this PR (TA5)

No fix. Document only. Follow-on backlog entry: **TA0d — Reconcile reg_projects and ds_projects**.
