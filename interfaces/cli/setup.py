"""
dream-studio setup — first-run setup, doctor check, and update.

Usage:
    py interfaces/cli/setup.py               # full setup (writes files)
    py interfaces/cli/setup.py --check       # read-only doctor report
    py interfaces/cli/setup.py --help        # print help only

Re-run after ``git pull`` to sync settings and pick up any new hooks.
Requirements: Python 3.11+, no third-party dependencies.

WO-GF-CLI-split: this module is now a thin facade. It runs as a script
(``python interfaces/cli/setup.py``, no package context) as well as an
importable module, so it re-establishes its own REPO_ROOT/sys.path bootstrap
BEFORE importing its siblings — ``setup_shared`` (paths, StepResult, UTF-8
console reconfigure), ``setup_steps`` (venv/deps/memory/analytics/marker/
excludes), ``setup_hooks`` (settings.json merge, hook projection sync,
uninstall, coexistence test), ``setup_diagnostics`` (read-only doctor/check
reporting), and ``setup_main`` (argparse entrypoint). Every public and
private name that used to live here is re-exported below so existing imports
and test patches (``interfaces.cli.setup.<name>``) keep working unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from interfaces.cli.setup_diagnostics import (  # noqa: E402
    _check_only,
    _check_only_json,
    _local_adapter_exclude_report,
    _print_schema_compatibility,
    _projection_completeness_report,
    _schema_compatibility_report,
)
from interfaces.cli.setup_hooks import (  # noqa: E402
    SETTINGS_JSON,
    _collect_commands,
    step_settings_merge,
    step_sync_hook_projection,
    step_uninstall,
    test_coexistence,
)
from interfaces.cli.setup_main import main  # noqa: E402
from interfaces.cli.setup_shared import (  # noqa: E402
    HOOKS_JSON,
    REPO_ROOT,
    REQUIREMENTS,
    VENV_DIR,
    StepResult,
)
from interfaces.cli.setup_steps import (  # noqa: E402
    _repo_slug,
    _venv_pip,
    step_analytics_bootstrap,
    step_first_run_marker,
    step_local_adapter_excludes,
    step_memory_init,
    step_python_version,
    step_venv_and_deps,
)

__all__ = [
    # setup_shared
    "REPO_ROOT",
    "VENV_DIR",
    "REQUIREMENTS",
    "HOOKS_JSON",
    "StepResult",
    # setup_steps
    "step_python_version",
    "_venv_pip",
    "step_venv_and_deps",
    "_repo_slug",
    "step_first_run_marker",
    "step_analytics_bootstrap",
    "step_memory_init",
    "step_local_adapter_excludes",
    # setup_hooks
    "SETTINGS_JSON",
    "_collect_commands",
    "step_settings_merge",
    "step_sync_hook_projection",
    "step_uninstall",
    "test_coexistence",
    # setup_diagnostics
    "_local_adapter_exclude_report",
    "_schema_compatibility_report",
    "_projection_completeness_report",
    "_print_schema_compatibility",
    "_check_only_json",
    "_check_only",
    # setup_main
    "main",
]

if __name__ == "__main__":
    sys.exit(main())
