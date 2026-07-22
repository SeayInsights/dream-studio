"""dream-studio setup — read-only doctor/check reporting.

Split from interfaces/cli/setup.py (WO-GF-CLI-split). Everything here is
read-only: no file is created, written, or deleted by this module.
"""

from __future__ import annotations

import json

from interfaces.cli.setup_hooks import SETTINGS_JSON
from interfaces.cli.setup_shared import HOOKS_JSON, REPO_ROOT, REQUIREMENTS, StepResult, VENV_DIR
from interfaces.cli.setup_steps import step_python_version

# ---------------------------------------------------------------------------
# Diagnostic reports
# ---------------------------------------------------------------------------


def _local_adapter_exclude_report() -> dict:
    """Return local adapter scratch exclude status without writing files."""
    try:
        from core.release.adapter_workspace_hygiene import required_local_exclude_patterns

        exclude_path = REPO_ROOT / ".git" / "info" / "exclude"
        existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
        configured = {
            line.strip()
            for line in existing.splitlines()
            if line.strip() and not line.startswith("#")
        }
        patterns = list(required_local_exclude_patterns())
        return {
            "available": True,
            "exclude_path": str(exclude_path),
            "patterns": patterns,
            "missing_patterns": [pattern for pattern in patterns if pattern not in configured],
            "local_only": True,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "error": str(exc),
            "local_only": True,
        }


def _schema_compatibility_report() -> dict:
    """Return runtime DB/code compatibility details without creating or migrating the DB."""
    try:
        from interfaces.cli.runtime_preflight import (
            format_schema_compatibility,
            inspect_schema_compatibility,
            schema_compatibility_is_blocking,
        )

        result = inspect_schema_compatibility(repo_root=REPO_ROOT)
        return {
            "available": True,
            "result": result,
            "formatted": format_schema_compatibility(result),
            "blocked": schema_compatibility_is_blocking(result),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "result": {},
            "formatted": "",
            "blocked": False,
            "error": str(exc),
        }


def _projection_completeness_report() -> dict:
    """Return DS hook projection health without writing anything."""
    projection_root = REPO_ROOT / ".claude" / "hooks" / "runtime" / "hooks"
    plugin_root_path = REPO_ROOT / ".claude" / "hooks" / ".plugin-root"
    expected_subdirs = ("meta", "quality", "domains", "core")

    present = [s for s in expected_subdirs if (projection_root / s).is_dir()]
    missing = [s for s in expected_subdirs if s not in present]

    plugin_root_ok = False
    plugin_root_value = ""
    expected_plugin_root = str(REPO_ROOT / ".claude" / "hooks")
    if plugin_root_path.exists():
        plugin_root_value = plugin_root_path.read_text(encoding="utf-8").strip()
        plugin_root_ok = plugin_root_value == expected_plugin_root

    # Check settings.json for DS hook presence
    ds_hooks_present = False
    if SETTINGS_JSON.exists():
        try:
            with SETTINGS_JSON.open(encoding="utf-8") as fh:
                settings = json.load(fh)
            for groups in settings.get("hooks", {}).values():
                if any(g.get("dream_studio_managed") for g in groups):
                    ds_hooks_present = True
                    break
        except Exception:
            pass

    return {
        "present_subdirs": present,
        "missing_subdirs": missing,
        "plugin_root_ok": plugin_root_ok,
        "plugin_root_value": plugin_root_value,
        "plugin_root_expected": expected_plugin_root,
        "ds_hooks_present": ds_hooks_present,
        "all_ok": not missing and plugin_root_ok and ds_hooks_present,
    }


