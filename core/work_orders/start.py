"""Work-order start: read brief, write context.md, mutate to in_progress — facade.

This module replaces the monolithic `_work_order_start` handler that lived in
`interfaces/cli/ds.py`. It decomposes the work into three pure functions so
skills, workflows, and hooks can compose them directly without going through
the CLI subprocess:

- `read_work_order_brief(work_order_id=, source_root=, dream_studio_home=)`
    Reads work order, type, milestone, project, pending tasks, design brief,
    gotchas, marker project id, and blocking-milestone count. Returns a
    fully-structured dict with everything needed to render the context.md and
    decide whether the start is allowed.

- `write_work_order_context(brief_data, planning_root, now)`
    Pure markdown generator. Takes the dict from `read_work_order_brief` and
    writes `<planning_root>/work-orders/<wo_id>/context.md`. Returns the
    written path.

- `start_work_order(work_order_id=, accept_no_brief=False, source_root=,
                    dream_studio_home=, planning_root=, brief_data=None)`
    Composer. Reads (or accepts pre-read) brief data, enforces the
    no-brief-for-UI guard via `accept_no_brief`, enforces the
    milestone-ordering guard, writes context.md, updates the row to
    in_progress, emits the `work_order.started` spool event, and returns a
    result dict (with workflow info if the type declares one).

The stdin y/N prompt that used to live in the CLI handler is REMOVED from
the pure path. Skills/operators are expected to confirm before calling
`start_work_order(accept_no_brief=True)`. The CLI wrapper in `ds.py`
preserves the legacy behaviour (warning to stderr, non-TTY auto-accepts)
for backward compat with operator terminals.

WO-GF-WO-LIFECYCLE: implementation moved to start_{shared,brief,context,
main}.py; this module re-exports the public API so existing
``from core.work_orders.start import X`` callers are unchanged.
"""

from __future__ import annotations

from .start_main import start_work_order
from .start_shared import (
    _BLOCKING_SEVERITIES,
    _BLOCKING_STATUSES,
    _UI_WO_TYPES,
    _check_sequence_order,
)

# WO-GF-WO-LIFECYCLE: _require_db / read_work_order_brief / write_work_order_context are
# re-exported dynamically (PEP 562 module __getattr__), NOT via a static `from .sibling
# import name` above. Tests patch these by their sibling-module path (e.g.
# `patch("core.work_orders.start_brief.read_work_order_brief", ...)`) so a lazy,
# function-local re-import inside start_work_order sees the patch. A static import here
# would bind a frozen snapshot the FIRST time this facade module is ever imported — if
# that first import happens to occur while some unrelated test's patch is active (the
# same order-dependent hazard confirmed empirically for verify.py's equivalent names:
# a later test's direct `from core.work_orders.verify import _collect_git_commits` call
# got permanently poisoned by an earlier test's mid-patch first-import). __getattr__
# re-resolves the CURRENT value from the defining sibling on every access, so no
# import-order accident can freeze a stale (possibly mocked) reference here.
_DYNAMIC_REEXPORTS = {
    "_require_db": ".start_shared",
    "read_work_order_brief": ".start_brief",
    "write_work_order_context": ".start_context",
}


def __getattr__(name: str):
    module_name = _DYNAMIC_REEXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_name, __package__)
    return getattr(module, name)


__all__ = [  # noqa: F822 -- _require_db/read_work_order_brief/write_work_order_context resolve via __getattr__ (flake8 reports F822 on this line, not the entries)
    "_BLOCKING_SEVERITIES",
    "_BLOCKING_STATUSES",
    "_UI_WO_TYPES",
    "_check_sequence_order",
    "_require_db",  # noqa: F822 -- resolved dynamically via __getattr__ above
    "read_work_order_brief",  # noqa: F822 -- resolved dynamically via __getattr__ above
    "start_work_order",
    "write_work_order_context",  # noqa: F822 -- resolved dynamically via __getattr__ above
]
