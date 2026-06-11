# ds-workorder:start — Start a work order

**Wraps:** `core.work_orders.start.start_work_order(work_order_id=..., source_root=..., dream_studio_home=..., planning_root=..., accept_no_brief=False)`

---

## When to invoke this mode

The user named a specific work order and asked to begin it ("start work order X", "begin the auth WO", "let's start <title>").

## What to do

1. **Resolve the work_order_id.** If the user named the WO by title, call `core.work_orders.queries.list_work_orders(project_id=..., source_root=..., dream_studio_home=...)` and match the title to a row. If multiple match, ask the user to choose. Never guess.

2. **Confirm before mutating.** Show the user the WO's title, type, and project — read from the `list_work_orders` row — and confirm: *"Start this work order? (yes/no)"*

3. **Call `start_work_order(work_order_id=<id>, source_root=..., dream_studio_home=...)`.**
   - If it returns `{"ok": False, "requires_brief_confirmation": True, ...}`, the WO is UI-typed and has no locked design brief. Surface the error verbatim, ask the user *"No locked design brief found. Proceed without one? (yes/no)"*, and if yes, re-call with `accept_no_brief=True`. This is a stop condition — wait for the user.
   - If it returns `{"ok": False, "error": "Cannot start ... earlier milestones are incomplete..."}`, surface the error. Suggest the user invoke `ds-project:manage` to switch milestones or call `list_work_orders(status_filter='in_progress')` to see what's currently underway.
   - On `{"ok": True, ...}`, present these fields to the user:
     - `title` (the WO that was started)
     - `type` (work order type)
     - `context_path` (where context.md was written)
     - `workflow` if present — tell the user *"This work order uses the `{workflow.template}` workflow. First node: `{workflow.first_node}`. Invoke `ds-core:think` to begin."*
     - `next_step` if present.
     - `sequence_warning` if present — earlier WOs in the milestone are still open; surface it, then proceed.
     - `pending_audits_notice` if present — advisory; surface it, then proceed.

4. **Mirror the task list into the native todo list.** Call `core.work_orders.queries.list_tasks(work_order_id=<id>, source_root=..., dream_studio_home=...)` and create one native todo item per task via the TodoWrite tool (content = task title; keep the `task_id` association). SQLite is the sole authority — the native todo list is a display-only mirror and must never be treated as the task source.

5. **Begin executing immediately.** After presenting the start result and mirroring the todo list, read the task descriptions from `list_tasks` and start executing task 1 under `ds-workorder:execute`. Do not stop to ask "shall I begin?" — the user's start instruction was the authorization. Stop only for the stop conditions listed in `ds-workorder:close`.

## Surface contract

On success, the returned dict shape is::

    {
      "ok": True,
      "work_order_id": str,
      "title": str,
      "type": str,
      "project_id": str,
      "context_path": str,
      "workflow": {"template": str, "first_node": str, "invoke": str} | absent,
      "next_step": str | absent,
      "sequence_warning": str | absent,        # earlier same-milestone WOs still open
      "sequence_blockers": [{...}, ...] | absent,  # the open earlier WOs
      "pending_audits": [{...}, ...] | absent,     # deferred audits, advisory
      "pending_audits_notice": str | absent,
    }

Surface every field the user can act on. Do not add fields.

## Side effects

- Sets the WO row's status to `in_progress` and timestamps it.
- Writes `<planning_root>/work-orders/<id>/context.md` with the module boundary, task list, design brief, and gotchas.
- Emits a `work_order.started` spool event.
