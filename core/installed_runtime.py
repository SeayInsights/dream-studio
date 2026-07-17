"""Installed Dream Studio runtime and adapter router read models."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config.sqlite_bootstrap import bootstrap_database, latest_migration_version
from core.event_store.studio_db import _connect
from core.module_profiles import module_profiles
from core.release.adapter_workspace_hygiene import adapter_workspace_policy
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.adapter_config_projection import adapter_config_projection_report
from core.shared_intelligence.adapter_staleness import adapter_staleness_report
from core.shared_intelligence.context_packets import generate_shared_context_packet
from core.shared_intelligence.usage_accounting import (
    adapter_usage_accounting_summary,
    register_default_adapter_accounting_profiles,
)

CONFIG_ENV = "DREAM_STUDIO_CONFIG"
SOURCE_ENV = "DREAM_STUDIO_SOURCE_ROOT"
HOME_ENV = "DREAM_STUDIO_HOME"
CONFIG_RELATIVE_PATH = "config/runtime.json"

ADAPTER_ACCESS_MODES: tuple[str, ...] = (
    "repo_attached",
    "cli_with_workdir",
    "app_workspace",
    "cloud_repo_environment",
    "mcp_capable",
    "context_packet_only",
    "unsupported",
)


@dataclass(frozen=True)
class InstalledRuntimePaths:
    """Resolved installed runtime paths."""

    source_root: Path
    dream_studio_home: Path

    @property
    def sqlite_path(self) -> Path:
        return self.dream_studio_home / "state" / "studio.db"

    @property
    def adapter_runtime_path(self) -> Path:
        return self.dream_studio_home / "adapters"

    @property
    def router_runtime_path(self) -> Path:
        return self.dream_studio_home / "router"

    @property
    def evidence_path(self) -> Path:
        return self.dream_studio_home / "meta"

    @property
    def context_packet_path(self) -> Path:
        return self.dream_studio_home / "context-packets"


def resolve_installed_runtime_paths(
    *,
    source_root: str | Path | None = None,
    dream_studio_home: str | Path | None = None,
) -> InstalledRuntimePaths:
    """Resolve source/state paths without depending on the caller's cwd."""

    source = Path(
        source_root or os.environ.get(SOURCE_ENV) or Path(__file__).resolve().parents[1]
    ).resolve()
    home = Path(
        dream_studio_home or os.environ.get(HOME_ENV) or Path.home() / ".dream-studio"
    ).resolve()
    return InstalledRuntimePaths(source_root=source, dream_studio_home=home)


