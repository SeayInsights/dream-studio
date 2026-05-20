"""Version status — repo migration version, source root, dream-studio home."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config.sqlite_bootstrap import latest_migration_version


def get_version(
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
