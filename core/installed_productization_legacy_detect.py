"""Legacy-install detection and update/rollback readiness checks.

WO-GF-INSTALLED-PROD: split from ``core/installed_productization.py``. Holds the
non-mutating detection surfaces (update readiness, legacy-install detection,
rollback check) and their private helpers. No logic changes — extracted
verbatim from the original module.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from core.config.sqlite_bootstrap import applied_schema_version, latest_migration_version
from core.event_store.studio_db import _connect
from core.installed_runtime import CONFIG_RELATIVE_PATH, resolve_installed_runtime_paths

from .installed_productization_shared import DEFAULT_GLOBAL_COMMAND_DIR

LEGACY_SPRAWL_CANDIDATES: tuple[str, ...] = (
    "work-orders",
    "handoffs",
    "reports",
    "evidence",
    "audit",
    "audits",
    "generated-prompts",
    "prompts",
    "cache",
    "caches",
    "logs",
    "meta/work-orders",
    "meta/handoffs",
    "meta/reports",
    "meta/evidence",
    "meta/audit",
    "meta/generated-prompts",
)


def update_runtime_check(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
) -> dict[str, Any]:
    """Return update readiness without mutating the installed runtime."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    schema_version = None
    if paths.sqlite_path.exists():
        conn = _connect(paths.sqlite_path)
        try:
            schema_version = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
        finally:
            conn.close()
    return {
        "model_name": "dream_studio_runtime_update_check",
        "source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "sqlite_exists": paths.sqlite_path.exists(),
        "schema_version": schema_version,
        "latest_migration_version": latest_migration_version(),
        "update_ready": paths.sqlite_path.exists()
        and (schema_version is None or int(schema_version) <= latest_migration_version()),
        "update_executed": False,
        "requires_backup_before_live_update": True,
        "live_state_mutated": False,
        "legacy_install_detection": detect_legacy_install(
            source_root=paths.source_root,
            dream_studio_home=paths.dream_studio_home,
        ),
    }


def detect_legacy_install(
    *,
    source_root: str | Path,
    dream_studio_home: str | Path,
    command_dir: str | Path | None = None,
    claude_settings_path: str | Path | None = None,
    codex_home: str | Path | None = None,
) -> dict[str, Any]:
    """Detect old install surfaces without mutating or printing secrets."""

    paths = resolve_installed_runtime_paths(
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )
    config_path = paths.dream_studio_home / CONFIG_RELATIVE_PATH
    runtime_config = _read_json_if_object(config_path)
    configured_source = runtime_config.get("source_root") if runtime_config else None
    source_mismatch = bool(
        configured_source and Path(configured_source).resolve() != paths.source_root
    )
    schema_version = _sqlite_schema_version(paths.sqlite_path)
    legacy_sprawl = _legacy_sprawl(paths.dream_studio_home)
    launcher_report = _launcher_path_report(
        command_dir=Path(command_dir).resolve() if command_dir else DEFAULT_GLOBAL_COMMAND_DIR,
        current_source=paths.source_root,
    )
    adapter_config_report = _adapter_config_path_report(
        source_root=paths.source_root,
        claude_settings_path=claude_settings_path,
        codex_home=codex_home,
    )
    stale_env = _stale_environment_report(paths.source_root, paths.dream_studio_home)
    unknown_manual_review = []
    if paths.dream_studio_home.exists() and not paths.sqlite_path.exists() and legacy_sprawl:
        unknown_manual_review.append("runtime_state_without_current_sqlite_authority")
    if configured_source and not Path(configured_source).exists():
        unknown_manual_review.append("runtime_config_source_path_missing")
    old_schema = schema_version is not None and schema_version < latest_migration_version()
    status = (
        "legacy_detected"
        if any(
            (
                source_mismatch,
                paths.dream_studio_home.exists() and old_schema,
                legacy_sprawl,
                launcher_report["stale_launcher_count"],
                adapter_config_report["stale_adapter_config_count"],
                stale_env["stale_env_count"],
                unknown_manual_review,
            )
        )
        else "current_or_not_installed"
    )
    return {
        "model_name": "dream_studio_legacy_install_detection",
        "derived_view": True,
        "primary_authority": False,
        "status": status,
        "current_source_root": str(paths.source_root),
        "dream_studio_home": str(paths.dream_studio_home),
        "runtime_config_path": str(config_path),
        "runtime_config_exists": config_path.exists(),
        "configured_source_root": configured_source,
        "old_source_checkout_detected": source_mismatch,
        "runtime_state_exists": paths.dream_studio_home.exists(),
        "sqlite_exists": paths.sqlite_path.exists(),
        "schema_version": schema_version,
        "latest_migration_version": latest_migration_version(),
        "old_sqlite_schema_detected": old_schema,
        "old_file_sprawl_detected": bool(legacy_sprawl),
        "legacy_file_sprawl": legacy_sprawl,
        "launcher_paths": launcher_report,
        "adapter_config_paths": adapter_config_report,
        "stale_environment": stale_env,
        "manual_review_items": unknown_manual_review,
        "destructive_action_authorized": False,
        "secret_values_read": False,
    }


