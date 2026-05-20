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
    _doctor_cmd = subcommands.add_parser("doctor", help="Run read-only runtime health checks")
    _doctor_cmd.add_argument("--fix", action="store_true", help="Attempt to fix failing checks")
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

    # spool subcommand group (Slice 3)
    from interfaces.cli.ds_spool import add_spool_subcommand

    add_spool_subcommand(subcommands)

    # workflow subcommand group (Slice 9b)
    from interfaces.cli.ds_workflow import add_workflow_subcommand

    add_workflow_subcommand(subcommands)

    # memory subcommand group (Slice 5d)
    from interfaces.cli.ds_memory import add_memory_subcommand

    add_memory_subcommand(subcommands)

    # project subcommand group (Slice 4 WS3 + Slice 5b)
    project = subcommands.add_parser("project", help="Manage Dream Studio projects")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    project_register = project_sub.add_parser("register", help="Register a new project")
    project_register.add_argument("--name", required=True, help="Project name")
    project_register.add_argument("--description", default="", help="Optional description")
    project_list = project_sub.add_parser("list", help="List registered projects")
    project_list.add_argument(
        "--status", default="active", help="Filter by status (default: active)"
    )
    project_status_cmd = project_sub.add_parser(
        "status", help="Show milestone/work-order summary for a project"
    )
    project_status_cmd.add_argument("project_id", help="Project UUID")
    project_next_cmd = project_sub.add_parser(
        "next", help="Return the first open work order for a project"
    )
    project_next_cmd.add_argument("project_id", help="Project UUID")
    project_set_active = project_sub.add_parser(
        "set-active", help="Set the active project in the database"
    )
    project_set_active.add_argument("project_id", help="Project UUID to activate")
    project_deactivate = project_sub.add_parser("deactivate", help="Deactivate a project")
    project_deactivate.add_argument("project_id", help="Project UUID to deactivate")
    project_start_cmd = project_sub.add_parser(
        "start", help="Activate project and start its next open work order"
    )
    project_start_cmd.add_argument("project_id", help="Project UUID")
    project_start_cmd.add_argument(
        "--planning-root",
        default=None,
        dest="planning_root",
        help="Override .planning/ directory (default: <cwd>/.planning)",
    )
    project_delete = project_sub.add_parser(
        "delete", help="Delete a project and all its dependents"
    )
    project_delete.add_argument("project_id", help="Project UUID to delete")
    project_delete.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Required to confirm deletion of a project with dependents",
    )
    project_state_cmd = project_sub.add_parser(
        "state",
        help="Single-query project state: active project, next WO, gates, brief, tasks, gotchas",
    )
    project_state_cmd.add_argument(
        "--planning-root",
        default=None,
        dest="planning_root",
        help="Override .planning/ directory for gate file checks (default: <cwd>/.planning)",
    )

    # integrate subcommand group
    integrate = subcommands.add_parser(
        "integrate", help="Manage AI tool integrations (detect, install, doctor)"
    )
    integrate_sub = integrate.add_subparsers(dest="integrate_command", required=True)

    integrate_sub.add_parser("detect", help="List detected AI tools and their config roots")
    integrate_sub.add_parser("status", help="One-line integration health summary per tool")

    integrate_doctor = integrate_sub.add_parser(
        "doctor", help="Full health report for a specific tool"
    )
    integrate_doctor.add_argument("tool", nargs="?", default="claude_code")

    integrate_plan = integrate_sub.add_parser(
        "plan", help="Print the dry-run file operation plan for a tool"
    )
    integrate_plan.add_argument("tool", choices=["claude_code"])
    integrate_plan.add_argument("--scope", choices=["user", "project"], default=None)

    integrate_install = integrate_sub.add_parser(
        "install", help="Install integration for a tool (requires --dry-run or --execute)"
    )
    integrate_install.add_argument("tool", choices=["claude_code"])
    integrate_install.add_argument("--scope", choices=["user", "project"], default=None)
    install_mode_group = integrate_install.add_mutually_exclusive_group()
    install_mode_group.add_argument(
        "--dry-run", action="store_true", default=False, help="Simulate; writes nothing"
    )
    install_mode_group.add_argument(
        "--execute", action="store_true", default=False, help="Write files"
    )

    # skill subcommand group (Slice 6c)
    skill = subcommands.add_parser("skill", help="Invoke or list Dream Studio skills")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)
    skill_invoke = skill_sub.add_parser("invoke", help="Invoke a skill (pack:mode format)")
    skill_invoke.add_argument(
        "specifier", help="Skill specifier in pack:mode format (e.g., core:build)"
    )
    skill_invoke.add_argument("--target", default=None, help="Target path or file")
    _invoke_ctx = skill_invoke.add_mutually_exclusive_group()
    _invoke_ctx.add_argument(
        "--work-order",
        default=None,
        dest="work_order_id",
        help="Work order UUID (sets pipeline mode)",
    )
    _invoke_ctx.add_argument(
        "--milestone",
        default=None,
        dest="milestone_id",
        help="Milestone UUID (writes to milestones dir)",
    )
    skill_invoke.add_argument("--project", default=None, dest="project_id", help="Project UUID")
    skill_invoke.add_argument(
        "--planning-root",
        default=None,
        dest="planning_root",
        help="Override .planning/ directory for gate artifact writes",
    )
    skill_list_cmd = skill_sub.add_parser("list", help="List available skills")
    skill_list_cmd.add_argument("--pack", default=None, help="Filter by pack name")

    # work-order subcommand group (Slice 6a)
    work_order = subcommands.add_parser("work-order", help="Manage work orders")
    work_order_sub = work_order.add_subparsers(dest="work_order_command", required=True)
    wo_start = work_order_sub.add_parser("start", help="Start a work order and write context")
    wo_start.add_argument("work_order_id", help="Work order UUID")
    wo_start.add_argument(
        "--planning-root",
        default=None,
        help="Override .planning/ directory (default: <cwd>/.planning)",
    )
    wo_list = work_order_sub.add_parser("list", help="List work orders")
    wo_list.add_argument("--project", default=None, dest="project_id", help="Filter by project_id")
    wo_list.add_argument("--status", default=None, dest="status_filter", help="Filter by status")
    wo_close = work_order_sub.add_parser("close", help="Close a work order (gate-checked)")
    wo_close.add_argument("work_order_id", help="Work order UUID")
    wo_close.add_argument(
        "--force", action="store_true", default=False, help="Bypass gate failures"
    )
    wo_close.add_argument(
        "--planning-root",
        default=None,
        help="Override .planning/ directory (default: <cwd>/.planning)",
    )
    wo_block = work_order_sub.add_parser("block", help="Block a work order with a reason")
    wo_block.add_argument("work_order_id", help="Work order UUID")
    wo_block.add_argument("--reason", required=True, help="Block reason")
    wo_unblock = work_order_sub.add_parser(
        "unblock", help="Unblock a work order (restore to in_progress)"
    )
    wo_unblock.add_argument("work_order_id", help="Work order UUID")
    wo_task_done = work_order_sub.add_parser(
        "task-done", help="Mark a task complete and update context.md"
    )
    wo_task_done.add_argument("work_order_id", help="Work order UUID")
    wo_task_done.add_argument("task_id", help="Task UUID")
    wo_task_done.add_argument(
        "--planning-root",
        default=None,
        help="Override .planning/ directory (default: <cwd>/.planning)",
    )
    wo_tasks = work_order_sub.add_parser("tasks", help="List tasks for a work order")
    wo_tasks.add_argument("work_order_id", help="Work order UUID")
    wo_add_tasks = work_order_sub.add_parser(
        "add-tasks", help="Parse a tasks.md file and insert tasks into ds_tasks"
    )
    wo_add_tasks.add_argument("work_order_id", help="Work order UUID")
    wo_add_tasks.add_argument(
        "--from-file",
        required=True,
        dest="tasks_file",
        help="Path to a tasks.md file with a numbered list of tasks",
    )

    # design-brief subcommand group (Slice 7a)
    design_brief_cmd = subcommands.add_parser("design-brief", help="Manage project design briefs")
    db_sub = design_brief_cmd.add_subparsers(dest="design_brief_command", required=True)
    db_show = db_sub.add_parser("show", help="Show design brief for a project")
    db_show.add_argument("project_id", help="Project UUID")
    db_create = db_sub.add_parser("create", help="Create a draft design brief for a project")
    db_create.add_argument("project_id", help="Project UUID")
    db_lock = db_sub.add_parser("lock", help="Lock a design brief (human approval gate)")
    db_lock.add_argument("brief_id", help="Brief UUID")
    db_update = db_sub.add_parser("update", help="Update a field on a draft design brief")
    db_update.add_argument("brief_id", help="Brief UUID")
    db_update.add_argument("--field", required=True, help="Field to update")
    db_update.add_argument("--value", required=True, help="New value")
    db_set_system = db_sub.add_parser("set-system", help="Set the design system for a brief")
    db_set_system.add_argument("brief_id", help="Brief UUID")
    db_set_system.add_argument("system_name", help="Design system name")

    # milestone subcommand group (Slice 7e)
    milestone_cmd = subcommands.add_parser("milestone", help="Manage project milestones")
    ms_sub = milestone_cmd.add_subparsers(dest="milestone_command", required=True)
    ms_close = ms_sub.add_parser("close", help="Close a milestone (runs verification sequence)")
    ms_close.add_argument("milestone_id", help="Milestone UUID")
    ms_close.add_argument(
        "--force", action="store_true", default=False, help="Bypass gate failures"
    )
    ms_close.add_argument("--planning-root", default=None, help="Override .planning/ directory")
    ms_list = ms_sub.add_parser("list", help="List milestones for a project")
    ms_list.add_argument("project_id", help="Project UUID")
    ms_status = ms_sub.add_parser("status", help="Show milestone detail and open gate checks")
    ms_status.add_argument("milestone_id", help="Milestone UUID")
    ms_status.add_argument("--planning-root", default=None, help="Override .planning/ directory")

    args = parser.parse_args(argv)
    source_root = Path(args.source_root).resolve() if args.source_root else REPO_ROOT
    home = Path(args.home).resolve() if args.home else None

    try:
        if args.command == "status":
            return _print(installed_runtime_model(source_root=source_root, dream_studio_home=home))
        if args.command == "version":
            return _print(_version_status(source_root=source_root, dream_studio_home=home))
        if args.command == "doctor":
            return _print(
                _doctor_status(
                    source_root=source_root,
                    dream_studio_home=home,
                    fix=getattr(args, "fix", False),
                )
            )
        if args.command == "update":
            return _update_command(
                source_root=source_root,
                dream_studio_home=home,
                dry_run=getattr(args, "dry_run", False),
            )
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
        if args.command == "project":
            return _project_dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "memory":
            if hasattr(args, "func"):
                return args.func(args)
            print("Usage: ds memory <subcommand>", file=sys.stderr)
            return 1
        if args.command == "spool":
            if hasattr(args, "func"):
                return args.func(args)
            print("Usage: ds spool <subcommand>", file=sys.stderr)
            return 1
        if args.command == "workflow":
            if hasattr(args, "func"):
                return args.func(args)
            print("Usage: ds workflow <subcommand>", file=sys.stderr)
            return 1
        if args.command == "integrate":
            return _integrate_dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "skill":
            return _skill_dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "work-order":
            return _work_order_dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "design-brief":
            return _design_brief_dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "milestone":
            return _milestone_dispatch(args, source_root=source_root, dream_studio_home=home)
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
    validation = _validate_status(source_root=source_root, dream_studio_home=dream_studio_home)
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    claude_dir = Path.home() / ".claude"

    dispatcher_ok = _check_dispatcher_hooks(claude_dir)
    skills_info = _check_skills_installed(claude_dir, source_root=source_root)
    agents_info = _check_agents_installed(claude_dir, source_root)
    failed_info = _check_failed_events(paths.dream_studio_home)
    version_info = _check_version_current(source_root, paths.dream_studio_home)

    core_pass = validation["ready"]
    critical_fail = (
        not dispatcher_ok
        or skills_info["missing"]
        or failed_info["count"] >= 6
        or not version_info["current"]
    )
    has_warnings = 0 < failed_info["count"] < 6

    if critical_fail:
        overall = "fail"
    elif not core_pass:
        overall = "attention_required"
    elif has_warnings:
        overall = "warn"
    else:
        overall = "pass"

    fix_actions: list[str] = []
    if fix:
        if not dispatcher_ok or skills_info["missing"] or agents_info["missing"]:
            try:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "interfaces.cli.ds",
                        "integrate",
                        "install",
                        "claude_code",
                        "--execute",
                    ],
                    check=False,
                )
                fix_actions.append("install: ran integrate install claude_code --execute")
            except Exception as exc:
                fix_actions.append(f"install: failed — {exc}")
        if failed_info["count"] > 0:
            try:
                spool_events_root = paths.dream_studio_home / "events"
                failed_dir = spool_events_root / "failed"
                spool_dir = spool_events_root / "spool"
                spool_dir.mkdir(parents=True, exist_ok=True)
                requeued = 0
                for event_file in list(failed_dir.glob("*.json")):
                    try:
                        os.replace(str(event_file), str(spool_dir / event_file.name))
                        requeued += 1
                    except OSError:
                        pass
                fix_actions.append(f"requeue: moved {requeued} failed event(s) back to spool/")
            except Exception as exc:
                fix_actions.append(f"requeue: failed — {exc}")
            try:
                subprocess.run(
                    [sys.executable, "-m", "interfaces.cli.ds", "spool", "ingest"],
                    check=False,
                )
                fix_actions.append("spool ingest: ran spool ingest to process requeued events")
            except Exception as exc:
                fix_actions.append(f"spool ingest: failed — {exc}")
        if not version_info["current"]:
            try:
                subprocess.run(
                    [sys.executable, "-m", "interfaces.cli.ds", "update"],
                    check=False,
                )
                fix_actions.append("update: ran ds update")
            except Exception as exc:
                fix_actions.append(f"update: failed — {exc}")

    result: dict[str, Any] = {
        "model_name": "dream_studio_doctor_status",
        "derived_view": True,
        "primary_authority": False,
        "status": overall,
        "checks": {
            "sqlite_exists": validation["sqlite_exists"],
            "schema_version_known": validation["schema_version"] is not None,
            "module_profiles_valid": not validation["module_profile_errors"],
            "doctor_runs_read_only": True,
            "dispatcher_hooks_installed": dispatcher_ok,
            "skills_installed": skills_info,
            "agents_installed": agents_info,
            "failed_events": failed_info,
            "version_current": version_info,
        },
        "validation": validation,
    }
    if fix:
        result["fix_actions"] = fix_actions
    return result


