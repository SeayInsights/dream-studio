#!/usr/bin/env python3
"""Read-only local runtime preflight for Dream Studio."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

USER_DATA_DIRNAME = ".dream-studio"
STATE_DIRNAME = "state"
DB_FILENAME = "studio.db"
HOOK_PACKS = ("core", "quality", "analyze", "domains", "meta")

BLOCKED_NEWER_THAN_CODE_GUIDANCE = [
    "Use a Dream Studio checkout containing migrations greater than or equal to the DB schema version.",
    "Inspect local backups before attempting recovery.",
    "Run python interfaces/cli/runtime_preflight.py --json for a read-only report.",
    "Run python interfaces/cli/runtime_recovery.py --dry-run --json to inspect backup candidates.",
    "Do not manually edit _schema_version or downgrade the DB.",
]

MIGRATION_AVAILABLE_GUIDANCE = [
    "A normal setup or runtime bootstrap from this checkout can apply pending migrations.",
    "Back up the local DB before running mutating setup/bootstrap commands.",
]

MISSING_DB_GUIDANCE = [
    "Run setup/apply or dashboard launch when you are ready to initialize the local runtime DB.",
    "This check did not create the missing DB.",
]

UNKNOWN_SCHEMA_GUIDANCE = [
    "Run the read-only preflight and inspect backups before running mutating migration commands.",
    "Run python interfaces/cli/runtime_recovery.py --dry-run --json to inspect backup candidates.",
    "Do not manually edit _schema_version.",
]


@dataclass(frozen=True)
class PreflightConfig:
    repo_root: Path = REPO_ROOT
    home: Path = Path.home()
    replay_migrations: bool = True


def _check(name: str, status: str, severity: str = "info", **details: Any) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "severity": severity,
        "details": details,
    }


def _user_data_dir(home: Path) -> Path:
    return home / USER_DATA_DIRNAME


def _state_dir(home: Path) -> Path:
    return _user_data_dir(home) / STATE_DIRNAME


def _db_path(home: Path) -> Path:
    return _state_dir(home) / DB_FILENAME


def canonical_db_path(home: Path | None = None) -> Path:
    """Return the expected local runtime DB path without creating directories."""
    return _db_path(home or Path.home())


def _latest_migration_version(repo_root: Path) -> int:
    migration_dir = repo_root / "core" / "event_store" / "migrations"
    versions = [int(path.stem.split("_", 1)[0]) for path in migration_dir.glob("[0-9]*.sql")]
    return max(versions) if versions else 0


def _writable_without_create(path: Path) -> bool:
    if path.exists():
        return os.access(path, os.W_OK)
    parent = path.parent
    return parent.exists() and os.access(parent, os.W_OK)


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _sqlite_read_only(db_path: Path) -> sqlite3.Connection:
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _backup_metadata(db_path: Path) -> dict[str, Any]:
    backup_path = db_path.with_suffix(".db.bak")
    metadata: dict[str, Any] = {
        "backup_path": str(backup_path),
        "backup_exists": backup_path.is_file(),
    }
    if backup_path.is_file():
        stat = backup_path.stat()
        metadata["backup_size_bytes"] = stat.st_size
        metadata["backup_age_seconds"] = int(time.time() - stat.st_mtime)
    return metadata


def inspect_schema_compatibility(
    *,
    db_path: Path | None = None,
    repo_root: Path = REPO_ROOT,
    home: Path | None = None,
) -> dict[str, Any]:
    """Inspect local runtime schema compatibility without mutating the DB."""
    target = Path(db_path) if db_path is not None else canonical_db_path(home)
    latest = _latest_migration_version(repo_root)
    backup = _backup_metadata(target)
    base: dict[str, Any] = {
        "db_path": str(target),
        "exists": target.is_file(),
        "latest_migration_version": latest,
        "read_only": True,
        **backup,
    }

    if not target.is_file():
        return {
            **base,
            "status": "missing",
            "severity": "warning",
            "compatible": None,
            "created": False,
            "guidance": MISSING_DB_GUIDANCE,
        }

    try:
        conn = _sqlite_read_only(target)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            schema_row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='_schema_version'"
            ).fetchone()
            if schema_row is None:
                return {
                    **base,
                    "status": "unknown_missing_schema_version",
                    "severity": "warning",
                    "compatible": None,
                    "integrity": integrity,
                    "journal_mode": journal_mode,
                    "foreign_keys": foreign_keys,
                    "schema_version": None,
                    "schema_current": False,
                    "guidance": UNKNOWN_SCHEMA_GUIDANCE,
                }
            current = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        return {
            **base,
            "status": "error",
            "severity": "error",
            "compatible": False,
            "error": str(exc),
            "guidance": UNKNOWN_SCHEMA_GUIDANCE,
        }

    if current is None:
        return {
            **base,
            "status": "unknown_missing_schema_version",
            "severity": "warning",
            "compatible": None,
            "integrity": integrity,
            "journal_mode": journal_mode,
            "foreign_keys": foreign_keys,
            "schema_version": None,
            "schema_current": False,
            "guidance": UNKNOWN_SCHEMA_GUIDANCE,
        }

    if integrity != "ok":
        status = "error"
        severity = "error"
        compatible = False
        guidance = UNKNOWN_SCHEMA_GUIDANCE
    elif current > latest:
        status = "blocked_newer_than_code"
        severity = "error"
        compatible = False
        guidance = BLOCKED_NEWER_THAN_CODE_GUIDANCE
    elif current < latest:
        status = "migration_available"
        severity = "warning"
        compatible = True
        guidance = MIGRATION_AVAILABLE_GUIDANCE
    else:
        status = "compatible"
        severity = "info"
        compatible = True
        guidance = ["No schema compatibility action required."]

    return {
        **base,
        "status": status,
        "severity": severity,
        "compatible": compatible,
        "integrity": integrity,
        "journal_mode": journal_mode,
        "foreign_keys": foreign_keys,
        "schema_version": current,
        "schema_current": current == latest,
        "guidance": guidance,
    }


def schema_compatibility_is_blocking(result: dict[str, Any]) -> bool:
    return result.get("status") in {"blocked_newer_than_code", "error"}


def format_schema_compatibility(result: dict[str, Any]) -> str:
    lines = [
        f"Schema compatibility: {result.get('status')} ({result.get('severity')})",
        f"  DB path: {result.get('db_path')}",
        f"  DB schema version: {result.get('schema_version', 'missing')}",
        f"  Code migration version: {result.get('latest_migration_version')}",
        f"  Backup: {result.get('backup_path')} "
        f"({'present' if result.get('backup_exists') else 'missing'})",
    ]
    if result.get("status") == "blocked_newer_than_code":
        lines.append(
            "  Readiness: blocked - this checkout must not bootstrap, migrate, "
            "or launch against this DB."
        )
    guidance = result.get("guidance") or []
    if guidance:
        lines.append("  Guidance:")
        lines.extend(f"    - {item}" for item in guidance)
    return "\n".join(lines)


def _extract_hook_commands(obj: Any) -> list[str]:
    commands: list[str] = []
    if isinstance(obj, dict):
        command = obj.get("command")
        if isinstance(command, str):
            commands.append(command)
        for value in obj.values():
            commands.extend(_extract_hook_commands(value))
    elif isinstance(obj, list):
        for item in obj:
            commands.extend(_extract_hook_commands(item))
    return commands


def _handler_name(command: str) -> str | None:
    parts = command.strip().split()
    if len(parts) < 2:
        return None
    return parts[-1].strip('"')


def _check_repo(config: PreflightConfig) -> dict[str, Any]:
    repo_root = config.repo_root
    return _check(
        "repo_root",
        "ok" if (repo_root / ".git").exists() else "warn",
        "warning" if not (repo_root / ".git").exists() else "info",
        repo_root=str(repo_root),
        git_dir_exists=(repo_root / ".git").exists(),
        hooks_manifest_exists=(repo_root / "hooks" / "hooks.json").is_file(),
    )


def _check_paths(config: PreflightConfig) -> dict[str, Any]:
    user_dir = _user_data_dir(config.home)
    state_dir = _state_dir(config.home)
    status = "ok" if user_dir.exists() and state_dir.exists() else "warn"
    return _check(
        "runtime_paths",
        status,
        "warning" if status == "warn" else "info",
        home=str(config.home),
        user_data_dir=str(user_dir),
        user_data_exists=user_dir.exists(),
        user_data_writable=_writable_without_create(user_dir),
        state_dir=str(state_dir),
        state_exists=state_dir.exists(),
        state_writable=_writable_without_create(state_dir),
    )


def _check_db_path_agreement(config: PreflightConfig) -> dict[str, Any]:
    repo_root = config.repo_root
    files = {
        "core/config/paths.py": repo_root / "core" / "config" / "paths.py",
        "core/config/database.py": repo_root / "core" / "config" / "database.py",
        "core/event_store/studio_db.py": repo_root / "core" / "event_store" / "studio_db.py",
    }
    findings: dict[str, bool] = {}
    for label, path in files.items():
        source = path.read_text(encoding="utf-8") if path.is_file() else ""
        findings[label] = (
            DB_FILENAME in source or USER_DATA_DIRNAME in source or "state_dir()" in source
        )
    aligned = all(findings.values())
    return _check(
        "canonical_db_path_agreement",
        "ok" if aligned else "error",
        "error" if not aligned else "info",
        expected_db_path=str(_db_path(config.home)),
        source_alignment=findings,
    )


def _check_db_health(config: PreflightConfig) -> dict[str, Any]:
    compatibility = inspect_schema_compatibility(repo_root=config.repo_root, home=config.home)
    details = {
        key: value for key, value in compatibility.items() if key not in {"status", "severity"}
    }
    return _check(
        "runtime_db",
        compatibility["status"],
        compatibility["severity"],
        **details,
    )


def _check_fresh_replay(config: PreflightConfig) -> dict[str, Any]:
    latest = _latest_migration_version(config.repo_root)
    if not config.replay_migrations:
        return _check("fresh_migration_replay", "skipped", "info", latest_migration_version=latest)

    temp_db_path = ""
    try:
        from core.event_store.studio_db import _connect  # noqa: PLC0415

        with tempfile.TemporaryDirectory(prefix="dream-studio-preflight-") as temp_dir:
            db_path = Path(temp_dir) / "fresh-replay.db"
            temp_db_path = str(db_path)
            conn = _connect(db_path)
            try:
                version = (
                    conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0] or 0
                )
            finally:
                conn.close()
    except Exception as exc:  # noqa: BLE001
        return _check(
            "fresh_migration_replay",
            "error",
            "error",
            latest_migration_version=latest,
            temp_db_path=temp_db_path,
            error=str(exc),
        )

    return _check(
        "fresh_migration_replay",
        "ok" if version == latest else "warn",
        "warning" if version != latest else "info",
        latest_migration_version=latest,
        replayed_version=version,
        temp_db_path=temp_db_path,
        canonical_db_path=str(_db_path(config.home)),
        used_canonical_db=False,
    )


def _check_hooks(config: PreflightConfig) -> dict[str, Any]:
    manifest = config.repo_root / "hooks" / "hooks.json"
    if not manifest.is_file():
        return _check("hooks", "error", "error", manifest=str(manifest), error="missing hooks.json")

    data, error = _read_json(manifest)
    if error or data is None:
        return _check("hooks", "error", "error", manifest=str(manifest), error=error)

    missing: list[str] = []
    handlers: list[str] = []
    emitter_commands: int = 0
    for command in _extract_hook_commands(data):
        # Slice 3: commands are self-contained emitter one-liners routing through
        # emitters/claude_code/run.py — no separate handler file to resolve.
        if "emitters" in command and "claude_code" in command and "run.py" in command:
            emitter_commands += 1
            handlers.append("<emitter>")
            continue
        handler = _handler_name(command)
        if not handler:
            missing.append(command)
            continue
        # Skip names that are clearly not filenames (contain '.' or '(')
        if "." in handler or "(" in handler:
            continue
        handlers.append(handler)
        if not any(
            (config.repo_root / "runtime" / "hooks" / pack / f"{handler}.py").is_file()
            for pack in HOOK_PACKS
        ):
            missing.append(handler)

    return _check(
        "hooks",
        "ok" if not missing else "error",
        "error" if missing else "info",
        manifest=str(manifest),
        handler_count=len(handlers),
        emitter_command_count=emitter_commands,
        missing_handlers=missing,
        hooks_lib_exists=(config.repo_root / "hooks" / "lib").exists(),
    )


def _check_dashboard(config: PreflightConfig) -> dict[str, Any]:
    dashboard = config.repo_root / "interfaces" / "cli" / "ds_dashboard.py"
    if not dashboard.is_file():
        return _check("dashboard_preflight", "error", "error", path=str(dashboard), error="missing")

    source = dashboard.read_text(encoding="utf-8")
    has_check = "--check" in source and "def run_check" in source
    localhost_default = 'default="127.0.0.1"' in source
    return _check(
        "dashboard_preflight",
        "ok" if has_check and localhost_default else "warn",
        "warning" if not (has_check and localhost_default) else "info",
        path=str(dashboard),
        mode="static_observational",
        check_flag_present=has_check,
        localhost_default=localhost_default,
        server_started=False,
    )


def _check_backup(config: PreflightConfig) -> dict[str, Any]:
    db_path = _db_path(config.home)
    metadata = _backup_metadata(db_path)
    exists = metadata["backup_exists"]
    details: dict[str, Any] = {
        "backup_path": metadata["backup_path"],
        "exists": metadata["backup_exists"],
        "state_dir_writable": _writable_without_create(_state_dir(config.home)),
    }
    if metadata["backup_exists"]:
        details["size_bytes"] = metadata["backup_size_bytes"]
        details["age_seconds"] = metadata["backup_age_seconds"]
    return _check(
        "backup",
        "ok" if exists else "missing",
        "warning" if not exists else "info",
        **details,
    )


def _check_cloud_backup(config: PreflightConfig) -> dict[str, Any]:
    config_path = _state_dir(config.home) / "backup-config.json"
    if not config_path.is_file():
        return _check(
            "optional_cloud_backup",
            "not_configured",
            "info",
            config_path=str(config_path),
            optional=True,
            authoritative=False,
        )

    data, error = _read_json(config_path)
    if error or data is None:
        return _check(
            "optional_cloud_backup",
            "warn",
            "warning",
            config_path=str(config_path),
            optional=True,
            authoritative=False,
            error=error,
        )

    return _check(
        "optional_cloud_backup",
        "configured" if data.get("remote") else "not_configured",
        "info",
        config_path=str(config_path),
        optional=True,
        authoritative=False,
        remote_configured=bool(data.get("remote")),
        auto_push=bool(data.get("auto_push")),
        last_push=data.get("last_push"),
        external_call_made=False,
    )


def run_preflight(config: PreflightConfig | None = None) -> dict[str, Any]:
    config = config or PreflightConfig()
    checks = [
        _check_repo(config),
        _check_paths(config),
        _check_db_path_agreement(config),
        _check_db_health(config),
        _check_fresh_replay(config),
        _check_hooks(config),
        _check_dashboard(config),
        _check_backup(config),
        _check_cloud_backup(config),
    ]
    errors = sum(1 for item in checks if item["severity"] == "error")
    warnings = sum(1 for item in checks if item["severity"] == "warning")
    overall = "error" if errors else "warn" if warnings else "ok"
    return {
        "overall": overall,
        "repo_root": str(config.repo_root),
        "canonical_db_path": str(_db_path(config.home)),
        "read_only": True,
        "checks": checks,
        "summary": {"errors": errors, "warnings": warnings, "checks": len(checks)},
    }


def format_text(report: dict[str, Any]) -> str:
    lines = [
        "Dream Studio local runtime preflight",
        f"Overall: {report['overall']}",
        f"Repo: {report['repo_root']}",
        f"DB: {report['canonical_db_path']}",
        "",
    ]
    for item in report["checks"]:
        lines.append(f"[{item['status']}] {item['name']} ({item['severity']})")
        details = item.get("details", {})
        for key in sorted(details):
            lines.append(f"  {key}: {details[key]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Dream Studio local runtime preflight")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--no-replay", action="store_true", help="Skip fresh temp-DB migration replay"
    )
    args = parser.parse_args(argv)

    report = run_preflight(PreflightConfig(replay_migrations=not args.no_replay))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_text(report))
    return 1 if report["overall"] == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
