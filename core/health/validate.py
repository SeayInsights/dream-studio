"""Validation status — SQLite + schema + module-profile readiness."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.config.sqlite_bootstrap import latest_migration_version, pending_migrations_info
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
        # Read-only: validation reports the schema, it does not migrate it. The migrating
        # _connect() applied pending migrations and set the journal mode on every call,
        # under a payload that says doctor_runs_read_only.
        conn = sqlite3.connect(
            f"{paths.sqlite_path.resolve().as_uri()}?mode=ro", uri=True, timeout=30.0
        )
        try:
            # A file with no schema yet reports None, as a missing file does.
            has_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = '_schema_version'"
            ).fetchone()
            if has_table:
                schema_version = conn.execute(
                    "SELECT MAX(version) FROM _schema_version"
                ).fetchone()[0]
        finally:
            conn.close()
    pending = pending_migrations_info(paths.sqlite_path)
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
