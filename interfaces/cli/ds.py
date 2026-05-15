"""Global Dream Studio command surface.

This CLI is designed to run from outside the repository. It resolves Dream
Studio source/state through explicit arguments or installed runtime config,
never by assuming the caller's current working directory is the repo.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config.sqlite_bootstrap import latest_migration_version  # noqa: E402
from core.event_store.studio_db import _connect  # noqa: E402
from core.analytics_ingestion import (  # noqa: E402
    ingest_analytics_payload,
    load_analytics_payload,
)
from core.installed_runtime import (  # noqa: E402
    adapter_router_status,
    bootstrap_rehearsal_runtime,
    installed_runtime_model,
    resolve_installed_runtime_paths,
)
from core.installed_productization import (  # noqa: E402
    backup_runtime,
    detect_legacy_install,
    first_run_setup,
    install_global_command_surface,
    migrate_legacy_install,
    productization_acceptance_report,
    repair_adapter_surfaces,
    rollback_runtime_check,
    restore_runtime_check,
    uninstall_runtime_check,
    update_runtime_check,
)
from core.module_profiles import module_profiles, validate_module_profiles  # noqa: E402
from core.shared_intelligence.contract_atlas import build_contract_atlas  # noqa: E402
from core.shared_intelligence.contract_atlas_lifecycle import (  # noqa: E402
    refresh_contract_atlas_exports,
)
from core.shared_intelligence.context_packets import generate_shared_context_packet  # noqa: E402
from core.shared_intelligence.platform_hardening import (  # noqa: E402
    evaluate_policy_decision,
    platform_hardening_summary,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ds", description="Dream Studio global command")
    parser.add_argument("--source-root", default=None, help="Dream Studio source/build root")
    parser.add_argument("--home", default=None, help="Dream Studio user-local state root")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("status", help="Show installed runtime status")
    subcommands.add_parser("version", help="Show Dream Studio source/runtime version")
    subcommands.add_parser("doctor", help="Run read-only runtime health checks")
    subcommands.add_parser("repair", help="Plan repair actions without mutating state")
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
    subcommands.add_parser("validate", help="Validate installed runtime readiness")
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

    subcommands.add_parser("update-check", help="Check update readiness without mutation")
    subcommands.add_parser("uninstall-check", help="Inventory uninstall targets without deleting")

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

    args = parser.parse_args(argv)
    source_root = Path(args.source_root).resolve() if args.source_root else REPO_ROOT
    home = Path(args.home).resolve() if args.home else None

    try:
        if args.command == "status":
            return _print(installed_runtime_model(source_root=source_root, dream_studio_home=home))
        if args.command == "version":
            return _print(_version_status(source_root=source_root, dream_studio_home=home))
        if args.command == "doctor":
            return _print(_doctor_status(source_root=source_root, dream_studio_home=home))
        if args.command == "repair":
            return _print(_repair_plan(source_root=source_root, dream_studio_home=home))
        if args.command == "dashboard":
            if args.serve:
                return _dashboard_serve(
                    source_root=source_root,
                    dream_studio_home=home,
                    host=args.host,
                    port=args.port,
                )
            if args.open:
                payload = _dashboard_open(
                    source_root=source_root,
                    dream_studio_home=home,
                    host=args.host,
                    port=args.port,
                    timeout_seconds=args.timeout_seconds,
                )
                _print(payload)
                return 0 if payload["ok"] else 1
            if args.check:
                payload = _dashboard_check(
                    source_root=source_root,
                    dream_studio_home=home,
                    host=args.host,
                    port=args.port,
                    timeout_seconds=args.timeout_seconds,
                )
                _print(payload)
                return 0 if payload["ok"] else 1
            return _print(
                _dashboard_status(
                    source_root=source_root,
                    dream_studio_home=home,
                    host=args.host,
                    port=args.port,
                )
            )
        if args.command == "validate":
            return _print(_validate_status(source_root=source_root, dream_studio_home=home))
        if args.command == "modules":
            return _print(module_profiles())
        if args.command in {"adapters", "router"}:
            return _with_conn(
                source_root=source_root,
                dream_studio_home=home,
                callback=lambda conn: adapter_router_status(
                    conn,
                    source_root=source_root,
                    dream_studio_home=home,
                ),
            )
        if args.command == "platform-hardening":
            return _with_conn(
                source_root=source_root,
                dream_studio_home=home,
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
                dream_studio_home=home,
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
                dream_studio_home=home,
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
                dream_studio_home=home,
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
                dream_studio_home=home,
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
                        dream_studio_home=home or _require_home_for_install(args.command),
                        command_dir=args.command_dir,
                        claude_settings_path=args.claude_settings_path,
                        codex_home=args.codex_home,
                    )
                )
            profiles = args.profiles or None
            return _print(
                first_run_setup(
                    source_root=source_root,
                    dream_studio_home=home or _require_home_for_install(args.command),
                    profiles=profiles,
                    rehearsal=bool(args.rehearsal),
                )
            )
        if args.command == "install-command":
            return _print(
                install_global_command_surface(
                    source_root=source_root,
                    dream_studio_home=home or _require_home_for_install(args.command),
                    command_dir=args.command_dir,
                    execute=bool(args.execute),
                )
            )
        if args.command == "acceptance":
            return _print(
                productization_acceptance_report(
                    source_root=source_root,
                    dream_studio_home=home or _require_home_for_install(args.command),
                    profiles=args.profiles or ["core", "analytics_only", "security_only", "full"],
                )
            )
        if args.command == "backup":
            return _print(
                backup_runtime(
                    source_root=source_root,
                    dream_studio_home=home or _require_home_for_install(args.command),
                    backup_dir=args.backup_dir,
                    execute=args.execute,
                )
            )
        if args.command == "restore-check":
            return _print(
                restore_runtime_check(
                    source_root=source_root,
                    dream_studio_home=home or _require_home_for_install(args.command),
                    backup_path=args.backup_path,
                )
            )
        if args.command == "update-check":
            return _print(
                update_runtime_check(
                    source_root=source_root,
                    dream_studio_home=home,
                )
            )
        if args.command == "uninstall-check":
            return _print(
                uninstall_runtime_check(
                    source_root=source_root,
                    dream_studio_home=home,
                )
            )
        if args.command == "migrate-legacy":
            return _print(
                migrate_legacy_install(
                    source_root=source_root,
                    dream_studio_home=home or _require_home_for_install(args.command),
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
                    dream_studio_home=home or _require_home_for_install(args.command),
                    command_dir=args.command_dir,
                    claude_settings_path=args.claude_settings_path,
                    codex_home=args.codex_home,
                    previous_source_root=args.previous_source_root,
                    execute=bool(args.execute),
                )
            )
        if args.command == "rollback-check":
            return _print(rollback_runtime_check(backup_path=args.backup_path))
    except (RuntimeError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    return 1


def _with_conn(*, source_root: Path, dream_studio_home: Path | None, callback: Any) -> int:
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError(
            "Dream Studio SQLite authority is missing. Run rehearsal-install for a rehearsal "
            "home, or install/bootstrap the real runtime through an approved update plan."
        )
    with _connect(paths.sqlite_path) as conn:
        return _print(callback(conn))


def _analytics_ingest(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    payload: dict[str, Any],
    execute: bool,
) -> int:
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError(
            "Dream Studio SQLite authority is missing. Run rehearsal-install for a rehearsal "
            "home, or install/bootstrap the real runtime through an approved update plan."
        )
    with _connect(paths.sqlite_path) as conn:
        return _print(ingest_analytics_payload(conn, payload, execute=execute))


def _dashboard_status(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> dict[str, Any]:
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


def _dashboard_serve(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    host: str,
    port: int,
) -> int:
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
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
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
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
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    return {
        "model_name": "dream_studio_version_status",
        "derived_view": True,
        "primary_authority": False,
        "source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "latest_migration_version": latest_migration_version(),
        "global_command": "ds",
        "version_source": "repo_migrations_and_installed_runtime_model",
    }


def _doctor_status(*, source_root: Path, dream_studio_home: Path | None) -> dict[str, Any]:
    validation = _validate_status(source_root=source_root, dream_studio_home=dream_studio_home)
    return {
        "model_name": "dream_studio_doctor_status",
        "derived_view": True,
        "primary_authority": False,
        "status": "pass" if validation["ready"] else "attention_required",
        "checks": {
            "sqlite_exists": validation["sqlite_exists"],
            "schema_version_known": validation["schema_version"] is not None,
            "module_profiles_valid": not validation["module_profile_errors"],
            "live_db_write_authorized": False,
        },
        "validation": validation,
    }


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
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    profile_errors = validate_module_profiles()
    db_exists = paths.sqlite_path.exists()
    schema_version = None
    if db_exists:
        with _connect(paths.sqlite_path) as conn:
            schema_version = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
    return {
        "model_name": "dream_studio_installed_runtime_validation",
        "derived_view": True,
        "primary_authority": False,
        "source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "sqlite_path": str(paths.sqlite_path),
        "sqlite_exists": db_exists,
        "schema_version": schema_version,
        "latest_migration_version": latest_migration_version(),
        "module_profile_errors": profile_errors,
        "ready": db_exists and not profile_errors,
        "live_db_write_authorized": False,
    }


def _print(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _changed_files_from_args(args: argparse.Namespace) -> list[str]:
    files = list(args.changed_file or [])
    if args.changed_files:
        normalized = str(args.changed_files).replace(";", "\n").replace(",", "\n")
        files.extend(item.strip() for item in normalized.splitlines() if item.strip())
    return sorted({item for item in files if item})


def _require_home_for_install(command: str) -> Path:
    raise RuntimeError(
        f"{command} requires --home for this productization flow unless a live install scope "
        "has been explicitly approved."
    )


if __name__ == "__main__":
    raise SystemExit(main())