def _update_command(
    *, source_root: Path, dream_studio_home: Path | None, dry_run: bool = False
) -> int:
    """Implement ds update [--dry-run]."""
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

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "interfaces.cli.ds",
            "integrate",
            "install",
            "claude_code",
            "--execute",
        ],
        capture_output=True,
        text=True,
    )
    install_output = result.stdout.strip() if result.stdout else ""

    if result.returncode == 0:
        installed_file.parent.mkdir(parents=True, exist_ok=True)
        installed_file.write_text(repo_version + "\n", encoding="utf-8")

    _print(
        {
            "ok": result.returncode == 0,
            "status": "updated" if result.returncode == 0 else "install_failed",
            "from": installed_version,
            "to": repo_version,
            "changes": install_output,
        }
    )
    return result.returncode


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
        "doctor_runs_read_only": True,
    }


def _project_dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    if args.project_command == "register":
        return _project_register(
            name=args.name,
            description=args.description,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "list":
        return _project_list(
            status_filter=args.status,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "status":
        return _project_status(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "next":
        return _project_next(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "set-active":
        return _project_set_active(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "deactivate":
        return _project_deactivate(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "delete":
        return _project_delete(
            project_id=args.project_id,
            confirm=args.confirm,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "start":
        planning_root = Path(args.planning_root).resolve() if args.planning_root else None
        return _project_start(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            planning_root=planning_root,
        )
    if args.project_command == "state":
        planning_root = Path(args.planning_root).resolve() if args.planning_root else None
        return _project_state(
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            planning_root=planning_root,
        )
    print(f"Unknown project command: {args.project_command}", file=sys.stderr)
    return 1


def _project_register(
    *,
    name: str,
    description: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    import uuid
    from datetime import datetime, timezone

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    project_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with _connect(paths.sqlite_path) as conn:
        conn.execute(
            "INSERT INTO ds_projects (project_id, name, description, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'active', ?, ?)",
            (project_id, name, description, now, now),
        )
        conn.commit()

    result = {
        "ok": True,
        "project_id": project_id,
        "name": name,
        "description": description,
        "status": "active",
        "created_at": now,
        "hint": f"To make this the active project, run: ds project set-active {project_id}",
    }
    print(json.dumps(result, indent=2))
    return 0


def _project_list(
    *,
    status_filter: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    with _connect(paths.sqlite_path) as conn:
        rows = conn.execute(
            "SELECT project_id, name, description, status, created_at FROM ds_projects"
            " WHERE status = ? ORDER BY created_at DESC",
            (status_filter,),
        ).fetchall()

    projects = [
        {
            "project_id": r[0],
            "name": r[1],
            "description": r[2],
            "status": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]
    print(json.dumps({"ok": True, "projects": projects}, indent=2))
    return 0


def _project_status(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    with _connect(paths.sqlite_path) as conn:
        proj = conn.execute(
            "SELECT project_id, name, status FROM ds_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if proj is None:
            print(json.dumps({"ok": False, "error": f"Project not found: {project_id}"}))
            return 1
        milestone_count = conn.execute(
            "SELECT COUNT(*) FROM ds_milestones WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
        work_order_count = conn.execute(
            "SELECT COUNT(*) FROM ds_work_orders WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
        open_work_order_count = conn.execute(
            "SELECT COUNT(*) FROM ds_work_orders WHERE project_id = ? AND status = 'open'",
            (project_id,),
        ).fetchone()[0]

    result = {
        "ok": True,
        "project_id": proj[0],
        "name": proj[1],
        "status": proj[2],
        "milestone_count": milestone_count,
        "work_order_count": work_order_count,
        "open_work_order_count": open_work_order_count,
    }
    print(json.dumps(result, indent=2))
    return 0


def _project_next(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    with _connect(paths.sqlite_path) as conn:
        # Resume any in_progress WO in the lowest-order incomplete milestone first.
        row = conn.execute(
            "SELECT wo.work_order_id, wo.title, wo.work_order_type, m.title AS milestone_title"
            " FROM ds_work_orders wo"
            " LEFT JOIN ds_milestones m ON wo.milestone_id = m.milestone_id"
            " WHERE wo.project_id = ? AND wo.status = 'in_progress'"
            " ORDER BY m.order_index ASC, wo.created_at ASC LIMIT 1",
            (project_id,),
        ).fetchone()

        if row is None:
            # No in_progress WOs — find the first open WO in the lowest incomplete milestone.
            row = conn.execute(
                "SELECT wo.work_order_id, wo.title, wo.work_order_type, m.title AS milestone_title"
                " FROM ds_work_orders wo"
                " LEFT JOIN ds_milestones m ON wo.milestone_id = m.milestone_id"
                " WHERE wo.project_id = ? AND wo.status = 'open'"
                " AND m.order_index = ("
                "   SELECT MIN(m2.order_index)"
                "   FROM ds_work_orders wo2"
                "   LEFT JOIN ds_milestones m2 ON wo2.milestone_id = m2.milestone_id"
                "   WHERE wo2.project_id = ? AND wo2.status IN ('open', 'in_progress')"
                " )"
                " ORDER BY wo.created_at ASC LIMIT 1",
                (project_id, project_id),
            ).fetchone()

    if row is None:
        print(json.dumps({"ok": True, "work_order": None, "message": "No open work orders"}))
        return 0

    wo_id = row[0]
    result = {
        "ok": True,
        "work_order": {
            "work_order_id": wo_id,
            "title": row[1],
            "work_order_type": row[2],
            "milestone": row[3] or "",
            "next_command": f"ds work-order start {wo_id}",
        },
    }
    print(json.dumps(result, indent=2))
    return 0


def _project_set_active(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from datetime import datetime, timezone

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    now = datetime.now(timezone.utc).isoformat()
    with _connect(paths.sqlite_path) as conn:
        row = conn.execute(
            "SELECT project_id FROM ds_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        if row is None:
            print(json.dumps({"ok": False, "error": f"Project not found: {project_id}"}))
            return 1
        conn.execute(
            "UPDATE ds_projects SET status = 'paused', updated_at = ? WHERE status = 'active'",
            (now,),
        )
        conn.execute(
            "UPDATE ds_projects SET status = 'active', updated_at = ? WHERE project_id = ?",
            (now, project_id),
        )
        conn.commit()

    print(json.dumps({"ok": True, "project_id": project_id, "status": "active"}))
    return 0


def _project_deactivate(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from datetime import datetime, timezone

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    now = datetime.now(timezone.utc).isoformat()
    with _connect(paths.sqlite_path) as conn:
        row = conn.execute(
            "SELECT project_id FROM ds_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        if row is None:
            print(json.dumps({"ok": False, "error": f"Project not found: {project_id}"}))
            return 1
        conn.execute(
            "UPDATE ds_projects SET status = 'paused', updated_at = ? WHERE project_id = ?",
            (now, project_id),
        )
        conn.commit()

    print(json.dumps({"ok": True, "project_id": project_id, "status": "paused"}))
    return 0


def _project_start(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    """Activate project and auto-start its next open work order."""
    from datetime import datetime, timezone

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    now = datetime.now(timezone.utc).isoformat()
    with _connect(paths.sqlite_path) as conn:
        proj_row = conn.execute(
            "SELECT name FROM ds_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        if proj_row is None:
            print(json.dumps({"ok": False, "error": f"Project not found: {project_id}"}))
            return 1
        project_name = proj_row[0]

        # Set project active
        conn.execute(
            "UPDATE ds_projects SET status = 'paused', updated_at = ? WHERE status = 'active'",
            (now,),
        )
        conn.execute(
            "UPDATE ds_projects SET status = 'active', updated_at = ? WHERE project_id = ?",
            (now, project_id),
        )
        conn.commit()

        # Find next open work order
        wo_row = conn.execute(
            "SELECT wo.work_order_id, wo.title, wo.work_order_type, m.title AS milestone_title"
            " FROM ds_work_orders wo"
            " LEFT JOIN ds_milestones m ON wo.milestone_id = m.milestone_id"
            " WHERE wo.project_id = ? AND wo.status = 'open'"
            " ORDER BY wo.created_at ASC LIMIT 1",
            (project_id,),
        ).fetchone()

        if wo_row is None:
            print(
                f"Project activated: {project_name}\n"
                "No open work orders found.\n"
                f"Run `ds project next {project_id}` to check status."
            )
            return 0

        wo_id, wo_title, wo_type, milestone_title = wo_row

    # Start the work order
    rc = _work_order_start(
        work_order_id=wo_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )

    if rc != 0:
        return rc

    # Count tasks
    p_root = planning_root or Path.cwd() / ".planning"
    context_path = p_root / "work-orders" / wo_id / "context.md"
    task_count = 0
    if context_path.exists():
        content = context_path.read_text(encoding="utf-8")
        task_count = content.count("- [ ]")

    milestone_str = milestone_title or "—"
    type_str = wo_type or "—"
    tasks_str = f"{task_count} tasks queued" if task_count else "tasks queued"

    print(
        f"\nProject activated: {project_name}\n"
        f"Starting: {wo_title}\n"
        f"Type: {type_str} | Milestone: {milestone_str}\n"
        f"\nContext loaded: {context_path}\n"
        f"Tasks ready: {tasks_str}\n"
        f"\nRun `ds work-order close {wo_id}` when done."
    )
    return 0


def _project_delete(
    *,
    project_id: str,
    confirm: bool,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    with _connect(paths.sqlite_path) as conn:
        row = conn.execute(
            "SELECT project_id FROM ds_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        if row is None:
            print(json.dumps({"ok": False, "error": f"Project not found: {project_id}"}))
            return 1

        wo_count = conn.execute(
            "SELECT COUNT(*) FROM ds_work_orders WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
        ms_count = conn.execute(
            "SELECT COUNT(*) FROM ds_milestones WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
        task_count = conn.execute(
            "SELECT COUNT(*) FROM ds_tasks WHERE project_id = ?", (project_id,)
        ).fetchone()[0]

        has_dependents = wo_count > 0 or ms_count > 0 or task_count > 0
        if has_dependents and not confirm:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": (
                            f"Project {project_id} has dependents "
                            f"({task_count} tasks, {wo_count} work orders, {ms_count} milestones). "
                            "Pass --confirm to cascade delete."
                        ),
                        "work_order_count": wo_count,
                        "milestone_count": ms_count,
                        "task_count": task_count,
                    }
                )
            )
            return 1

        # Cascade: tasks → work_orders → milestones → design_briefs → projects
        conn.execute("DELETE FROM ds_tasks WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM ds_work_orders WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM ds_milestones WHERE project_id = ?", (project_id,))
        try:
            conn.execute("DELETE FROM ds_design_briefs WHERE project_id = ?", (project_id,))
        except Exception:
            pass  # Table may not exist in all schema versions.
        conn.execute("DELETE FROM ds_projects WHERE project_id = ?", (project_id,))
        conn.commit()

    print(
        json.dumps(
            {
                "ok": True,
                "project_id": project_id,
                "deleted": {
                    "tasks": task_count,
                    "work_orders": wo_count,
                    "milestones": ms_count,
                },
            }
        )
    )
    return 0


def _project_state(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    """Single-call project state: active project + next WO + gates + brief + tasks + gotchas."""
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    p_root = planning_root or Path.cwd() / ".planning"

    with _connect(paths.sqlite_path) as conn:
        projects_raw = conn.execute(
            "SELECT project_id, name, status FROM ds_projects WHERE status = 'active'"
            " ORDER BY updated_at DESC"
        ).fetchall()

        if not projects_raw:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "projects": [],
                        "next_action": "No active projects. Run `ds-project scope` to scope a new one.",
                    }
                )
            )
            return 0

        result_projects = []
        for proj in projects_raw:
            pid = proj["project_id"]

            # Next open/in_progress WO in lowest-order milestone.
            wo_row = conn.execute(
                "SELECT wo.work_order_id, wo.title, wo.status, wo.work_order_type,"
                " m.milestone_id, m.title AS milestone_title, m.order_index,"
                " wot.label, wot.pre_build_gate, wot.build_executor, wot.post_build_gate,"
                " wot.workflow_template, wot.precondition_skill, wot.task_generator,"
                " (SELECT COUNT(*) FROM ds_tasks t"
                "  WHERE t.work_order_id = wo.work_order_id AND t.status = 'pending') AS pending_tasks,"
                " (SELECT COUNT(*) FROM ds_tasks t"
                "  WHERE t.work_order_id = wo.work_order_id) AS total_tasks"
                " FROM ds_work_orders wo"
                " LEFT JOIN ds_milestones m ON wo.milestone_id = m.milestone_id"
                " LEFT JOIN ds_work_order_types wot ON wot.type_id = wo.work_order_type"
                " WHERE wo.project_id = ? AND wo.status IN ('open', 'in_progress')"
                " ORDER BY m.order_index ASC, wo.created_at ASC LIMIT 1",
                (pid,),
            ).fetchone()

            # Design brief (most recent for this project).
            brief_row = None
            try:
                brief_row = conn.execute(
                    "SELECT brief_id, status, purpose, audience, tone, design_system,"
                    " font_pairing, brand_tokens FROM ds_design_briefs"
                    " WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                    (pid,),
                ).fetchone()
            except Exception:
                pass

            brief_info: dict[str, Any] | None = None
            if brief_row:
                fields = [
                    "purpose",
                    "audience",
                    "tone",
                    "design_system",
                    "font_pairing",
                    "brand_tokens",
                ]
                filled = sum(1 for f in fields if brief_row[f])
                brief_info = {
                    "brief_id": brief_row["brief_id"],
                    "status": brief_row["status"],
                    "fields_filled": filled,
                    "fields_total": len(fields),
                }

            wo_info: dict[str, Any] | None = None
            next_action = "No open work orders. All milestones may be complete."

            if wo_row:
                wo_type = wo_row["work_order_type"]
                build_exec = wo_row["build_executor"]
                pre_gate = wo_row["pre_build_gate"]
                precondition_skill = wo_row["precondition_skill"]
                workflow_template = wo_row["workflow_template"]
                task_generator = wo_row["task_generator"] or "ds-core:plan"

                # Gate check using the same logic as work-order close.
                gate_satisfied = True
                if pre_gate:
                    gate_passed, _ = _run_gate_check(
                        pre_gate,
                        planning_root=p_root,
                        work_order_id=wo_row["work_order_id"],
                        project_id=pid,
                        conn=conn,
                    )
                    gate_satisfied = gate_passed

                # Gotchas relevant to this WO type / executor.
                gotcha_rows: list[Any] = []
                try:
                    gotcha_rows = conn.execute(
                        "SELECT severity, title, fix FROM reg_gotchas"
                        " WHERE skill_id = ? OR skill_id LIKE ?"
                        " ORDER BY times_hit DESC, discovered DESC LIMIT 3",
                        (build_exec or "", f"{wo_type}%" if wo_type else ""),
                    ).fetchall()
                except Exception:
                    pass

                gotchas = [
                    {"severity": g["severity"], "title": g["title"], "fix": g["fix"]}
                    for g in gotcha_rows
                ]

                # Compute next_action.
                if not gate_satisfied and pre_gate:
                    skill_hint = precondition_skill or "ds-project:brief"
                    next_action = (
                        f"Gate `{pre_gate}` is not satisfied. "
                        f"Invoke `{skill_hint}` to resolve it."
                    )
                elif wo_row["total_tasks"] == 0:
                    next_action = (
                        f"No tasks defined for this work order. "
                        f"Invoke `{task_generator}` to decompose tasks, "
                        f"then `ds work-order start {wo_row['work_order_id']}`."
                    )
                elif wo_row["status"] == "open":
                    next_action = f"Run: ds work-order start {wo_row['work_order_id']}"
                    if workflow_template:
                        next_action += (
                            f"\nWorkflow: `{workflow_template}`. "
                            f"First node: `think`. Invoke `ds-core:think` to begin."
                        )
                else:
                    next_action = (
                        f"Work order in progress. Complete remaining tasks, "
                        f"then: ds work-order close {wo_row['work_order_id']}"
                    )

                wo_info = {
                    "work_order_id": wo_row["work_order_id"],
                    "title": wo_row["title"],
                    "status": wo_row["status"],
                    "type": wo_type,
                    "type_label": wo_row["label"],
                    "workflow_template": workflow_template,
                    "pending_tasks": wo_row["pending_tasks"],
                    "total_tasks": wo_row["total_tasks"],
                    "gates": {
                        "pre_build": pre_gate,
                        "pre_build_satisfied": gate_satisfied,
                        "precondition_skill": precondition_skill,
                        "build_executor": build_exec,
                        "post_build": wo_row["post_build_gate"],
                    },
                    "design_brief": brief_info,
                    "milestone": {
                        "milestone_id": wo_row["milestone_id"],
                        "title": wo_row["milestone_title"],
                        "order_index": wo_row["order_index"],
                    },
                    "gotchas": gotchas,
                }

            result_projects.append(
                {
                    "project_id": pid,
                    "name": proj["name"],
                    "status": proj["status"],
                    "next_work_order": wo_info,
                    "next_action": next_action,
                }
            )

        print(json.dumps({"ok": True, "projects": result_projects}, indent=2))
    return 0


def _integrate_dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from integrations.detector import detect_all, detect_claude_code
    from integrations.health import doctor
    from integrations.installer.base import RefusalError
    from integrations.installer.claude_code import ClaudeCodeInstaller
    from integrations.manifest import get_ds_home

    canonical_root = source_root / "canonical"
    ds_home = dream_studio_home or get_ds_home()

    if args.integrate_command == "detect":
        tools = detect_all()
        return _print(
            {
                "model_name": "dream_studio_integrate_detect",
                "derived_view": True,
                "primary_authority": False,
                "tools": [
                    {"tool_id": t.tool_id, "scope": t.scope, "config_root": str(t.config_root)}
                    for t in tools
                ],
            }
        )

    if args.integrate_command == "status":
        tools = detect_all()
        statuses: list[dict[str, Any]] = []
        for t in tools:
            result = doctor(
                t.tool_id,
                t.config_root,
                ds_home=ds_home,
                canonical_root=canonical_root,
            )
            statuses.append(
                {
                    "tool_id": t.tool_id,
                    "scope": t.scope,
                    "state": result["state"],
                }
            )
        return _print(
            {
                "model_name": "dream_studio_integrate_status",
                "derived_view": True,
                "primary_authority": False,
                "tools": statuses,
            }
        )

    if args.integrate_command == "doctor":
        tool_id = getattr(args, "tool", "claude_code")
        scope = getattr(args, "scope", None)
        detected = detect_claude_code(scope_override=scope)
        result = doctor(
            detected.tool_id,
            detected.config_root,
            ds_home=ds_home,
            canonical_root=canonical_root,
        )
        return _print(
            {
                "model_name": "dream_studio_integrate_doctor",
                "derived_view": True,
                "primary_authority": False,
                **result,
            }
        )

    if args.integrate_command == "plan":
        scope = getattr(args, "scope", None)
        detected = detect_claude_code(scope_override=scope)
        installer = ClaudeCodeInstaller(
            detected.config_root,
            detected.scope,
            canonical_root=canonical_root,
            ds_home=ds_home,
        )
        plan = installer.plan()
        return _print(
            {
                "model_name": "dream_studio_integrate_plan",
                "derived_view": True,
                "primary_authority": False,
                "tool": "claude_code",
                "scope": detected.scope,
                "config_root": str(detected.config_root),
                "plan": plan.summary(),
            }
        )

    if args.integrate_command == "install":
        scope = getattr(args, "scope", None)
        dry_run = getattr(args, "dry_run", False)
        execute = getattr(args, "execute", False)

        if not dry_run and not execute:
            raise RefusalError(
                "ds integrate install requires --dry-run or --execute. "
                "Use --dry-run to simulate, --execute to write files."
            )

        mode = "dry_run" if dry_run else "execute"
        detected = detect_claude_code(scope_override=scope)
        installer = ClaudeCodeInstaller(
            detected.config_root,
            detected.scope,
            canonical_root=canonical_root,
            ds_home=ds_home,
        )
        result = installer.install(mode)
        return _print(
            {
                "model_name": "dream_studio_integrate_install",
                "derived_view": True,
                "primary_authority": False,
                **result,
            }
        )

    raise RuntimeError(f"Unknown integrate subcommand: {args.integrate_command}")


def _work_order_dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    if args.work_order_command == "start":
        planning_root = Path(args.planning_root).resolve() if args.planning_root else None
        return _work_order_start(
            work_order_id=args.work_order_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            planning_root=planning_root,
        )
    if args.work_order_command == "list":
        return _work_order_list(
            project_id=args.project_id,
            status_filter=args.status_filter,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "close":
        planning_root = Path(args.planning_root).resolve() if args.planning_root else None
        return _work_order_close(
            work_order_id=args.work_order_id,
            force=args.force,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            planning_root=planning_root,
        )
    if args.work_order_command == "block":
        return _work_order_block(
            work_order_id=args.work_order_id,
            reason=args.reason,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "unblock":
        return _work_order_unblock(
            work_order_id=args.work_order_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "task-done":
        planning_root = Path(args.planning_root).resolve() if args.planning_root else None
        return _work_order_task_done(
            work_order_id=args.work_order_id,
            task_id=args.task_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
            planning_root=planning_root,
        )
    if args.work_order_command == "tasks":
        return _work_order_tasks(
            work_order_id=args.work_order_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "add-tasks":
        return _work_order_add_tasks(
            work_order_id=args.work_order_id,
            tasks_file=Path(args.tasks_file),
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    print(f"Unknown work-order command: {args.work_order_command}", file=sys.stderr)
    return 1


def _work_order_start(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    import uuid as _uuid
    from datetime import datetime, timezone

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    with _connect(paths.sqlite_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title, status, work_order_type, milestone_id, project_id"
            " FROM ds_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            print(json.dumps({"ok": False, "error": f"Work order not found: {work_order_id}"}))
            return 1

        wo_id, title, wo_status, wo_type, milestone_id, project_id = wo_row

        if not wo_type:
            print(json.dumps({"ok": False, "error": "Work order has no type assigned"}))
            return 1

        type_row = conn.execute(
            "SELECT type_id, label, pre_build_gate, build_executor, post_build_gate,"
            " workflow_template, precondition_skill"
            " FROM ds_work_order_types WHERE type_id = ?",
            (wo_type,),
        ).fetchone()
        if type_row is None:
            print(json.dumps({"ok": False, "error": f"Unrecognized work order type: {wo_type}"}))
            return 1

        type_id, label, pre_gate, build_exec, post_gate, workflow_template, precondition_skill = (
            type_row
        )

        milestone_title = None
        if milestone_id:
            ms_row = conn.execute(
                "SELECT title FROM ds_milestones WHERE milestone_id = ?", (milestone_id,)
            ).fetchone()
            milestone_title = ms_row[0] if ms_row else None

        proj_row = conn.execute(
            "SELECT name FROM ds_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        project_name = proj_row[0] if proj_row else project_id

        open_tasks = conn.execute(
            "SELECT title FROM ds_tasks"
            " WHERE work_order_id = ? AND status = 'pending' ORDER BY created_at ASC",
            (work_order_id,),
        ).fetchall()

        _UI_WO_TYPES = frozenset(["ui_component", "ui_page"])
        brief_locked = None
        brief_warning = False
        if type_id in _UI_WO_TYPES and project_id:
            try:
                b_row = conn.execute(
                    "SELECT brief_id, purpose, audience, tone, design_system,"
                    " font_pairing, brand_tokens, status"
                    " FROM ds_design_briefs"
                    " WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                    (project_id,),
                ).fetchone()
                if b_row and b_row[7] == "locked":
                    brief_locked = {
                        "brief_id": b_row[0],
                        "purpose": b_row[1],
                        "audience": b_row[2],
                        "tone": b_row[3],
                        "design_system": b_row[4],
                        "font_pairing": b_row[5],
                        "brand_tokens": b_row[6],
                    }
                else:
                    brief_warning = True
            except sqlite3.OperationalError:
                brief_warning = True

        now = datetime.now(timezone.utc).isoformat()

        marker_project_id = None
        try:
            from emitters.claude_code.project import read_project_id

            marker_project_id = read_project_id(source_root)
        except Exception:
            pass

        if brief_warning:
            print(
                "WARNING: No locked design brief found. It is strongly recommended to run "
                "website:discover before building UI. Continue anyway? [y/N]",
                file=sys.stderr,
            )
            if sys.stdin.isatty():
                answer = sys.stdin.readline().strip().lower()
                if answer not in ("y", "yes"):
                    return 0

        p_root = planning_root or Path.cwd() / ".planning"
        context_dir = p_root / "work-orders" / work_order_id
        context_dir.mkdir(parents=True, exist_ok=True)
        context_path = context_dir / "context.md"

        lines = [
            f"# Work Order: {title}",
            "",
            f"**ID:** `{work_order_id}`",
            f"**Type:** {label} (`{type_id}`)",
            f"**Status:** {wo_status}",
            f"**Project:** {project_name} (`{project_id}`)",
        ]
        if milestone_title:
            lines.append(f"**Milestone:** {milestone_title}")
        if marker_project_id:
            lines.append(f"**Active project (marker):** `{marker_project_id}`")
        lines += [
            "",
            "## Gates",
            "",
            f"- **Pre-build gate:** {pre_gate or '—'}",
            f"- **Build executor:** {build_exec or '—'}",
            f"- **Post-build gate:** {post_gate or '—'}",
        ]
        if workflow_template:
            lines += [
                f"- **Workflow:** {workflow_template} — invoke `ds-core:think` to begin",
            ]
        lines += [
            "",
            "## Open Tasks",
            "",
        ]
        if open_tasks:
            for (task_title,) in open_tasks:
                lines.append(f"- [ ] {task_title}")
        else:
            lines.append("_No pending tasks._")

        if brief_locked:
            lines += ["", "## Design Brief", ""]
            for _lbl, _key in [
                ("Purpose", "purpose"),
                ("Audience", "audience"),
                ("Tone", "tone"),
                ("Font pairing", "font_pairing"),
                ("Brand tokens", "brand_tokens"),
            ]:
                _val = brief_locked.get(_key)
                if _val:
                    lines.append(f"- **{_lbl}:** {_val}")
            if brief_locked.get("design_system"):
                _ds = brief_locked["design_system"]
                lines += [
                    "",
                    "## Design System",
                    "",
                    f"System: {_ds}",
                    f"Reference: canonical/skills/domains/design-systems/{_ds}/",
                    "",
                    "Apply the principles from this design system to all UI output in this"
                    " work order. Do not deviate from the system's token definitions.",
                ]
        elif brief_warning:
            lines += [
                "",
                "> **WARNING:** No locked design brief found."
                " Run `website:discover` before building UI for consistent results.",
            ]

        lines += [
            "",
            "## DREAM STUDIO ENFORCEMENT",
            "",
            "You are operating in Dream Studio managed mode.",
            "This is a hard boundary, not a suggestion.",
            "",
            f"AUTHORIZED scope: {type_id}",
            f"ACTIVE work order: {work_order_id}",
            "AUTHORIZED tasks: listed above under ## Tasks",
            "",
            "RULES:",
            "1. Do not create or modify files outside the authorized scope above.",
            "2. Complete tasks in the order listed.",
            "3. Mark each task done:",
            f"   py -m interfaces.cli.ds work-order task-done {work_order_id} <task_id>",
            "4. When all tasks are complete, run:",
            f"   py -m interfaces.cli.ds work-order close {work_order_id}",
            "5. Do not start work on any other work order until this one is closed.",
            "6. If you encounter something outside your scope that needs to be addressed,",
            "   emit a note and continue. Do not fix it inline.",
            "",
            "Violations of these rules break traceability.",
            "Dream Studio exists to make your work verifiable.",
        ]

        # Inject relevant gotchas from past sessions.
        try:
            gotcha_rows = conn.execute(
                "SELECT severity, title, fix FROM reg_gotchas"
                " WHERE skill_id = ? OR skill_id LIKE ?"
                " ORDER BY times_hit DESC, discovered DESC LIMIT 3",
                (build_exec or "", f"{type_id}%" if type_id else ""),
            ).fetchall()
            if gotcha_rows:
                lines += ["", "## Known Issues (from past sessions)", ""]
                for g_sev, g_title, g_fix in gotcha_rows:
                    lines.append(f"- **[{g_sev}]** {g_title}")
                    if g_fix:
                        lines.append(f"  Fix: {g_fix}")
        except Exception:
            pass

        lines += ["", f"_Generated: {now}_", ""]
        context_path.write_text("\n".join(lines), encoding="utf-8")

        try:
            import spool.writer as _spool_writer

            _spool_writer.write_event(
                {
                    "event_id": str(_uuid.uuid4()),
                    "event_type": "work_order.started",
                    "timestamp": now,
                    "trace": {"work_order_id": work_order_id, "project_id": project_id},
                    "severity": "info",
                    "payload": {
                        "work_order_id": work_order_id,
                        "title": title,
                        "type": type_id,
                        "project_id": project_id,
                    },
                    "source_type": "confirmed",
                }
            )
        except Exception:
            pass

        # Guard: refuse to start a WO if any earlier milestone has incomplete work.
        if milestone_id:
            ms_order_row = conn.execute(
                "SELECT order_index FROM ds_milestones WHERE milestone_id = ?",
                (milestone_id,),
            ).fetchone()
            if ms_order_row is not None:
                blocking_count = conn.execute(
                    "SELECT COUNT(*) FROM ds_work_orders wo"
                    " LEFT JOIN ds_milestones m ON wo.milestone_id = m.milestone_id"
                    " WHERE wo.project_id = ? AND m.order_index < ?"
                    " AND wo.status NOT IN ('complete', 'cancelled')",
                    (project_id, ms_order_row[0]),
                ).fetchone()[0]
                if blocking_count > 0:
                    print(
                        json.dumps(
                            {
                                "ok": False,
                                "error": (
                                    f"Cannot start this work order — {blocking_count} work order(s) in "
                                    f"earlier milestones are incomplete. "
                                    f"Run 'ds project next {project_id}' to see what should be worked on first."
                                ),
                            }
                        )
                    )
                    return 1

        conn.execute(
            "UPDATE ds_work_orders SET status = 'in_progress', updated_at = ?"
            " WHERE work_order_id = ?",
            (now, work_order_id),
        )
        conn.commit()

    start_result: dict[str, Any] = {
        "ok": True,
        "work_order_id": work_order_id,
        "title": title,
        "type": type_id,
        "project_id": project_id,
        "context_path": str(context_path),
    }
    if workflow_template:
        start_result["workflow"] = {
            "template": workflow_template,
            "first_node": "think",
            "invoke": f"workflow: {workflow_template}",
        }
        start_result["next_step"] = (
            f"This work order uses the `{workflow_template}` workflow. "
            f"First node: `think`. Invoke `ds-core:think` to begin."
        )
    print(json.dumps(start_result, indent=2))
    return 0


def _work_order_list(
    *,
    project_id: str | None,
    status_filter: str | None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    conditions: list[str] = []
    params: list[Any] = []
    if project_id:
        conditions.append("wo.project_id = ?")
        params.append(project_id)
    if status_filter:
        conditions.append("wo.status = ?")
        params.append(status_filter)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    query = (
        "SELECT wo.work_order_id, wo.title, wo.work_order_type, wo.status,"
        " m.title AS milestone_title"
        " FROM ds_work_orders wo"
        " LEFT JOIN ds_milestones m ON wo.milestone_id = m.milestone_id"
        f" {where}"
        " ORDER BY wo.created_at ASC"
    )

    with _connect(paths.sqlite_path) as conn:
        rows = conn.execute(query, params).fetchall()

    work_orders = [
        {
            "id": r[0],
            "title": r[1],
            "type": r[2] or "",
            "status": r[3],
            "milestone": r[4] or "",
        }
        for r in rows
    ]
    print(json.dumps({"ok": True, "work_orders": work_orders}, indent=2))
    return 0


_SKILL_SPECIFIER_RE = __import__("re").compile(r"^[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$")
_SKILL_FM_RE = __import__("re").compile(r"^---\s*\n(.*?)\n---", __import__("re").DOTALL)


def _load_packs(source_root: Path) -> dict[str, Any]:
    packs_path = source_root / "packs.yaml"
    if not packs_path.is_file():
        return {}
    try:
        import yaml as _yaml

        return _yaml.safe_load(packs_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _skill_dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    if args.skill_command == "invoke":
        return _skill_invoke(
            specifier=args.specifier,
            target=args.target,
            work_order_id=args.work_order_id,
            milestone_id=args.milestone_id,
            project_id=args.project_id,
            planning_root=Path(args.planning_root) if args.planning_root else None,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.skill_command == "list":
        return _skill_list(
            pack_filter=args.pack,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    print(f"Unknown skill command: {args.skill_command}", file=sys.stderr)
    return 1


def _skill_invoke(
    *,
    specifier: str,
    target: str | None,
    work_order_id: str | None,
    milestone_id: str | None = None,
    project_id: str | None,
    planning_root: Path | None = None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    import uuid as _uuid
    from datetime import datetime, timezone

    _UNKNOWN = f"Unknown skill: {specifier}. Run `ds skill list` to see available skills."

    if not _SKILL_SPECIFIER_RE.match(specifier):
        print(_UNKNOWN, file=sys.stderr)
        return 1

    pack, mode = specifier.split(":", 1)

    packs_data = _load_packs(source_root)
    packs = packs_data.get("packs", {})

    if pack not in packs:
        print(_UNKNOWN, file=sys.stderr)
        return 1

    if mode not in packs[pack].get("modes", []):
        print(_UNKNOWN, file=sys.stderr)
        return 1

    _skill_path_key = packs[pack].get("skill_path")
    if _skill_path_key:
        skill_md = source_root / _skill_path_key / "modes" / mode / "SKILL.md"
    else:
        skill_md = source_root / "canonical" / "skills" / pack / "modes" / mode / "SKILL.md"
    if not skill_md.is_file():
        print(f"Skill content not found for {specifier} (expected {skill_md})", file=sys.stderr)
        return 1

    invocation_mode = "pipeline" if work_order_id else "direct"

    resolved_project_id = project_id
    if resolved_project_id is None and work_order_id is not None:
        try:
            paths = resolve_installed_runtime_paths(
                source_root=source_root,
                dream_studio_home=dream_studio_home,
            )
            if paths.sqlite_path.exists():
                with _connect(paths.sqlite_path) as conn:
                    row = conn.execute(
                        "SELECT project_id FROM ds_work_orders WHERE work_order_id = ?",
                        (work_order_id,),
                    ).fetchone()
                    if row:
                        resolved_project_id = row[0]
        except Exception:
            pass
    if resolved_project_id is None:
        try:
            from emitters.claude_code.project import read_project_id

            resolved_project_id = read_project_id(None)
        except Exception:
            pass

    now = datetime.now(timezone.utc).isoformat()
    skill_id = f"ds-{pack}"

    try:
        import spool.writer as _spool_writer

        _spool_writer.write_event(
            {
                "event_id": str(_uuid.uuid4()),
                "event_type": "skill.invoked",
                "timestamp": now,
                "skill_id": skill_id,
                "mode": mode,
                "invocation_mode": invocation_mode,
                "project_id": resolved_project_id,
                "trace": {
                    "skill_specifier": specifier,
                    "project_id": resolved_project_id,
                },
                "severity": "info",
                "payload": {
                    "skill_specifier": specifier,
                    "target": target,
                    "work_order_id": work_order_id,
                },
                "source_type": "confirmed",
                "schema_version": 1,
            }
        )
    except Exception:
        pass

    skill_content = skill_md.read_text(encoding="utf-8")
    print(skill_content)
    print("---")
    print(f"Skill: {specifier}")
    print(f"Mode: {invocation_mode}")
    print(f"Target: {target or 'not specified'}")
    print(f"Work order: {work_order_id or 'none'}")
    print("Invocation recorded.")
    print()
    print(
        "The AI reading this output has the skill instructions above and should now execute them."
    )

    if work_order_id or milestone_id:
        from datetime import datetime, timezone as _tz

        _date_str = datetime.now(_tz.utc).isoformat()[:10]
        _p_root = planning_root or Path.cwd() / ".planning"
        if milestone_id:
            _wo_dir = _p_root / "milestones" / milestone_id
        else:
            _wo_dir = _p_root / "work-orders" / work_order_id
        _wo_dir.mkdir(parents=True, exist_ok=True)

        if specifier == "website:critique":
            (_wo_dir / "design-critique.md").write_text(
                f"# Design Critique — Work Order {work_order_id}\n"
                f"Date: {_date_str}\n"
                f"Skill: website:critique\n"
                f"Target: {target or 'not specified'}\n\n"
                "## Scores\n"
                "Score: [PENDING]/4\n\n"
                "## Dimension Scores\n"
                "- Visual Hierarchy: [score]/1\n"
                "- Typography: [score]/1\n"
                "- Spacing & Layout: [score]/1\n"
                "- Color & Contrast: [score]/1\n"
                "- Component Cohesion: [score]/1\n\n"
                "## Findings\n"
                "[AI to complete after critique]\n\n"
                "## Verdict\n"
                "[PASS/FAIL]\n",
                encoding="utf-8",
            )

        elif specifier == "security:scan":
            (_wo_dir / "security-scan.md").write_text(
                f"# Security Scan — Work Order {work_order_id}\n"
                f"Date: {_date_str}\n"
                f"Skill: security:scan\n"
                f"Target: {target or 'not specified'}\n\n"
                "## Result\n"
                "Status: [PENDING]\n\n"
                "## Findings\n"
                "[AI to complete]\n\n"
                "## Verdict\n"
                "[PASS/BLOCKED]\n",
                encoding="utf-8",
            )

        elif specifier == "website:discover" and project_id:
            try:
                paths = resolve_installed_runtime_paths(
                    source_root=source_root,
                    dream_studio_home=dream_studio_home,
                )
                if paths.sqlite_path.exists():
                    with _connect(paths.sqlite_path) as _conn:
                        existing = _conn.execute(
                            "SELECT brief_id FROM ds_design_briefs"
                            " WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                            (project_id,),
                        ).fetchone()
                    if existing is None:
                        _design_brief_create(
                            project_id=project_id,
                            source_root=source_root,
                            dream_studio_home=dream_studio_home,
                        )
            except Exception:
                pass

    return 0


def _skill_list(
    *,
    pack_filter: str | None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    packs_data = _load_packs(source_root)
    packs = packs_data.get("packs", {})

    skills: list[dict[str, Any]] = []
    for pack_name, pack_info in packs.items():
        if pack_filter and pack_name != pack_filter:
            continue
        for mode_name in pack_info.get("modes", []):
            _skill_path_key = pack_info.get("skill_path")
            if _skill_path_key:
                skill_md = source_root / _skill_path_key / "modes" / mode_name / "SKILL.md"
            else:
                skill_md = (
                    source_root
                    / "canonical"
                    / "skills"
                    / pack_name
                    / "modes"
                    / mode_name
                    / "SKILL.md"
                )
            config_yml = skill_md.parent / "config.yml"

            model_preference = None
            estimated_duration = None

            if config_yml.is_file():
                try:
                    import yaml as _yaml

                    config_data = _yaml.safe_load(config_yml.read_text(encoding="utf-8"))
                    if isinstance(config_data, dict):
                        model_preference = config_data.get("model_tier")
                except Exception:
                    pass

            if skill_md.is_file():
                try:
                    import yaml as _yaml

                    text = skill_md.read_text(encoding="utf-8-sig")
                    fm_match = _SKILL_FM_RE.match(text)
                    if fm_match:
                        fm_data = _yaml.safe_load(fm_match.group(1))
                        if isinstance(fm_data, dict):
                            ds_section = fm_data.get("dream_studio", {})
                            if isinstance(ds_section, dict):
                                estimated_duration = ds_section.get("estimated_duration")
                except Exception:
                    pass

            skills.append(
                {
                    "specifier": f"{pack_name}:{mode_name}",
                    "model_preference": model_preference or "sonnet",
                    "estimated_duration": estimated_duration,
                }
            )

    print(json.dumps({"ok": True, "skills": skills}, indent=2))
    return 0


def _run_gate_check(
    gate_name: str | None,
    *,
    planning_root: Path,
    work_order_id: str,
    project_id: str,
    conn: Any,
) -> tuple[bool, str]:
    """Return (passed, failure_reason). failure_reason is empty string when passed=True."""
    if not gate_name:
        return True, ""

    wo_dir = planning_root / "work-orders" / work_order_id

    if gate_name == "design_brief_locked":
        try:
            row = conn.execute(
                "SELECT 1 FROM ds_design_briefs"
                " WHERE project_id = ? AND status = 'locked' LIMIT 1",
                (project_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            try:
                row = conn.execute(
                    "SELECT 1 FROM ds_documents"
                    " WHERE doc_type = 'design_brief' AND project_id = ? LIMIT 1",
                    (project_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                row = None
        if row is None:
            return False, "design_brief_locked: no locked design brief found for this project"
        return True, ""

    if gate_name == "api_contract_exists":
        if not (wo_dir / "api-contract.md").is_file():
            return False, "api_contract_exists: api-contract.md not found"
        return True, ""

    if gate_name == "api_contract_and_security_review":
        if not (wo_dir / "api-contract.md").is_file():
            return False, "api_contract_and_security_review: api-contract.md not found"
        if not (wo_dir / "security-scan.md").is_file():
            return False, "api_contract_and_security_review: security-scan.md not found"
        return True, ""

    if gate_name == "spec_approved":
        if not (wo_dir / "spec.md").is_file():
            return False, "spec_approved: spec.md not found"
        return True, ""

    if gate_name == "all_tests_pass":
        results_path = wo_dir / "test-results.md"
        if not results_path.is_file():
            return False, "all_tests_pass: test-results.md not found"
        content = results_path.read_text(encoding="utf-8")
        if "PASSED" not in content.upper():
            return False, "all_tests_pass: test-results.md does not contain PASSED"
        return True, ""

    if gate_name == "design_critique":
        import re as _re

        critique_path = wo_dir / "design-critique.md"
        if not critique_path.is_file():
            return False, "design_critique: design-critique.md not found"
        content = critique_path.read_text(encoding="utf-8")
        match = _re.search(r"Score:\s*(\d+)/(\d+)", content)
        if not match:
            return False, "design_critique: no 'Score: N/M' found in design-critique.md"
        score = int(match.group(1))
        if score < 3:
            return False, f"design_critique: score {score} is below minimum 3"
        return True, ""

    if gate_name == "security_scan":
        scan_path = wo_dir / "security-scan.md"
        if not scan_path.is_file():
            return False, "security_scan: security-scan.md not found"
        content = scan_path.read_text(encoding="utf-8")
        if "BLOCKED" in content.upper():
            return False, "security_scan: security-scan.md contains BLOCKED"
        return True, ""

    if gate_name == "game_validate":
        if not (wo_dir / "game-validate.md").is_file():
            return False, "game_validate: game-validate.md not found"
        return True, ""

    if gate_name == "anti_slop_passed":
        lint_path = wo_dir / "lint-results.md"
        if not lint_path.is_file():
            return False, (
                f"anti_slop_passed: lint-results.md not found. Run: python "
                f"canonical/skills/domains/modes/website/scripts/lint-artifact.py "
                f"<artifact_path> > .planning/work-orders/{work_order_id}/lint-results.md"
            )
        _lint_content = lint_path.read_text(encoding="utf-8")
        if "BLOCKED" in _lint_content.upper():
            return False, "anti_slop_passed: lint-results.md contains BLOCKED"
        if "PASSED" not in _lint_content.upper():
            return False, "anti_slop_passed: lint-results.md does not contain PASSED"
        return True, ""

    return True, ""


def _work_order_close(
    *,
    work_order_id: str,
    force: bool = False,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    import uuid as _uuid
    from datetime import datetime, timezone

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    p_root = planning_root or Path.cwd() / ".planning"

    with _connect(paths.sqlite_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title, status, work_order_type, project_id, milestone_id"
            " FROM ds_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            print(json.dumps({"ok": False, "error": f"Work order not found: {work_order_id}"}))
            return 1

        wo_id, title, wo_status, wo_type, project_id, wo_milestone_id = wo_row

        type_row = None
        if wo_type:
            type_row = conn.execute(
                "SELECT pre_build_gate, build_executor, post_build_gate"
                " FROM ds_work_order_types WHERE type_id = ?",
                (wo_type,),
            ).fetchone()

        pre_gate = type_row[0] if type_row else None
        post_gate = type_row[2] if type_row else None

        gate_failures: list[str] = []
        _gates_to_check: list[str] = []
        for _raw_gate in (pre_gate, post_gate):
            if _raw_gate:
                _gates_to_check.extend(_raw_gate.split("|"))
        for gate_name in _gates_to_check:
            passed, reason = _run_gate_check(
                gate_name,
                planning_root=p_root,
                work_order_id=work_order_id,
                project_id=project_id,
                conn=conn,
            )
            if not passed:
                gate_failures.append(reason)

        if gate_failures and not force:
            print(
                json.dumps({"ok": False, "error": "Gate check failed", "failures": gate_failures})
            )
            return 1

        now = datetime.now(timezone.utc).isoformat()

        if force and gate_failures:
            for reason in gate_failures:
                print(f"[gate.bypassed] WARNING: {reason}", file=sys.stderr)
                try:
                    import spool.writer as _spool_writer

                    _spool_writer.write_event(
                        {
                            "event_id": str(_uuid.uuid4()),
                            "event_type": "gate.bypassed",
                            "timestamp": now,
                            "trace": {"work_order_id": work_order_id, "project_id": project_id},
                            "severity": "warning",
                            "payload": {
                                "work_order_id": work_order_id,
                                "gate": reason.split(":")[0],
                                "reason": reason,
                            },
                            "source_type": "confirmed",
                        }
                    )
                except Exception:
                    pass

        try:
            import spool.writer as _spool_writer

            _spool_writer.write_event(
                {
                    "event_id": str(_uuid.uuid4()),
                    "event_type": "work_order.closed",
                    "timestamp": now,
                    "trace": {"work_order_id": work_order_id, "project_id": project_id},
                    "severity": "info",
                    "payload": {
                        "work_order_id": work_order_id,
                        "title": title,
                        "project_id": project_id,
                        "forced": force,
                    },
                    "source_type": "confirmed",
                }
            )
        except Exception:
            pass

        conn.execute(
            "UPDATE ds_work_orders SET status = 'complete', updated_at = ?"
            " WHERE work_order_id = ?",
            (now, work_order_id),
        )
        conn.commit()

        # Look up next open WO in same milestone, or check if milestone is complete.
        next_wo: dict[str, Any] | None = None
        milestone_complete = False
        if wo_milestone_id:
            next_row = conn.execute(
                "SELECT work_order_id, title, work_order_type FROM ds_work_orders"
                " WHERE milestone_id = ? AND status = 'open' ORDER BY created_at ASC LIMIT 1",
                (wo_milestone_id,),
            ).fetchone()
            if next_row:
                next_wo = {
                    "work_order_id": next_row[0],
                    "title": next_row[1],
                    "type": next_row[2],
                    "next_command": f"ds work-order start {next_row[0]}",
                }
            else:
                remaining = conn.execute(
                    "SELECT COUNT(*) FROM ds_work_orders"
                    " WHERE milestone_id = ? AND status NOT IN ('complete', 'cancelled')",
                    (wo_milestone_id,),
                ).fetchone()[0]
                if remaining == 0:
                    milestone_complete = True

    result: dict[str, Any] = {
        "ok": True,
        "work_order_id": work_order_id,
        "title": title,
        "status": "complete",
        "forced": force,
        "bypassed_gates": gate_failures if force else [],
    }
    if next_wo:
        result["next_work_order"] = next_wo
        result["next_command"] = next_wo["next_command"]
    elif milestone_complete and wo_milestone_id:
        result["milestone_complete"] = True
        result["milestone_id"] = wo_milestone_id
        result["next_command"] = f"ds milestone close {wo_milestone_id}"

    print(json.dumps(result, indent=2))
    return 0


def _work_order_block(
    *,
    work_order_id: str,
    reason: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    import uuid as _uuid
    from datetime import datetime, timezone

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    with _connect(paths.sqlite_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title, project_id FROM ds_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            print(json.dumps({"ok": False, "error": f"Work order not found: {work_order_id}"}))
            return 1

        wo_id, title, project_id = wo_row
        now = datetime.now(timezone.utc).isoformat()

        try:
            import spool.writer as _spool_writer

            _spool_writer.write_event(
                {
                    "event_id": str(_uuid.uuid4()),
                    "event_type": "work_order.blocked",
                    "timestamp": now,
                    "trace": {"work_order_id": work_order_id, "project_id": project_id},
                    "severity": "warning",
                    "payload": {
                        "work_order_id": work_order_id,
                        "title": title,
                        "project_id": project_id,
                        "reason": reason,
                    },
                    "source_type": "confirmed",
                }
            )
        except Exception:
            pass

        conn.execute(
            "UPDATE ds_work_orders SET status = 'blocked', block_reason = ?, updated_at = ?"
            " WHERE work_order_id = ?",
            (reason, now, work_order_id),
        )
        conn.commit()

    print(
        json.dumps(
            {
                "ok": True,
                "work_order_id": work_order_id,
                "status": "blocked",
                "block_reason": reason,
            },
            indent=2,
        )
    )
    return 0


def _work_order_unblock(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from datetime import datetime, timezone

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    with _connect(paths.sqlite_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title, status FROM ds_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            print(json.dumps({"ok": False, "error": f"Work order not found: {work_order_id}"}))
            return 1

        wo_id, title, wo_status = wo_row
        if wo_status != "blocked":
            print(
                json.dumps(
                    {"ok": False, "error": f"Work order is not blocked (status: {wo_status})"}
                )
            )
            return 1

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE ds_work_orders SET status = 'in_progress', block_reason = NULL, updated_at = ?"
            " WHERE work_order_id = ?",
            (now, work_order_id),
        )
        conn.commit()

    print(
        json.dumps(
            {
                "ok": True,
                "work_order_id": work_order_id,
                "status": "in_progress",
            },
            indent=2,
        )
    )
    return 0


def _work_order_task_done(
    *,
    work_order_id: str,
    task_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    import uuid as _uuid
    from datetime import datetime, timezone

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    with _connect(paths.sqlite_path) as conn:
        task_row = conn.execute(
            "SELECT task_id, work_order_id, title, status FROM ds_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if task_row is None:
            print(json.dumps({"ok": False, "error": f"Task not found: {task_id}"}))
            return 1

        t_id, t_wo_id, t_title, t_status = task_row
        if t_wo_id != work_order_id:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": f"Task {task_id} does not belong to work order {work_order_id}",
                    }
                )
            )
            return 1

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE ds_tasks SET status = 'complete', updated_at = ? WHERE task_id = ?",
            (now, task_id),
        )
        conn.commit()

        remaining = conn.execute(
            "SELECT COUNT(*) FROM ds_tasks"
            " WHERE work_order_id = ? AND status NOT IN ('complete', 'cancelled')",
            (work_order_id,),
        ).fetchone()[0]

        task_index = (
            conn.execute(
                "SELECT COUNT(*) FROM ds_tasks"
                " WHERE work_order_id = ? AND created_at <= ("
                "   SELECT created_at FROM ds_tasks WHERE task_id = ?"
                ")",
                (work_order_id, task_id),
            ).fetchone()[0]
            - 1
        )

    p_root = planning_root or Path.cwd() / ".planning"
    context_path = p_root / "work-orders" / work_order_id / "context.md"
    if context_path.is_file():
        text = context_path.read_text(encoding="utf-8")
        text = text.replace(f"- [ ] {t_title}", f"- [x] {t_title}", 1)
        context_path.write_text(text, encoding="utf-8")

    try:
        import spool.writer as _spool_writer

        _spool_writer.write_event(
            {
                "event_id": str(_uuid.uuid4()),
                "event_type": "task.completed",
                "timestamp": now,
                "trace": {"work_order_id": work_order_id, "task_id": task_id},
                "severity": "info",
                "payload": {
                    "task_id": task_id,
                    "work_order_id": work_order_id,
                    "tasks_remaining": remaining,
                },
                "source_type": "confirmed",
            }
        )
    except Exception:
        pass

    settings_path = source_root / ".claude" / "settings.json"
    if os.environ.get("CLAUDE_CODE") or settings_path.is_file():
        todo_id = f"wo-{work_order_id[:8]}-{task_index}"
        print(json.dumps({"todowrite_update": {"id": todo_id, "status": "completed"}}, indent=2))

    result: dict[str, Any] = {
        "ok": True,
        "task_id": task_id,
        "work_order_id": work_order_id,
        "title": t_title,
        "status": "complete",
        "tasks_remaining": remaining,
    }
    if remaining == 0:
        result["all_tasks_complete"] = True
        result["suggested_action"] = (
            f"All tasks complete. Close work order: ds work-order close {work_order_id}"
        )
    print(json.dumps(result, indent=2))
    return 0


def _work_order_tasks(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    with _connect(paths.sqlite_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, title FROM ds_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            print(json.dumps({"ok": False, "error": f"Work order not found: {work_order_id}"}))
            return 1

        rows = conn.execute(
            "SELECT task_id, title, status FROM ds_tasks"
            " WHERE work_order_id = ? ORDER BY created_at ASC",
            (work_order_id,),
        ).fetchall()

    tasks = []
    for row in rows:
        t_id, t_title, t_status = row
        if t_status == "complete":
            indicator = "[x]"
        elif t_status == "in_progress":
            indicator = "[~]"
        else:
            indicator = "[ ]"
        tasks.append(
            {
                "task_id": t_id,
                "title": t_title,
                "status": t_status,
                "indicator": indicator,
            }
        )

    print(json.dumps({"ok": True, "work_order_id": work_order_id, "tasks": tasks}, indent=2))
    return 0


def _work_order_add_tasks(
    *,
    work_order_id: str,
    tasks_file: Path,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Parse a numbered-list tasks.md file and insert tasks into ds_tasks."""
    import re
    import uuid as _uuid
    from datetime import datetime, timezone

    if not tasks_file.is_file():
        print(json.dumps({"ok": False, "error": f"File not found: {tasks_file}"}))
        return 1

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing. Run rehearsal-install first.")

    with _connect(paths.sqlite_path) as conn:
        wo_row = conn.execute(
            "SELECT work_order_id, project_id FROM ds_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if wo_row is None:
            print(json.dumps({"ok": False, "error": f"Work order not found: {work_order_id}"}))
            return 1
        project_id = wo_row[1]

        text = tasks_file.read_text(encoding="utf-8").replace("\r\n", "\n")
        # Parse numbered list: "1. Title\n   Description" or just "1. Title"
        items = re.findall(
            r"^\s*\d+\.\s+(.+?)(?=\n\s*\d+\.|\Z)",
            text,
            re.MULTILINE | re.DOTALL,
        )
        if not items:
            print(json.dumps({"ok": False, "error": "No numbered list items found in file"}))
            return 1

        now = datetime.now(timezone.utc).isoformat()
        inserted = []
        for raw in items:
            lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
            if not lines:
                continue
            t_title = lines[0]
            t_desc = " ".join(lines[1:]) if len(lines) > 1 else ""
            t_id = str(_uuid.uuid4())
            conn.execute(
                "INSERT INTO ds_tasks"
                " (task_id, work_order_id, project_id, title, description, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                (t_id, work_order_id, project_id, t_title, t_desc, now, now),
            )
            inserted.append({"task_id": t_id, "title": t_title})
        conn.commit()

    print(
        json.dumps(
            {
                "ok": True,
                "work_order_id": work_order_id,
                "tasks_inserted": len(inserted),
                "tasks": inserted,
            },
            indent=2,
        )
    )
    return 0


_VALID_DESIGN_SYSTEMS: frozenset[str] = frozenset(
    [
        "tech-minimal",
        "editorial-modern",
        "brutalist-bold",
        "playful-rounded",
        "executive-clean",
    ]
)

_BRIEF_UPDATABLE_FIELDS: frozenset[str] = frozenset(
    [
        "purpose",
        "audience",
        "tone",
        "design_system",
        "font_pairing",
        "brand_tokens",
        "raw_output",
    ]
)


def _design_brief_dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    if args.design_brief_command == "show":
        return _design_brief_show(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.design_brief_command == "create":
        return _design_brief_create(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.design_brief_command == "lock":
        return _design_brief_lock(
            brief_id=args.brief_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.design_brief_command == "update":
        return _design_brief_update(
            brief_id=args.brief_id,
            field=args.field,
            value=args.value,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.design_brief_command == "set-system":
        return _design_brief_set_system(
            brief_id=args.brief_id,
            system_name=args.system_name,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    print(f"Unknown design-brief command: {args.design_brief_command}", file=sys.stderr)
    return 1


def _design_brief_show(
    *, project_id: str, source_root: Path, dream_studio_home: Path | None
) -> int:
    paths = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")
    with _connect(paths.sqlite_path) as conn:
        row = conn.execute(
            "SELECT brief_id, status, purpose, audience, tone, design_system,"
            " font_pairing, brand_tokens, raw_output, created_at, updated_at"
            " FROM ds_design_briefs WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    if row is None:
        print(f"No design brief. Run ds design-brief create {project_id}")
        return 0
    (
        brief_id,
        status,
        purpose,
        audience,
        tone,
        design_system,
        font_pairing,
        brand_tokens,
        raw_output,
        created_at,
        updated_at,
    ) = row
    status_label = "LOCKED" if status == "locked" else "DRAFT — not yet locked"
    print(
        json.dumps(
            {
                "ok": True,
                "brief_id": brief_id,
                "project_id": project_id,
                "status": f"Status: {status_label}",
                "purpose": purpose,
                "audience": audience,
                "tone": tone,
                "design_system": design_system,
                "font_pairing": font_pairing,
                "brand_tokens": brand_tokens,
                "created_at": created_at,
                "updated_at": updated_at,
            },
            indent=2,
        )
    )
    return 0


def _design_brief_create(
    *, project_id: str, source_root: Path, dream_studio_home: Path | None
) -> int:
    import uuid as _uuid
    from datetime import datetime, timezone

    paths = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")
    brief_id = str(_uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _connect(paths.sqlite_path) as conn:
        conn.execute(
            "INSERT INTO ds_design_briefs (brief_id, project_id, status, created_at, updated_at)"
            " VALUES (?, ?, 'draft', ?, ?)",
            (brief_id, project_id, now, now),
        )
        conn.commit()
    print(f"Draft brief created: {brief_id}")
    print(f"Next: invoke website:discover with --work-order <wo_id> to populate the brief")
    return 0


def _design_brief_lock(*, brief_id: str, source_root: Path, dream_studio_home: Path | None) -> int:
    from datetime import datetime, timezone

    paths = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")
    now = datetime.now(timezone.utc).isoformat()
    with _connect(paths.sqlite_path) as conn:
        row = conn.execute(
            "SELECT brief_id FROM ds_design_briefs WHERE brief_id = ?", (brief_id,)
        ).fetchone()
        if row is None:
            print(json.dumps({"ok": False, "error": f"Brief not found: {brief_id}"}))
            return 1
        conn.execute(
            "UPDATE ds_design_briefs SET status = 'locked', updated_at = ? WHERE brief_id = ?",
            (now, brief_id),
        )
        conn.commit()
    print(f"Brief {brief_id} locked.")
    return 0


def _design_brief_update(
    *, brief_id: str, field: str, value: str, source_root: Path, dream_studio_home: Path | None
) -> int:
    from datetime import datetime, timezone

    if field not in _BRIEF_UPDATABLE_FIELDS:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Unknown field: {field}. Valid fields: {sorted(_BRIEF_UPDATABLE_FIELDS)}",
                }
            )
        )
        return 1
    paths = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")
    now = datetime.now(timezone.utc).isoformat()
    with _connect(paths.sqlite_path) as conn:
        row = conn.execute(
            "SELECT status FROM ds_design_briefs WHERE brief_id = ?", (brief_id,)
        ).fetchone()
        if row is None:
            print(json.dumps({"ok": False, "error": f"Brief not found: {brief_id}"}))
            return 1
        if row[0] == "locked":
            print(json.dumps({"ok": False, "error": "Brief is locked and cannot be updated"}))
            return 1
        conn.execute(
            f"UPDATE ds_design_briefs SET {field} = ?, updated_at = ? WHERE brief_id = ?",
            (value, now, brief_id),
        )
        conn.commit()
    print(json.dumps({"ok": True, "brief_id": brief_id, "field": field, "value": value}, indent=2))
    return 0


def _design_brief_set_system(
    *, brief_id: str, system_name: str, source_root: Path, dream_studio_home: Path | None
) -> int:
    from datetime import datetime, timezone

    if system_name not in _VALID_DESIGN_SYSTEMS:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Invalid design system: {system_name}. Valid values: {sorted(_VALID_DESIGN_SYSTEMS)}",
                }
            )
        )
        return 1
    paths = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")
    now = datetime.now(timezone.utc).isoformat()
    with _connect(paths.sqlite_path) as conn:
        row = conn.execute(
            "SELECT status FROM ds_design_briefs WHERE brief_id = ?", (brief_id,)
        ).fetchone()
        if row is None:
            print(json.dumps({"ok": False, "error": f"Brief not found: {brief_id}"}))
            return 1
        if row[0] == "locked":
            print(json.dumps({"ok": False, "error": "Brief is locked and cannot be updated"}))
            return 1
        conn.execute(
            "UPDATE ds_design_briefs SET design_system = ?, updated_at = ? WHERE brief_id = ?",
            (system_name, now, brief_id),
        )
        conn.commit()
    print(json.dumps({"ok": True, "brief_id": brief_id, "design_system": system_name}, indent=2))
    return 0


def _milestone_dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    if args.milestone_command == "close":
        return _milestone_close(
            milestone_id=args.milestone_id,
            force=args.force,
            planning_root=Path(args.planning_root) if args.planning_root else None,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.milestone_command == "list":
        return _milestone_list(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.milestone_command == "status":
        return _milestone_status(
            milestone_id=args.milestone_id,
            planning_root=Path(args.planning_root) if args.planning_root else None,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    print(f"Unknown milestone command: {args.milestone_command}", file=sys.stderr)
    return 1


def _milestone_close(
    *,
    milestone_id: str,
    force: bool = False,
    planning_root: Path | None = None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    import re as _re
    import uuid as _uuid
    from datetime import datetime, timezone

    paths = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")

    p_root = planning_root or Path.cwd() / ".planning"
    ms_dir = p_root / "milestones" / milestone_id

    with _connect(paths.sqlite_path) as conn:
        ms_row = conn.execute(
            "SELECT milestone_id, project_id, title, status FROM ds_milestones WHERE milestone_id = ?",
            (milestone_id,),
        ).fetchone()
        if ms_row is None:
            print(json.dumps({"ok": False, "error": f"Milestone not found: {milestone_id}"}))
            return 1

        ms_id, project_id, ms_title, ms_status = ms_row

        wo_rows = conn.execute(
            "SELECT work_order_id, title, status, work_order_type"
            " FROM ds_work_orders WHERE milestone_id = ? ORDER BY created_at ASC",
            (milestone_id,),
        ).fetchall()

        # a) All work orders must be complete
        open_wos = [(r[0], r[1], r[2]) for r in wo_rows if r[2] != "complete"]
        if open_wos:
            items = [{"work_order_id": r[0], "title": r[1], "status": r[2]} for r in open_wos]
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "Cannot close milestone: open work orders remain",
                        "open_work_orders": items,
                    }
                )
            )
            return 1

        # b) Determine if this is a UI milestone
        ui_types = frozenset(["ui_component", "ui_page"])
        has_ui = any(r[3] in ui_types for r in wo_rows)

        # b) Milestone verification checks
        failures: list[str] = []

        def _check_file_exists_no_pattern(filename: str, absent_msg: str) -> Path | None:
            p = ms_dir / filename
            if not p.is_file():
                failures.append(absent_msg)
                return None
            return p

        # CHECK 1 — design audit
        audit_path = ms_dir / "design-audit.md"
        if not audit_path.is_file():
            failures.append(
                "Design audit required. Invoke website:critique across all UI surfaces and"
                f" write results to .planning/milestones/{milestone_id}/design-audit.md"
            )
        else:
            content = audit_path.read_text(encoding="utf-8")
            for m in _re.finditer(r"Score:\s*(\d+)/(\d+)", content):
                if int(m.group(1)) < 3:
                    failures.append(
                        f"Design audit: score {m.group(1)}/{m.group(2)} is below minimum 3"
                    )
                    break

        # CHECK 2 — security audit
        sec_path = ms_dir / "security-audit.md"
        if not sec_path.is_file():
            failures.append("Security audit required.")
        else:
            if "BLOCKED" in sec_path.read_text(encoding="utf-8").upper():
                failures.append("Security audit: security-audit.md contains BLOCKED")

        # CHECK 3 — hardening
        harden_path = ms_dir / "harden-results.md"
        if not harden_path.is_file():
            failures.append("Hardening check required. Invoke quality:harden and write results.")
        else:
            if "PASSED" not in harden_path.read_text(encoding="utf-8").upper():
                failures.append("Hardening check: harden-results.md does not contain PASSED")

        # CHECK 4 — Core Web Vitals (UI milestones only)
        if has_ui:
            cwv_path = ms_dir / "cwv-results.md"
            if not cwv_path.is_file():
                failures.append("Core Web Vitals check required.")
            else:
                if "PASSED" not in cwv_path.read_text(encoding="utf-8").upper():
                    failures.append("Core Web Vitals: cwv-results.md does not contain PASSED")

        now = datetime.now(timezone.utc).isoformat()

        if failures and not force:
            print(
                json.dumps(
                    {"ok": False, "error": "Milestone verification failed", "failures": failures}
                )
            )
            return 1

        if force and failures:
            for reason in failures:
                print(f"[gate.bypassed] WARNING: {reason}", file=sys.stderr)
                try:
                    import spool.writer as _spool_writer

                    _spool_writer.write_event(
                        {
                            "event_id": str(_uuid.uuid4()),
                            "event_type": "gate.bypassed",
                            "timestamp": now,
                            "trace": {"milestone_id": milestone_id, "project_id": project_id},
                            "severity": "warning",
                            "payload": {"milestone_id": milestone_id, "reason": reason},
                            "source_type": "confirmed",
                        }
                    )
                except Exception:
                    pass

        conn.execute(
            "UPDATE ds_milestones SET status = 'complete', updated_at = ? WHERE milestone_id = ?",
            (now, milestone_id),
        )
        conn.commit()

    try:
        import spool.writer as _spool_writer

        _spool_writer.write_event(
            {
                "event_id": str(_uuid.uuid4()),
                "event_type": "milestone.completed",
                "timestamp": now,
                "trace": {"milestone_id": milestone_id, "project_id": project_id},
                "severity": "info",
                "payload": {"milestone_id": milestone_id, "title": ms_title, "forced": force},
                "source_type": "confirmed",
            }
        )
    except Exception:
        pass

    print(
        f"Milestone {milestone_id} closed."
        f" Run ds project status {project_id} to see updated progress."
    )
    return 0


def _milestone_list(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    paths = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")
    with _connect(paths.sqlite_path) as conn:
        ms_rows = conn.execute(
            "SELECT milestone_id, title, status FROM ds_milestones"
            " WHERE project_id = ? ORDER BY created_at ASC",
            (project_id,),
        ).fetchall()
        milestones = []
        for ms_id, title, status in ms_rows:
            wo_count = conn.execute(
                "SELECT COUNT(*) FROM ds_work_orders WHERE milestone_id = ?", (ms_id,)
            ).fetchone()[0]
            milestones.append(
                {
                    "milestone_id": ms_id[:8],
                    "milestone_id_full": ms_id,
                    "title": title,
                    "status": status,
                    "work_order_count": wo_count,
                    "depends_on": None,
                }
            )
    print(json.dumps({"ok": True, "milestones": milestones}, indent=2))
    return 0


def _milestone_status(
    *,
    milestone_id: str,
    planning_root: Path | None = None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    paths = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    )
    if not paths.sqlite_path.exists():
        raise RuntimeError("Dream Studio SQLite authority is missing.")

    p_root = planning_root or Path.cwd() / ".planning"
    ms_dir = p_root / "milestones" / milestone_id

    with _connect(paths.sqlite_path) as conn:
        ms_row = conn.execute(
            "SELECT milestone_id, project_id, title, status, due_date FROM ds_milestones"
            " WHERE milestone_id = ?",
            (milestone_id,),
        ).fetchone()
        if ms_row is None:
            print(json.dumps({"ok": False, "error": f"Milestone not found: {milestone_id}"}))
            return 1

        ms_id, project_id, title, status, due_date = ms_row

        wo_rows = conn.execute(
            "SELECT work_order_id, title, status, work_order_type FROM ds_work_orders"
            " WHERE milestone_id = ? ORDER BY created_at ASC",
            (milestone_id,),
        ).fetchall()

    ui_types = frozenset(["ui_component", "ui_page"])
    has_ui = any(r[3] in ui_types for r in wo_rows)

    open_checks = []
    for filename, label in [
        ("design-audit.md", "design_audit"),
        ("security-audit.md", "security_audit"),
        ("harden-results.md", "harden_results"),
    ]:
        if not (ms_dir / filename).is_file():
            open_checks.append(label)
    if has_ui and not (ms_dir / "cwv-results.md").is_file():
        open_checks.append("cwv_results")

    print(
        json.dumps(
            {
                "ok": True,
                "milestone_id": ms_id,
                "project_id": project_id,
                "title": title,
                "status": status,
                "due_date": due_date,
                "work_orders": [
                    {"work_order_id": r[0], "title": r[1], "status": r[2], "type": r[3]}
                    for r in wo_rows
                ],
                "open_gate_checks": open_checks,
            },
            indent=2,
        )
    )
    return 0


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
