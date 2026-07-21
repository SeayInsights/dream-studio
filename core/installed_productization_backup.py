"""Runtime backup and restore flows.

WO-GF-INSTALLED-PROD: split from ``core/installed_productization.py``. Holds the
backup planner/executor and the restore validate/execute flows. No logic
changes — extracted verbatim from the original module.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.config.sqlite_bootstrap import latest_migration_version
from core.installed_runtime import resolve_installed_runtime_paths

from .installed_productization_shared import _timestamp_slug, _write_json


def backup_runtime(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    backup_dir: str | Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Plan or perform a local runtime backup inside an explicit backup dir."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    target_dir = Path(backup_dir or paths.dream_studio_home / "backups").resolve()
    backup_id = f"backup-{_timestamp_slug()}"
    sqlite_exists = paths.sqlite_path.exists()
    if execute:
        target = target_dir / backup_id
        target.mkdir(parents=True, exist_ok=True)
        if sqlite_exists:
            shutil.copy2(paths.sqlite_path, target / "studio.db")
        _write_json(target / "backup-manifest.json", _backup_manifest(paths, backup_id))
        status = "created"
        backup_path = str(target)
    else:
        status = "planned"
        backup_path = str(target_dir / backup_id)
    return {
        "model_name": "dream_studio_runtime_backup",
        "status": status,
        "backup_id": backup_id,
        "backup_path": backup_path,
        "sqlite_exists": sqlite_exists,
        "execute": execute,
        "destructive": False,
        "runtime_state_write": execute,
        "live_state_mutation": False,
        "requires_operator_approval_for_live_home": execute,
    }


def restore_runtime_check(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    backup_path: str | Path,
) -> dict[str, Any]:
    """Validate that a backup can be restored without performing the restore."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    backup = Path(backup_path).resolve()
    sqlite_backup = backup / "studio.db"
    manifest = backup / "backup-manifest.json"
    return {
        "model_name": "dream_studio_runtime_restore_check",
        "backup_path": str(backup),
        "target_home": str(paths.dream_studio_home),
        "backup_exists": backup.exists(),
        "sqlite_backup_exists": sqlite_backup.exists(),
        "manifest_exists": manifest.exists(),
        "restore_ready": backup.exists() and sqlite_backup.exists(),
        "restore_executed": False,
        "destructive": False,
        "requires_operator_approval": True,
    }


_RESTORABLE_STATE_FILES: tuple[str, ...] = ("studio.db", "files.db")


def restore_runtime(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    backup_path: str | Path,
    backup_dir: str | Path | None = None,
    execute: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Restore Dream Studio state from a backup, reversibly.

    Companion to ``restore_runtime_check`` (validate-only) and to the
    backup-before-mutation pattern used by install/update/uninstall.

    - Default (``execute=False``): dry-run. Validates the backup via
      ``restore_runtime_check`` and returns the plan. Mutates nothing.
    - ``execute=True``: takes a pre-restore backup of the CURRENT state FIRST
      (so the restore is itself reversible), then replaces the state-tier
      databases (``studio.db`` / ``files.db``) from the chosen backup.

    Refuses a backup that is not restore-ready unless ``force=True``.
    """

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    home = paths.dream_studio_home
    state_dir = home / "state"
    backup = Path(backup_path).resolve()

    check = restore_runtime_check(
        source_root=paths.source_root,
        dream_studio_home=home,
        backup_path=backup,
    )
    # Restore exactly the state files present in the CHOSEN backup directory.
    restorable = [name for name in _RESTORABLE_STATE_FILES if (backup / name).is_file()]

    result: dict[str, Any] = {
        "model_name": "dream_studio_runtime_restore",
        "backup_path": str(backup),
        "target_home": str(home),
        "execute": execute,
        "force": force,
        "restore_check": check,
        "restore_ready": check["restore_ready"],
        "restorable_files": restorable,
        "pre_restore_backup_path": None,
        "restored_files": [],
        "restore_executed": False,
        "requires_operator_approval": True,
    }

    if not check["restore_ready"] and not force:
        result["status"] = "refused"
        result["error"] = (
            "Backup is not restore-ready (missing backup dir or studio.db). "
            "Use --force to override."
        )
        return result

    if not execute:
        result["status"] = "planned"
        return result

    # T2 — pre-restore safety backup of CURRENT state FIRST, written outside the
    # home so a subsequent purge cannot destroy it. Makes the restore reversible.
    backup_root = Path(backup_dir or home.parent / f"{home.name}-restore-backups").resolve()
    pre = backup_runtime(
        source_root=paths.source_root,
        dream_studio_home=home,
        backup_dir=backup_root,
        execute=True,
    )
    result["pre_restore_backup_path"] = pre["backup_path"]

    # Replace the state-tier databases from the chosen backup. Clear the live
    # WAL/SHM sidecars first: copying only the main .db while a stale -wal exists
    # would let uncommitted frames mask the restored data (WAL mode).
    state_dir.mkdir(parents=True, exist_ok=True)
    restored: list[str] = []
    for name in restorable:
        target = state_dir / name
        for sidecar in (target, state_dir / f"{name}-wal", state_dir / f"{name}-shm"):
            if sidecar.exists():
                sidecar.unlink()
        shutil.copy2(backup / name, target)
        restored.append(name)
    result["restored_files"] = restored
    result["restore_executed"] = True
    result["status"] = "restored"
    return result


def _backup_manifest(paths: Any, backup_id: str) -> dict[str, Any]:
    return {
        "backup_id": backup_id,
        "source_home": str(paths.dream_studio_home),
        "sqlite_path": str(paths.sqlite_path),
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": latest_migration_version(),
        "restore_requires_operator_approval": True,
    }
