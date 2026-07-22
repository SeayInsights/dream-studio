"""ds system command group — install/backup/restore/uninstall/rehearsal lifecycle.

Split from interfaces/cli/commands/system.py (WO-GF-CLI-split). The facade at
interfaces/cli/commands/system.py re-exports this module's public+private
surface; interfaces/cli/commands/system_dispatch.py composes register_lifecycle()/
dispatch_lifecycle() together with the other three group siblings.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from interfaces.cli.cli_utils import (
    _default_claude_settings_paths,
    _print,
    _require_home_for_install,
)

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------

#: Commands handled by this group.
LIFECYCLE_COMMANDS = frozenset(
    {
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
        "rehearsal-install",
    }
)


def register_lifecycle(subcommands: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Attach install/backup/restore/uninstall/rehearsal subparsers."""

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

    rehearsal = subcommands.add_parser("rehearsal-install", help="Bootstrap a rehearsal runtime")
    rehearsal.add_argument("--rehearsal-home", required=True)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch_lifecycle(
    args: argparse.Namespace,
    *,
    source_root: Path,
    dream_studio_home: Path | None,
) -> int:
    """Route an install/backup/restore/uninstall/rehearsal command."""
    from core.installed_runtime import bootstrap_rehearsal_runtime
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

    return 1
