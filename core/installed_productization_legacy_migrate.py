"""Legacy-install migration and adapter-surface repair.

WO-GF-INSTALLED-PROD: split from ``core/installed_productization.py``. Holds the
mutating legacy-upgrade flow (backup-first fresh active install + compatible
SQLite authority copy) and the launcher/adapter-hook repair flow, plus their
private helpers. No logic changes — extracted verbatim from the original module.
"""

from __future__ import annotations

import gc
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from core.installed_runtime import CONFIG_RELATIVE_PATH, resolve_installed_runtime_paths

from .installed_productization_legacy_detect import (
    _read_json_if_object,
    _verify_sqlite_read_only,
    detect_legacy_install,
)
from .installed_productization_setup import first_run_setup, install_global_command_surface
from .installed_productization_shared import (
    DEFAULT_GLOBAL_COMMAND_DIR,
    DEFAULT_INSTALL_PROFILES,
    _timestamp_slug,
    _write_json,
)

LEGACY_BACKUP_ROOT_NAME = "Dream Studio Legacy Backups"
SQLITE_COPY_EXCLUDED_PREFIXES: tuple[str, ...] = ("sqlite_",)
SQLITE_COPY_EXCLUDED_SUFFIXES: tuple[str, ...] = (
    "_fts",
    "_fts_data",
    "_fts_idx",
    "_fts_docsize",
    "_fts_config",
)
SQLITE_COPY_EXCLUDED_TABLES: set[str] = {
    "_schema_version",
    "canonical_events",
    "legacy_canonical_event_import_map",
}


