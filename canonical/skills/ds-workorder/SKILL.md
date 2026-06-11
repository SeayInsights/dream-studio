# ds-workorder — Work Order Lifecycle

**Type:** Function-backed skill pack
**Invocation:** matched by per-mode triggers in `modes/*/metadata.yml`
**Not a CLI command.** The AI invokes one of the five modes below by calling the named function in `core.work_orders.*` and presenting the returned dict to the user.

The Dream Studio source-of-truth is the SQLite authority. This pack does not reason about work-order state from session memory or training knowledge. Every mode calls a named query or mutation function and surfaces its returned data.

---

## Mode dispatch

| Mode | File | Wraps | Keywords |
|------|------|-------|----------|
| start | `modes/start/SKILL.md` | `core.work_orders.start.start_work_order` | start work order:, begin work order: |
| execute | `modes/execute/SKILL.md` | `core.work_orders.mutations.mark_task_done` | mark task done:, task done:, complete task: |
| close | `modes/close/SKILL.md` | `core.work_orders.close.close_work_order` (+ `check_close_gates`) | close work order:, finish work order: |
| block | `modes/block/SKILL.md` | `core.work_orders.mutations.block_work_order` | block:, blocked by: |
| status | `modes/status/SKILL.md` | `core.work_orders.queries.list_work_orders` (+ `list_tasks`) | work order status:, show tasks: |

---

## Rules that apply to every mode

1. **Read functions before you write.** If a state-surfacing instruction below does not name the specific query function being called, stop and add it. Never narrate state from session context or training data.
2. **Present returned dicts. Don't invent fields.** The function returns a dict with a known shape. Show those fields. If the user asks for a field that isn't there, say so — don't fabricate it.
3. **Mutations require explicit user confirmation.** start, execute, close, block all mutate state. Confirm intent before calling the function, then call it, then show the user the returned dict so they can verify the change.
4. **Errors are operator-visible.** When a function returns `ok=False`, surface the `error` field verbatim. Do not paraphrase or soften the message.
5. **No raw UUIDs to the user unless asked.** Use the work_order_id internally; refer to the work order by its `title` in conversation. The user can ask for the ID.
6. **Task descriptions should include behavioral acceptance criteria.** When authoring tasks (via scope or during a WO), each task description should include an "Acceptance:" clause stating what the operator observes when the task is done. The independent review completion grader will emit a warning gap if feature/infrastructure WOs have no observable behavioral AC — this is not a fail, but it signals that the grader could not verify expected operator outcomes.
