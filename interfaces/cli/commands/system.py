"""ds system-level command group — flat/system commands.

This module handles all the flat/system-level commands that don't belong to a
named entity group: status, version, doctor, repair, update, dashboard,
validate, migrate, modules, adapters, router, platform-hardening, policy,
contract-atlas, analytics-ingest, install, install-command, acceptance,
backup, restore, restore-check, update-check, uninstall, uninstall-check,
migrate-legacy, repair-adapters, rollback-check, context-packet,
rehearsal-install, and the delegated add_*_subcommand groups.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from interfaces.cli.cli_utils import (
    _changed_files_from_args,
    _default_claude_settings_paths,
    _print,
    _require_home_for_install,
    _with_conn,
)

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def register(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach all flat/system subparsers to *subcommands*."""

    subcommands.add_parser("status", help="Show installed runtime status")
    subcommands.add_parser("version", help="Show Dream Studio source/runtime version")

    _doctor_cmd = subcommands.add_parser(
        "doctor",
        help="Verify Claude Code integration health (skills, agents, hooks, routing)",
        description=(
            "Verify Claude Code integration health: dispatcher hooks wired, skills\n"
            "installed and current, agents deployed, routing triggers covered, version\n"
            "current. Use this after `ds integrate install` or before starting a session.\n"
            "For DB-level health (schema version, migrations), use `ds validate`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _doctor_cmd.add_argument("--fix", action="store_true", help="Attempt to fix failing checks")
    _doctor_cmd.add_argument(
        "mode",
        nargs="?",
        default=None,
        help=(
            "Optional mode.  Supported values:\n"
            "  dashboard-truth  Run live-authority invariant checks against the SQLite DB."
        ),
    )

    subcommands.add_parser("repair", help="Plan repair actions without mutating state")

    _update_cmd = subcommands.add_parser("update", help="Update Dream Studio integration pack")
    _update_cmd.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Show what would change without installing",
    )

    dashboard = subcommands.add_parser(
        "dashboard", help="Show, serve, open, or check the local dashboard"
    )
    dashboard_mode = dashboard.add_mutually_exclusive_group()
    dashboard_mode.add_argument(
        "--status",
        action="store_true",
        help="Report dashboard readiness without starting a server (default).",
    )
    dashboard_mode.add_argument(
        "--serve",
        action="store_true",
        help="Start the local dashboard server in the foreground.",
    )
    dashboard_mode.add_argument(
        "--open",
        action="store_true",
        help="Start or reuse the local dashboard server and open a browser.",
    )
    dashboard_mode.add_argument(
        "--check",
        action="store_true",
        help="Validate dashboard and API route health on a running server.",
    )
    dashboard.add_argument("--host", default="127.0.0.1", help="Dashboard bind/probe host")
    dashboard.add_argument("--port", type=int, default=8000, help="Dashboard server port")
    dashboard.add_argument(
        "--timeout-seconds",
        type=float,
        default=15.0,
        help="Seconds to wait for dashboard readiness in --open/--check modes.",
    )

    subcommands.add_parser(
        "validate",
        help="Verify DB health (schema version, migrations, module profiles)",
        description=(
            "Verify DB health: schema version, migration completeness, module profile\n"
            "validity. Use this after migrations or DB-related changes. For Claude Code\n"
            "integration health (skills, agents, hooks, routing), use `ds doctor`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subcommands.add_parser("contract-atlas", help="Show Contract Atlas summary")
    atlas_refresh = subcommands.add_parser(
        "contract-atlas-refresh",
        help="Plan or refresh Contract Atlas lifecycle exports",
    )
    atlas_refresh.add_argument("--output-dir", default=None)
    atlas_refresh.add_argument("--execute", action="store_true", default=False)
    atlas_refresh.add_argument("--include-private", action="store_true", default=False)
    atlas_refresh.add_argument("--changed-file", action="append", default=[])
    atlas_refresh.add_argument("--changed-files", default=None)
    atlas_refresh.add_argument("--docs-reviewed-no-change", action="append", default=[])

    subcommands.add_parser("adapters", help="Show adapter status")
    subcommands.add_parser("modules", help="Show module profile status")
    subcommands.add_parser("router", help="Show adapter router status")
    subcommands.add_parser("platform-hardening", help="Show platform hardening status")

    policy = subcommands.add_parser("policy", help="Preview a policy decision")
    policy.add_argument("--actor", default="operator")
    policy.add_argument("--action", default="read_only_action")
    policy.add_argument("--target", default=None)
    policy.add_argument("--approved", action="store_true", default=False)

    analytics_ingest = subcommands.add_parser(
        "analytics-ingest", help="Import normalized analytics facts into SQLite authority"
    )
    analytics_ingest.add_argument("--file", required=True, help="Normalized analytics JSON payload")
    analytics_ingest.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Write records. Omit for dry-run planning.",
    )

    install = subcommands.add_parser("install", help="Run first-run setup for selected profiles")
    install.add_argument("--profile", action="append", dest="profiles", default=[])
    install.add_argument("--rehearsal", action="store_true", default=False)
    install.add_argument(
        "--check-legacy",
        action="store_true",
        default=False,
        help="Detect legacy install surfaces without mutation",
    )
    install.add_argument("--command-dir", default=None)
    install.add_argument("--claude-settings-path", default=None)
    install.add_argument("--codex-home", default=None)

    install_command = subcommands.add_parser(
        "install-command", help="Install user-local launchers for the plain ds command"
    )
    install_command.add_argument("--command-dir", default=None)
    install_command.add_argument("--execute", action="store_true", default=False)

    acceptance = subcommands.add_parser(
        "acceptance", help="Run installed platform acceptance against a rehearsal home"
    )
    acceptance.add_argument("--profile", action="append", dest="profiles", default=[])

    backup = subcommands.add_parser("backup", help="Plan or create a runtime backup")
    backup.add_argument("--backup-dir", default=None)
    backup.add_argument("--execute", action="store_true", default=False)

    restore = subcommands.add_parser("restore-check", help="Validate a backup without restoring it")
    restore.add_argument("--backup-path", required=True)

    restore_cmd = subcommands.add_parser(
        "restore",
        help=(
            "Restore state from a backup. Default is a dry-run; --execute applies, "
            "taking a pre-restore backup of current state first. --force overrides "
            "a not-restore-ready backup."
        ),
    )
    restore_cmd.add_argument("backup_path", help="Path to the backup directory to restore from")
    restore_cmd.add_argument("--execute", action="store_true", default=False)
    restore_cmd.add_argument("--force", action="store_true", default=False)
    restore_cmd.add_argument("--backup-dir", default=None, dest="backup_dir")

    subcommands.add_parser("update-check", help="Check update readiness without mutation")
    subcommands.add_parser("uninstall-check", help="Inventory uninstall targets without deleting")

    uninstall = subcommands.add_parser(
        "uninstall",
        help=(
            "Uninstall DS adapter wiring. Default is a dry-run; --execute removes "
            ".claude hook wiring + launchers (state preserved). --purge-state --force "
            "additionally wipes ~/.dream-studio after an automatic backup."
        ),
    )
    uninstall.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Apply the teardown. Without it, only the inventory/plan is printed.",
    )
    uninstall.add_argument(
        "--purge-state",
        action="store_true",
        default=False,
        dest="purge_state",
        help="Also wipe ~/.dream-studio state (requires --force as the second confirmation).",
    )
    uninstall.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Second confirmation for --purge-state. Backup is always taken first.",
    )
    uninstall.add_argument("--backup-dir", default=None, dest="backup_dir")
    uninstall.add_argument("--command-dir", default=None, dest="command_dir")
    uninstall.add_argument(
        "--claude-settings-path",
        action="append",
        default=None,
        dest="claude_settings_paths",
        help="Override the .claude settings.json copies to clear (repeatable).",
    )

    migrate_legacy = subcommands.add_parser(
        "migrate-legacy", help="Plan or execute a guarded legacy install migration"
    )
    migrate_legacy.add_argument("--backup-root", default=None)
    migrate_legacy.add_argument("--command-dir", default=None)
    migrate_legacy.add_argument("--claude-settings-path", default=None)
    migrate_legacy.add_argument("--codex-home", default=None)
    migration_mode = migrate_legacy.add_mutually_exclusive_group()
    migration_mode.add_argument("--dry-run", action="store_true", default=True)
    migration_mode.add_argument("--execute", action="store_true", default=False)

    migrate_cmd = subcommands.add_parser(
        "migrate", help="Manage migration activation state on the live authority DB"
    )
    migrate_sub = migrate_cmd.add_subparsers(dest="migrate_subcommand", required=True)
    migrate_sub.add_parser("status", help="Show merged-but-not-activated migrations")
    migrate_activate_cmd = migrate_sub.add_parser(
        "activate",
        help="Apply pending-activation migrations (operator-invoked; creates backup first)",
    )
    migrate_activate_cmd.add_argument(
        "--db-path",
        default=None,
        dest="db_path",
        help="Override live DB path (default: ~/.dream-studio/state/studio.db)",
    )
    migrate_activate_cmd.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Skip interactive confirmation prompt and apply immediately",
    )

    repair_adapters = subcommands.add_parser(
        "repair-adapters", help="Plan or repair Dream-Studio-owned adapter surfaces"
    )
    repair_adapters.add_argument("--command-dir", default=None)
    repair_adapters.add_argument("--claude-settings-path", default=None)
    repair_adapters.add_argument("--codex-home", default=None)
    repair_adapters.add_argument("--previous-source-root", default=None)
    repair_adapters.add_argument("--execute", action="store_true", default=False)

    rollback = subcommands.add_parser(
        "rollback-check", help="Validate a legacy-upgrade backup without restoring"
    )
    rollback.add_argument("--backup-path", required=True)

    packet = subcommands.add_parser("context-packet", help="Preview a context packet")
    packet.add_argument("--adapter", default="codex")
    packet.add_argument("--packet-type", default="resume")
    packet.add_argument("--surface", dest="packet_type", help="Alias for --packet-type")
    packet.add_argument("--project-id", default="dream-studio")

    rehearsal = subcommands.add_parser("rehearsal-install", help="Bootstrap a rehearsal runtime")
    rehearsal.add_argument("--rehearsal-home", required=True)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