def migrate_legacy_install(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    backup_root: str | Path | None = None,
    command_dir: str | Path | None = None,
    claude_settings_path: str | Path | None = None,
    codex_home: str | Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Plan or execute a fresh active install from a legacy runtime home."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    backup_base = Path(backup_root or paths.dream_studio_home.parent / LEGACY_BACKUP_ROOT_NAME)
    backup_path = backup_base / f".dream-studio-legacy-upgrade-{_timestamp_slug()}"
    detection = detect_legacy_install(
        source_root=paths.source_root,
        dream_studio_home=paths.dream_studio_home,
        command_dir=command_dir,
        claude_settings_path=claude_settings_path,
        codex_home=codex_home,
    )
    planned_writes = [
        str(backup_path),
        str(paths.dream_studio_home),
        str(paths.sqlite_path),
        str(paths.dream_studio_home / CONFIG_RELATIVE_PATH),
    ]
    if command_dir:
        planned_writes.extend(
            [
                str(Path(command_dir).resolve() / "ds.cmd"),
                str(Path(command_dir).resolve() / "ds.ps1"),
            ]
        )
    dry_run = {
        "model_name": "dream_studio_legacy_install_migration",
        "status": "dry_run" if not execute else "pending",
        "execute": execute,
        "current_source_path": str(paths.source_root),
        "installed_runtime_path": str(paths.dream_studio_home),
        "backup_path": str(backup_path),
        "planned_writes": planned_writes,
        "detection": detection,
        "strategy": {
            "backup_first": True,
            "fresh_active_home": True,
            "apply_current_migrations": True,
            "copy_legacy_file_sprawl_forward": False,
            "compatible_sqlite_authority_only": True,
            "merge_unrelated_git_histories": False,
            "delete_old_source_or_backups": False,
            "inspect_secrets": False,
        },
        "rollback_instructions": [
            "Stop Dream Studio commands.",
            "Move the fresh active .dream-studio aside.",
            "Restore the backed-up .dream-studio directory from backup_path.",
            "Re-run ds rollback-check --backup-path <backup_path> before resuming.",
        ],
    }
    if not execute:
        return dry_run
    if not paths.dream_studio_home.exists():
        raise RuntimeError("Cannot migrate legacy install because the runtime home does not exist.")

    gc.collect()
    backup_base.mkdir(parents=True, exist_ok=True)
    backup_runtime_path = backup_path / "runtime-home"
    shutil.copytree(paths.dream_studio_home, backup_runtime_path)
    _write_json(backup_path / "legacy-detection.json", detection)
    _write_text(
        backup_path / "ROLLBACK.txt",
        "\n".join(dry_run["rollback_instructions"]) + "\n",
    )
    backup_verified = _verify_sqlite_read_only(backup_runtime_path / "state" / "studio.db")

    moved_runtime_path = backup_path / "previous-active-runtime-home"
    gc.collect()
    shutil.move(str(paths.dream_studio_home), str(moved_runtime_path))
    setup = first_run_setup(
        source_root=paths.source_root,
        dream_studio_home=paths.dream_studio_home,
        profiles=DEFAULT_INSTALL_PROFILES,
        rehearsal=False,
    )
    migration = _migrate_compatible_sqlite_authority(
        source_db=backup_runtime_path / "state" / "studio.db",
        target_db=paths.sqlite_path,
    )
    launcher = None
    if command_dir:
        launcher = install_global_command_surface(
            source_root=paths.source_root,
            dream_studio_home=paths.dream_studio_home,
            command_dir=command_dir,
            execute=True,
        )
    adapter_repair = repair_adapter_surfaces(
        source_root=paths.source_root,
        dream_studio_home=paths.dream_studio_home,
        command_dir=command_dir,
        claude_settings_path=claude_settings_path,
        codex_home=codex_home,
        previous_source_root=detection.get("configured_source_root"),
        execute=True,
    )
    return {
        **dry_run,
        "status": "migrated",
        "backup_verified": backup_verified,
        "backup_runtime_path": str(backup_runtime_path),
        "moved_previous_runtime_path": str(moved_runtime_path),
        "fresh_setup": setup,
        "sqlite_migration": migration,
        "launcher_refresh": launcher,
        "adapter_repair": adapter_repair,
        "old_file_sprawl_copied_forward": False,
        "destructive_sqlite_mutation": False,
        "external_projects_mutated": False,
    }


def repair_adapter_surfaces(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    command_dir: str | Path | None = None,
    claude_settings_path: str | Path | None = None,
    codex_home: str | Path | None = None,
    previous_source_root: str | Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Plan or repair Dream-Studio-owned launchers and adapter hook paths."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    command_target = Path(command_dir).resolve() if command_dir else DEFAULT_GLOBAL_COMMAND_DIR
    detection = detect_legacy_install(
        source_root=paths.source_root,
        dream_studio_home=paths.dream_studio_home,
        command_dir=command_target,
        claude_settings_path=claude_settings_path,
        codex_home=codex_home,
    )
    planned_writes = [str(command_target / "ds.cmd"), str(command_target / "ds.ps1")]
    if claude_settings_path:
        planned_writes.append(str(Path(claude_settings_path).resolve()))
    result: dict[str, Any] = {
        "model_name": "dream_studio_adapter_surface_repair",
        "status": "planned",
        "execute": execute,
        "source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "planned_writes": planned_writes,
        "detection": detection,
        "secret_values_read": False,
        "external_projects_mutated": False,
        "adapter_hooks_repaired": 0,
        "launchers_repaired": 0,
    }
    if not execute:
        return result
    launcher = install_global_command_surface(
        source_root=paths.source_root,
        dream_studio_home=paths.dream_studio_home,
        command_dir=command_target,
        execute=True,
    )
    result["launchers_repaired"] = len(launcher["written"])
    if claude_settings_path and previous_source_root:
        result["adapter_hooks_repaired"] = sum(
            _replace_source_in_dream_studio_json_strings(
                Path(claude_settings_path).resolve(),
                old=old_source,
                new=str(paths.source_root),
            )
            for old_source in sorted(
                {str(previous_source_root), str(Path(previous_source_root).resolve())}
            )
        )
    result["status"] = "repaired"
    result["launcher_refresh"] = launcher
    return result


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _migrate_compatible_sqlite_authority(*, source_db: Path, target_db: Path) -> dict[str, Any]:
    if not source_db.exists():
        return {
            "status": "skipped",
            "reason": "legacy_sqlite_missing",
            "migrated_tables": [],
            "skipped_tables": [],
        }
    migrated = []
    skipped = []
    with (
        closing(sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)) as src,
        closing(sqlite3.connect(str(target_db))) as dst,
    ):
        src.row_factory = sqlite3.Row
        dst.row_factory = sqlite3.Row
        source_tables = _table_names(src)
        target_tables = _table_names(dst)
        for table in sorted(source_tables & target_tables):
            if _skip_sqlite_copy_table(table):
                skipped.append({"table": table, "reason": "excluded_rebuildable_or_legacy"})
                continue
            source_columns = _table_columns(src, table)
            target_columns = _table_columns(dst, table)
            common_columns = [column for column in source_columns if column in target_columns]
            if not common_columns:
                skipped.append({"table": table, "reason": "no_common_columns"})
                continue
            rows = src.execute(
                f"SELECT {', '.join(_q(column) for column in common_columns)} FROM {_q(table)}"
            ).fetchall()
            inserted = 0
            if rows:
                placeholders = ", ".join("?" for _ in common_columns)
                sql = (
                    f"INSERT OR IGNORE INTO {_q(table)} "
                    f"({', '.join(_q(column) for column in common_columns)}) "
                    f"VALUES ({placeholders})"
                )
                for row in rows:
                    before = dst.total_changes
                    dst.execute(sql, [row[column] for column in common_columns])
                    inserted += dst.total_changes - before
            migrated.append(
                {
                    "table": table,
                    "source_rows": len(rows),
                    "inserted_rows": inserted,
                    "common_column_count": len(common_columns),
                    "source_ref": f"{source_db.name}:{table}",
                }
            )
        dst.commit()
    return {
        "status": "pass",
        "migrated_tables": migrated,
        "skipped_tables": skipped,
        "source_refs_preserved": True,
        "legacy_tables_recreated": False,
    }


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        if not str(row[0]).startswith("sqlite_")
    }


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({_q(table)})")]


def _skip_sqlite_copy_table(table: str) -> bool:
    return (
        table in SQLITE_COPY_EXCLUDED_TABLES
        or table.startswith(SQLITE_COPY_EXCLUDED_PREFIXES)
        or table.endswith(SQLITE_COPY_EXCLUDED_SUFFIXES)
    )


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _replace_source_in_dream_studio_json_strings(path: Path, *, old: str, new: str) -> int:
    data = _read_json_if_object(path)
    if not data:
        return 0
    data, changed, replaced = _replace_source_in_value(data, old=old, new=new)
    if changed:
        _write_json(path, data)
    return replaced


def _replace_source_in_value(value: Any, *, old: str, new: str) -> tuple[Any, bool, int]:
    if isinstance(value, dict):
        changed = False
        replaced = 0
        for key, item in value.items():
            new_item, item_changed, item_replaced = _replace_source_in_value(item, old=old, new=new)
            changed = changed or item_changed
            replaced += item_replaced
            value[key] = new_item
        return value, changed, replaced
    if isinstance(value, list):
        changed = False
        replaced = 0
        for index, item in enumerate(value):
            new_item, item_changed, item_replaced = _replace_source_in_value(item, old=old, new=new)
            changed = changed or item_changed
            replaced += item_replaced
            value[index] = new_item
        return value, changed, replaced
    if isinstance(value, str) and old in value and "dream-studio" in value.lower():
        return value.replace(old, new), True, 1
    return value, False, 0
