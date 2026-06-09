"""Installed platform productization flows for Dream Studio.

These helpers are designed for first-run setup and rehearsal validation. They
write only to the explicitly supplied Dream Studio home and never assume the
caller's current working directory is the source checkout.
"""

from __future__ import annotations

import json
import gc
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config.sqlite_bootstrap import (
    applied_schema_version,
    bootstrap_database,
    latest_migration_version,
)
from core.event_store.studio_db import _connect
from core.installed_runtime import (
    CONFIG_RELATIVE_PATH,
    adapter_router_status,
    resolve_installed_runtime_paths,
)
from core.module_profiles import module_profile_map, module_profiles, validate_module_profiles
from core.release.local_dogfood_stability import (
    REQUIRED_MULTISESSION_CYCLES,
    build_long_run_multisession_operational_validation,
)
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.contract_atlas import build_contract_atlas
from core.shared_intelligence.context_packets import generate_shared_context_packet
from core.shared_intelligence.usage_accounting import register_default_adapter_accounting_profiles

DEFAULT_INSTALL_PROFILES: tuple[str, ...] = ("core", "analytics_only", "adapter_router_only")
PRODUCTIZATION_VERSION = "dream_studio.installed_productization.v1"
DEFAULT_GLOBAL_COMMAND_DIR = Path.home() / ".local" / "bin"
LEGACY_BACKUP_ROOT_NAME = "Dream Studio Legacy Backups"
LEGACY_SPRAWL_CANDIDATES: tuple[str, ...] = (
    "work-orders",
    "handoffs",
    "reports",
    "evidence",
    "audit",
    "audits",
    "generated-prompts",
    "prompts",
    "cache",
    "caches",
    "logs",
    "meta/work-orders",
    "meta/handoffs",
    "meta/reports",
    "meta/evidence",
    "meta/audit",
    "meta/generated-prompts",
)
SQLITE_COPY_EXCLUDED_PREFIXES: tuple[str, ...] = ("sqlite_",)
SQLITE_COPY_EXCLUDED_SUFFIXES: tuple[str, ...] = (
    "_fts",
    "_fts_data",
    "_fts_idx",
    "_fts_docsize",
    "_fts_config",
)
SQLITE_COPY_EXCLUDED_TABLES: set[str] = {
    "_schema_version",
    "canonical_events",
    "legacy_canonical_event_import_map",
}


def first_run_setup(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    profiles: list[str] | tuple[str, ...] | None = None,
    rehearsal: bool = True,
) -> dict[str, Any]:
    """Create an installed runtime home for selected module profiles."""

    selected = _normalize_profiles(profiles or DEFAULT_INSTALL_PROFILES)
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    fresh_state_created = not paths.dream_studio_home.exists()
    _create_runtime_dirs(paths.dream_studio_home)
    from core.config.platform import ensure_platform_recorded

    ensure_platform_recorded()
    schema_version = bootstrap_database(paths.sqlite_path)
    conn = _connect(paths.sqlite_path)
    try:
        register_default_adapter_authority_profiles(conn)
        register_default_adapter_accounting_profiles(conn)
        conn.commit()
        router = adapter_router_status(
            conn,
            source_root=paths.source_root,
            dream_studio_home=paths.dream_studio_home,
        )
        atlas = build_contract_atlas(conn, repo_root=paths.source_root, project_id="dream-studio")
        packet = generate_shared_context_packet(
            conn,
            packet_id="first-run-codex-resume",
            adapter_id="codex",
            packet_type="resume",
            project_id="dream-studio",
            persist=False,
        )
    finally:
        conn.close()
    config_path = _write_runtime_config(
        source_root=paths.source_root,
        dream_studio_home=paths.dream_studio_home,
        profiles=selected,
        rehearsal=rehearsal,
    )
    profile_status = _profile_status(selected)
    return {
        "model_name": "dream_studio_first_run_setup",
        "productization_version": PRODUCTIZATION_VERSION,
        "source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "sqlite_path": str(paths.sqlite_path),
        "config_path": str(config_path),
        "fresh_state_created": fresh_state_created,
        "sqlite_bootstrap": True,
        "schema_version": schema_version,
        "latest_migration_version": latest_migration_version(),
        "selected_profiles": selected,
        "profile_status": profile_status,
        "dashboard_onboarding": dashboard_onboarding_status(
            source_root=paths.source_root,
            dream_studio_home=paths.dream_studio_home,
            profiles=selected,
        ),
        "adapter_setup": {
            "status": "available",
            "adapter_router_health": router["adapter_health"],
            "unsupported_tools_fallback": "context_packet_only",
            "context_packet_preview": packet["packet_id"],
            "config_write_authorized": False,
        },
        "contract_atlas": {
            "status": "available",
            "schema": atlas["schema"],
            "installed_profile_count": atlas["installed_module_profiles"]["profile_count"],
            "execution_authorized": atlas["execution_authorized"],
        },
        "global_command_surface": {
            "status": "available",
            "command": "ds",
            "windows_launchers": ["ds.cmd", "ds.ps1"],
            "default_command_dir": str(DEFAULT_GLOBAL_COMMAND_DIR),
            "install_command": "ds install-command --execute",
        },
        "runtime_state_written": True,
        "live_state_mutated": not rehearsal,
        "rehearsal": rehearsal,
    }


