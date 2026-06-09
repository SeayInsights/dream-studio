# ds-workorder:execute — Mark a task complete

**Wraps:** `core.work_orders.mutations.mark_task_done(work_order_id=..., task_id=..., source_root=..., dream_studio_home=..., planning_root=...)`

---

## When to invoke this mode

The user signaled that a task within the active work order is done ("mark task X done", "task done", "completed task 3"). This is the most common mid-work-order action — once per task.

## What to do

1. **Resolve the task_id.** Call `core.work_orders.queries.list_tasks(work_order_id=<wo>, source_root=..., dream_studio_home=...)`. The returned dict has a `tasks` list with each task's `task_id`, `title`, `description`, and `status`. Match the user's named task to a row whose `status == 'pending'`. If multiple pending tasks match by title, ask the user to choose. If none match, surface the available pending titles.

2. **Confirm before mutating.** Show the matched task's `title` and confirm: *"Mark this task complete? (yes/no)"* — one line, no extra prose.

3. **Call `mark_task_done(work_order_id=<wo>, task_id=<task>, source_root=..., dream_studio_home=...)`.**
   - On `{"ok": False, "error": ...}`, surface the error verbatim.
   - On `{"ok": True, ...}`, present:
     - `title` (task that was marked done)
     - `tasks_remaining` (how many pending tasks are left in this WO)
     - If `all_tasks_complete is True`, surface `suggested_action` verbatim — it tells the user how to close the WO.

4. **Do not chain into `close` automatically.** Closing the WO is a separate explicit action under `ds-workorder:close`. If `all_tasks_complete` is True, simply tell the user *"All tasks complete. Invoke ds-workorder:close to verify gates and close this work order."*

## Surface contract

On success::

    {
      "ok": True,
      "task_id": str,
      "work_order_id": str,
      "title": str,
      "status": "complete",
      "tasks_remaining": int,
      "task_index": int,
      "all_tasks_complete": True | absent,
      "suggested_action": str | absent,  # only when all_tasks_complete
    }

## Side effects

- Sets the task row's `status` to `complete`.
- Emits a `task.completed` spool event with `tasks_remaining` in the payload.
