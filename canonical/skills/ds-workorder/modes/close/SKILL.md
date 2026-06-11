# ds-workorder:close — Close a work order

**Wraps:**
- `core.work_orders.close.check_close_gates(work_order_id=..., source_root=..., dream_studio_home=..., planning_root=...)` — preview gate status without mutating.
- `core.work_orders.close.close_work_order(work_order_id=..., force=False, source_root=..., dream_studio_home=..., planning_root=...)` — verify gates + mutate to closed + emit spool events.

---

## When to invoke this mode

An active work order is done — the user said so ("close work order", "finish the auth WO", "wrap up this WO"), or `ds-workorder:execute` just reported `all_tasks_complete: True` (chain into close directly, no confirmation needed).

## What to do

1. **Preview gates first.** Call `check_close_gates(work_order_id=<wo>, source_root=..., dream_studio_home=..., planning_root=...)`. The returned dict tells you whether the WO would close cleanly without actually mutating anything.

2. **If `gates_pass is True`:** call `close_work_order(work_order_id=<wo>, source_root=..., dream_studio_home=..., planning_root=...)` directly — no confirmation on the normal path. Surface the result dict (see contract below).

3. **If `gates_pass is False`:** present the `gate_failures` list verbatim — one bullet per failure. Then offer two paths:
   - **Fix the gates** (preferred): suggest the skill that addresses each failure. For example, `design_brief_locked` → invoke `ds-project:brief` to fill and then `ds-project:brief` lock mode; `design_critique` → invoke `website:critique`; `security_scan` → invoke `security:scan`; `api_contract_exists` → write the contract artifact.
   - **Force close** (requires explicit user approval — this is a stop condition): explain that `force=True` will bypass the failed gates and emit `gate.bypassed` spool events. Confirm: *"Bypass these gates? This is recorded for audit. (yes/no)"* — only on explicit yes, call `close_work_order(work_order_id=<wo>, force=True, ...)`.

4. **Surface the close result and continue.**
   - If `gaps_block` is present, print it verbatim — the independent review found gaps and registered a remediation WO (`spawned_work_orders`).
   - If `auto_started` is present, announce it in one line — *"AUTO-STARTED: {auto_started.title}"* — then complete/clear the native todo list for the closed WO, mirror the new WO's task list into a fresh todo list, and IMMEDIATELY continue executing the new WO's tasks without waiting for operator input.
   - If `auto_start_error` is present, surface it and stop — this is a stop condition.
   - If `auto_start_message` or `milestone_complete` is present, the milestone is done: surface `next_command` (milestone close) and stop — this is a stop condition.
   - Otherwise surface `next_block` / `next_command` so the user knows what's next.

## Stop conditions

The ONLY places the agent waits for the operator across start → execute → close:
- Force-close approval (gate bypass).
- `requires_brief_confirmation` on start.
- `auto_start_error` on close.
- `milestone_complete` / `auto_start_message` (milestone done — milestone close is an operator decision).
- A blocked WO.
- A genuine blocking question the agent cannot resolve from the WO, the code, or sensible defaults.

Everything else flows continuously: start → execute each task → close → auto-started next WO.

## Surface contract

`check_close_gates` returns::

    {
      "ok": True,
      "work_order_id": str,
      "title": str,
      "type_id": str | None,
      "project_id": str,
      "milestone_id": str | None,
      "pre_gate": str | None,
      "post_gate": str | None,
      "gates_pass": bool,
      "gate_failures": [str, ...],
    }

`close_work_order` returns one of three shapes:

- WO not found: `{"ok": False, "error": "Work order not found: <id>"}`
- Gates failed without force: `{"ok": False, "error": "Gate check failed", "failures": [...]}`
- Success or forced::

      {
        "ok": True,
        "work_order_id": str,
        "title": str,
        "status": "closed",
        "forced": bool,
        "bypassed_gates": [str, ...],          # populated when forced
        "verify_warning": str | absent,        # inline verify was unreviewable (no commit evidence) — surface verbatim
        "next_work_order": {...} | absent,     # next open WO in same milestone
        "next_command": str | absent,          # explicit next-step hint
        "next_block": str,                     # printable NEXT WORK ORDER / MILESTONE COMPLETE / none-found block
        "milestone_complete": True | absent,
        "milestone_id": str | absent,
        "gaps_block": str | absent,            # printable GAPS FOUND block when independent review failed
        "spawned_work_orders": [{...}] | absent,  # remediation WOs registered from review gaps
        "auto_started": {"work_order_id": str, "title": str, "message": str} | absent,  # next/remediation WO already started
        "auto_start_error": str | absent,      # auto-start attempted and failed — stop condition
        "auto_start_message": str | absent,    # "MILESTONE COMPLETE" — no next WO to start
      }

## Side effects

- Sets the WO row's `status` to `closed`.
- Emits a `work_order.closed` spool event.
- When `force=True` with failures, emits one `gate.bypassed` event per failure for audit.
- When the post-build gate is `independent_review`, runs the fresh-context verify inline; review gaps register remediation WOs and the first one is auto-started.
- When verify passes, the next WO in the project is auto-started (`auto_started`).
