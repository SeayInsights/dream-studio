# ds-workorder:close — Close a work order

**Wraps:**
- `core.work_orders.close.check_close_gates(work_order_id=..., source_root=..., dream_studio_home=..., planning_root=...)` — preview gate status without mutating.
- `core.work_orders.close.close_work_order(work_order_id=..., force=False, source_root=..., dream_studio_home=..., planning_root=...)` — verify gates + mutate to complete + emit spool events.

---

## When to invoke this mode

The user signaled that an active work order is done ("close work order", "finish the auth WO", "wrap up this WO"). Usually fires after `ds-workorder:execute` reports `all_tasks_complete: True`.

## What to do

1. **Preview gates first.** Call `check_close_gates(work_order_id=<wo>, source_root=..., dream_studio_home=..., planning_root=...)`. The returned dict tells you whether the WO would close cleanly without actually mutating anything.

2. **If `gates_pass is True`:** confirm with the user *"All gates pass. Close work order? (yes/no)"* and on confirmation call `close_work_order(work_order_id=<wo>, source_root=..., dream_studio_home=..., planning_root=...)`. Surface the result dict (see contract below).

3. **If `gates_pass is False`:** present the `gate_failures` list verbatim — one bullet per failure. Then offer two paths:
   - **Fix the gates** (preferred): suggest the skill that addresses each failure. For example, `design_brief_locked` → invoke `ds-project:brief` to fill and then `ds-project:brief` lock mode; `design_critique` → invoke `website:critique`; `security_scan` → invoke `security:scan`; `api_contract_exists` → write the contract artifact.
   - **Force close** (requires explicit user approval): explain that `--force` will bypass the failed gates and emit `gate.bypassed` spool events. Confirm: *"Bypass these gates? This is recorded for audit. (yes/no)"* — only on explicit yes, call `close_work_order(work_order_id=<wo>, force=True, ...)`.

4. **Surface the close result.** The `next_command` field tells the user what's next: another work order in the same milestone, or a milestone close. Present that field.

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
        "status": "complete",
        "forced": bool,
        "bypassed_gates": [str, ...],          # populated when forced
        "next_work_order": {...} | absent,     # next open WO in same milestone
        "next_command": str | absent,          # explicit next-step hint
        "milestone_complete": True | absent,
        "milestone_id": str | absent,
      }

## Side effects

- Sets the WO row's `status` to `complete`.
- Emits a `work_order.closed` spool event.
- When `force=True` with failures, emits one `gate.bypassed` event per failure for audit.
