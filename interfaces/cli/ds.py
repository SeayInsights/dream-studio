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
    restore_runtime,
    rollback_runtime_check,
    restore_runtime_check,
    uninstall_runtime,
    uninstall_runtime_check,
    update_runtime_check,
)
from core.module_profiles import module_profiles  # noqa: E402
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
    parser.add_argument(
        "--debug", action="store_true", help="Emit diagnostic output (DB path, authority, command)"
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

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

    # spool subcommand group (Slice 3)
    from interfaces.cli.ds_spool import add_spool_subcommand

    add_spool_subcommand(subcommands)

    # workflow subcommand group (Slice 9b)
    from interfaces.cli.ds_workflow import add_workflow_subcommand

    add_workflow_subcommand(subcommands)

    # learn subcommand group (Phase 19.3)
    from interfaces.cli.ds_learn import add_learn_subcommand

    add_learn_subcommand(subcommands)

    # memory subcommand group (Slice 5d)
    from interfaces.cli.ds_memory import add_memory_subcommand

    add_memory_subcommand(subcommands)

    # files subcommand group (WO-TS5)
    from interfaces.cli.ds_files import add_files_subcommand

    add_files_subcommand(subcommands)

    # projection subcommand group (Phase 18.1.5)
    from interfaces.cli.projection_cli import add_projection_subcommand

    add_projection_subcommand(subcommands)

    # project subcommand group (Slice 4 WS3 + Slice 5b)
    project = subcommands.add_parser("project", help="Manage Dream Studio projects")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    project_register = project_sub.add_parser("register", help="Register a new project")
    project_register.add_argument("--name", required=True, help="Project name")
    project_register.add_argument("--description", default="", help="Optional description")
    project_register.add_argument(
        "--path",
        required=True,
        metavar="DIR",
        help="Path to the project directory. A .dream-studio-project marker file will be written here.",
    )
    project_list = project_sub.add_parser("list", help="List registered projects")
    project_list.add_argument(
        "--status", default="active", help="Filter by status (default: active)"
    )
    project_list.add_argument(
        "--include-deleted",
        action="store_true",
        default=False,
        dest="include_deleted",
        help="Include soft-deleted projects (status=deleted) in output",
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

    from integrations.detector import SUPPORTED_TOOLS as _SUPPORTED_TOOLS

    integrate_plan = integrate_sub.add_parser(
        "plan", help="Print the dry-run file operation plan for a tool"
    )
    integrate_plan.add_argument("tool", choices=list(_SUPPORTED_TOOLS))
    integrate_plan.add_argument("--scope", choices=["user", "project"], default=None)

    integrate_install = integrate_sub.add_parser(
        "install", help="Install integration for a tool (requires --dry-run or --execute)"
    )
    integrate_install.add_argument("tool", choices=list(_SUPPORTED_TOOLS))
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
    wo_start.add_argument(
        "--in-sequence",
        action="store_true",
        default=False,
        dest="in_sequence",
        help="Abort (exit 1) if earlier-sequence WOs in the same milestone are not closed",
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
    wo_tasks.add_argument(
        "--verbose", "-v", action="store_true", help="Include full description for each task"
    )
    wo_set_order = work_order_sub.add_parser(
        "set-order", help="Set sequence_order on a work order (sparse 10/20/30)"
    )
    wo_set_order.add_argument("work_order_id", help="Work order UUID")
    wo_set_order.add_argument("sequence_order", type=int, help="Sequence order (integer, e.g. 10)")
    wo_add_dep = work_order_sub.add_parser(
        "add-dep", help="Add a dependency: work_order_id waits for depends_on_id to close"
    )
    wo_add_dep.add_argument("work_order_id", help="Work order UUID")
    wo_add_dep.add_argument("depends_on_id", help="Dependency target UUID")
    wo_remove_dep = work_order_sub.add_parser("remove-dep", help="Remove a dependency edge")
    wo_remove_dep.add_argument("work_order_id", help="Work order UUID")
    wo_remove_dep.add_argument("depends_on_id", help="Dependency target UUID")
    wo_next = work_order_sub.add_parser(
        "next", help="Show next unblocked work order for a project (ready-set selector)"
    )
    wo_next.add_argument("project_id", help="Project UUID")
    wo_verify = work_order_sub.add_parser(
        "verify", help="Run independent fresh-context review; gaps become new work orders"
    )
    wo_verify.add_argument("work_order_id", help="Work order UUID")
    wo_executor = work_order_sub.add_parser(
        "executor", help="Resolve which model should execute this WO (escalation-aware)"
    )
    wo_executor.add_argument("work_order_id", help="Work order UUID")

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

    # task subcommand group (TA2)
    task_cmd = subcommands.add_parser("task", help="Manage active task context")
    task_sub = task_cmd.add_subparsers(dest="task_command", required=True)
    t_set_active = task_sub.add_parser("set-active", help="Set the active task context")
    t_set_active.add_argument("task_id", help="Task UUID")
    task_sub.add_parser("active", help="Show the current active task context")
    task_sub.add_parser("clear-active", help="Clear the active task context")
    t_list = task_sub.add_parser("list", help="Alias for 'ds work-order tasks <work_order_id>'")
    t_list.add_argument("work_order_id", help="Work order UUID")
    t_list.add_argument(
        "--verbose", "-v", action="store_true", help="Include full description for each task"
    )

    # analyze subcommand group (brownfield intake)
    analyze_cmd = subcommands.add_parser(
        "analyze", help="Analysis commands (brownfield intake, repo scanning)"
    )
    analyze_sub = analyze_cmd.add_subparsers(dest="analyze_command", required=True)
    analyze_aggregate = analyze_sub.add_parser(  # noqa: F841
        "aggregate", help="Run ML metrics aggregation (studio.db → aggregate_metrics.db)"
    )

    analyze_intake = analyze_sub.add_parser(
        "intake", help="Register a brownfield repo for intake scanning"
    )
    analyze_intake.add_argument(
        "target_path",
        metavar="TARGET_PATH",
        help="Path to the repository to scan",
    )
    analyze_intake.add_argument(
        "--persistent",
        action="store_true",
        default=False,
        help=(
            "Write a .dream-studio-project marker file for persistent session attribution "
            "(skips the interactive prompt)"
        ),
    )

    # eval subcommand group (18.8.3)
    eval_cmd = subcommands.add_parser("eval", help="Behavioral eval runner (18.8.3)")
    eval_sub = eval_cmd.add_subparsers(dest="eval_command", required=True)
    eval_run_cmd = eval_sub.add_parser("run", help="Run behavioral evals")
    eval_run_cmd.add_argument("--all", action="store_true", default=False, help="Run all evals")
    eval_run_cmd.add_argument(
        "--eval-id", default=None, dest="eval_id", help="Run a specific eval by ID"
    )
    eval_run_cmd.add_argument(
        "--skill", default=None, dest="skill_filter", help="Filter evals by skill_id"
    )
    eval_run_cmd.add_argument(
        "--evals-dir", default=None, dest="evals_dir", help="Override evals directory"
    )
    eval_run_cmd.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Live mode: spawn a fresh claude subprocess and score its events (requires claude CLI in PATH)",
    )
    eval_baseline_cmd = eval_sub.add_parser("baseline", help="Print current baseline scores")
    eval_baseline_cmd.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Run eval in live mode and capture the result as the live baseline (requires --eval-id)",
    )
    eval_baseline_cmd.add_argument(
        "--eval-id",
        default=None,
        dest="eval_id",
        help="Eval ID to capture live baseline for (required when --live is specified)",
    )
    eval_compare_cmd = eval_sub.add_parser(
        "compare", help="Compare recent run scores against baseline"
    )
    eval_compare_cmd.add_argument(
        "--eval-id", default=None, dest="eval_id", help="Compare specific eval"
    )
    eval_list_cmd = eval_sub.add_parser("list", help="List available eval cases")
    eval_list_cmd.add_argument(
        "--skill", default=None, dest="skill_filter", help="Filter by skill_id"
    )
    eval_list_cmd.add_argument(
        "--evals-dir", default=None, dest="evals_dir", help="Override evals directory"
    )
    eval_registry_cmd = eval_sub.add_parser(
        "registry", help="Unified eval registry across skills, hooks, workflows, agents"
    )
    eval_registry_sub = eval_registry_cmd.add_subparsers(dest="registry_command", required=True)
    eval_registry_list_cmd = eval_registry_sub.add_parser(
        "list", help="List all registered eval targets with latest status"
    )
    eval_registry_list_cmd.add_argument(
        "--type",
        default=None,
        dest="target_type",
        choices=["skill", "hook", "workflow", "agent"],
        help="Filter by target type",
    )
    eval_registry_show_cmd = eval_registry_sub.add_parser(
        "show", help="Show eval run history for a specific target"
    )
    eval_registry_show_cmd.add_argument("target_id", help="Target ID to inspect")

    eval_queue_cmd = eval_sub.add_parser(
        "queue", help="Friction-flagged re-run queue: show pending evals or run them"
    )
    eval_queue_sub = eval_queue_cmd.add_subparsers(dest="queue_command", required=True)
    eval_queue_sub.add_parser("show", help="Show eval targets pending re-run (friction_flag=1)")
    eval_queue_sub.add_parser(
        "run",
        help="Run live evals for all friction-flagged targets and clear their flags on pass",
    )
    eval_queue_sub.add_parser(
        "aggregate", help="Aggregate friction signals from raw_sessions, corrections, guardrails"
    )

    # config subcommand group (WO-FRICTION-CONFIG)
    config_cmd = subcommands.add_parser("config", help="Operator-local key/value config")
    config_sub = config_cmd.add_subparsers(dest="config_command", required=True)
    config_set_cmd = config_sub.add_parser("set", help="Set a config value")
    config_set_cmd.add_argument("key", help="Config key (e.g. eval.friction_threshold)")
    config_set_cmd.add_argument("value", help="Value to store")
    config_sub.add_parser("show", help="Show all config values")

    # diagnostics subcommand group (TA3)
    diag_cmd = subcommands.add_parser(
        "diagnostics", help="Read or clear the TA3 diagnostic log stream"
    )
    diag_sub = diag_cmd.add_subparsers(dest="diagnostics_command", required=True)
    diag_list = diag_sub.add_parser("list", help="Show recent diagnostic entries")
    diag_list.add_argument(
        "--source", default=None, help="Filter by source prefix (e.g. token-capture)"
    )
    diag_list.add_argument(
        "--category",
        default=None,
        choices=["failure", "anomaly", "performance"],
        help="Filter by category",
    )
    diag_list.add_argument(
        "--limit", type=int, default=50, help="Max entries to return (default 50)"
    )
    diag_clear = diag_sub.add_parser("clear", help="Truncate diagnostic log files")
    diag_clear.add_argument(
        "--source", default=None, help="Clear only files matching this source prefix"
    )

    args = parser.parse_args(argv)
    source_root = Path(args.source_root).resolve() if args.source_root else REPO_ROOT
    home = Path(args.home).resolve() if args.home else None

    if getattr(args, "debug", False):
        import sys as _sys

        try:
            _paths = resolve_installed_runtime_paths(
                source_root=source_root, dream_studio_home=home
            )
            _db_path = _paths.sqlite_path
        except Exception as _e:
            _db_path = f"<error: {_e}>"
        print(f"[debug] source_root: {source_root}", file=_sys.stderr)
        print(f"[debug] dream_studio_home: {home}", file=_sys.stderr)
        print(f"[debug] db_path: {_db_path}", file=_sys.stderr)
        print(f"[debug] command: {getattr(args, 'command', None)}", file=_sys.stderr)
        _sub = getattr(args, "work_order_command", None) or getattr(args, "project_command", None)
        if _sub:
            print(f"[debug] subcommand: {_sub}", file=_sys.stderr)

    try:
        if args.command == "status":
            from core.health.status import get_runtime_status

            return _print(get_runtime_status(source_root=source_root, dream_studio_home=home))
        if args.command == "version":
            return _print(_version_status(source_root=source_root, dream_studio_home=home))
        if args.command == "doctor":
            _doctor_mode = getattr(args, "mode", None)
            if _doctor_mode == "dashboard-truth":
                from core.gates.dashboard_truth import run_dashboard_truth

                _dt_paths = resolve_installed_runtime_paths(
                    source_root=source_root,
                    dream_studio_home=home,
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
        if args.command == "migrate":
            return _migrate_command(args)
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
        if args.command == "restore":
            return _print(
                restore_runtime(
                    source_root=source_root,
                    dream_studio_home=home or _require_home_for_install(args.command),
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
        if args.command == "uninstall":
            settings_paths = args.claude_settings_paths or _default_claude_settings_paths()
            return _print(
                uninstall_runtime(
                    source_root=source_root,
                    dream_studio_home=home or _require_home_for_install(args.command),
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
        if args.command == "learn":
            if hasattr(args, "func"):
                return args.func(args)
            print("Usage: ds learn review [--limit N] [--batch]", file=sys.stderr)
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
        if args.command == "task":
            return _task_dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "projection":
            from interfaces.cli.projection_cli import handle_projection_command

            return handle_projection_command(args)
        if args.command == "diagnostics":
            return _diagnostics_dispatch(args)
        if args.command == "config":
            return _config_dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "analyze":
            return _analyze_dispatch(args, source_root=source_root, dream_studio_home=home)
        if args.command == "eval":
            return _eval_dispatch(args, source_root=source_root)
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
    from integrations.manifest import compute_hash

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
        if compute_hash(handler.read_text(encoding="utf-8")) != recorded:
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


def _migrate_command(args: "argparse.Namespace") -> int:
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
            project_path=Path(args.path).resolve(),
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.project_command == "list":
        return _project_list(
            status_filter=args.status,
            include_deleted=getattr(args, "include_deleted", False),
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
    project_path: Path,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.mutations import register_project

    result = register_project(
        name=name,
        description=description,
        project_path=project_path,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if result.get("ok"):
        result["hint"] = (
            f"To make this the active project, run: ds project set-active {result['project_id']}"
        )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_list(
    *,
    status_filter: str,
    include_deleted: bool = False,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.queries import get_project_list

    result = get_project_list(
        status_filter=status_filter,
        include_deleted=include_deleted,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_status(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.queries import get_project_status

    result = get_project_status(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_next(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.queries import get_next_work_order

    result = get_next_work_order(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_set_active(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.mutations import set_active_project

    result = set_active_project(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_deactivate(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.mutations import deactivate_project

    result = deactivate_project(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _project_start(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    """CLI wrapper around `core.projects.start.start_project`.

    Converts the composer's compound result dict into the legacy
    operator-facing output: the inner `work_order_start` JSON on stdout
    (so tests that parse it still work), then a human-readable summary
    with the project name, work-order title, type/milestone, context.md
    path, task count, and close hint.
    """

    from core.projects.start import start_project

    result = start_project(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )

    if not result.get("ok"):
        print(json.dumps(result))
        return 1

    project_name = result.get("project_name", project_id)

    if result.get("no_open_work_orders"):
        print(
            f"Project activated: {project_name}\n"
            "No open work orders found.\n"
            f"Run `ds project next {project_id}` to check status."
        )
        return 0

    next_wo = result.get("next_work_order") or {}
    wo_id = next_wo.get("work_order_id", "")
    wo_title = next_wo.get("title", "")
    wo_type = next_wo.get("work_order_type") or "—"
    milestone_str = next_wo.get("milestone") or "—"
    context_path = result.get("context_path") or ""
    task_count = result.get("tasks_count", 0)
    tasks_str = f"{task_count} tasks queued" if task_count else "tasks queued"

    # Preserve the legacy operator surface: the inner work-order start JSON
    # was previously printed by _work_order_start before the summary.
    wo_start = result.get("work_order_start") or {}
    print(json.dumps(wo_start, indent=2))

    print(
        f"\nProject activated: {project_name}\n"
        f"Starting: {wo_title}\n"
        f"Type: {wo_type} | Milestone: {milestone_str}\n"
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
    """CLI wrapper around ``core.projects.mutations.delete_project``.

    The CLI ``--confirm`` flag maps to the function's ``confirm=True``
    kwarg. The function returns a dict whose error path mentions
    ``confirm=True`` (the kwarg name); the wrapper post-processes the
    message to use ``--confirm`` (the operator-facing flag name) so the
    CLI error text stays as it was before A6.3 lifted the function.
    """

    from core.projects.mutations import delete_project

    result = delete_project(
        project_id=project_id,
        confirm=confirm,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not result.get("ok"):
        error = result.get("error", "")
        if "Pass confirm=True" in error:
            result = {**result, "error": error.replace("Pass confirm=True", "Pass --confirm")}
        print(json.dumps(result))
        return 1
    print(json.dumps(result))
    return 0


def _project_state(
    *,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    """Single-call project state: active project + next WO + gates + brief + tasks + gotchas."""
    from core.projects.queries import get_project_state

    result = get_project_state(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


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

        # Phase 20: native-AGENTS.md tools use the generic installer (AGENTS.md only,
        # no hooks/skills). Claude Code keeps its dedicated installer below.
        tool_id = getattr(args, "tool", "claude_code")
        if tool_id != "claude_code":
            from integrations.installer.agents_target import AgentsTargetInstaller

            installer = AgentsTargetInstaller(
                tool_id,
                project_root=Path.cwd(),
                canonical_root=canonical_root,
            )
            result = installer.install(mode)
            return _print(
                {
                    "model_name": "dream_studio_integrate_install",
                    "derived_view": True,
                    "primary_authority": False,
                    "tool": tool_id,
                    **result,
                }
            )

        detected = detect_claude_code(scope_override=scope)
        # B.3: install the git pre-push hook into the cwd's repo (if any).
        # Tests do NOT pass cwd, so the operator's real .git/hooks/ is untouched.
        cwd = Path.cwd()
        git_repo_root = cwd if (cwd / ".git").is_dir() else None
        # Read skip_hook_install from ~/.dream-studio/config.json if present.
        _skip_hook = False
        try:
            _cfg_path = (ds_home or (Path.home() / ".dream-studio")) / "config.json"
            if _cfg_path.is_file():
                import json as _json

                _skip_hook = bool(
                    _json.loads(_cfg_path.read_text(encoding="utf-8")).get(
                        "skip_hook_install", False
                    )
                )
        except Exception:
            pass
        installer = ClaudeCodeInstaller(
            detected.config_root,
            detected.scope,
            canonical_root=canonical_root,
            ds_home=ds_home,
            git_repo_root=git_repo_root,
            skip_hook_install=_skip_hook,
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
            in_sequence=getattr(args, "in_sequence", False),
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
            verbose=getattr(args, "verbose", False),
        )
    if args.work_order_command == "set-order":
        return _work_order_set_order(
            work_order_id=args.work_order_id,
            sequence_order=args.sequence_order,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "add-dep":
        return _work_order_add_dep(
            work_order_id=args.work_order_id,
            depends_on_id=args.depends_on_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "remove-dep":
        return _work_order_remove_dep(
            work_order_id=args.work_order_id,
            depends_on_id=args.depends_on_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "next":
        return _work_order_next(
            project_id=args.project_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "verify":
        return _work_order_verify(
            work_order_id=args.work_order_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    if args.work_order_command == "executor":
        return _work_order_executor(
            work_order_id=args.work_order_id,
            source_root=source_root,
            dream_studio_home=dream_studio_home,
        )
    print(f"Unknown work-order command: {args.work_order_command}", file=sys.stderr)
    return 1


def _work_order_executor(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Resolve and print the executor (model) for a WO — escalation-aware (T5).

    The autonomous execute-work-orders loop calls this to honor the escalation
    capability flag (route an escalated WO's retry to Opus); the manual path honors
    the same flag via start_work_order's ``executor`` field. Both consume
    ``escalation.resolve_executor`` so routing is identical on both surfaces.
    """
    from core.work_orders.escalation import read_escalation, resolve_executor

    db_path = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    ).sqlite_path
    executor = resolve_executor(work_order_id, db_path=db_path)
    esc = read_escalation(work_order_id, db_path=db_path)
    result = {
        "ok": True,
        "work_order_id": work_order_id,
        "executor": executor,
        "escalated": bool(esc and (esc.get("escalation_level") or 0) >= 1),
        "escalation_level": (esc or {}).get("escalation_level", 0),
    }
    print(json.dumps(result, indent=2))
    return 0


def _work_order_start(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
    accept_no_brief: bool = False,
    in_sequence: bool = False,
) -> int:
    """CLI wrapper around `core.work_orders.start.start_work_order`.

    Preserves the legacy operator-terminal behavior: prints a stderr WARNING
    when the work order is UI-typed but lacks a locked design brief; if the
    operator is running interactively (TTY), prompts y/N; otherwise auto-
    accepts (so test fixtures and non-interactive scripts keep working).

    Skills should call `start_work_order(accept_no_brief=...)` directly and
    never go through this CLI surface.
    """

    from core.work_orders.start import read_work_order_brief, start_work_order

    brief_data = read_work_order_brief(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not brief_data.get("ok"):
        print(json.dumps(brief_data, indent=2))
        return 1

    if brief_data.get("brief_warning") and not accept_no_brief:
        print(
            "WARNING: No locked design brief found. It is strongly recommended to run "
            "website:discover before building UI. Continue anyway? [y/N]",
            file=sys.stderr,
        )
        if sys.stdin.isatty():
            try:
                answer = sys.stdin.readline().strip().lower()
            except OSError:
                # On Windows, stdin may claim isatty()=True but fail on read
                # (WinError 1) in certain pipe/test contexts. Treat as non-interactive.
                answer = ""
            if answer not in ("y", "yes"):
                return 0
        # Non-interactive context (tests, scripts): auto-accept to preserve
        # legacy behavior — the warning is still emitted to stderr.
        accept_no_brief = True

    result = start_work_order(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
        accept_no_brief=accept_no_brief,
        brief_data=brief_data,
        in_sequence=in_sequence,
    )
    if result.get("ok") and result.get("sequence_warning"):
        print(result["sequence_warning"], file=sys.stderr)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_list(
    *,
    project_id: str | None,
    status_filter: str | None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.queries import list_work_orders

    result = list_work_orders(
        project_id=project_id,
        status_filter=status_filter,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


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
    """CLI wrapper around `core.skills.invocation`.

    Composes the three pure functions in dependency order:
    1. ``load_skill_content`` — validates specifier and reads SKILL.md;
       fail-fast prints to stderr and returns 1.
    2. Prints the SKILL.md body + operator footer to stdout (the legacy
       handler's user-facing output is preserved verbatim).
    3. ``record_skill_invocation`` — best-effort project_id resolution +
       `skill.invoked` spool event emission.
    4. ``seed_gate_artifact_files`` — writes the pre-shaped artifacts
       (design-critique.md / security-scan.md) and triggers the design
       brief seeding for website:discover.

    Steps 3 and 4 are best-effort: failure does not change the exit code.
    """

    from core.skills.invocation import (
        load_skill_content,
        record_skill_invocation,
        seed_gate_artifact_files,
    )

    load_result = load_skill_content(specifier=specifier, source_root=source_root)
    if not load_result.get("ok"):
        print(load_result["error"], file=sys.stderr)
        return 1

    record_result = record_skill_invocation(
        specifier=specifier,
        target=target,
        work_order_id=work_order_id,
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )

    print(load_result["skill_content"])
    print("---")
    print(f"Skill: {specifier}")
    print(f"Mode: {record_result['invocation_mode']}")
    print(f"Target: {target or 'not specified'}")
    print(f"Work order: {work_order_id or 'none'}")
    print("Invocation recorded.")
    print()
    print(
        "The AI reading this output has the skill instructions above and should now execute them."
    )

    seed_gate_artifact_files(
        specifier=specifier,
        target=target,
        work_order_id=work_order_id,
        milestone_id=milestone_id,
        project_id=project_id,
        planning_root=planning_root,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )

    return 0


def _skill_list(
    *,
    pack_filter: str | None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.skills.queries import list_skills

    result = list_skills(
        pack_filter=pack_filter,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_close(
    *,
    work_order_id: str,
    force: bool = False,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    """CLI wrapper around `core.work_orders.close.close_work_order`.

    Preserves the legacy operator-terminal behaviour by re-emitting
    `[gate.bypassed] WARNING: <reason>` to stderr from the returned
    `bypassed_gates` list. Skills should call `close_work_order` directly.
    """

    from core.work_orders.close import close_work_order

    result = close_work_order(
        work_order_id=work_order_id,
        force=force,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )

    if result.get("ok") and result.get("forced") and result.get("bypassed_gates"):
        for reason in result["bypassed_gates"]:
            print(f"[gate.bypassed] WARNING: {reason}", file=sys.stderr)

    print(json.dumps(result, indent=2))
    if result.get("ok") and result.get("next_block"):
        print(file=sys.stderr)
        print(result["next_block"], file=sys.stderr)
    return 0 if result.get("ok") else 1


def _work_order_block(
    *,
    work_order_id: str,
    reason: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.mutations import block_work_order

    result = block_work_order(
        work_order_id=work_order_id,
        reason=reason,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_unblock(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.mutations import unblock_work_order

    result = unblock_work_order(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_task_done(
    *,
    work_order_id: str,
    task_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    planning_root: Path | None = None,
) -> int:
    from core.work_orders.mutations import mark_task_done, todowrite_should_emit

    result = mark_task_done(
        work_order_id=work_order_id,
        task_id=task_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )
    if result.get("ok") and todowrite_should_emit(source_root):
        task_index = result.get("task_index", 0)
        todo_id = f"wo-{work_order_id[:8]}-{task_index}"
        print(json.dumps({"todowrite_update": {"id": todo_id, "status": "completed"}}, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_tasks(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
    verbose: bool = False,
) -> int:
    from core.work_orders.queries import list_tasks

    result = list_tasks(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        verbose=verbose,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_verify(
    *,
    work_order_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.verify import verify_work_order

    result = verify_work_order(
        work_order_id=work_order_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=source_root / ".planning",
    )
    if not result.get("ok"):
        print(f"Error: {result.get('error', 'unknown error')}", file=sys.stderr)
        return 1
    passed = result["passed"]
    print(f"Verification {'PASSED' if passed else 'FAILED'}: {result['summary']}")
    for tv in result.get("tasks_verified", []):
        indicator = "✓" if tv["verdict"] == "pass" else ("~" if tv["verdict"] == "partial" else "✗")
        print(f"  {indicator} [{tv['verdict']}] {tv['task_title']}: {tv['evidence']}")
    spawned = result.get("spawned_work_orders", [])
    if spawned:
        print(f"\nGap work orders created ({len(spawned)}):")
        for wo in spawned:
            print(f"  [{wo['type']}] {wo['title']}  (id: {wo['work_order_id']})")
    print(f"\nVerdict: {result['verdict_path']}")
    return 0 if passed else 1


def _work_order_set_order(
    *,
    work_order_id: str,
    sequence_order: int,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.ordering import set_sequence_order

    result = set_sequence_order(
        work_order_id=work_order_id,
        sequence_order=sequence_order,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_add_dep(
    *,
    work_order_id: str,
    depends_on_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.ordering import add_dependency

    result = add_dependency(
        work_order_id=work_order_id,
        depends_on_id=depends_on_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_remove_dep(
    *,
    work_order_id: str,
    depends_on_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.work_orders.ordering import remove_dependency

    result = remove_dependency(
        work_order_id=work_order_id,
        depends_on_id=depends_on_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _work_order_next(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.projects.queries import get_next_work_order

    result = get_next_work_order(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


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
    from core.design_briefs.queries import get_design_brief

    result = get_design_brief(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    # `get_design_brief` returns `{"ok": True, "brief": None, "message": ...}` when
    # no brief exists, vs a brief-shaped dict (with `brief_id`) when one exists.
    if result.get("ok") and result.get("brief_id") is None:
        print(result.get("message", "No design brief found."))
        return 0
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _design_brief_create(
    *, project_id: str, source_root: Path, dream_studio_home: Path | None
) -> int:
    """CLI wrapper around ``core.design_briefs.mutations.create_design_brief``."""

    from core.design_briefs.mutations import create_design_brief

    result = create_design_brief(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not result.get("ok"):
        print(json.dumps(result))
        return 1
    print(f"Draft brief created: {result['brief_id']}")
    print(f"Next: {result['next_step']}")
    return 0


def _design_brief_lock(*, brief_id: str, source_root: Path, dream_studio_home: Path | None) -> int:
    """CLI wrapper around ``core.design_briefs.mutations.lock_design_brief``."""

    from core.design_briefs.mutations import lock_design_brief

    result = lock_design_brief(
        brief_id=brief_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    if not result.get("ok"):
        print(json.dumps(result))
        return 1
    print(f"Brief {brief_id} locked.")
    return 0


def _design_brief_update(
    *, brief_id: str, field: str, value: str, source_root: Path, dream_studio_home: Path | None
) -> int:
    from core.design_briefs.mutations import update_design_brief_field

    result = update_design_brief_field(
        brief_id=brief_id,
        field=field,
        value=value,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _design_brief_set_system(
    *, brief_id: str, system_name: str, source_root: Path, dream_studio_home: Path | None
) -> int:
    from core.design_briefs.mutations import set_design_system

    result = set_design_system(
        brief_id=brief_id,
        system_name=system_name,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


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
    """CLI wrapper around ``core.milestones.close.close_milestone``.

    The pure function returns one canonical result dict; this wrapper
    formats the legacy operator-facing output:
    - failures (missing milestone / open WOs / gate failures) → JSON to
      stdout + exit 1;
    - forced bypass with failures → emit
      ``[gate.bypassed] WARNING: <reason>`` to stderr per failure, then
      the success line;
    - success → plain-text ``Milestone <id> closed. Run ds project
      status <project_id> to see updated progress.``
    """

    from core.milestones.close import close_milestone

    result = close_milestone(
        milestone_id=milestone_id,
        force=force,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )

    if not result.get("ok"):
        print(json.dumps(result))
        return 1

    if result.get("forced") and result.get("bypassed_gates"):
        for reason in result["bypassed_gates"]:
            print(f"[gate.bypassed] WARNING: {reason}", file=sys.stderr)

    print(
        f"Milestone {milestone_id} closed."
        f" Run ds project status {result['project_id']} to see updated progress."
    )
    return 0


def _milestone_list(
    *,
    project_id: str,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.milestones.queries import list_milestones

    result = list_milestones(
        project_id=project_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _milestone_status(
    *,
    milestone_id: str,
    planning_root: Path | None = None,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    from core.milestones.queries import get_milestone_status

    result = get_milestone_status(
        milestone_id=milestone_id,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
        planning_root=planning_root,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _task_dispatch(
    args: argparse.Namespace,
    source_root: Path | None = None,
    dream_studio_home: Path | None = None,
) -> int:
    if args.task_command == "set-active":
        return _task_set_active(task_id=args.task_id)
    if args.task_command == "active":
        return _task_get_active()
    if args.task_command == "clear-active":
        return _task_clear_active()
    if args.task_command == "list":
        return _work_order_tasks(
            work_order_id=args.work_order_id,
            source_root=source_root or REPO_ROOT,
            dream_studio_home=dream_studio_home,
            verbose=getattr(args, "verbose", False),
        )
    print(f"Unknown task command: {args.task_command}", file=sys.stderr)
    return 1


def _task_set_active(*, task_id: str) -> int:
    from core.sdlc.active_task import set_active_task

    try:
        ctx = set_active_task(task_id)
        import dataclasses

        print(json.dumps(dataclasses.asdict(ctx), indent=2))
        return 0
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


def _task_get_active() -> int:
    from core.sdlc.active_task import get_active_task

    ctx = get_active_task()
    if ctx is None:
        print(json.dumps({"active_task": None, "message": "no active task"}, indent=2))
        return 0
    import dataclasses

    print(json.dumps({"active_task": dataclasses.asdict(ctx)}, indent=2))
    return 0


def _task_clear_active() -> int:
    from core.sdlc.active_task import clear_active_task

    removed = clear_active_task()
    print(json.dumps({"ok": True, "cleared": removed}, indent=2))
    return 0


def _diagnostics_dispatch(args: argparse.Namespace) -> int:
    from core.telemetry.diagnostics import _diagnostics_dir

    diag_dir = _diagnostics_dir()
    if args.diagnostics_command == "list":
        source_filter = getattr(args, "source", None)
        cat_filter = getattr(args, "category", None)
        limit = getattr(args, "limit", 50)
        entries: list[dict[str, Any]] = []
        if diag_dir.exists():
            jsonl_files = sorted(diag_dir.glob("*.jsonl"))
            if source_filter:
                jsonl_files = [f for f in jsonl_files if source_filter in f.stem]
            for path in jsonl_files:
                try:
                    for line in path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        entry = json.loads(line)
                        if cat_filter and entry.get("category") != cat_filter:
                            continue
                        entry["_file"] = path.name
                        entries.append(entry)
                except Exception:
                    pass
        # Most recent first; apply limit.
        entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
        entries = entries[:limit]
        print(json.dumps({"ok": True, "count": len(entries), "entries": entries}, indent=2))
        return 0

    if args.diagnostics_command == "clear":
        source_filter = getattr(args, "source", None)
        cleared: list[str] = []
        if diag_dir.exists():
            for path in diag_dir.glob("*.jsonl"):
                if source_filter and source_filter not in path.stem:
                    continue
                try:
                    path.write_text("", encoding="utf-8")
                    cleared.append(path.name)
                except Exception:
                    pass
        print(json.dumps({"ok": True, "cleared": cleared}, indent=2))
        return 0

    print(f"Unknown diagnostics command: {args.diagnostics_command}", file=sys.stderr)
    return 1


def _analyze_dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    if args.analyze_command == "intake":
        return _analyze_intake(args, source_root=source_root, dream_studio_home=dream_studio_home)
    if args.analyze_command == "aggregate":
        return _analyze_aggregate(args)
    print(f"Unknown analyze command: {args.analyze_command}", file=sys.stderr)
    return 1


def _analyze_aggregate(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Run ML metrics aggregation from studio.db into aggregate_metrics.db."""
    from core.analytics.aggregate_metrics import run_aggregation

    result = run_aggregation()
    return _print(result)


def _analyze_intake(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Register a brownfield repo for intake scanning.

    Prompts interactively when stdin is a TTY and --persistent is not passed.
    Non-interactive callers (CI, scripts, pipes) get write_marker=False by default.
    """
    from core.projects.intake import register_project_for_intake

    target_path = Path(args.target_path).resolve()

    # Determine write_marker from flag or interactive prompt
    write_marker: bool = getattr(args, "persistent", False)

    if not write_marker and sys.stdin.isatty():
        print(
            "Scan type:\n"
            "  [1] One-time scan  (default — no marker written, no persistent project)\n"
            "  [2] Persistent project (write .dream-studio-project marker for session attribution)\n"
            "Enter 1 or 2 [1]: ",
            end="",
            flush=True,
        )
        try:
            choice = sys.stdin.readline().strip()
        except OSError:
            choice = ""
        if choice == "2":
            write_marker = True

    result = register_project_for_intake(
        target_path=target_path,
        write_marker=write_marker,
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )

    if not result.get("ok"):
        print(json.dumps(result, indent=2), file=sys.stderr)
        return 1

    project_id = result.get("project_id", "")
    mode_label = "persistent" if write_marker else "one-time scan"
    print(f"✓ Project registered: {project_id} ({mode_label})")
    return 0


def _print(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _config_dispatch(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Dispatch ds config {set,show} commands (WO-FRICTION-CONFIG)."""
    from core.config.authority import list_config, set_config_value

    paths = resolve_installed_runtime_paths(
        source_root=source_root, dream_studio_home=dream_studio_home
    )
    db_path = paths.sqlite_path

    if args.config_command == "set":
        set_config_value(args.key, args.value, db_path)
        return _print({"ok": True, "key": args.key, "value": args.value})

    if args.config_command == "show":
        rows = list_config(db_path)
        return _print({"ok": True, "config": rows, "count": len(rows)})


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


def _default_claude_settings_paths() -> list[str]:
    """Resolve the two generated .claude settings.json copies (hook-projection model).

    Mirrors install: the detected (project or user) scope copy plus the user-global
    copy. Returns deduped absolute path strings so uninstall clears both — nothing
    left hanging.
    """

    paths: list[Path] = []
    try:
        from integrations.detector import detect_claude_code

        detected = detect_claude_code()
        paths.append(Path(detected.config_root) / "settings.json")
    except Exception:  # noqa: BLE001 — detection is best-effort; user-global is the fallback
        pass
    paths.append(Path.home() / ".claude" / "settings.json")
    seen: set[str] = set()
    deduped: list[str] = []
    for p in paths:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            deduped.append(str(p))
    return deduped


def _eval_dispatch(args: argparse.Namespace, *, source_root: Path) -> int:
    """Dispatch ds eval {run,baseline,compare,list} commands (18.8.3)."""
    from core.eval.runner import EvalRunner, format_results_report, load_eval_cases

    evals_dir = Path(args.evals_dir) if getattr(args, "evals_dir", None) else source_root / "evals"

    if args.eval_command == "list":
        cases = load_eval_cases(evals_dir)
        skill = getattr(args, "skill_filter", None)
        if skill:
            cases = [c for c in cases if c.skill_id == skill]
        rows = [
            {
                "eval_id": c.eval_id,
                "version": c.version,
                "skill_id": c.skill_id,
                "description": c.description,
            }
            for c in cases
        ]
        return _print({"evals": rows, "count": len(rows)})

    if args.eval_command == "run":
        runner = EvalRunner(evals_dir=evals_dir)
        eval_id = getattr(args, "eval_id", None)
        skill_filter = getattr(args, "skill_filter", None)
        run_all = getattr(args, "all", False)
        live_mode = getattr(args, "live", False)
        if eval_id:
            from core.eval.schema import EvalCase

            path = evals_dir / f"{eval_id}.json"
            if not path.exists():
                print(
                    json.dumps({"ok": False, "error": f"Eval not found: {eval_id}"}),
                    file=sys.stderr,
                )
                return 1
            case = EvalCase.from_json(path)
            result = runner.run_case(case, live=live_mode)
            out: dict = {
                "eval_id": result.eval_id,
                "passed": result.passed,
                "composite_score": result.composite_score,
                "event_score": result.event_score,
                "behavior_score": getattr(result, "behavior_score", None),
                "run_mode": result.run_mode,
            }
            if live_mode:
                out["delta_from_fixture_baseline"] = round(
                    (result.baseline_score or 0) - result.composite_score, 4
                )
                out["failure_reasons"] = list(
                    result.match_result.missing_events + result.match_result.negative_violations
                )
            return _print(out)
        if run_all or skill_filter:
            results = runner.run_all(skill_filter=skill_filter, live=live_mode)
            report = format_results_report(results)
            print(report)
            passed = sum(1 for r in results if r.passed)
            return 0 if passed == len(results) else 1
        print("Specify --all, --eval-id, or --skill to run evals.", file=sys.stderr)
        return 1

    if args.eval_command == "baseline":
        live_mode = getattr(args, "live", False)
        eval_id = getattr(args, "eval_id", None)
        if live_mode:
            if not eval_id:
                print("--eval-id is required when --live is specified", file=sys.stderr)
                return 1
            from core.eval.schema import EvalCase

            path = evals_dir / f"{eval_id}.json"
            if not path.exists():
                print(
                    json.dumps({"ok": False, "error": f"Eval not found: {eval_id}"}),
                    file=sys.stderr,
                )
                return 1
            case = EvalCase.from_json(path)
            runner = EvalRunner(evals_dir=evals_dir)
            result = runner.run_case(case, live=True)
            from core.eval.baseline import load_baseline

            live_baseline = load_baseline(eval_id + ":live", case.version)
            return _print(
                {
                    "eval_id": eval_id,
                    "live_baseline_score": (
                        live_baseline["baseline_score"] if live_baseline else result.composite_score
                    ),
                    "passed": result.passed,
                    "run_mode": result.run_mode,
                }
            )
        from core.eval.baseline import get_all_baselines

        rows = get_all_baselines()
        return _print({"baselines": rows, "count": len(rows)})

    if args.eval_command == "compare":
        from core.eval.baseline import load_baseline

        eval_id = getattr(args, "eval_id", None)
        if not eval_id:
            print("--eval-id required for compare", file=sys.stderr)
            return 1
        baseline = load_baseline(eval_id, "1.0.0")
        if baseline is None:
            print(json.dumps({"ok": False, "error": f"No baseline for {eval_id}"}), file=sys.stderr)
            return 1
        return _print({"eval_id": eval_id, "baseline": baseline})

    if args.eval_command == "registry":
        return _eval_registry_dispatch(args, source_root=source_root)

    if args.eval_command == "queue":
        return _eval_queue_dispatch(args, evals_dir=evals_dir)

    print(f"Unknown eval command: {args.eval_command}", file=sys.stderr)
    return 1


def _eval_registry_dispatch(args: argparse.Namespace, *, source_root: Path) -> int:
    """Dispatch ds eval registry {list,show} commands (WO-EVAL-REGISTRY)."""
    from core.config.database import DatabaseRuntime

    db_path = DatabaseRuntime.get_instance().db_path
    import sqlite3

    registry_command = getattr(args, "registry_command", None)

    if registry_command == "list":
        target_type = getattr(args, "target_type", None)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if not _table_exists_in_conn(conn, "eval_registry"):
                return _print(
                    {"ok": False, "error": "eval_registry table not found. Run migrations."}
                )
            where = "WHERE er.target_type = ?" if target_type else ""
            params = [target_type] if target_type else []
            rows = conn.execute(
                f"""
                SELECT
                    er.eval_id,
                    er.target_type,
                    er.target_id,
                    er.rubric_score,
                    er.last_run_at,
                    er.friction_flag,
                    COALESCE(dr.passed, hr.passed, NULL) AS passed
                FROM eval_registry er
                LEFT JOIN ds_eval_runs dr ON dr.run_id = er.last_run_id
                LEFT JOIN hook_eval_runs hr
                    ON er.target_type = 'hook' AND hr.hook_id = er.target_id
                    AND hr.created_at = er.last_run_at
                {where}
                ORDER BY er.target_type, er.target_id
                """,
                params,
            ).fetchall()
        result = [
            {
                "eval_id": r["eval_id"],
                "target_type": r["target_type"],
                "target_id": r["target_id"],
                "rubric_score": r["rubric_score"],
                "last_run_at": r["last_run_at"],
                "passed": "Y" if r["passed"] else ("N" if r["passed"] is not None else "—"),
                "friction_flag": bool(r["friction_flag"]),
            }
            for r in rows
        ]
        return _print({"registry": result, "count": len(result)})

    if registry_command == "show":
        target_id = getattr(args, "target_id", None)
        if not target_id:
            print("target_id required", file=sys.stderr)
            return 1
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if not _table_exists_in_conn(conn, "eval_registry"):
                return _print(
                    {"ok": False, "error": "eval_registry table not found. Run migrations."}
                )
            entry = conn.execute(
                "SELECT * FROM eval_registry WHERE target_id = ?", (target_id,)
            ).fetchone()
            if entry is None:
                return _print(
                    {"ok": False, "error": f"No registry entry for target_id={target_id!r}"}
                )
            # Fetch run history depending on target type
            target_type = entry["target_type"]
            if target_type == "hook":
                runs = conn.execute(
                    """SELECT run_id, eval_type, passed, score, failure_reasons, created_at
                    FROM hook_eval_runs WHERE hook_id = ?
                    ORDER BY created_at DESC LIMIT 20""",
                    (target_id,),
                ).fetchall()
                run_rows = [dict(r) for r in runs]
            else:
                runs = conn.execute(
                    """SELECT run_id, eval_id, eval_version, total_score, passed,
                    failure_reasons, started_at, completed_at
                    FROM ds_eval_runs WHERE eval_id = ?
                    ORDER BY started_at DESC LIMIT 20""",
                    (target_id,),
                ).fetchall()
                run_rows = [dict(r) for r in runs]
        return _print(
            {
                "target_id": target_id,
                "target_type": target_type,
                "rubric_score": entry["rubric_score"],
                "last_run_at": entry["last_run_at"],
                "friction_flag": bool(entry["friction_flag"]),
                "runs": run_rows,
            }
        )

    print(f"Unknown registry command: {registry_command}", file=sys.stderr)
    return 1


def _eval_queue_dispatch(args: argparse.Namespace, *, evals_dir: Path) -> int:
    """Dispatch ds eval queue {show,run,aggregate} commands (WO-EVAL-LOOP)."""
    from core.config.database import DatabaseRuntime
    import sqlite3

    db_path = DatabaseRuntime.get_instance().db_path
    queue_command = getattr(args, "queue_command", None)

    if queue_command == "aggregate":
        from core.eval.friction import aggregate_friction_signals

        result = aggregate_friction_signals(db_path=db_path)
        return _print(result)

    if queue_command == "show":
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if not _table_exists_in_conn(conn, "eval_registry"):
                return _print(
                    {"ok": False, "error": "eval_registry table not found. Run migrations."}
                )
            rows = conn.execute("""
                SELECT eval_id, target_type, target_id, rubric_score,
                       last_run_at, friction_flag, pending_rerun, updated_at
                FROM eval_registry
                WHERE pending_rerun = 1
                ORDER BY updated_at DESC
                """).fetchall()
        return _print({"pending_rerun": [dict(r) for r in rows], "count": len(rows)})

    if queue_command == "run":
        from core.eval.runner import EvalRunner
        from core.eval.schema import EvalCase

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if not _table_exists_in_conn(conn, "eval_registry"):
                return _print(
                    {"ok": False, "error": "eval_registry table not found. Run migrations."}
                )
            pending = conn.execute(
                "SELECT target_id, target_type FROM eval_registry WHERE pending_rerun = 1"
            ).fetchall()

        runner = EvalRunner(evals_dir=evals_dir)
        results = []
        for row in pending:
            target_id = row["target_id"]
            path = evals_dir / f"{target_id}.json"
            if not path.exists():
                results.append(
                    {"target_id": target_id, "status": "skipped", "reason": "eval case not found"}
                )
                continue
            case = EvalCase.from_json(path)
            result = runner.run_case(case, live=True)
            if result.passed:
                with sqlite3.connect(db_path) as conn:
                    conn.execute(
                        "UPDATE eval_registry"
                        " SET friction_flag=0, pending_rerun=0, updated_at=datetime('now')"
                        " WHERE target_id=?",
                        (target_id,),
                    )
            results.append(
                {
                    "target_id": target_id,
                    "passed": result.passed,
                    "composite_score": result.composite_score,
                    "friction_cleared": result.passed,
                }
            )
        return _print({"results": results, "count": len(results)})

    print(f"Unknown queue command: {queue_command}", file=sys.stderr)
    return 1


def _table_exists_in_conn(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone()
    return row is not None


if __name__ == "__main__":
    raise SystemExit(main())
