# ds-project:manage — Project lifecycle management (list / switch / archive / delete)

**Wraps:**
- `core.projects.queries.get_project_list(status_filter='active', source_root=..., dream_studio_home=...)` — list projects, optionally filtered by status.
- `core.projects.mutations.set_active_project(project_id=..., source_root=..., dream_studio_home=...)` — make this project active (demotes any other active project to `paused`).
- `core.projects.mutations.deactivate_project(project_id=..., source_root=..., dream_studio_home=...)` — set status to `paused` (archive without deletion).
- `core.projects.mutations.delete_project(project_id=..., confirm=False, source_root=..., dream_studio_home=...)` — cascade-delete a project + all its tasks, work orders, milestones, design briefs.

---

## When to invoke this mode

The user signaled they want to manage projects at a portfolio level rather than work inside a specific project. Examples:

- "list projects" / "what projects do I have?" → list
- "switch to project X" / "make X active" → switch (set active)
- "archive project X" / "pause project X" → archive (deactivate)
- "delete project X" / "remove project X" → delete (high stakes — see below)

This mode is **not** for scoping new projects (use `ds-project:scope`), filling a brief (`ds-project:brief`), or resuming work inside the active project (`ds-project:resume`).

---

## What to do

### List

1. Call `get_project_list(status_filter=None, source_root=..., dream_studio_home=...)`. The default `status_filter='active'` returns only active projects; pass `None` (or omit) for all.
2. Present the returned `projects` list grouped by `status` (active → paused → complete → cancelled). For each row show `name`, `description`, `status`, `created_at`. Keep `project_id` internal — only surface it if the user asks.

### Switch (set active)

1. Resolve the target `project_id`. If the user named the project by description, call `get_project_list(status_filter=None, ...)` and match on `name`. If multiple match, ask the user to choose.
2. Show the user the project's `name` + current `status` and confirm: *"Switch to this project? Any currently-active project will be paused. (yes/no)"*
3. Call `set_active_project(project_id=<id>, source_root=..., dream_studio_home=...)`. Surface the result dict (`{"ok": True, "project_id": str, "status": "active"}`).
4. Suggest *"Run `ds-project:resume` to pick up where this project left off."*

### Archive (deactivate)

1. Resolve the `project_id` the same way as Switch.
2. Confirm: *"Pause this project? You can switch back to it later. (yes/no)"*
3. Call `deactivate_project(project_id=<id>, source_root=..., dream_studio_home=...)`. Surface `{"ok": True, "project_id": str, "status": "paused"}`.

### Delete (high stakes — cascade)

1. Resolve the `project_id`.
2. **Always preview dependents first.** Call `delete_project(project_id=<id>, confirm=False, source_root=..., dream_studio_home=...)`. If the project has dependents, the function returns `ok=False` with counts: `task_count`, `work_order_count`, `milestone_count`.
3. **Surface the full impact.** *"This will delete N tasks, M work orders, and K milestones. This is not reversible. Confirm? (yes/no)"* — show the user every count returned.
4. **Wait for explicit, unambiguous yes.** "yes", "delete it", or naming the project explicitly count. "ok", "sure", "go ahead" do NOT count — ask again with the project name.
5. On confirmation, re-call `delete_project(project_id=<id>, confirm=True, ...)`. Surface the returned `deleted` counts as the final acknowledgement.

## Surface contract

`get_project_list` returns::

    {
      "ok": True,
      "projects": [
        {"project_id": str, "name": str, "description": str,
         "status": str, "created_at": str},
        ...
      ],
    }

`set_active_project` returns::

    {"ok": True, "project_id": str, "status": "active"}
    | {"ok": False, "error": "Project not found: <id>"}

`deactivate_project` returns::

    {"ok": True, "project_id": str, "status": "paused"}
    | {"ok": False, "error": "Project not found: <id>"}

`delete_project` returns one of three shapes:

- Missing project: ``{"ok": False, "error": "Project not found: <id>"}``
- Has dependents without confirm: ``{"ok": False, "error": "Project <id> has dependents (... tasks, ... work orders, ... milestones). Pass confirm=True to cascade delete.", "task_count": int, "work_order_count": int, "milestone_count": int}``
- Success: ``{"ok": True, "project_id": str, "deleted": {"tasks": int, "work_orders": int, "milestones": int}}``

## Side effects

- **List**: none (read-only against SQLite).
- **Switch**: updates `status` to `paused` for any currently-active project and to `active` for the target.
- **Archive**: sets the target's `status` to `paused`.
- **Delete**: cascade-deletes rows from `ds_tasks`, `ds_work_orders`, `ds_milestones`, `ds_design_briefs`, then `ds_projects`. Irreversible.
