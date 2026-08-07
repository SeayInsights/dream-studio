# ds-workorder:block — Block a work order with a stated reason

**Wraps:** `core.work_orders.mutations.block_work_order(work_order_id=..., reason=..., source_root=..., dream_studio_home=...)`

To unblock later: `core.work_orders.mutations.unblock_work_order(work_order_id=..., source_root=..., dream_studio_home=...)`.

---

## When to invoke this mode

The user signaled a work order is blocked by something they can't resolve right now ("blocked on the design system pick", "block this WO until ops approves", "I'm stuck on auth, blocked by Naomi"). The block records the reason in the WO row and emits a `work_order.blocked` event so the audit trail captures why progress stopped.

## What to do

1. **Resolve the work_order_id.** Use `core.work_orders.queries.list_work_orders(project_id=..., status_filter='in_progress', ...)` if the user didn't supply one. Match by title.

2. **Require a non-empty reason.** Ask the user *"What's blocking this work order? (one sentence)"* if they didn't supply one. The reason is the audit record — empty strings are not acceptable.

3. **Confirm before mutating.** Show the user the WO's title and the reason you'll record, then confirm: *"Block this work order with that reason? (yes/no)"*

4. **Call `block_work_order(work_order_id=<wo>, reason=<one-line>, source_root=..., dream_studio_home=...)`.** Surface the returned dict.

5. **If the user later wants to unblock:** invoke `unblock_work_order(work_order_id=<wo>, ...)`. Same confirm-then-call pattern.

## Surface contract

`block_work_order` returns::

    {
      "ok": True,
      "work_order_id": str,
      "title": str,
      "status": "blocked",
      "reason": str,
      "blocked_at": str,
    }

or::

    {"ok": False, "error": "Work order not found: <id>"}

## Side effects

- Sets the WO row's `status` to `blocked` and records the reason.
- Emits a `work_order.blocked` spool event with the reason in the payload.
