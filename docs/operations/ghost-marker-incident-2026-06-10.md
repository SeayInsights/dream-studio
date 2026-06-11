# Ghost-Marker Incident — 2026-06-10
**Incident:** `.dream-studio-project` marker written for non-existent project 'Hinted' (ddd5383f)
**Work Order:** WO-MARKER-FORMAT (80294f4a-0dea-40ca-bab5-06605d360945)
**Authority DB audit record:** `decision_log.decision_id = 8cc3a6d0-c67d-4dc8-b157-3928e8ba1cb1`

## Root Cause

**Module:** `core/projects/mutations.py`
**Function:** `_write_project_marker()`
**Triggering condition:** Called with `write_marker=True` via the brownfield acquisition
path on a directory that already contained a marker for a different project. No guard
existed against overwriting existing markers.

## Triggering Code Path

```
core.projects.bulk_intake.bulk_acquire(write_marker=True)
  -> core.projects.acquisition.acquire_project(write_marker=True)
     [core/projects/acquisition.py]
  -> core.projects.intake.register_project_for_intake(write_marker=True)
     [core/projects/intake.py]
  -> core.projects.mutations.register_project(write_marker=True)
     [core/projects/mutations.py]
  -> core.projects.mutations._write_project_marker()
     [core/projects/mutations.py, lines 367–440 before fix]
```

All three entry points (`bulk_intake`, `acquisition`, `intake`) forward the
`write_marker` flag to `register_project()`, which calls `_write_project_marker()`
unconditionally when `write_marker=True`. Before PR #278, `_write_project_marker()`
had no check for an existing marker.

## What Happened

The target directory already held a valid `.dream-studio-project` marker for a
different project. A brownfield acquisition call with `write_marker=True` on that
same directory caused `_write_project_marker()` to silently overwrite the existing
marker with the new project_id (ddd5383f / 'Hinted'). The new project row was
later deleted or never completed registration, leaving a ghost marker (filesystem
marker pointing to a project_id absent from `business_projects`).

## Fix

Two guards shipped via WO-MARKER-FORMAT (merged 2026-06-11):

**PR #278** — cross-project overwrite guard:
- `_write_project_marker()` now reads any existing marker and raises `ValueError`
  if the stored `project_id` differs from the new one.

**PR #279** — DB-existence guard (remediation WO 993ba17a):
- Added optional `db_path` parameter to `_write_project_marker()`.
- When `db_path` is provided (as it is from `register_project()`), the function
  queries `business_projects` to confirm the `project_id` exists before writing.
- Raises `ValueError("project_id does not exist in business_projects")` for
  deleted or phantom project IDs.
