"""dream-studio setup — CLI entrypoint (argparse wiring).

Split from interfaces/cli/setup.py (WO-GF-CLI-split). ``main()`` is re-exported
by the interfaces/cli/setup.py facade, which keeps the trailing
``if __name__ == "__main__": sys.exit(main())`` guard so ``python
interfaces/cli/setup.py`` still works as a standalone script.
"""

from __future__ import annotations

import argparse
import sys

from interfaces.cli.setup_diagnostics import _check_only, _check_only_json
from interfaces.cli.setup_hooks import (
    step_settings_merge,
    step_sync_hook_projection,
    step_uninstall,
    test_coexistence,
)
from interfaces.cli.setup_shared import HOOKS_JSON, StepResult
from interfaces.cli.setup_steps import (
    step_analytics_bootstrap,
    step_first_run_marker,
    step_local_adapter_excludes,
    step_memory_init,
    step_python_version,
    step_venv_and_deps,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="setup.py",
        description="dream-studio first-run setup and doctor check.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        action="store_true",
        help="Read-only doctor report (creates no files)",
    )
    group.add_argument(
        "--apply",
        action="store_true",
        help="Full setup: create venv, merge hooks, seed memory (default if no flag)",
    )
    group.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove DS hook entries (dream_studio_managed=true) and projection files",
    )
    group.add_argument(
        "--test-coexistence",
        action="store_true",
        dest="test_coexistence",
        help="Run install/uninstall coexistence test against a mock settings.json",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="With --check, emit a machine-readable read-only readiness report",
    )
    args = parser.parse_args(argv)

    if args.json and not args.check:
        parser.error("--json is only supported with --check")

    if args.check:
        if args.json:
            return _check_only_json()
        return _check_only()

    if args.uninstall:
        return step_uninstall()

    if args.test_coexistence:
        return test_coexistence()

    # Default behavior (no flag or --apply): full setup
    # Validate repo root early — fail before any filesystem mutation
    if not HOOKS_JSON.exists():
        print(f"ERROR: hooks.json not found at {HOOKS_JSON}", file=sys.stderr)
        print("Run from the repo root directory.", file=sys.stderr)
        return 1

    print("[dream-studio] First-run setup")
    print()

    steps = [
        step_python_version,
        step_local_adapter_excludes,
        step_venv_and_deps,
        step_settings_merge,
        step_memory_init,
        step_analytics_bootstrap,
        step_first_run_marker,
        step_sync_hook_projection,
    ]

    results: list[StepResult] = []
    abort = False

    for fn in steps:
        result = fn()
        results.append(result)
        # Python version failure is fatal — remaining steps depend on 3.11+.
        if not result.passed and fn is step_python_version:
            abort = True
            break

    print("Setup checklist:")
    for r in results:
        if r.passed:
            marker = "  ✓"
            suffix = f" ({r.detail})" if r.detail else ""
            print(f"{marker} {r.name}{suffix}")
        else:
            print(f"  ✗ {r.name} — {r.detail}")

    if abort:
        remaining = steps[len(results) :]
        for fn in remaining:
            doc = (fn.__doc__ or fn.__name__).strip().splitlines()[0]
            label = doc.split(": ", 1)[-1] if ": " in doc else doc
            print(f"  - {label} (skipped)")

    all_passed = all(r.passed for r in results) and not abort
    return 0 if all_passed else 1
