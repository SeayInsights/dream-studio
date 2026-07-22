"""ds system-level command group — flat/system commands.

This module handles all the flat/system-level commands that don't belong to a
named entity group: status, version, doctor, repair, update, dashboard,
validate, migrate, modules, adapters, router, platform-hardening, policy,
contract-atlas, analytics-ingest, install, install-command, acceptance,
backup, restore, restore-check, update-check, uninstall, uninstall-check,
migrate-legacy, repair-adapters, rollback-check, context-packet,
rehearsal-install, and the delegated add_*_subcommand groups.

WO-GF-CLI-split: this module is now a thin facade. The command set is
partitioned into four content siblings by cohesive group —
``system_health`` (status/doctor/validate/migrate/...), ``system_dashboard``
(dashboard), ``system_analytics`` (contract-atlas/policy/analytics-ingest/
context-packet), and ``system_lifecycle`` (install/backup/restore/uninstall/
rehearsal) — composed by ``system_dispatch``. Every public and private name
that used to live here is re-exported below so existing imports and test
patches (``interfaces.cli.commands.system.<name>``) keep working unchanged.
"""

from __future__ import annotations

from interfaces.cli.commands.system_analytics import (
    ANALYTICS_COMMANDS,
    _analytics_ingest,
    dispatch_analytics,
    register_analytics,
)
from interfaces.cli.commands.system_dashboard import (
    DASHBOARD_COMMANDS,
    _dashboard_check,
    _dashboard_client_host,
    _dashboard_env,
    _dashboard_http_status,
    _dashboard_open,
    _dashboard_port_in_use,
    _dashboard_serve,
    _dashboard_status,
    _refresh_derived_store,
    _wait_for_dashboard,
    dispatch_dashboard,
    register_dashboard,
)
from interfaces.cli.commands.system_dispatch import SYSTEM_COMMANDS, dispatch, register
from interfaces.cli.commands.system_health import (
    HEALTH_COMMANDS,
    _canonical_hook_drift,
    _check_agents_installed,
    _check_dispatcher_hooks,
    _check_failed_events,
    _check_skills_installed,
    _check_version_current,
    _doctor_status,
    _get_expected_skill_ids,
    _migrate_command,
    _repair_plan,
    _update_command,
    _validate_status,
    _version_status,
    dispatch_health,
    register_health,
)
from interfaces.cli.commands.system_lifecycle import (
    LIFECYCLE_COMMANDS,
    dispatch_lifecycle,
    register_lifecycle,
)

__all__ = [
    # Composed facade surface
    "SYSTEM_COMMANDS",
    "register",
    "dispatch",
    # Group command sets
    "HEALTH_COMMANDS",
    "DASHBOARD_COMMANDS",
    "ANALYTICS_COMMANDS",
    "LIFECYCLE_COMMANDS",
    # Group register/dispatch functions
    "register_health",
    "dispatch_health",
    "register_dashboard",
    "dispatch_dashboard",
    "register_analytics",
    "dispatch_analytics",
    "register_lifecycle",
    "dispatch_lifecycle",
    # system_health private helpers
    "_version_status",
    "_check_dispatcher_hooks",
    "_get_expected_skill_ids",
    "_check_skills_installed",
    "_check_agents_installed",
    "_check_failed_events",
    "_check_version_current",
    "_doctor_status",
    "_canonical_hook_drift",
    "_update_command",
    "_repair_plan",
    "_validate_status",
    "_migrate_command",
    # system_dashboard private helpers
    "_dashboard_status",
    "_refresh_derived_store",
    "_dashboard_serve",
    "_dashboard_open",
    "_dashboard_check",
    "_dashboard_env",
    "_dashboard_port_in_use",
    "_dashboard_client_host",
    "_wait_for_dashboard",
    "_dashboard_http_status",
    # system_analytics private helpers
    "_analytics_ingest",
]