def installed_runtime_model(
    *,
    source_root: str | Path | None = None,
    dream_studio_home: str | Path | None = None,
) -> dict[str, Any]:
    """Return the installed Dream Studio runtime model."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    return {
        "model_name": "dream_studio_installed_runtime_model",
        "derived_view": True,
        "primary_authority": False,
        "source_build_location": str(paths.source_root),
        "user_local_state_location": str(paths.dream_studio_home),
        "canonical_sqlite_path": str(paths.sqlite_path),
        "adapter_runtime_path": str(paths.adapter_runtime_path),
        "router_api_service": {
            "kind": "local_read_model",
            "api_routes": ["/api/shared-intelligence/adapter-router"],
            "global_command": "ds router",
            "execution_authorized": False,
        },
        "module_profile_configuration": module_profiles(),
        "global_command_surface": [
            "ds status",
            "ds install",
            "ds install-command",
            "ds dashboard",
            "ds dashboard --status",
            "ds dashboard --serve",
            "ds dashboard --open",
            "ds dashboard --check",
            "ds validate",
            "ds contract-atlas",
            "ds contract-atlas-refresh",
            "ds adapters",
            "ds context-packet",
            "ds modules",
            "ds router",
            "ds analytics-ingest",
            "ds acceptance",
            "ds backup",
            "ds restore-check",
            "ds restore",
            "ds update-check",
            "ds migrate-legacy",
            "ds repair-adapters",
            "ds rollback-check",
            "ds uninstall-check",
            "ds uninstall",
        ],
        "productization_surface": {
            "windows_launchers": ["ds.cmd", "ds.ps1"],
            "installer": "ds install --profile <profile>",
            "plain_command_installer": "ds install-command --execute",
            "first_run_setup": "ds install",
            "acceptance_tests": "ds acceptance",
            "backup": "ds backup",
            "restore_check": "ds restore-check",
            "restore": "ds restore <backup> --execute",
            "update_check": "ds update-check",
            "legacy_check": "ds install --check-legacy",
            "legacy_migration": "ds migrate-legacy --dry-run",
            "adapter_repair": "ds repair-adapters",
            "rollback_check": "ds rollback-check",
            "uninstall_check": "ds uninstall-check",
            "uninstall": "ds uninstall --execute",
            "uninstall_purge_state": "ds uninstall --execute --purge-state --force",
            "dashboard": {
                "status": "ds dashboard --status",
                "serve": "ds dashboard --serve",
                "open": "ds dashboard --open",
                "check": "ds dashboard --check",
                "default": "status_only_no_server_started",
            },
            "live_update_requires_guardrail_approval": True,
        },
        "context_packet_fallback": {
            "path": str(paths.context_packet_path),
            "mode": "context_packet_only",
            "private_model_memory_required": False,
        },
        "adapter_health_status_surface": {
            "global_command": "ds adapters",
            "api_route": "/api/shared-intelligence/adapter-router",
        },
        "source_state_separation": True,
        "live_db_write_authorized": False,
    }


def adapter_access_mode_summary() -> dict[str, Any]:
    """Classify supported adapter access modes honestly."""

    adapters = [
        {
            "adapter_id": "claude",
            "surface": "Claude Code CLI",
            "access_mode": "cli_with_workdir",
            "status": "live_consumption_proven",
        },
        {
            "adapter_id": "claude",
            "surface": "Claude Code app/workspace",
            "access_mode": "app_workspace",
            "status": "live_consumption_proven_with_workspace_head_check",
        },
        {
            "adapter_id": "codex",
            "surface": "Codex CLI",
            "access_mode": "cli_with_workdir",
            "status": "live_consumption_proven",
        },
        {
            "adapter_id": "codex",
            "surface": "Codex app configured environment",
            "access_mode": "app_workspace",
            "status": "live_consumption_proven",
        },
        {
            "adapter_id": "codex-cloud",
            "surface": "Codex cloud/GitHub environment",
            "access_mode": "cloud_repo_environment",
            "status": "not_proven_in_local_runtime",
        },
        {
            "adapter_id": "mcp",
            "surface": "MCP-capable clients",
            "access_mode": "mcp_capable",
            "status": "router_contract_available",
        },
        {
            "adapter_id": "shell",
            "surface": "shell tools",
            "access_mode": "cli_with_workdir",
            "status": "supported_via_global_ds_command",
        },
        {
            "adapter_id": "plain-web-chat",
            "surface": "plain web/chat tools",
            "access_mode": "context_packet_only",
            "status": "context_packet_only",
        },
    ]
    return {
        "model_name": "dream_studio_adapter_access_modes",
        "derived_view": True,
        "primary_authority": False,
        "access_modes": list(ADAPTER_ACCESS_MODES),
        "adapters": adapters,
        "unsupported_overclaiming_prevented": True,
    }


def adapter_router_status(
    conn: sqlite3.Connection,
    *,
    source_root: str | Path | None = None,
    dream_studio_home: str | Path | None = None,
    project_id: str | None = "dream-studio",
) -> dict[str, Any]:
    """Return the local adapter/router read model."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    projection_report = adapter_config_projection_report(conn, project_id=project_id)
    staleness = adapter_staleness_report(conn, config_root=paths.source_root, project_id=project_id)
    usage_accounting = adapter_usage_accounting_summary(conn, project_id=project_id)
    return {
        "model_name": "dream_studio_installed_adapter_router",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "execution_authorized": False,
        "db_write_authorized": False,
        "project_id": project_id,
        "runtime_model": installed_runtime_model(
            source_root=paths.source_root,
            dream_studio_home=paths.dream_studio_home,
        ),
        "adapter_access_modes": adapter_access_mode_summary(),
        "adapter_projection_summary": {
            "adapter_count": projection_report["adapter_count"],
            "config_write_authorized": projection_report["config_write_authorized"],
        },
        "adapter_health": {
            "adapter_count": staleness["adapter_count"],
            "aligned_count": staleness["aligned_count"],
            "stale_count": staleness["stale_count"],
            "repair_candidate_count": len(staleness["repair_work_order_candidates"]),
            "live_execution_proven": staleness["live_execution_proven"],
        },
        # capability_routes section removed migration 147 (WO-SCHEMALEAN) — the
        # capability_route_records summary it read was a dead persist=False surface.
        "usage_accounting": {
            "profile_count": usage_accounting["profile_count"],
            "token_record_count": usage_accounting["token_record_count"],
            "operational_record_count": usage_accounting["operational_record_count"],
            "by_adapter": usage_accounting["by_adapter"],
            "policy": usage_accounting["policy"],
        },
        "capabilities": [
            "current_route_state",
            "skills",
            "workflows",
            "hooks",
            "telemetry_capture",
            "evidence_capture",
            "context_packet_generation",
            "adapter_result_normalization",
            "contract_atlas_queries",
            "dashboard_attention",
            "module_profile_status",
        ],
        "workspace_hygiene": adapter_workspace_policy(),
        "empty_state": "Adapter router is available; unsupported adapters remain context-packet-only.",
    }


def bootstrap_rehearsal_runtime(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
) -> dict[str, Any]:
    """Create a rehearsal runtime home and bootstrap SQLite authority there."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    for path in (
        paths.dream_studio_home,
        paths.adapter_runtime_path,
        paths.router_runtime_path,
        paths.evidence_path,
        paths.context_packet_path,
        paths.sqlite_path.parent,
    ):
        path.mkdir(parents=True, exist_ok=True)
    from core.config.platform import ensure_platform_recorded

    ensure_platform_recorded()
    bootstrap_database(paths.sqlite_path)
    with _connect(paths.sqlite_path) as conn:
        register_default_adapter_authority_profiles(conn)
        register_default_adapter_accounting_profiles(conn)
        conn.commit()
        packet = generate_shared_context_packet(
            conn,
            packet_id="rehearsal-codex-resume",
            adapter_id="codex",
            packet_type="resume",
            project_id="dream-studio",
            persist=False,
        )
    config_path = paths.dream_studio_home / CONFIG_RELATIVE_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_payload = {
        "source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "sqlite_path": str(paths.sqlite_path),
        "module_profiles": ["core", "analytics_only", "adapter_router_only"],
        "live_state": False,
    }
    config_path.write_text(json.dumps(config_payload, indent=2, sort_keys=True) + "\n")
    return {
        "model_name": "dream_studio_rehearsal_install_validation",
        "source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "sqlite_path": str(paths.sqlite_path),
        "schema_version": latest_migration_version(),
        "fresh_state_created": True,
        "sqlite_bootstrap": True,
        "module_profiles_installed": config_payload["module_profiles"],
        "context_packet_generated": packet["packet_id"],
        "live_state_mutated": False,
        "config_path": str(config_path),
    }
