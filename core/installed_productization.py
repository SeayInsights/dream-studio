"""Installed platform productization flows for Dream Studio — facade.

These helpers are designed for first-run setup and rehearsal validation. They
write only to the explicitly supplied Dream Studio home and never assume the
caller's current working directory is the source checkout.

WO-GF-INSTALLED-PROD: implementation moved to installed_productization_{shared,
setup,backup,legacy_detect,legacy_migrate,uninstall,acceptance}.py; this module
re-exports the public API so existing
``from core.installed_productization import X`` callers are unchanged.
"""

from __future__ import annotations

from .installed_productization_acceptance import (
    final_installed_modular_platform_closeout,
    productization_acceptance_report,
)
from .installed_productization_backup import (
    backup_runtime,
    restore_runtime,
    restore_runtime_check,
)
from .installed_productization_legacy_detect import (
    LEGACY_SPRAWL_CANDIDATES,
    detect_legacy_install,
    rollback_runtime_check,
    update_runtime_check,
)
from .installed_productization_legacy_migrate import (
    LEGACY_BACKUP_ROOT_NAME,
    SQLITE_COPY_EXCLUDED_PREFIXES,
    SQLITE_COPY_EXCLUDED_SUFFIXES,
    SQLITE_COPY_EXCLUDED_TABLES,
    migrate_legacy_install,
    repair_adapter_surfaces,
)
from .installed_productization_setup import (
    dashboard_onboarding_status,
    first_run_setup,
    install_global_command_surface,
)
from .installed_productization_shared import (
    DEFAULT_GLOBAL_COMMAND_DIR,
    DEFAULT_INSTALL_PROFILES,
    PRODUCTIZATION_VERSION,
)
from .installed_productization_uninstall import (
    uninstall_runtime,
    uninstall_runtime_check,
)

__all__ = [
    "DEFAULT_GLOBAL_COMMAND_DIR",
    "DEFAULT_INSTALL_PROFILES",
    "LEGACY_BACKUP_ROOT_NAME",
    "LEGACY_SPRAWL_CANDIDATES",
    "PRODUCTIZATION_VERSION",
    "SQLITE_COPY_EXCLUDED_PREFIXES",
    "SQLITE_COPY_EXCLUDED_SUFFIXES",
    "SQLITE_COPY_EXCLUDED_TABLES",
    "backup_runtime",
    "dashboard_onboarding_status",
    "detect_legacy_install",
    "final_installed_modular_platform_closeout",
    "first_run_setup",
    "install_global_command_surface",
    "migrate_legacy_install",
    "productization_acceptance_report",
    "repair_adapter_surfaces",
    "restore_runtime",
    "restore_runtime_check",
    "rollback_runtime_check",
    "uninstall_runtime",
    "uninstall_runtime_check",
    "update_runtime_check",
]