#: Commands handled by this module.
SYSTEM_COMMANDS = frozenset(
    {
        "status",
        "version",
        "doctor",
        "repair",
        "update",
        "dashboard",
        "validate",
        "migrate",
        "modules",
        "adapters",
        "router",
        "platform-hardening",
        "policy",
        "contract-atlas",
        "contract-atlas-refresh",
        "analytics-ingest",
        "install",
        "install-command",
        "acceptance",
        "backup",
        "restore-check",
        "restore",
        "update-check",
        "uninstall-check",
        "uninstall",
        "migrate-legacy",
        "repair-adapters",
        "rollback-check",
        "context-packet",
        "rehearsal-install",
    }
)


def dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Route a system-level command to the correct implementation."""
    from core.analytics_ingestion import load_analytics_payload
    from core.installed_runtime import (
        adapter_router_status,
        bootstrap_rehearsal_runtime,
    )

    # Resolve via interfaces.cli.ds so the single patch point
    # (interfaces.cli.ds.resolve_installed_runtime_paths) reaches CLI dispatch too.
    from interfaces.cli.ds import resolve_installed_runtime_paths
    from core.installed_productization import (
        backup_runtime,
        detect_legacy_install,
        first_run_setup,
        install_global_command_surface,
        migrate_legacy_install,
        productization_acceptance_report,
        repair_adapter_surfaces,
        restore_runtime,
        restore_runtime_check,
        rollback_runtime_check,
        uninstall_runtime,
        uninstall_runtime_check,
        update_runtime_check,
    )
    from core.module_profiles import module_profiles
    from core.shared_intelligence.contract_atlas import build_contract_atlas
    from core.shared_intelligence.contract_atlas_lifecycle import refresh_contract_atlas_exports
    from core.shared_intelligence.context_packets import generate_shared_context_packet
    from core.shared_intelligence.platform_hardening import (
        evaluate_policy_decision,
        platform_hardening_summary,
    )

    if args.command == "status":
        from core.health.status import get_runtime_status

        return _print(
            get_runtime_status(source_root=source_root, dream_studio_home=dream_studio_home)
        )

    if args.command == "version":
        return _print(_version_status(source_root=source_root, dream_studio_home=dream_studio_home))

    if args.command == "doctor":
        _doctor_mode = getattr(args, "mode", None)
        if _doctor_mode == "dashboard-truth":
            from core.gates.dashboard_truth import run_dashboard_truth

            _dt_paths = resolve_installed_runtime_paths(
                source_root=source_root,
                dream_studio_home=dream_studio_home,
            )
            _dt_result = run_dashboard_truth(_dt_paths.sqlite_path)
            for _inv in _dt_result["results"]:
                _status = "PASS" if _inv["passed"] else "FAIL"
                _err = f" — {_inv['error']}" if _inv["error"] else ""
                print(f"[dashboard-truth] {_status}: {_inv['name']}{_err}")
            if not _dt_result["ok"]:
                print("[dashboard-truth] OVERALL: FAIL — one or more invariants failed")
                return 1
            print("[dashboard-truth] OVERALL: PASS")
            return 0
        return _print(
            _doctor_status(
                source_root=source_root,
                dream_studio_home=dream_studio_home,
                fix=getattr(args, "fix", False),
            )
        )

    if args.command == "update":
        return _update_command(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            dry_run=getattr(args, "dry_run", False),
        )

    if args.command == "repair":
        return _print(_repair_plan(source_root=source_root, dream_studio_home=dream_studio_home))

    if args.command == "dashboard":
        if args.serve:
            return _dashboard_serve(
                source_root=source_root,
                dream_studio_home=dream_studio_home,
                host=args.host,
                port=args.port,
            )
        if args.open:
            payload = _dashboard_open(
                source_root=source_root,
                dream_studio_home=dream_studio_home,
                host=args.host,
                port=args.port,
                timeout_seconds=args.timeout_seconds,
            )
            _print(payload)
            return 0 if payload["ok"] else 1
        if args.check:
            payload = _dashboard_check(
                source_root=source_root,
                dream_studio_home=dream_studio_home,
                host=args.host,
                port=args.port,
                timeout_seconds=args.timeout_seconds,
            )
            _print(payload)
            return 0 if payload["ok"] else 1
        return _print(
            _dashboard_status(
                source_root=source_root,
                dream_studio_home=dream_studio_home,
                host=args.host,
                port=args.port,
            )
        )

    if args.command == "validate":
        return _print(
            _validate_status(source_root=source_root, dream_studio_home=dream_studio_home)
        )

    if args.command == "migrate":
        return _migrate_command(args)

    if args.command == "modules":
        return _print(module_profiles())

    if args.command in {"adapters", "router"}:
        return _with_conn(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            callback=lambda conn: adapter_router_status(
                conn,
                source_root=source_root,
                dream_studio_home=dream_studio_home,
            ),
        )

    if args.command == "platform-hardening":
        return _with_conn(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            callback=platform_hardening_summary,
        )

    if args.command == "policy":
        return _print(
            {
                "model_name": "dream_studio_policy_decision_preview",
                "derived_view": True,
                "primary_authority": False,
                "execution_authorized": False,
                **evaluate_policy_decision(
                    actor=args.actor,
                    action=args.action,
                    target=args.target,
                    scope={},
                    approved=bool(args.approved),
                ),
            }
        )

    if args.command == "contract-atlas":
        return _with_conn(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            callback=lambda conn: build_contract_atlas(
                conn,
                repo_root=source_root,
                project_id="dream-studio",
            ),
        )

    if args.command == "contract-atlas-refresh":
        changed_files = _changed_files_from_args(args)
        return _with_conn(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            callback=lambda conn: refresh_contract_atlas_exports(
                conn,
                repo_root=source_root,
                output_dir=Path(args.output_dir).resolve() if args.output_dir else None,
                project_id="dream-studio",
                changed_files=changed_files,
                reviewed_no_change_domains=args.docs_reviewed_no_change,
                include_private=bool(args.include_private),
                execute=bool(args.execute),
            ),
        )

    if args.command == "context-packet":
        return _with_conn(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            callback=lambda conn: generate_shared_context_packet(
                conn,
                packet_id=f"dry-run-{args.adapter}-{args.packet_type}",
                adapter_id=args.adapter,
                packet_type=args.packet_type,
                project_id=args.project_id,
                persist=False,
            ),
        )

    if args.command == "analytics-ingest":
        payload = load_analytics_payload(args.file)
        return _analytics_ingest(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            payload=payload,
            execute=bool(args.execute),
        )

    if args.command == "rehearsal-install":
        return _print(
            bootstrap_rehearsal_runtime(
                source_root=source_root,
                dream_studio_home=args.rehearsal_home,
            )
        )

    if args.command == "install":
        if args.check_legacy:
            return _print(
                detect_legacy_install(
                    source_root=source_root,
                    dream_studio_home=dream_studio_home or _require_home_for_install(args.command),
                    command_dir=args.command_dir,
                    claude_settings_path=args.claude_settings_path,
                    codex_home=args.codex_home,
                )
            )
        profiles = args.profiles or None
        return _print(
            first_run_setup(
                source_root=source_root,
                dream_studio_home=dream_studio_home or _require_home_for_install(args.command),
                profiles=profiles,
                rehearsal=bool(args.rehearsal),
            )
        )

    if args.command == "install-command":
        return _print(
            install_global_command_surface(
                source_root=source_root,
                dream_studio_home=dream_studio_home or _require_home_for_install(args.command),
                command_dir=args.command_dir,
                execute=bool(args.execute),
            )
        )

    if args.command == "acceptance":
        return _print(
            productization_acceptance_report(
                source_root=source_root,
                dream_studio_home=dream_studio_home or _require_home_for_install(args.command),
                profiles=args.profiles or ["core", "analytics_only", "security_only", "full"],
            )
        )

    if args.command == "backup":
        return _print(
            backup_runtime(
                source_root=source_root,
                dream_studio_home=dream_studio_home or _require_home_for_install(args.command),
                backup_dir=args.backup_dir,
                execute=args.execute,
            )
        )

    if args.command == "restore-check":
        return _print(
            restore_runtime_check(
                source_root=source_root,
                dream_studio_home=dream_studio_home or _require_home_for_install(args.command),
                backup_path=args.backup_path,
            )
        )

    if args.command == "restore":
        return _print(
            restore_runtime(
                source_root=source_root,
                dream_studio_home=dream_studio_home or _require_home_for_install(args.command),
                backup_path=args.backup_path,
                backup_dir=args.backup_dir,
                execute=bool(args.execute),
                force=bool(args.force),
            )
        )

    if args.command == "update-check":
        return _print(
            update_runtime_check(
                source_root=source_root,
                dream_studio_home=dream_studio_home,
            )
        )

    if args.command == "uninstall-check":
        return _print(
            uninstall_runtime_check(
                source_root=source_root,
                dream_studio_home=dream_studio_home,
            )
        )

    if args.command == "uninstall":
        settings_paths = args.claude_settings_paths or _default_claude_settings_paths()
        return _print(
            uninstall_runtime(
                source_root=source_root,
                dream_studio_home=dream_studio_home or _require_home_for_install(args.command),
                claude_settings_paths=settings_paths,
                command_dir=args.command_dir,
                backup_dir=args.backup_dir,
                execute=bool(args.execute),
                purge_state=bool(args.purge_state),
                confirm_purge=bool(args.force),
            )
        )

    if args.command == "migrate-legacy":
        return _print(
            migrate_legacy_install(
                source_root=source_root,
                dream_studio_home=dream_studio_home or _require_home_for_install(args.command),
                backup_root=args.backup_root,
                command_dir=args.command_dir,
                claude_settings_path=args.claude_settings_path,
                codex_home=args.codex_home,
                execute=bool(args.execute),
            )
        )

    if args.command == "repair-adapters":
        return _print(
            repair_adapter_surfaces(
                source_root=source_root,
                dream_studio_home=dream_studio_home or _require_home_for_install(args.command),
                command_dir=args.command_dir,
                claude_settings_path=args.claude_settings_path,
                codex_home=args.codex_home,
                previous_source_root=args.previous_source_root,
                execute=bool(args.execute),
            )
        )

    if args.command == "rollback-check":
        return _print(rollback_runtime_check(backup_path=args.backup_path))

    print(f"Unknown system command: {args.command}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Implementation helpers
# ---------------------------------------------------------------------------


def _analytics_ingest(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    payload: dict[str, Any],
    execute: bool,
) -> int:
    from core.event_store.studio_db import _connect
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError(
            "Dream Studio SQLite authority is missing. Run rehearsal-install for a rehearsal "
            "home, or install/bootstrap the real runtime through an approved update plan."
        )
    from core.analytics_ingestion import ingest_analytics_payload

    with _connect(paths.sqlite_path) as conn:
        return _print(ingest_analytics_payload(conn, payload, execute=execute))


def _dashboard_status(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> dict[str, Any]:
    from core.installed_runtime import installed_runtime_model

    model = installed_runtime_model(source_root=source_root, dream_studio_home=dream_studio_home)
    base_url = f"http://{_dashboard_client_host(host)}:{port}"
    return {
        "model_name": "dream_studio_dashboard_command_status",
        "derived_view": True,
        "primary_authority": False,
        "mode": "status",
        "safe_default": True,
        "dashboard_command_available": True,
        "dashboard_route": "/dashboard",
        "api_routes": ["/api/telemetry/*", "/api/shared-intelligence/*", "/api/v1/hooks/*"],
        "url": f"{base_url}/dashboard",
        "source_root": model["source_build_location"],
        "sqlite_path": model["canonical_sqlite_path"],
        "sqlite_exists": Path(model["canonical_sqlite_path"]).is_file(),
        "starts_server": False,
        "available_modes": {
            "status": "ds dashboard --status",
            "serve": "ds dashboard --serve",
            "open": "ds dashboard --open",
            "check": "ds dashboard --check",
        },
        "default_behavior": "status_only_no_server_started",
        "start_server_command": "ds dashboard --serve",
        "open_browser_command": "ds dashboard --open",
        "check_command": "ds dashboard --check",
        "empty_state": (
            "Status mode is safe and does not start a server. Run "
            "`ds dashboard --serve` to start the local dashboard server, or "
            "`ds dashboard --open` to start/reuse it and open a browser."
        ),
    }


def _refresh_derived_store(sqlite_path: Path) -> None:
    """WO-DASH-FRESHNESS: rebuild the derived DuckDB store from the authority before
    serving the dashboard, so a fresh open always reflects current data (the open
    path never did this, so rollups/events_fact were only as fresh as the last
    manual ``ds analyze aggregate``). Best-effort — a failure degrades to whatever
    the store already held. Runs: spool ingest + projections, then the events_fact
    derivation, then the aggregate rollups."""
    try:
        from core.projections.runner import sync_tick

        sync_tick()
    except Exception:
        pass
    try:
        from core.analytics.duckdb_store import connect_analytics, derive_events_fact

        conn = connect_analytics(read_only=False)
        try:
            derive_events_fact(conn, str(sqlite_path))
        finally:
            conn.close()
    except Exception:
        pass
    try:
        from core.analytics.aggregate_metrics import run_aggregation

        run_aggregation()
    except Exception:
        pass


def _dashboard_serve(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    host: str,
    port: int,
) -> int:
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    _refresh_derived_store(paths.sqlite_path)
    if host == "0.0.0.0":
        print(
            "[dashboard] WARNING: binding to 0.0.0.0 exposes the dashboard to the network.",
            file=sys.stderr,
        )
    url = f"http://{_dashboard_client_host(host)}:{port}/dashboard"
    print("[dashboard] Starting Dream Studio dashboard server")
    print(f"[dashboard] URL: {url}")
    print(f"[dashboard] Source root: {paths.source_root}")
    print(f"[dashboard] SQLite authority: {paths.sqlite_path}")
    print("[dashboard] Press Ctrl+C to stop.")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "projections.api.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    try:
        return subprocess.run(
            cmd,
            cwd=paths.source_root,
            env=_dashboard_env(paths.source_root, paths.dream_studio_home, paths.sqlite_path),
            check=False,
        ).returncode
    except KeyboardInterrupt:
        return 130


def _dashboard_open(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    host: str,
    port: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    _refresh_derived_store(paths.sqlite_path)
    client_host = _dashboard_client_host(host)
    url = f"http://{client_host}:{port}/dashboard"
    process_id = None
    if not _dashboard_port_in_use(client_host, port):
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "projections.api.main:app",
            "--host",
            host,
            "--port",
            str(port),
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            cmd,
            cwd=paths.source_root,
            env=_dashboard_env(paths.source_root, paths.dream_studio_home, paths.sqlite_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        process_id = proc.pid
    ready = _wait_for_dashboard(host=client_host, port=port, timeout_seconds=timeout_seconds)
    opened = False
    if ready:
        opened = webbrowser.open(url)
    return {
        "model_name": "dream_studio_dashboard_open_result",
        "derived_view": True,
        "primary_authority": False,
        "mode": "open",
        "ok": ready,
        "url": url,
        "server_started": process_id is not None,
        "process_id": process_id,
        "browser_open_requested": ready,
        "browser_open_result": opened,
        "source_root": str(paths.source_root),
        "sqlite_path": str(paths.sqlite_path),
        "live_db_destructive_mutation_authorized": False,
        "empty_state": None if ready else "Dashboard server did not become reachable in time.",
    }


def _dashboard_check(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    host: str,
    port: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    base_url = f"http://{_dashboard_client_host(host)}:{port}"
    routes = {
        "dashboard": f"{base_url}/dashboard",
        "api_health": f"{base_url}/api/health",
    }
    probes = {
        name: _dashboard_http_status(url, timeout_seconds=timeout_seconds)
        for name, url in routes.items()
    }
    ok = all(probe["status_code"] == 200 for probe in probes.values())
    return {
        "model_name": "dream_studio_dashboard_route_health_check",
        "derived_view": True,
        "primary_authority": False,
        "mode": "check",
        "ok": ok,
        "url": f"{base_url}/dashboard",
        "source_root": str(paths.source_root),
        "sqlite_path": str(paths.sqlite_path),
        "sqlite_exists": paths.sqlite_path.is_file(),
        "routes": probes,
        "live_db_destructive_mutation_authorized": False,
        "empty_state": None if ok else "Start the server with `ds dashboard --serve` first.",
    }


def _dashboard_env(source_root: Path, dream_studio_home: Path, sqlite_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["DREAM_STUDIO_SOURCE_ROOT"] = str(source_root)
    env["DREAM_STUDIO_HOME"] = str(dream_studio_home)
    env["DREAM_STUDIO_DB_PATH"] = str(sqlite_path)
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(source_root)
        if not current_pythonpath
        else f"{source_root}{os.pathsep}{current_pythonpath}"
    )
    return env


def _dashboard_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _dashboard_client_host(host: str) -> str:
    return "127.0.0.1" if host in {"0.0.0.0", "::"} else host


def _wait_for_dashboard(*, host: str, port: int, timeout_seconds: float) -> bool:
    start = time.time()
    while time.time() - start < timeout_seconds:
        probe = _dashboard_http_status(
            f"http://{host}:{port}/dashboard",
            timeout_seconds=min(2.0, timeout_seconds),
        )
        if probe["status_code"] == 200:
            return True
        time.sleep(0.3)
    return False


def _dashboard_http_status(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return {
                "url": url,
                "status_code": response.status,
                "ok": response.status == 200,
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        return {"url": url, "status_code": exc.code, "ok": False, "error": str(exc)}
    except OSError as exc:
        return {"url": url, "status_code": None, "ok": False, "error": str(exc)}


def _version_status(*, source_root: Path, dream_studio_home: Path | None) -> dict[str, Any]:
    from core.health.version import get_version

    return get_version(source_root=source_root, dream_studio_home=dream_studio_home)


def _check_dispatcher_hooks(claude_dir: Path) -> bool:
    """Return True if the DS dispatcher hook is registered for UserPromptSubmit."""
    _DISPATCHER_MARKERS = (
        "hooks\\dispatch\\hooks.py",  # installed path (Windows)
        "hooks/dispatch/hooks.py",  # installed path (Unix)
        "runtime/dispatch/hooks",  # legacy repo-relative path
        "'dispatch'/'hooks.py'",  # legacy pathlib expression
    )
    try:
        settings_path = claude_dir / "settings.json"
        if not settings_path.is_file():
            return False
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        hooks_section = data.get("hooks", {})
        event_entries = hooks_section.get("UserPromptSubmit", [])
        for entry in event_entries:
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if any(m in cmd for m in _DISPATCHER_MARKERS):
                    return True
        return False
    except Exception:
        return False


def _get_expected_skill_ids(source_root: Path) -> list[str]:
    """Derive expected Claude Code skill IDs from canonical/skills/ directory."""
    skills_dir = source_root / "canonical" / "skills"
    if not skills_dir.is_dir():
        return ["ds-bootstrap"]
    ids = [
        (d.name if d.name.startswith("ds-") else f"ds-{d.name}")
        for d in sorted(skills_dir.iterdir())
        if d.is_dir() and (d / "SKILL.md").is_file()
    ]
    return ids or ["ds-bootstrap"]


def _check_skills_installed(claude_dir: Path, source_root: Path | None = None) -> dict[str, Any]:
    """Return skills install status — checks all canonical skill IDs."""
    expected = _get_expected_skill_ids(source_root) if source_root is not None else ["ds-bootstrap"]
    try:
        skills_dir = claude_dir / "skills"
        installed = [sid for sid in expected if (skills_dir / sid / "SKILL.md").is_file()]
        missing = [sid for sid in expected if sid not in installed]
        return {"total_expected": len(expected), "installed": len(installed), "missing": missing}
    except Exception:
        return {"total_expected": len(expected), "installed": 0, "missing": expected}


def _check_agents_installed(claude_dir: Path, source_root: Path) -> dict[str, Any]:
    """Return agents install status — checks canonical/agents/ vs ~/.claude/agents/."""
    try:
        agents_src = source_root / "canonical" / "agents"
        expected = (
            [p.stem for p in agents_src.glob("*.md") if p.name != "README.md"]
            if agents_src.is_dir()
            else []
        )
        agents_dir = claude_dir / "agents"
        installed = [name for name in expected if (agents_dir / f"{name}.md").is_file()]
        missing = [name for name in expected if name not in installed]
        return {"total_expected": len(expected), "installed": len(installed), "missing": missing}
    except Exception:
        return {"total_expected": 0, "installed": 0, "missing": []}


def _check_failed_events(dream_studio_home: Path) -> dict[str, int]:
    """Return count of *.json files in ~/.dream-studio/events/failed/ root only."""
    try:
        failed_dir = dream_studio_home / "events" / "failed"
        if not failed_dir.is_dir():
            return {"count": 0}
        count = sum(1 for p in failed_dir.iterdir() if p.is_file() and p.suffix == ".json")
        return {"count": count}
    except Exception:
        return {"count": 0}


def _check_version_current(source_root: Path, dream_studio_home: Path) -> dict[str, Any]:
    """Compare repo VERSION vs installed-version. Fail-open."""
    try:
        repo_file = source_root / "VERSION"
        installed_file = dream_studio_home / "state" / "installed-version"
        repo_ver = repo_file.read_text(encoding="utf-8").strip() if repo_file.is_file() else None
        installed_ver = (
            installed_file.read_text(encoding="utf-8").strip() if installed_file.is_file() else None
        )
        current = repo_ver is not None and repo_ver == installed_ver
        return {"repo": repo_ver, "installed": installed_ver, "current": current}
    except Exception:
        return {"repo": None, "installed": None, "current": False}


def _doctor_status(
    *, source_root: Path, dream_studio_home: Path | None, fix: bool = False
) -> dict[str, Any]:
    from core.config.platform import ensure_platform_recorded
    from core.health.doctor import run_doctor_checks

    ensure_platform_recorded()
    return run_doctor_checks(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        fix=fix,
    )


def _canonical_hook_drift(source_root: Path, manifest: dict) -> list[str]:
    """Return names of hook meta files whose canonical source has changed since last install.

    The manifest records content_hash = hash(canonical_source) at install time.
    If the canonical source has since been updated (e.g. a bug fix without a version bump),
    the hashes differ and re-projection is required.  Returns an empty list when everything
    matches (no reinstall needed).
    """
    # Index manifest by filename for hook meta files (ignore duplicates — first match wins)
    meta_hashes: dict[str, str] = {}
    for entry in manifest.get("files", []):
        if entry.get("operation") == "skip":
            continue
        p = entry.get("path", "")
        # Match installed hook meta handlers in either projection tree
        if "hooks" in p and "meta" in p and p.endswith(".py") and "__init__" not in p:
            name = Path(p).name
            if name not in meta_hashes:
                meta_hashes[name] = entry.get("content_hash", "")

    meta_src = source_root / "runtime" / "hooks" / "meta"
    if not meta_src.is_dir():
        return []

    drift: list[str] = []
    for handler in sorted(meta_src.glob("*.py")):
        if handler.name == "__init__.py":
            continue
        recorded = meta_hashes.get(handler.name, "")
        if not recorded:
            continue
        from integrations.manifest import compute_hash as _compute_hash

        if _compute_hash(handler.read_text(encoding="utf-8")) != recorded:
            drift.append(handler.name)
    return drift


def _update_command(
    *, source_root: Path, dream_studio_home: Path | None, dry_run: bool = False
) -> int:
    """Implement ``ds update [--dry-run]``.

    A2.8: replaced the legacy ``subprocess.run(['ds', 'integrate', 'install',
    'claude_code', '--execute'])`` self-shell-out with a direct in-process
    call to ``ClaudeCodeInstaller.install('execute')`` — same pattern as
    the ``ds integrate install`` command path uses today. The shell-out
    spawned a fresh Python interpreter that re-imported the whole CLI
    just to run code that lives in the same process; the direct call
    skips the interpreter overhead, keeps tracebacks intact, and lets
    callers patch the installer with ``unittest.mock``.
    """
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    repo_file = source_root / "VERSION"
    installed_file = paths.dream_studio_home / "state" / "installed-version"

    repo_version = repo_file.read_text(encoding="utf-8").strip() if repo_file.is_file() else None
    if repo_version is None:
        _print({"ok": False, "error": "VERSION file not found in source root"})
        return 1

    installed_version = (
        installed_file.read_text(encoding="utf-8").strip() if installed_file.is_file() else None
    )

    if installed_version == repo_version:
        # Version stamp matches, but check whether canonical hook source has drifted
        # from what the manifest recorded at the last install.  A hook code change
        # without a version bump (e.g. WO-A) must still trigger re-projection.
        from integrations.manifest import read_manifest

        manifest = read_manifest("claude_code", ds_home=paths.dream_studio_home)
        if manifest and _canonical_hook_drift(source_root, manifest):
            pass  # fall through to reinstall
        else:
            _print({"ok": True, "status": "already_current", "version": repo_version})
            return 0

    if dry_run:
        _print(
            {
                "ok": True,
                "status": "update_available",
                "from": installed_version,
                "to": repo_version,
                "dry_run": True,
                "would_run": "ds integrate install claude_code --execute",
            }
        )
        return 0

    from integrations.detector import detect_claude_code
    from integrations.installer.claude_code import ClaudeCodeInstaller
    from integrations.manifest import get_ds_home

    canonical_root = source_root / "canonical"
    ds_home = dream_studio_home or get_ds_home()

    try:
        detected = detect_claude_code()
        installer = ClaudeCodeInstaller(
            detected.config_root,
            detected.scope,
            canonical_root=canonical_root,
            ds_home=ds_home,
        )
        install_result = installer.install("execute")
        install_ok = bool(install_result.get("ok", True))

        # When running from a project-scope dir, also update the user-global surface so
        # both projection trees stay in sync.  The project-scope tree has no hook registrations
        # (dispatch consolidation); the user-global tree is the single dispatch surface.
        if install_ok and detected.scope == "project":
            user_installer = ClaudeCodeInstaller(
                Path.home() / ".claude",
                "user",
                canonical_root=canonical_root,
                ds_home=ds_home,
            )
            user_result = user_installer.install("execute")
            if not user_result.get("ok", True):
                install_result["user_scope_warning"] = user_result
    except Exception as exc:  # noqa: BLE001 — surface the install failure to operator
        install_result = {"ok": False, "error": str(exc), "error_type": type(exc).__name__}
        install_ok = False

    install_output = json.dumps(install_result, indent=2, sort_keys=True)

    if install_ok:
        installed_file.parent.mkdir(parents=True, exist_ok=True)
        installed_file.write_text(repo_version + "\n", encoding="utf-8")

    _print(
        {
            "ok": install_ok,
            "status": "updated" if install_ok else "install_failed",
            "from": installed_version,
            "to": repo_version,
            "changes": install_output,
        }
    )
    return 0 if install_ok else 1


def _repair_plan(*, source_root: Path, dream_studio_home: Path | None) -> dict[str, Any]:
    doctor = _doctor_status(source_root=source_root, dream_studio_home=dream_studio_home)
    actions = []
    if not doctor["checks"]["sqlite_exists"]:
        actions.append("Run ds install --home <explicit-home> --rehearsal for rehearsal setup.")
    if not doctor["checks"]["module_profiles_valid"]:
        actions.append("Review module profile validation errors before runtime update.")
    return {
        "model_name": "dream_studio_repair_plan",
        "derived_view": True,
        "primary_authority": False,
        "repair_executed": False,
        "mutation_authorized": False,
        "delete_authorized": False,
        "actions": actions,
        "status": "pass" if not actions else "attention_required",
        "rollback_guidance": "No rollback required; this command is plan-only.",
    }


def _validate_status(*, source_root: Path, dream_studio_home: Path | None) -> dict[str, Any]:
    from core.health.validate import run_validation

    return run_validation(source_root=source_root, dream_studio_home=dream_studio_home)


def _migrate_command(args: argparse.Namespace) -> int:
    from core.config.sqlite_bootstrap import activate_pending_migrations, pending_migrations_info

    if args.migrate_subcommand == "status":
        pending = pending_migrations_info()
        if not pending:
            return _print(
                {"ok": True, "pending_count": 0, "message": "All merged migrations are activated."}
            )
        return _print(
            {
                "ok": True,
                "pending_count": len(pending),
                "message": (
                    f"{len(pending)} merged migration(s) await activation on the live authority."
                    " Run `ds migrate activate --confirm` to apply."
                ),
                "pending_migrations": pending,
            }
        )

    if args.migrate_subcommand == "activate":
        pending = pending_migrations_info()
        if not pending:
            return _print(
                {"ok": True, "applied": [], "message": "No pending migrations to activate."}
            )

        if not getattr(args, "confirm", False):
            print(f"\n  {len(pending)} migration(s) will be applied to the live authority DB:\n")
            for m in pending:
                print(f"    [{m['version']}] {m['description']}")
            print("\n  A backup will be created before applying.")
            print("  Re-run with --confirm to proceed.\n")
            return 0

        db_path = Path(args.db_path).resolve() if getattr(args, "db_path", None) else None
        result = activate_pending_migrations(db_path)
        return _print(result)

    return 1
