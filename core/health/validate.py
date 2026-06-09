"""Validation status — SQLite + schema + module-profile readiness."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config.sqlite_bootstrap import latest_migration_version, pending_migrations_info
from core.event_store.studio_db import _connect
from core.module_profiles import validate_module_profiles


def run_validation(
    *,
    source_root: Path,
    dream_studio_home: Path | None = None,
) -> dict[str, Any]:
    # Lazy import via ds.py so test patches at `interfaces.cli.ds.resolve_installed_runtime_paths` apply.
    from interfaces.cli.ds import resolve_installed_runtime_paths

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    profile_errors = validate_module_profiles()
    db_exists = paths.sqlite_path.exists()
    schema_version: int | None = None
    if db_exists:
        with _connect(paths.sqlite_path) as conn:
            schema_version = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
    pending = pending_migrations_info()
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
        "pending_activation_count": len(pending),
        "pending_activation_migrations": [m["version"] for m in pending],
        "module_profile_errors": profile_errors,
        "ready": db_exists and not profile_errors,
        "doctor_runs_read_only": True,
    }
