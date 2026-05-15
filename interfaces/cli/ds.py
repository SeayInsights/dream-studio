"""Global Dream Studio command surface.

This CLI is designed to run from outside the repository. It resolves Dream
Studio source/state through explicit arguments or installed runtime config,
never by assuming the caller's current working directory is the repo.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config.sqlite_bootstrap import latest_migration_version  # noqa: E402
from core.event_store.studio_db import _connect  # noqa: E402
from core.installed_runtime import (  # noqa: E402
    adapter_router_status,
    bootstrap_rehearsal_runtime,
    installed_runtime_model,
    resolve_installed_runtime_paths,
)
from core.module_profiles import module_profiles, validate_module_profiles  # noqa: E402
from core.shared_intelligence.contract_atlas import build_contract_atlas  # noqa: E402
from core.shared_intelligence.context_packets import generate_shared_context_packet  # noqa: E402

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
    subcommands.add_parser("dashboard", help="Show dashboard service status")
    subcommands.add_parser("validate", help="Validate installed runtime readiness")
    subcommands.add_parser("contract-atlas", help="Show Contract Atlas summary")
    subcommands.add_parser("adapters", help="Show adapter status")
    subcommands.add_parser("modules", help="Show module profile status")
    subcommands.add_parser("router", help="Show adapter router status")

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
        if args.command == "dashboard":
            return _print(_dashboard_status(source_root=source_root, dream_studio_home=home))
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
        if args.command == "rehearsal-install":
            return _print(
                bootstrap_rehearsal_runtime(
                    source_root=source_root,
                    dream_studio_home=args.rehearsal_home,
                )
            )
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


def _dashboard_status(*, source_root: Path, dream_studio_home: Path | None) -> dict[str, Any]:
    model = installed_runtime_model(source_root=source_root, dream_studio_home=dream_studio_home)
    return {
        "model_name": "dream_studio_dashboard_command_status",
        "derived_view": True,
        "primary_authority": False,
        "dashboard_command_available": True,
        "dashboard_route": "/dashboard",
        "api_routes": ["/api/telemetry/*", "/api/shared-intelligence/*", "/api/v1/hooks/*"],
        "source_root": model["source_build_location"],
        "sqlite_path": model["canonical_sqlite_path"],
        "starts_server": False,
        "empty_state": "Use the local dashboard service when started; this command reports readiness.",
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


if __name__ == "__main__":
    raise SystemExit(main())
