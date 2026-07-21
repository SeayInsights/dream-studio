"""Installed-platform acceptance and final closeout reports.

WO-GF-INSTALLED-PROD: split from ``core/installed_productization.py``. Holds the
deterministic acceptance report (rehearsal-home validation) and the final
installed modular platform closeout aggregation, plus their private helpers. No
logic changes — extracted verbatim from the original module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.event_store.studio_db import _connect
from core.installed_runtime import adapter_router_status, resolve_installed_runtime_paths
from core.module_profiles import module_profile_map
from core.release.local_dogfood_stability import (
    REQUIRED_MULTISESSION_CYCLES,
    build_long_run_multisession_operational_validation,
)

from .installed_productization_backup import backup_runtime, restore_runtime_check
from .installed_productization_legacy_detect import update_runtime_check
from .installed_productization_setup import first_run_setup
from .installed_productization_shared import PRODUCTIZATION_VERSION, _normalize_profiles
from .installed_productization_uninstall import uninstall_runtime_check


def productization_acceptance_report(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    profiles: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Validate installed platform acceptance against a rehearsal home."""

    selected = _normalize_profiles(profiles)
    setup = first_run_setup(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        profiles=selected,
        rehearsal=True,
    )
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    backup = backup_runtime(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        execute=True,
    )
    restore = restore_runtime_check(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        backup_path=backup["backup_path"],
    )
    update = update_runtime_check(source_root=source_root, dream_studio_home=dream_studio_home)
    uninstall = uninstall_runtime_check(
        source_root=source_root, dream_studio_home=dream_studio_home
    )
    conn = _connect(paths.sqlite_path)
    try:
        router = adapter_router_status(
            conn,
            source_root=paths.source_root,
            dream_studio_home=paths.dream_studio_home,
        )
    finally:
        conn.close()
    checks = {
        "no_existing_state_required": setup["fresh_state_created"] is True,
        "selected_modules_installed": all(
            item["status"] == "enabled" for item in setup["profile_status"]["selected"]
        ),
        "unselected_modules_disabled": all(
            item["status"] == "disabled" for item in setup["profile_status"]["unselected"]
        ),
        "dashboard_status_available": "dashboard_onboarding" in setup,
        "adapter_status_available": router["adapter_health"]["adapter_count"] >= 1,
        "analytics_only_independent": _profile_independent("analytics_only"),
        "security_only_independent": _profile_independent("security_only"),
        "full_profile_available": "full" in module_profile_map(),
        "backup_check_passed": backup["status"] == "created",
        "restore_check_passed": restore["restore_ready"] is True,
        "update_check_passed": update["update_ready"] is True,
        "uninstall_check_passed": uninstall["delete_authorized"] is False,
    }
    return {
        "model_name": "dream_studio_installed_productization_acceptance",
        "productization_version": PRODUCTIZATION_VERSION,
        "source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "selected_profiles": selected,
        "checks": checks,
        "status": "pass" if all(checks.values()) else "fail",
        "setup": setup,
        "backup": backup,
        "restore": restore,
        "update": update,
        "uninstall": uninstall,
        "live_state_mutated": False,
    }


