# ds-workorder:execute — Mark a task complete

**Wraps:** `core.work_orders.mutations.mark_task_done(work_order_id=..., task_id=..., source_root=..., dream_studio_home=..., planning_root=...)`

---

## When to invoke this mode

A task within the active work order is done — either the user said so ("mark task X done", "task done", "completed task 3") or the agent just finished executing a task inside an already-started WO. This is the most common mid-work-order action — once per task.

## What to do

1. **Resolve the task_id.** Call `core.work_orders.queries.list_tasks(work_order_id=<wo>, source_root=..., dream_studio_home=...)`. The returned dict has a `tasks` list with each task's `task_id`, `title`, `description`, and `status`. Match the completed task to a row whose `status == 'pending'`. If the user named the task and multiple pending tasks match by title, ask the user to choose. If none match, surface the available pending titles.

2. **Confirm only when acting on the user's words.** When the *user* asked to mark a task done, show the matched task's `title` and confirm: *"Mark this task complete? (yes/no)"* — one line, no extra prose. When the *agent* is executing inside an already-started WO, the start was the authorization: call `mark_task_done` directly after the task's work is verifiably done, with no per-task confirmation. **"Verifiably done" means someone other than the author ran the tests** — spawn a runner, give it the node ids rather than your conclusion, and treat its report as the evidence. Your own green run confirms your assumptions, not the behaviour.

3. **Call `mark_task_done(work_order_id=<wo>, task_id=<task>, source_root=..., dream_studio_home=...)`.**
   - On `{"ok": False, "error": ...}`, surface the error verbatim. **The task is NOT done** —
     do not mark the todo complete and do not move to the next task. If the error names
     `ds projection dead-letter list`, the completion event was written but the projection
     could not apply it; the authority still reports the task open and the `tasks_done`
     close gate will agree.
   - On `{"ok": True, ...}`, present:
     - `title` (task that was marked done)
     - `tasks_remaining` (how many pending tasks are left in this WO)
     - `read_model_pending` when present — the completion is durably recorded but
       `business_tasks` has not materialized it yet, so `ds work-order tasks` will lag
       until the next projection pass. Say so rather than reporting a clean completion.
   - Mark the matching native todo item completed (TodoWrite). SQLite is the authority; the todo list is a display-only mirror.

4. **Chain forward.** If `all_tasks_complete` is True, invoke `ds-workorder:close` directly — do not stop to ask. Otherwise continue with the next pending task. **Do not attempt to close a WO with pending tasks** — close enforces a `tasks_done` gate and will refuse (no 0/N or partial closes); finish every task here first.

## Surface contract

On success::

    {
      "ok": True,
      "task_id": str,
      "work_order_id": str,
      "title": str,
      "status": str,                     # READ BACK from business_tasks, not asserted
      "tasks_remaining": int,
      "task_index": int,
      "all_tasks_complete": True | absent,
      "suggested_action": str | absent,  # only when all_tasks_complete
      "read_model_pending": True | absent,  # status is not yet 'complete'
      "note": str | absent,              # accompanies read_model_pending
    }

On failure (issue #718)::

    {
      "ok": False,
      "status": str,                     # what the authority actually holds
      "error": str,                      # names the cause and where to look
      "event_write_error": str | absent,     # the task.completed write raised
      "projection_error": str | absent,      # sync_tick raised
      "read_back_error": str | absent,       # the verification read failed
    }

`status` is never fabricated. It reports what `business_tasks` holds after the write,
so it may read `pending`, `unknown` (no row), or a done status — and `ok` is False only
when the completion was lost, not when the read model is merely behind.

## Side effects

- Emits a `task.completed` spool event with `tasks_remaining` in the payload, then runs a projection tick (`sync_tick()`) inline — so the TaskProjection applies it to the `business_tasks` row (status `complete`) before the call returns. No separate sync step is needed; `list_tasks` reflects the completion immediately (WO-TASKDONE-SYNC).
- Then READS THE ROW BACK and reports that status (issue #718). A projection failure does
  not raise: `framework_engine_dispatch` catches a handler error, dead-letters the event,
  and returns normally — so a task could be reported `complete` while no `business_tasks`
  row existed at all. A completion whose event is queued for retry or dead-lettered now
  fails the call; one that is merely waiting on the next projection pass does not.

## If it can be computed, compute it {#deterministic-first}

Marking a task done is a claim, and a claim with an exact answer never rests on reading.
**A grep is not a drive** — finding the symbol in a file's source proves the line was
typed, not that it runs; import it and call it. A remembered artifact shape is not a read
one. A symbol's existence is not its reachability: search for the caller rather than
assuming one.

**Do not certify your own work by reading it.** If the task's acceptance criterion is a
`TEST-CHECK`, run that node and use the exit code — and where the rule is that an author
does not run their own suite, hand the node ids to a separate runner and use what it
reports, not a conclusion you wrote. `close_work_order` executes every criterion anyway,
so a task marked done on a reading is a task that will fail at close, later and with less
context.

When a claim genuinely cannot be computed — a design judgement, an operator attestation —
say so and say why. A fact recorded as `unknown` **with a reason** is honest; the same
fact recorded as done because nobody could check it is the false-done every gate here
exists to prevent.

<!-- Last reviewed 2026-09-17 — issue #718 / WO b6ca23fa: mark_task_done now reads business_tasks back and reports the status the authority holds instead of asserting "complete". Additive result fields (read_model_pending, note, event_write_error, projection_error, read_back_error) and one semantic change: ok is False when the completion was lost (event write failed, or the projection queued/dead-lettered the event), and stays True for ordinary read-model lag. all_tasks_complete and the delivery-boundary stamp are gated on the same verdict, so a lost completion no longer chains into close. -->