def _print_schema_compatibility() -> bool:
    """Report runtime DB/code compatibility without creating or migrating the DB."""
    report = _schema_compatibility_report()
    if not report["available"]:
        print(f"  [warn] Runtime DB schema compatibility unavailable: {report['error']}")
        return False

    result = report["result"]
    label = "ok" if result.get("severity") == "info" else result.get("severity", "warn")
    print(f"  [{label}] Runtime DB schema compatibility")
    for line in report["formatted"].splitlines():
        print(f"    {line}")
    return bool(report["blocked"])


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _check_only_json() -> int:
    """Read-only doctor report for operator/dashboard automation."""
    if not HOOKS_JSON.exists():
        print(
            json.dumps(
                {
                    "mode": "check",
                    "read_only": True,
                    "repo_root": str(REPO_ROOT),
                    "ready_for_apply": False,
                    "error": f"hooks.json not found at {HOOKS_JSON}",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    results = [step_python_version(emit=False)]
    schema_report = _schema_compatibility_report()
    schema_blocked = bool(schema_report["blocked"])
    adapter_excludes = _local_adapter_exclude_report()
    files = [
        {"label": label, "path": str(path), "exists": path.exists()}
        for label, path in [
            ("requirements.txt", REQUIREMENTS),
            ("hooks.json", HOOKS_JSON),
            (".venv", VENV_DIR),
            ("settings.json", SETTINGS_JSON),
        ]
    ]
    print(
        json.dumps(
            {
                "mode": "check",
                "read_only": True,
                "repo_root": str(REPO_ROOT),
                "ready_for_apply": all(r.passed for r in results) and not schema_blocked,
                "check_policy": {
                    "blocked_newer_than_code": "advisory_exit_0_for_check",
                },
                "steps": [
                    {"name": r.name, "passed": r.passed, "detail": r.detail} for r in results
                ],
                "files": files,
                "schema_compatibility": schema_report,
                "adapter_workspace_hygiene": adapter_excludes,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _check_only() -> int:
    """Read-only doctor: report prerequisites without writing anything."""
    print("[dream-studio] Doctor check (read-only)")
    print()

    checks = [
        ("Python version", step_python_version),
    ]
    # Validate repo root before anything else
    if not HOOKS_JSON.exists():
        print(f"  ✗ Repo root — hooks.json not found at {HOOKS_JSON}")
        print("    Run from the repo root: py interfaces/cli/setup.py --check")
        return 1

    results: list[StepResult] = [fn() for _, fn in checks]

    # Report file existence (read-only)
    for label, path in [
        ("requirements.txt", REQUIREMENTS),
        ("hooks.json", HOOKS_JSON),
        (".venv", VENV_DIR),
        ("settings.json", SETTINGS_JSON),
    ]:
        exists = path.exists()
        marker = "  ✓" if exists else "  ✗"
        print(f"{marker} {label} {'exists' if exists else 'missing'} — {path}")

    for r in results:
        marker = "  ✓" if r.passed else "  ✗"
        suffix = f" ({r.detail})" if r.detail else ""
        print(f"{marker} {r.name}{suffix}")

    adapter_excludes = _local_adapter_exclude_report()
    if adapter_excludes["available"]:
        missing = adapter_excludes["missing_patterns"]
        marker = "  [ok]" if not missing else "  [warn]"
        detail = (
            "configured" if not missing else "missing local-only patterns: " + ", ".join(missing)
        )
        print(f"{marker} Adapter workspace local excludes - {detail}")
    else:
        print(
            "  [warn] Adapter workspace local excludes unavailable - "
            f"{adapter_excludes['error']}"
        )

    schema_blocked = _print_schema_compatibility()
    if schema_blocked:
        print(
            "    setup --check policy: advisory exit 0; treat blocked_newer_than_code "
            "as a readiness blocker for setup --apply, dashboard bootstrap, and migration checks."
        )

    proj = _projection_completeness_report()
    ds_marker = "  ✓" if proj["ds_hooks_present"] else "  ✗"
    print(f"{ds_marker} DS hooks in settings.json (dream_studio_managed)")
    subdirs_ok = not proj["missing_subdirs"]
    subdirs_marker = "  ✓" if subdirs_ok else "  ✗"
    subdirs_detail = (
        "meta/quality/domains/core all present"
        if subdirs_ok
        else f"missing: {', '.join(proj['missing_subdirs'])}"
    )
    print(f"{subdirs_marker} .claude/hooks/ projection — {subdirs_detail}")
    pr_marker = "  ✓" if proj["plugin_root_ok"] else "  ✗"
    pr_detail = (
        proj["plugin_root_value"]
        if proj["plugin_root_ok"]
        else f"got '{proj['plugin_root_value']}' expected '{proj['plugin_root_expected']}'"
    )
    print(f"{pr_marker} .plugin-root — {pr_detail}")

    return 0
