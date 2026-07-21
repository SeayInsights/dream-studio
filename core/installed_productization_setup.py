"""First-run setup and global command-surface install.

WO-GF-INSTALLED-PROD: split from ``core/installed_productization.py``. Holds the
first-run install flow, the user-local ``ds`` launcher install, dashboard
onboarding status, and their private helpers. No logic changes — extracted
verbatim from the original module.
"""

from __future__ import annotations

from datetime import UTC, datetime
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

from .installed_productization_shared import (
    DEFAULT_GLOBAL_COMMAND_DIR,
    DEFAULT_INSTALL_PROFILES,
    PRODUCTIZATION_VERSION,
    _normalize_profiles,
    _write_json,
)


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
        "created_at": datetime.now(UTC).isoformat(),
    }
    _write_json(config_path, payload)
    return config_path


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