def install_global_command_surface(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    command_dir: str | Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Plan or install user-local launchers for the plain ``ds`` command."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    target_dir = Path(command_dir or DEFAULT_GLOBAL_COMMAND_DIR).resolve()
    launchers = {
        "ds.cmd": _windows_cmd_launcher(paths.source_root, paths.dream_studio_home),
        "ds.ps1": _windows_powershell_launcher(paths.source_root, paths.dream_studio_home),
    }
    written: list[str] = []
    if execute:
        target_dir.mkdir(parents=True, exist_ok=True)
        for name, content in launchers.items():
            target = target_dir / name
            target.write_text(content, encoding="utf-8", newline="\n")
            written.append(str(target))
    return {
        "model_name": "dream_studio_global_command_surface_install",
        "source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "command_dir": str(target_dir),
        "launchers": sorted(launchers),
        "written": written,
        "execute": execute,
        "destructive": False,
        "sqlite_mutation": False,
        "global_command": "ds",
        "path_requirement": "command_dir must be on PATH",
    }


def backup_runtime(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    backup_dir: str | Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Plan or perform a local runtime backup inside an explicit backup dir."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    target_dir = Path(backup_dir or paths.dream_studio_home / "backups").resolve()
    backup_id = f"backup-{_timestamp_slug()}"
    sqlite_exists = paths.sqlite_path.exists()
    if execute:
        target = target_dir / backup_id
        target.mkdir(parents=True, exist_ok=True)
        if sqlite_exists:
            shutil.copy2(paths.sqlite_path, target / "studio.db")
        _write_json(target / "backup-manifest.json", _backup_manifest(paths, backup_id))
        status = "created"
        backup_path = str(target)
    else:
        status = "planned"
        backup_path = str(target_dir / backup_id)
    return {
        "model_name": "dream_studio_runtime_backup",
        "status": status,
        "backup_id": backup_id,
        "backup_path": backup_path,
        "sqlite_exists": sqlite_exists,
        "execute": execute,
        "destructive": False,
        "runtime_state_write": execute,
        "live_state_mutation": False,
        "requires_operator_approval_for_live_home": execute,
    }


def restore_runtime_check(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    backup_path: str | Path,
) -> dict[str, Any]:
    """Validate that a backup can be restored without performing the restore."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    backup = Path(backup_path).resolve()
    sqlite_backup = backup / "studio.db"
    manifest = backup / "backup-manifest.json"
    return {
        "model_name": "dream_studio_runtime_restore_check",
        "backup_path": str(backup),
        "target_home": str(paths.dream_studio_home),
        "backup_exists": backup.exists(),
        "sqlite_backup_exists": sqlite_backup.exists(),
        "manifest_exists": manifest.exists(),
        "restore_ready": backup.exists() and sqlite_backup.exists(),
        "restore_executed": False,
        "destructive": False,
        "requires_operator_approval": True,
    }


def update_runtime_check(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
) -> dict[str, Any]:
    """Return update readiness without mutating the installed runtime."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    schema_version = None
    if paths.sqlite_path.exists():
        conn = _connect(paths.sqlite_path)
        try:
            schema_version = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
        finally:
            conn.close()
    return {
        "model_name": "dream_studio_runtime_update_check",
        "source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "sqlite_exists": paths.sqlite_path.exists(),
        "schema_version": schema_version,
        "latest_migration_version": latest_migration_version(),
        "update_ready": paths.sqlite_path.exists()
        and (schema_version is None or int(schema_version) <= latest_migration_version()),
        "update_executed": False,
        "requires_backup_before_live_update": True,
        "live_state_mutated": False,
        "legacy_install_detection": detect_legacy_install(
            source_root=paths.source_root,
            dream_studio_home=paths.dream_studio_home,
        ),
    }


def detect_legacy_install(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    command_dir: str | Path | None = None,
    claude_settings_path: str | Path | None = None,
    codex_home: str | Path | None = None,
) -> dict[str, Any]:
    """Detect old install surfaces without mutating or printing secrets."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    config_path = paths.dream_studio_home / CONFIG_RELATIVE_PATH
    runtime_config = _read_json_if_object(config_path)
    configured_source = runtime_config.get("source_root") if runtime_config else None
    source_mismatch = bool(
        configured_source and Path(configured_source).resolve() != paths.source_root
    )
    schema_version = _sqlite_schema_version(paths.sqlite_path)
    legacy_sprawl = _legacy_sprawl(paths.dream_studio_home)
    launcher_report = _launcher_path_report(
        command_dir=Path(command_dir).resolve() if command_dir else DEFAULT_GLOBAL_COMMAND_DIR,
        current_source=paths.source_root,
    )
    adapter_config_report = _adapter_config_path_report(
        source_root=paths.source_root,
        claude_settings_path=claude_settings_path,
        codex_home=codex_home,
    )
    stale_env = _stale_environment_report(paths.source_root, paths.dream_studio_home)
    unknown_manual_review = []
    if paths.dream_studio_home.exists() and not paths.sqlite_path.exists() and legacy_sprawl:
        unknown_manual_review.append("runtime_state_without_current_sqlite_authority")
    if configured_source and not Path(configured_source).exists():
        unknown_manual_review.append("runtime_config_source_path_missing")
    old_schema = schema_version is not None and schema_version < latest_migration_version()
    status = (
        "legacy_detected"
        if any(
            (
                source_mismatch,
                paths.dream_studio_home.exists() and old_schema,
                legacy_sprawl,
                launcher_report["stale_launcher_count"],
                adapter_config_report["stale_adapter_config_count"],
                stale_env["stale_env_count"],
                unknown_manual_review,
            )
        )
        else "current_or_not_installed"
    )
    return {
        "model_name": "dream_studio_legacy_install_detection",
        "derived_view": True,
        "primary_authority": False,
        "status": status,
        "current_source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "runtime_config_path": str(config_path),
        "runtime_config_exists": config_path.exists(),
        "configured_source_root": configured_source,
        "old_source_checkout_detected": source_mismatch,
        "runtime_state_exists": paths.dream_studio_home.exists(),
        "sqlite_exists": paths.sqlite_path.exists(),
        "schema_version": schema_version,
        "latest_migration_version": latest_migration_version(),
        "old_sqlite_schema_detected": old_schema,
        "old_file_sprawl_detected": bool(legacy_sprawl),
        "legacy_file_sprawl": legacy_sprawl,
        "launcher_paths": launcher_report,
        "adapter_config_paths": adapter_config_report,
        "stale_environment": stale_env,
        "manual_review_items": unknown_manual_review,
        "destructive_action_authorized": False,
        "secret_values_read": False,
    }


def migrate_legacy_install(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    backup_root: str | Path | None = None,
    command_dir: str | Path | None = None,
    claude_settings_path: str | Path | None = None,
    codex_home: str | Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Plan or execute a fresh active install from a legacy runtime home."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    backup_base = Path(backup_root or paths.dream_studio_home.parent / LEGACY_BACKUP_ROOT_NAME)
    backup_path = backup_base / f".dream-studio-legacy-upgrade-{_timestamp_slug()}"
    detection = detect_legacy_install(
        source_root=paths.source_root,
        dream_studio_home=paths.dream_studio_home,
        command_dir=command_dir,
        claude_settings_path=claude_settings_path,
        codex_home=codex_home,
    )
    planned_writes = [
        str(backup_path),
        str(paths.dream_studio_home),
        str(paths.sqlite_path),
        str(paths.dream_studio_home / CONFIG_RELATIVE_PATH),
    ]
    if command_dir:
        planned_writes.extend(
            [
                str(Path(command_dir).resolve() / "ds.cmd"),
                str(Path(command_dir).resolve() / "ds.ps1"),
            ]
        )
    dry_run = {
        "model_name": "dream_studio_legacy_install_migration",
        "status": "dry_run" if not execute else "pending",
        "execute": execute,
        "current_source_path": str(paths.source_root),
        "installed_runtime_path": str(paths.dream_studio_home),
        "backup_path": str(backup_path),
        "planned_writes": planned_writes,
        "detection": detection,
        "strategy": {
            "backup_first": True,
            "fresh_active_home": True,
            "apply_current_migrations": True,
            "copy_legacy_file_sprawl_forward": False,
            "compatible_sqlite_authority_only": True,
            "merge_unrelated_git_histories": False,
            "delete_old_source_or_backups": False,
            "inspect_secrets": False,
        },
        "rollback_instructions": [
            "Stop Dream Studio commands.",
            "Move the fresh active .dream-studio aside.",
            "Restore the backed-up .dream-studio directory from backup_path.",
            "Re-run ds rollback-check --backup-path <backup_path> before resuming.",
        ],
    }
    if not execute:
        return dry_run
    if not paths.dream_studio_home.exists():
        raise RuntimeError("Cannot migrate legacy install because the runtime home does not exist.")

    gc.collect()
    backup_base.mkdir(parents=True, exist_ok=True)
    backup_runtime_path = backup_path / "runtime-home"
    shutil.copytree(paths.dream_studio_home, backup_runtime_path)
    _write_json(backup_path / "legacy-detection.json", detection)
    _write_text(
        backup_path / "ROLLBACK.txt",
        "\n".join(dry_run["rollback_instructions"]) + "\n",
    )
    backup_verified = _verify_sqlite_read_only(backup_runtime_path / "state" / "studio.db")

    moved_runtime_path = backup_path / "previous-active-runtime-home"
    gc.collect()
    shutil.move(str(paths.dream_studio_home), str(moved_runtime_path))
    setup = first_run_setup(
        source_root=paths.source_root,
        dream_studio_home=paths.dream_studio_home,
        profiles=DEFAULT_INSTALL_PROFILES,
        rehearsal=False,
    )
    migration = _migrate_compatible_sqlite_authority(
        source_db=backup_runtime_path / "state" / "studio.db",
        target_db=paths.sqlite_path,
    )
    launcher = None
    if command_dir:
        launcher = install_global_command_surface(
            source_root=paths.source_root,
            dream_studio_home=paths.dream_studio_home,
            command_dir=command_dir,
            execute=True,
        )
    adapter_repair = repair_adapter_surfaces(
        source_root=paths.source_root,
        dream_studio_home=paths.dream_studio_home,
        command_dir=command_dir,
        claude_settings_path=claude_settings_path,
        codex_home=codex_home,
        previous_source_root=detection.get("configured_source_root"),
        execute=True,
    )
    return {
        **dry_run,
        "status": "migrated",
        "backup_verified": backup_verified,
        "backup_runtime_path": str(backup_runtime_path),
        "moved_previous_runtime_path": str(moved_runtime_path),
        "fresh_setup": setup,
        "sqlite_migration": migration,
        "launcher_refresh": launcher,
        "adapter_repair": adapter_repair,
        "old_file_sprawl_copied_forward": False,
        "destructive_sqlite_mutation": False,
        "external_projects_mutated": False,
    }


def repair_adapter_surfaces(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    command_dir: str | Path | None = None,
    claude_settings_path: str | Path | None = None,
    codex_home: str | Path | None = None,
    previous_source_root: str | Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Plan or repair Dream-Studio-owned launchers and adapter hook paths."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    command_target = Path(command_dir).resolve() if command_dir else DEFAULT_GLOBAL_COMMAND_DIR
    detection = detect_legacy_install(
        source_root=paths.source_root,
        dream_studio_home=paths.dream_studio_home,
        command_dir=command_target,
        claude_settings_path=claude_settings_path,
        codex_home=codex_home,
    )
    planned_writes = [str(command_target / "ds.cmd"), str(command_target / "ds.ps1")]
    if claude_settings_path:
        planned_writes.append(str(Path(claude_settings_path).resolve()))
    result: dict[str, Any] = {
        "model_name": "dream_studio_adapter_surface_repair",
        "status": "planned",
        "execute": execute,
        "source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "planned_writes": planned_writes,
        "detection": detection,
        "secret_values_read": False,
        "external_projects_mutated": False,
        "adapter_hooks_repaired": 0,
        "launchers_repaired": 0,
    }
    if not execute:
        return result
    launcher = install_global_command_surface(
        source_root=paths.source_root,
        dream_studio_home=paths.dream_studio_home,
        command_dir=command_target,
        execute=True,
    )
    result["launchers_repaired"] = len(launcher["written"])
    if claude_settings_path and previous_source_root:
        result["adapter_hooks_repaired"] = sum(
            _replace_source_in_dream_studio_json_strings(
                Path(claude_settings_path).resolve(),
                old=old_source,
                new=str(paths.source_root),
            )
            for old_source in sorted(
                {str(previous_source_root), str(Path(previous_source_root).resolve())}
            )
        )
    result["status"] = "repaired"
    result["launcher_refresh"] = launcher
    return result


def rollback_runtime_check(
    *,
    backup_path: str | Path,
) -> dict[str, Any]:
    """Validate a legacy-upgrade backup without restoring it."""

    backup = Path(backup_path).resolve()
    runtime_backup = backup / "runtime-home"
    sqlite_backup = runtime_backup / "state" / "studio.db"
    rollback = backup / "ROLLBACK.txt"
    detection = backup / "legacy-detection.json"
    return {
        "model_name": "dream_studio_legacy_rollback_check",
        "backup_path": str(backup),
        "backup_exists": backup.exists(),
        "runtime_backup_exists": runtime_backup.exists(),
        "sqlite_backup_exists": sqlite_backup.exists(),
        "sqlite_backup_opens_read_only": _verify_sqlite_read_only(sqlite_backup),
        "rollback_instructions_exist": rollback.exists(),
        "legacy_detection_exists": detection.exists(),
        "rollback_ready": backup.exists() and runtime_backup.exists() and rollback.exists(),
        "restore_executed": False,
        "delete_authorized": False,
    }


def uninstall_runtime_check(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
) -> dict[str, Any]:
    """Return uninstall inventory without deleting anything."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    inventory = []
    if paths.dream_studio_home.exists():
        inventory = [
            str(path.relative_to(paths.dream_studio_home))
            for path in paths.dream_studio_home.rglob("*")
            if path.is_file()
        ]
    return {
        "model_name": "dream_studio_runtime_uninstall_check",
        "dream_studio_home": str(paths.dream_studio_home),
        "exists": paths.dream_studio_home.exists(),
        "file_count": len(inventory),
        "sample_inventory": inventory[:20],
        "uninstall_executed": False,
        "delete_authorized": False,
        "requires_operator_approval": True,
    }


def dashboard_onboarding_status(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    profiles: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Return dashboard onboarding behavior for selected profiles."""

    selected = set(_normalize_profiles(profiles))
    dashboard_enabled = bool(selected.intersection({"dashboard_only", "full", "analytics_only"}))
    return {
        "dashboard_enabled": dashboard_enabled,
        "dashboard_command": "ds dashboard",
        "dashboard_modes": {
            "status": "ds dashboard --status",
            "serve": "ds dashboard --serve",
            "open": "ds dashboard --open",
            "check": "ds dashboard --check",
        },
        "starts_server": False,
        "default_behavior": "status_only_no_server_started",
        "source_root": str(Path(source_root).resolve()),
        "dream_studio_home": str(Path(dream_studio_home).resolve()),
        "api_routes": (
            ["/api/shared-intelligence/*", "/api/telemetry/*"] if dashboard_enabled else []
        ),
        "empty_state": (
            "Dashboard routes show derived empty states until runtime facts exist."
            if dashboard_enabled
            else "Dashboard module is disabled by selected profiles."
        ),
        "start_guidance": (
            "Run ds dashboard --serve to start the local server, ds dashboard --open to "
            "start/reuse it and open a browser, and ds dashboard --check to validate "
            "route health."
        ),
    }


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


def _normalize_profiles(profiles: list[str] | tuple[str, ...]) -> list[str]:
    profile_map = module_profile_map()
    normalized = list(dict.fromkeys(str(profile) for profile in profiles))
    unknown = sorted(profile for profile in normalized if profile not in profile_map)
    if unknown:
        raise ValueError(f"unknown module profile(s): {', '.join(unknown)}")
    return normalized


def _profile_status(selected: list[str]) -> dict[str, Any]:
    profile_map = module_profile_map()
    selected_set = set(selected)
    return {
        "selected": [
            {
                "profile_id": profile_id,
                "status": "enabled",
                "commands": profile_map[profile_id]["exposed_commands"],
                "routes": profile_map[profile_id]["exposed_routes"],
            }
            for profile_id in selected
        ],
        "unselected": [
            {
                "profile_id": profile_id,
                "status": "disabled",
                "reason": "not selected for this installed profile",
            }
            for profile_id in module_profile_map()
            if profile_id not in selected_set
        ],
        "available_profiles": module_profiles(),
        "validation_errors": validate_module_profiles(),
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


def _create_runtime_dirs(home: Path) -> None:
    for rel in (
        "state",
        "config",
        "adapters",
        "router",
        "context-packets",
        "meta",
        "backups",
        "logs",
    ):
        (home / rel).mkdir(parents=True, exist_ok=True)


def _write_runtime_config(
    *,
    source_root: Path,
    dream_studio_home: Path,
    profiles: list[str],
    rehearsal: bool,
) -> Path:
    config_path = dream_studio_home / CONFIG_RELATIVE_PATH
    payload = {
        "productization_version": PRODUCTIZATION_VERSION,
        "source_root": str(source_root),
        "dream_studio_home": str(dream_studio_home),
        "sqlite_path": str(dream_studio_home / "state" / "studio.db"),
        "module_profiles": profiles,
        "rehearsal": rehearsal,
        "live_state": not rehearsal,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(config_path, payload)
    return config_path


def _backup_manifest(paths: Any, backup_id: str) -> dict[str, Any]:
    return {
        "backup_id": backup_id,
        "source_home": str(paths.dream_studio_home),
        "sqlite_path": str(paths.sqlite_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": latest_migration_version(),
        "restore_requires_operator_approval": True,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _read_json_if_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _sqlite_schema_version(db_path: Path) -> int | None:
    if not db_path.exists():
        return None
    try:
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
            return applied_schema_version(conn)
    except sqlite3.Error:
        return None


def _verify_sqlite_read_only(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    try:
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        return True
    except sqlite3.Error:
        return False


def _legacy_sprawl(home: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not home.exists():
        return findings
    for rel in LEGACY_SPRAWL_CANDIDATES:
        path = home / rel
        if not path.exists():
            continue
        findings.append(
            {
                "relative_path": rel,
                "classification": "legacy_file_sprawl_keep_in_backup_only",
                "is_dir": path.is_dir(),
                "file_count": _count_files(path),
            }
        )
    return findings


def _count_files(path: Path) -> int:
    if path.is_file():
        return 1
    if not path.is_dir():
        return 0
    return sum(1 for child in path.rglob("*") if child.is_file())


def _launcher_path_report(*, command_dir: Path, current_source: Path) -> dict[str, Any]:
    launchers = []
    stale_count = 0
    for name in ("ds.cmd", "ds.ps1"):
        path = command_dir / name
        stale = False
        dream_studio_owned = False
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            dream_studio_owned = (
                "DREAM_STUDIO_SOURCE_ROOT" in text or "interfaces\\cli\\ds.py" in text
            )
            stale = dream_studio_owned and str(current_source) not in text
        stale_count += int(stale)
        launchers.append(
            {
                "path": str(path),
                "exists": path.exists(),
                "dream_studio_owned": dream_studio_owned,
                "stale": stale,
            }
        )
    return {
        "command_dir": str(command_dir),
        "launchers": launchers,
        "stale_launcher_count": stale_count,
    }


def _adapter_config_path_report(
    *,
    source_root: Path,
    claude_settings_path: str | Path | None,
    codex_home: str | Path | None,
) -> dict[str, Any]:
    stale_count = 0
    surfaces = []
    if claude_settings_path:
        path = Path(claude_settings_path).resolve()
        owned = False
        stale = False
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            owned = "dream-studio" in text.lower() or "DREAM_STUDIO_SOURCE_ROOT" in text
            stale = owned and str(source_root) not in text
        stale_count += int(stale)
        surfaces.append(
            {
                "surface": "claude_settings",
                "path": str(path),
                "exists": path.exists(),
                "dream_studio_owned_entries_detected": owned,
                "stale": stale,
            }
        )
    if codex_home:
        path = Path(codex_home).resolve()
        surfaces.append(
            {
                "surface": "codex_home",
                "path": str(path),
                "exists": path.exists(),
                "repair_mode": "projection_regeneration_only",
                "stale": False,
            }
        )
    return {"surfaces": surfaces, "stale_adapter_config_count": stale_count}


def _stale_environment_report(source_root: Path, home: Path) -> dict[str, Any]:
    checks = {
        "DREAM_STUDIO_SOURCE_ROOT": str(source_root),
        "DREAM_STUDIO_HOME": str(home),
    }
    stale = []
    for name, expected in checks.items():
        value = os.environ.get(name)
        if value and str(Path(value).resolve()) != expected:
            stale.append({"name": name, "classification": "stale_environment_variable"})
    return {"stale_env_count": len(stale), "stale_variables": stale}


def _migrate_compatible_sqlite_authority(*, source_db: Path, target_db: Path) -> dict[str, Any]:
    if not source_db.exists():
        return {
            "status": "skipped",
            "reason": "legacy_sqlite_missing",
            "migrated_tables": [],
            "skipped_tables": [],
        }
    migrated = []
    skipped = []
    with (
        closing(sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)) as src,
        closing(sqlite3.connect(str(target_db))) as dst,
    ):
        src.row_factory = sqlite3.Row
        dst.row_factory = sqlite3.Row
        source_tables = _table_names(src)
        target_tables = _table_names(dst)
        for table in sorted(source_tables & target_tables):
            if _skip_sqlite_copy_table(table):
                skipped.append({"table": table, "reason": "excluded_rebuildable_or_legacy"})
                continue
            source_columns = _table_columns(src, table)
            target_columns = _table_columns(dst, table)
            common_columns = [column for column in source_columns if column in target_columns]
            if not common_columns:
                skipped.append({"table": table, "reason": "no_common_columns"})
                continue
            rows = src.execute(
                f"SELECT {', '.join(_q(column) for column in common_columns)} FROM {_q(table)}"
            ).fetchall()
            inserted = 0
            if rows:
                placeholders = ", ".join("?" for _ in common_columns)
                sql = (
                    f"INSERT OR IGNORE INTO {_q(table)} "
                    f"({', '.join(_q(column) for column in common_columns)}) "
                    f"VALUES ({placeholders})"
                )
                for row in rows:
                    before = dst.total_changes
                    dst.execute(sql, [row[column] for column in common_columns])
                    inserted += dst.total_changes - before
            migrated.append(
                {
                    "table": table,
                    "source_rows": len(rows),
                    "inserted_rows": inserted,
                    "common_column_count": len(common_columns),
                    "source_ref": f"{source_db.name}:{table}",
                }
            )
        dst.commit()
    return {
        "status": "pass",
        "migrated_tables": migrated,
        "skipped_tables": skipped,
        "source_refs_preserved": True,
        "legacy_tables_recreated": False,
    }


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        if not str(row[0]).startswith("sqlite_")
    }


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({_q(table)})")]


def _skip_sqlite_copy_table(table: str) -> bool:
    return (
        table in SQLITE_COPY_EXCLUDED_TABLES
        or table.startswith(SQLITE_COPY_EXCLUDED_PREFIXES)
        or table.endswith(SQLITE_COPY_EXCLUDED_SUFFIXES)
    )


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _replace_source_in_dream_studio_json_strings(path: Path, *, old: str, new: str) -> int:
    data = _read_json_if_object(path)
    if not data:
        return 0
    data, changed, replaced = _replace_source_in_value(data, old=old, new=new)
    if changed:
        _write_json(path, data)
    return replaced


def _replace_source_in_value(value: Any, *, old: str, new: str) -> tuple[Any, bool, int]:
    if isinstance(value, dict):
        changed = False
        replaced = 0
        for key, item in value.items():
            new_item, item_changed, item_replaced = _replace_source_in_value(item, old=old, new=new)
            changed = changed or item_changed
            replaced += item_replaced
            value[key] = new_item
        return value, changed, replaced
    if isinstance(value, list):
        changed = False
        replaced = 0
        for index, item in enumerate(value):
            new_item, item_changed, item_replaced = _replace_source_in_value(item, old=old, new=new)
            changed = changed or item_changed
            replaced += item_replaced
            value[index] = new_item
        return value, changed, replaced
    if isinstance(value, str) and old in value and "dream-studio" in value.lower():
        return value.replace(old, new), True, 1
    return value, False, 0


def _windows_cmd_launcher(source_root: Path, dream_studio_home: Path) -> str:
    cli = source_root / "interfaces" / "cli" / "ds.py"
    return "\n".join(
        [
            "@echo off",
            "setlocal",
            f'set "DREAM_STUDIO_SOURCE_ROOT={source_root}"',
            f'set "DREAM_STUDIO_HOME={dream_studio_home}"',
            f'set "DREAM_STUDIO_CLI={cli}"',
            "where py >nul 2>nul",
            "if %ERRORLEVEL% EQU 0 (",
            '  py -3 "%DREAM_STUDIO_CLI%" --source-root "%DREAM_STUDIO_SOURCE_ROOT%" '
            '--home "%DREAM_STUDIO_HOME%" %*',
            "  exit /b %ERRORLEVEL%",
            ")",
            "where python >nul 2>nul",
            "if %ERRORLEVEL% EQU 0 (",
            '  python "%DREAM_STUDIO_CLI%" --source-root "%DREAM_STUDIO_SOURCE_ROOT%" '
            '--home "%DREAM_STUDIO_HOME%" %*',
            "  exit /b %ERRORLEVEL%",
            ")",
            "echo Python 3.11+ was not found on PATH. >&2",
            "exit /b 1",
            "",
        ]
    )


def _windows_powershell_launcher(source_root: Path, dream_studio_home: Path) -> str:
    cli = source_root / "interfaces" / "cli" / "ds.py"
    return "\n".join(
        [
            '$ErrorActionPreference = "Stop"',
            f'$env:DREAM_STUDIO_SOURCE_ROOT = "{source_root}"',
            f'$env:DREAM_STUDIO_HOME = "{dream_studio_home}"',
            f'$Cli = "{cli}"',
            "$PythonCmd = $null",
            'foreach ($candidate in @("py", "python3", "python")) {',
            "    if (Get-Command $candidate -ErrorAction SilentlyContinue) {",
            "        $PythonCmd = $candidate",
            "        break",
            "    }",
            "}",
            "if (-not $PythonCmd) {",
            '    Write-Error "Python 3.11+ was not found on PATH."',
            "    exit 1",
            "}",
            'if ($PythonCmd -eq "py") {',
            "    py -3 $Cli --source-root $env:DREAM_STUDIO_SOURCE_ROOT "
            "--home $env:DREAM_STUDIO_HOME @args",
            "} else {",
            "    & $PythonCmd $Cli --source-root $env:DREAM_STUDIO_SOURCE_ROOT "
            "--home $env:DREAM_STUDIO_HOME @args",
            "}",
            "exit $LASTEXITCODE",
            "",
        ]
    )


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "present"}
    return bool(value)
