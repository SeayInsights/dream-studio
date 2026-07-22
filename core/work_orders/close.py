"""Work-order close: run pre/post gates, mutate to complete, surface next step — facade.

This module replaces the monolithic `_work_order_close` handler that lived in
`interfaces/cli/ds.py`. It decomposes the work into three composable,
side-effect-aware functions so skills, workflows, and hooks can call them
directly without going through the CLI subprocess:

- `run_gate_check(gate_name, planning_root=, work_order_id=, project_id=, conn=)`
    The per-gate predicate. Pure read against the planning artifact tree and
    the (caller-owned) SQLite connection. Returns `(passed, failure_reason)`.
    Moved verbatim from ds.py so the predicate semantics stay identical.

- `check_close_gates(work_order_id=, source_root=, dream_studio_home=,
                      planning_root=)`
    Pure read. Opens its own connection, looks up the work order and its
    type, evaluates every gate (pre|post split on `|`), and returns a dict
    with the WO metadata, the gate list, and the failures. Does NOT mutate
    state or emit spool events. Skills/workflows call this to preview
    whether a close would succeed.

- `close_work_order(work_order_id=, force=False, source_root=,
                     dream_studio_home=, planning_root=)`
    Composer. Re-runs the gate evaluation inside the same connection that
    performs the status mutation, so the gate→close transition is atomic.
    Emits the `gate.bypassed` spool event(s) when `force=True` is used to
    override failures, emits `work_order.closed`, updates the row to
    complete, and computes the next-step hint (next open WO in the same
    milestone, or milestone-complete signal). Returns a result dict with
    the canonical shape — no `print()`, no `sys.exit`.

The stderr `[gate.bypassed] WARNING:` line that used to be emitted from
this handler is REMOVED from the pure path. The CLI wrapper in ds.py
re-emits it from the returned `bypassed_gates` list so operator-terminal
behavior stays identical.

WO-GF-WO-LIFECYCLE: implementation moved to close_{shared,gates,continuation,
main}.py; this module re-exports the public API so existing
``from core.work_orders.close import X`` callers are unchanged. The
close -> verify coupling (``_run_ac_gate`` and ``close_work_order``'s lazy
``verify_work_order`` import) stays pointed at ``core.work_orders.verify``
(this facade's sibling), not a verify_* sibling — this is what keeps
``patch("core.work_orders.verify.verify_work_order", ...)`` tests working.
"""

from __future__ import annotations

from .close_gates import (
    _check_originating_symptom,
    _evaluate_gates,
    _read_wo_tasks,
    _run_ac_gate,
    run_gate_check,
)
from .close_main import check_close_gates, close_work_order
from .close_shared import _artifact_text, _lookup_work_order_and_gates, _require_db

__all__ = [
    "_artifact_text",
    "_check_originating_symptom",
    "_evaluate_gates",
    "_lookup_work_order_and_gates",
    "_read_wo_tasks",
    "_require_db",
    "_run_ac_gate",
    "check_close_gates",
    "close_work_order",
    "run_gate_check",
]