def rollback_runtime_check(
    *,
    backup_path: str | Path,
) -> dict[str, Any]:
    """Validate a legacy-upgrade backup without restoring it."""

    backup = Path(backup_path).resolve()
    runtime_backup = backup / "runtime-home"
    sqlite_backup = runtime_backup / "state" / "studio.db"
    rollback = backup / "ROLLBACK.txt"
    detection = backup / "legacy-detection.json"
    return {
        "model_name": "dream_studio_legacy_rollback_check",
        "backup_path": str(backup),
        "backup_exists": backup.exists(),
        "runtime_backup_exists": runtime_backup.exists(),
        "sqlite_backup_exists": sqlite_backup.exists(),
        "sqlite_backup_opens_read_only": _verify_sqlite_read_only(sqlite_backup),
        "rollback_instructions_exist": rollback.exists(),
        "legacy_detection_exists": detection.exists(),
        "rollback_ready": backup.exists() and runtime_backup.exists() and rollback.exists(),
        "restore_executed": False,
        "delete_authorized": False,
    }


def _read_json_if_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _sqlite_schema_version(db_path: Path) -> int | None:
    if not db_path.exists():
        return None
    try:
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
            return applied_schema_version(conn)
    except sqlite3.Error:
        return None


def _verify_sqlite_read_only(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    try:
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        return True
    except sqlite3.Error:
        return False


def _legacy_sprawl(home: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not home.exists():
        return findings
    for rel in LEGACY_SPRAWL_CANDIDATES:
        path = home / rel
        if not path.exists():
            continue
        findings.append(
            {
                "relative_path": rel,
                "classification": "legacy_file_sprawl_keep_in_backup_only",
                "is_dir": path.is_dir(),
                "file_count": _count_files(path),
            }
        )
    return findings


def _count_files(path: Path) -> int:
    if path.is_file():
        return 1
    if not path.is_dir():
        return 0
    return sum(1 for child in path.rglob("*") if child.is_file())


def _launcher_path_report(*, command_dir: Path, current_source: Path) -> dict[str, Any]:
    launchers = []
    stale_count = 0
    for name in ("ds.cmd", "ds.ps1"):
        path = command_dir / name
        stale = False
        dream_studio_owned = False
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            dream_studio_owned = (
                "DREAM_STUDIO_SOURCE_ROOT" in text or "interfaces\\cli\\ds.py" in text
            )
            stale = dream_studio_owned and str(current_source) not in text
        stale_count += int(stale)
        launchers.append(
            {
                "path": str(path),
                "exists": path.exists(),
                "dream_studio_owned": dream_studio_owned,
                "stale": stale,
            }
        )
    return {
        "command_dir": str(command_dir),
        "launchers": launchers,
        "stale_launcher_count": stale_count,
    }


def _adapter_config_path_report(
    *,
    source_root: Path,
    claude_settings_path: str | Path | None,
    codex_home: str | Path | None,
) -> dict[str, Any]:
    stale_count = 0
    surfaces = []
    if claude_settings_path:
        path = Path(claude_settings_path).resolve()
        owned = False
        stale = False
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            owned = "dream-studio" in text.lower() or "DREAM_STUDIO_SOURCE_ROOT" in text
            stale = owned and str(source_root) not in text
        stale_count += int(stale)
        surfaces.append(
            {
                "surface": "claude_settings",
                "path": str(path),
                "exists": path.exists(),
                "dream_studio_owned_entries_detected": owned,
                "stale": stale,
            }
        )
    if codex_home:
        path = Path(codex_home).resolve()
        surfaces.append(
            {
                "surface": "codex_home",
                "path": str(path),
                "exists": path.exists(),
                "repair_mode": "projection_regeneration_only",
                "stale": False,
            }
        )
    return {"surfaces": surfaces, "stale_adapter_config_count": stale_count}


def _stale_environment_report(source_root: Path, home: Path) -> dict[str, Any]:
    checks = {
        "DREAM_STUDIO_SOURCE_ROOT": str(source_root),
        "DREAM_STUDIO_HOME": str(home),
    }
    stale = []
    for name, expected in checks.items():
        value = os.environ.get(name)
        if value and str(Path(value).resolve()) != expected:
            stale.append({"name": name, "classification": "stale_environment_variable"})
    return {"stale_env_count": len(stale), "stale_variables": stale}
