# ds-milestone:close — Close a milestone after verifying gates

**Wraps:** `core.milestones.close.close_milestone(milestone_id=..., force=False, source_root=..., dream_studio_home=..., planning_root=...)`

---

## When to invoke this mode

The user signaled a milestone is done ("close milestone 1", "milestone done", "wrap up the alpha release"). Milestone close runs four gate checks before mutating:

1. All work orders in the milestone must be `status='complete'`.
2. `design-audit.md` must exist with every `Score: N/M` having `N >= 3`.
3. `security-audit.md` must exist and not contain `BLOCKED`.
4. `harden-results.md` must exist and contain `PASSED`.
5. For UI milestones (any work order with `work_order_type` in `ui_component`, `ui_page`), `cwv-results.md` must also exist and contain `PASSED`.

These artifacts live in the files.db docstore (names `milestones/<milestone_id>/<artifact>.md`), authored via `ds files write --category planning` — never on `.planning/` disk (zero-disk; the on-edit hook denies disk writes). The close gate reads them from the docstore (with a disk fallback during the transition).

## What to do

1. **Preview gates first.** Call `close_milestone(milestone_id=<ms>, source_root=..., dream_studio_home=..., planning_root=...)` — the function returns the gate status without mutating when checks fail. If the user wants a true non-mutating preview before any close attempt, use `ds-milestone:status` instead.

2. **If `ok=True`** the milestone closed. Present:
   - `title` and `milestone_id`
   - `completed_at`
   - `next_action` from caller's perspective — usually the next milestone or a project status check.

3. **If `ok=False` with `open_work_orders`:** the milestone has incomplete work orders. List them by `title` and `status`. Tell the user *"Close each work order via `ds-workorder:close` before closing this milestone."* — do not offer `--force` here.

4. **If `ok=False` with `failures`:** the gate artifacts are missing or failing. Present each failure as a bullet. Offer two paths:
   - **Fix the gates** (preferred): invoke the skill that produces each artifact, then author its result to the docstore (zero-disk — `.planning/` disk writes are denied) as `ds files write "milestones/<milestone_id>/<artifact>.md" --category planning`. For example, `design_audit_required` → `website:critique` (each UI page), aggregate, write `milestones/<id>/design-audit.md`; `security_audit_required` → `security:scan` → `security-audit.md`; `harden_results_required` → `quality:harden` → `harden-results.md`; `cwv_results_required` → run a CWV check → `cwv-results.md`. The close gate reads these from the docstore.
   - **Force close** (requires explicit user approval): explain that `--force` will bypass the failed gates and emit `gate.bypassed` spool events. Confirm: *"Bypass these gates and close the milestone? This is recorded for audit. (yes/no)"* — only on explicit yes, re-call `close_milestone(milestone_id=<ms>, force=True, ...)`. Surface the returned `bypassed_gates` list.

## Surface contract

`close_milestone` returns one of four dict shapes — all keyed by ``ok``:

- Missing milestone: ``{"ok": False, "error": "Milestone not found: <id>"}``
- Open WOs remain: ``{"ok": False, "error": "Cannot close milestone: open work orders remain", "open_work_orders": [{"work_order_id", "title", "status"}, ...]}``
- Gate failures: ``{"ok": False, "error": "Milestone verification failed", "failures": [str, ...]}``
- Success or forced::

      {
        "ok": True,
        "milestone_id": str,
        "title": str,
        "project_id": str,
        "status": "complete",
        "completed_at": str,
        "forced": bool,
        "bypassed_gates": [str, ...],
      }

## Side effects

- Sets the milestone row's `status` to `complete`.
- Emits a `milestone.completed` spool event.
- When `force=True` with failures, emits one `gate.bypassed` event per failure for audit.
