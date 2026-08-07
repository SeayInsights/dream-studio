# ds-workorder:status — Read-only status of work orders + tasks

**Wraps:**
- `core.work_orders.queries.list_work_orders(project_id=..., status_filter=None, source_root=..., dream_studio_home=...)` — list WOs for a project.
- `core.work_orders.queries.list_tasks(work_order_id=..., source_root=..., dream_studio_home=...)` — list tasks under a single WO.

---

## When to invoke this mode

The user asked about the state of work — "what work orders are open?", "show tasks for the auth WO", "what's in progress?", "where are we on milestone 1?". This mode is **read-only**. It does not mutate anything.

## What to do

1. **If the user asked about work orders broadly:** call `list_work_orders(project_id=<active project>, source_root=..., dream_studio_home=...)`. To narrow, pass `status_filter` — one of `'open'`, `'in_progress'`, `'complete'`, `'blocked'`, `'cancelled'`. Present the returned `work_orders` list as a plain-English summary grouped by status. Each WO has `id`, `title`, `type`, `status`, `milestone`.

2. **If the user asked about a specific WO's tasks:** call `list_tasks(work_order_id=<wo>, source_root=..., dream_studio_home=...)`. Present the `tasks` list — each task has `task_id`, `title`, `description`, `status`. Group by status if there's a mix.

3. **Surface only what the function returned.** If the user asks about something the dict doesn't expose (e.g., recent activity, who last touched it), tell them this mode doesn't have that data and suggest the source — for example, `git log` for code-side activity, or the dashboard for spool events.

4. **Do not invent UUIDs.** If the user asked for a WO they don't remember the title of, ask for a fragment and search the returned list. Don't make up identifiers.

## Surface contract

`list_work_orders` returns::

    {
      "ok": True,
      "work_orders": [
        {"id": str, "title": str, "type": str, "status": str, "milestone": str},
        ...
      ],
    }

`list_tasks` returns::

    {
      "ok": True,
      "work_order_id": str,
      "tasks": [
        {"task_id": str, "title": str, "description": str, "status": str},
        ...
      ],
    }

## Side effects

None. This mode reads the SQLite authority and does not mutate, write files, or emit spool events.