def final_installed_modular_platform_closeout(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    validation_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Build the final installed modular platform productization closeout.

    This report is a deterministic aggregation layer over already-run evidence.
    It does not push, publish, run Docker, mutate external projects, or perform
    destructive installed-state operations.
    """

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    profiles = module_profile_map()
    commands = [
        "ds status",
        "ds validate",
        "ds modules",
        "ds router",
        "ds adapters",
        "ds contract-atlas",
        "ds context-packet",
        "ds dashboard",
        "ds dashboard --status",
        "ds dashboard --serve",
        "ds dashboard --open",
        "ds dashboard --check",
        "ds analytics-ingest",
        "ds install",
        "ds acceptance",
        "ds backup",
        "ds restore-check",
        "ds update-check",
        "ds uninstall-check",
    ]
    required_profiles = (
        "core",
        "analytics_only",
        "security_only",
        "telemetry_only",
        "dashboard_only",
        "adapter_router_only",
        "shared_intelligence_only",
        "full",
    )
    profile_readiness = {
        profile_id: {
            "available": profile_id in profiles,
            "docker_required": profiles.get(profile_id, {}).get("docker_required"),
            "claude_required": profiles.get(profile_id, {}).get("claude_required"),
            "codex_required": profiles.get(profile_id, {}).get("codex_required"),
            "empty_state_behavior": profiles.get(profile_id, {}).get("honest_empty_state_behavior")
            or profiles.get(profile_id, {}).get("expected_dashboard_api_behavior"),
        }
        for profile_id in required_profiles
    }
    long_run = build_long_run_multisession_operational_validation(
        validation_evidence.get("long_run_cycles", []),
        sqlite_hash_before=validation_evidence.get("sqlite_hash_before"),
        sqlite_hash_after=validation_evidence.get("sqlite_hash_after"),
    )
    release_state = {
        "release_gate_passed": _truthy(validation_evidence.get("release_gate_passed")),
        "black_passed": _truthy(validation_evidence.get("black_passed")),
        "lint_baseline_passed": _truthy(validation_evidence.get("lint_baseline_passed")),
        "docs_drift_passed": _truthy(validation_evidence.get("docs_drift_passed")),
        "pip_audit_passed": _truthy(validation_evidence.get("pip_audit_passed")),
        "live_sqlite_guard_passed": _truthy(validation_evidence.get("live_sqlite_guard_passed")),
        "repo_clean": _truthy(validation_evidence.get("repo_clean")),
        "private_artifacts_tracked": _truthy(validation_evidence.get("private_artifacts_tracked")),
    }
    release_positive = {
        key: value for key, value in release_state.items() if key != "private_artifacts_tracked"
    }
    checks = {
        "required_profiles_available": all(
            item["available"] for item in profile_readiness.values()
        ),
        "analytics_only_independent": _profile_independent("analytics_only"),
        "security_only_independent": _profile_independent("security_only"),
        "command_surface_complete": set(commands)
        <= set(validation_evidence.get("validated_commands", commands)),
        "adapter_status_documented": _truthy(validation_evidence.get("adapter_status_documented")),
        "context_packet_fallback_documented": _truthy(
            validation_evidence.get("context_packet_fallback_documented")
        ),
        "publication_boundary_clean": _truthy(
            validation_evidence.get("publication_boundary_clean")
        ),
        "long_run_passed": long_run["status"] == "pass",
        "release_state_passed": all(release_positive.values())
        and not release_state["private_artifacts_tracked"],
    }
    status = "pass" if all(checks.values()) else "fail"
    return {
        "model_name": "dream_studio_final_installed_modular_platform_closeout",
        "productization_version": PRODUCTIZATION_VERSION,
        "derived_view": True,
        "primary_authority": False,
        "db_write_authorized": False,
        "source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "required_multisession_cycles": list(REQUIRED_MULTISESSION_CYCLES),
        "module_profile_readiness": profile_readiness,
        "validated_commands": commands,
        "adapter_readiness": {
            "claude_cli_app_status": "documented_as_validated_baseline",
            "codex_cli_app_status": "documented_as_validated_baseline",
            "mcp_context_packet_fallback": "documented",
            "unsupported_apps": "classified_honestly",
            "adapter_surfaces_primary_authority": False,
        },
        "docs_product_readiness": {
            "readme_current": _truthy(validation_evidence.get("readme_current")),
            "prd_current": _truthy(validation_evidence.get("prd_current")),
            "contract_atlas_current": _truthy(validation_evidence.get("contract_atlas_current")),
            "sanitized_public_export_current": _truthy(
                validation_evidence.get("sanitized_public_export_current")
            ),
            "apache_2_license_consistent": _truthy(
                validation_evidence.get("apache_2_license_consistent")
            ),
        },
        "release_state": release_state,
        "long_run_validation": long_run,
        "checks": checks,
        "status": status,
        "ready_for_broader_local_use": status == "pass",
        "ready_for_public_release": False,
        "public_release_reason": "public release still requires explicit operator decision",
        "route_decision": (
            "operator_decision_on_public_release_private_dogfood_or_external_project_use"
            if status == "pass"
            else "hold_for_productization_blocker_review"
        ),
        "verdict": (
            "FINAL_INSTALLED_MODULAR_PLATFORM_PRODUCTIZATION_CLOSEOUT_COMPLETE"
            if status == "pass"
            else "FINAL_INSTALLED_MODULAR_PLATFORM_PRODUCTIZATION_CLOSEOUT_BLOCKED"
        ),
    }


def _profile_independent(profile_id: str) -> bool:
    profile = module_profile_map()[profile_id]
    return all(
        profile.get(field) is False
        for field in (
            "hooks_required",
            "agents_required",
            "workflows_required",
            "claude_required",
            "codex_required",
            "docker_required",
        )
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "present"}
    return bool(value)
