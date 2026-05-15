"""Installed platform productization flows for Dream Studio.

These helpers are designed for first-run setup and rehearsal validation. They
write only to the explicitly supplied Dream Studio home and never assume the
caller's current working directory is the source checkout.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config.sqlite_bootstrap import bootstrap_database, latest_migration_version
from core.event_store.studio_db import _connect
from core.installed_runtime import (
    CONFIG_RELATIVE_PATH,
    adapter_router_status,
    resolve_installed_runtime_paths,
)
from core.module_profiles import module_profile_map, module_profiles, validate_module_profiles
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.contract_atlas import build_contract_atlas
from core.shared_intelligence.context_packets import generate_shared_context_packet
from core.shared_intelligence.usage_accounting import register_default_adapter_accounting_profiles

DEFAULT_INSTALL_PROFILES: tuple[str, ...] = ("core", "analytics_only", "adapter_router_only")
PRODUCTIZATION_VERSION = "dream_studio.installed_productization.v1"


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
    schema_version = bootstrap_database(paths.sqlite_path)
    with _connect(paths.sqlite_path) as conn:
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
        "runtime_state_written": True,
        "live_state_mutated": not rehearsal,
        "rehearsal": rehearsal,
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
        with _connect(paths.sqlite_path) as conn:
            schema_version = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
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
        "starts_server": False,
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
    with _connect(paths.sqlite_path) as conn:
        router = adapter_router_status(
            conn,
            source_root=paths.source_root,
            dream_studio_home=paths.dream_studio_home,
        )
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


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
