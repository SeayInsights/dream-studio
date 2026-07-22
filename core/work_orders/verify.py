"""Work-order independent verification via parallel fresh-context graders — facade.

WO-GF-WO-LIFECYCLE: implementation moved to verify_{shared,prompts,db,executor,
git,graders,gaps,persist,main}.py; this module re-exports the public API so
existing ``from core.work_orders.verify import X`` callers, and
``core.work_orders.verify.<name>`` mock.patch targets for names that remain
defined via facade-pointed lazy imports elsewhere, are unchanged.

Entry point: ``verify_work_order(work_order_id=, source_root=, dream_studio_home=)``.
See ``verify_main.py`` for the full architecture docstring (parallel graders,
scoring thresholds, DREAM_STUDIO_VERIFY_MOCK).
"""

from __future__ import annotations

from .verify_db import (
    _format_sql_checks,
    _read_tasks,
    _read_work_order,
    _require_db,
    _run_sql_checks,
)
from .verify_executor import (
    _CHECK_PREFIXES,
    _TEST_CHECK_TIMEOUT,
    _emit_validation_result_event,
    _run_one_api_check,
    _run_one_sql_check,
    _run_one_test_check,
    run_executable_checks,
)
from .verify_gaps import (
    _ADVISORY_PROJECT_WIDE_CATEGORIES,
    _THRESHOLD_RE,
    _filter_invented_threshold_gaps,
    _gap_category,
    _gap_key,
    _gap_key_marker,
    _insert_gap_work_orders,
    _migration_risks_to_gaps,
    _quality_issues_to_gaps,
    _violations_to_gaps,
)
from .verify_git import _authority_evidence, _find_migration_files
from .verify_graders import _extract_first_json_object
from .verify_main import _compute_scores, verify_work_order
from .verify_persist import _persist_review_verdict, _write_eval_run
from .verify_prompts import (
    _COMPLETION_PROMPT_TEMPLATE,
    _CORRECTNESS_PROMPT_TEMPLATE,
    _MIGRATION_PROMPT_TEMPLATE,
    _QUALITY_PROMPT_TEMPLATE,
)
from .verify_shared import (
    _MOCK_COMPLETION,
    _MOCK_CORRECTNESS,
    _MOCK_ENV,
    _MOCK_FIXTURE,
    _MOCK_MIGRATION,
    _MOCK_QUALITY,
)

# WO-GF-WO-LIFECYCLE: _collect_git_commits / _run_graders_parallel / _spawn_grader /
# _collect_grader are re-exported dynamically (PEP 562 module __getattr__), NOT via a
# static `from .sibling import name` above. Tests patch these by their sibling-module
# path (e.g. `patch("core.work_orders.verify_git._collect_git_commits", ...)`) so a
# lazy, function-local re-import inside verify_work_order sees the patch. A static
# import here would bind a frozen snapshot the FIRST time this facade module is ever
# imported — if that first import happens to occur while some unrelated test's patch
# is active (a real, order-dependent hazard confirmed empirically: running
# test_review_traceability.py's tests in sequence poisoned a later test's direct
# `from core.work_orders.verify import _collect_git_commits` call permanently, since
# module-level bindings never re-resolve). __getattr__ re-resolves the CURRENT value
# from the defining sibling on every access, so no import-order accident can freeze a
# stale (possibly mocked) reference here.
_DYNAMIC_REEXPORTS = {
    "_collect_git_commits": ".verify_git",
    "_run_graders_parallel": ".verify_graders",
    "_spawn_grader": ".verify_graders",
    "_collect_grader": ".verify_graders",
}


def __getattr__(name: str):
    module_name = _DYNAMIC_REEXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_name, __package__)
    return getattr(module, name)


__all__ = [  # noqa: F822 -- _collect_git_commits/_run_graders_parallel/_spawn_grader/_collect_grader resolve via __getattr__ (flake8 reports F822 on this line, not the entries)
    "_ADVISORY_PROJECT_WIDE_CATEGORIES",
    "_CHECK_PREFIXES",
    "_COMPLETION_PROMPT_TEMPLATE",
    "_CORRECTNESS_PROMPT_TEMPLATE",
    "_MIGRATION_PROMPT_TEMPLATE",
    "_MOCK_COMPLETION",
    "_MOCK_CORRECTNESS",
    "_MOCK_ENV",
    "_MOCK_FIXTURE",
    "_MOCK_MIGRATION",
    "_MOCK_QUALITY",
    "_QUALITY_PROMPT_TEMPLATE",
    "_TEST_CHECK_TIMEOUT",
    "_THRESHOLD_RE",
    "_authority_evidence",
    "_collect_git_commits",  # noqa: F822 -- resolved dynamically via __getattr__ above
    "_collect_grader",  # noqa: F822 -- resolved dynamically via __getattr__ above
    "_compute_scores",
    "_emit_validation_result_event",
    "_extract_first_json_object",
    "_filter_invented_threshold_gaps",
    "_find_migration_files",
    "_format_sql_checks",
    "_gap_category",
    "_gap_key",
    "_gap_key_marker",
    "_insert_gap_work_orders",
    "_migration_risks_to_gaps",
    "_persist_review_verdict",
    "_quality_issues_to_gaps",
    "_read_tasks",
    "_read_work_order",
    "_require_db",
    "_run_graders_parallel",  # noqa: F822 -- resolved dynamically via __getattr__ above
    "_run_one_api_check",
    "_run_one_sql_check",
    "_run_one_test_check",
    "_run_sql_checks",
    "_spawn_grader",  # noqa: F822 -- resolved dynamically via __getattr__ above
    "_violations_to_gaps",
    "_write_eval_run",
    "run_executable_checks",
    "verify_work_order",
]
