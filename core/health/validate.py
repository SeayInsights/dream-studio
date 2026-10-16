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
    authority_error: str | None = None
    if db_exists:
        # Read-only: validation reports the schema, it does not migrate it. The migrating
        # _connect() applied pending migrations and set the journal mode on every call,
        # under a payload that says doctor_runs_read_only.
        from core.config.sqlite_readonly import connect_read_only

        try:
            conn = connect_read_only(paths.sqlite_path, timeout=30.0)
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
        except sqlite3.DatabaseError as exc:
            # A file that is not a database is reported with the way back, not raised as
            # a bare "file is not a database".
            from core.config.sqlite_bootstrap import unreadable_authority_message

            authority_error = unreadable_authority_message(paths.sqlite_path, exc)
    pending = [] if authority_error else pending_migrations_info(paths.sqlite_path)
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
        "ready": db_exists and not profile_errors and not authority_error,
        **({"authority_error": authority_error} if authority_error else {}),
        "doctor_runs_read_only": True,
    }
