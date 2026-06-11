# ds-workorder:execute — Mark a task complete

**Wraps:** `core.work_orders.mutations.mark_task_done(work_order_id=..., task_id=..., source_root=..., dream_studio_home=..., planning_root=...)`

---

## When to invoke this mode

A task within the active work order is done — either the user said so ("mark task X done", "task done", "completed task 3") or the agent just finished executing a task inside an already-started WO. This is the most common mid-work-order action — once per task.

## What to do

1. **Resolve the task_id.** Call `core.work_orders.queries.list_tasks(work_order_id=<wo>, source_root=..., dream_studio_home=...)`. The returned dict has a `tasks` list with each task's `task_id`, `title`, `description`, and `status`. Match the completed task to a row whose `status == 'pending'`. If the user named the task and multiple pending tasks match by title, ask the user to choose. If none match, surface the available pending titles.

2. **Confirm only when acting on the user's words.** When the *user* asked to mark a task done, show the matched task's `title` and confirm: *"Mark this task complete? (yes/no)"* — one line, no extra prose. When the *agent* is executing inside an already-started WO, the start was the authorization: call `mark_task_done` directly after the task's work is verifiably done, with no per-task confirmation.

3. **Call `mark_task_done(work_order_id=<wo>, task_id=<task>, source_root=..., dream_studio_home=...)`.**
   - On `{"ok": False, "error": ...}`, surface the error verbatim.
   - On `{"ok": True, ...}`, present:
     - `title` (task that was marked done)
     - `tasks_remaining` (how many pending tasks are left in this WO)
   - Mark the matching native todo item completed (TodoWrite). SQLite is the authority; the todo list is a display-only mirror.

4. **Chain forward.** If `all_tasks_complete` is True, invoke `ds-workorder:close` directly — do not stop to ask. Otherwise continue with the next pending task.

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

- Emits a `task.completed` spool event with `tasks_remaining` in the payload; the TaskProjection applies it to the `business_tasks` row (status `complete`) on the next projection tick.
