#!/usr/bin/env python3
"""Read-only local runtime recovery diagnostics for Dream Studio."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from interfaces.cli.runtime_preflight import (  # noqa: E402
    canonical_db_path,
    inspect_schema_compatibility,
)

RECOVERY_NOTICE = (
    "Dry-run only: no restore, downgrade, schema edit, migration, backup creation, "
    "or repair was attempted."
)

RESTORE_PLAN_NOTICE = (
    "Restore-plan preview only: no restore, copy, safety copy, downgrade, schema edit, "
    "migration, backup creation, or repair was attempted."
)


@dataclass(frozen=True)
class RecoveryConfig:
    repo_root: Path = REPO_ROOT
    home: Path = Path.home()


def _iso_mtime(path: Path) -> str | None:
    if not path.is_file():
        return None
    return (
        datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _file_metadata(path: Path) -> dict[str, Any]:
    exists = path.is_file()
    return {
        "path": str(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else None,
        "modified_at": _iso_mtime(path),
    }


def _candidate_key(path: Path) -> str:
    return str(path.resolve()).casefold()


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def discover_backup_candidates(db_path: Path) -> list[dict[str, Any]]:
    """Return local backup candidates without creating directories or files."""
    state_dir = db_path.parent
    candidates: list[tuple[str, Path]] = [
        ("default_backup", db_path.with_suffix(".db.bak")),
    ]

    if state_dir.is_dir():
        patterns = [
            ("timestamped_export", "studio-*.db.bak"),
            ("cloud_pull_backup", "studio-cloud-pull.db.bak"),
            ("pre_restore_safety_copy", "studio.db.pre-restore.bak"),
            ("local_db_backup", "*.db.bak"),
        ]
        seen = {_candidate_key(path) for _, path in candidates}
        for role, pattern in patterns:
            for path in sorted(state_dir.glob(pattern)):
                key = _candidate_key(path)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append((role, path))

    return [{"role": role, "path": path} for role, path in candidates]


def inspect_candidate(path: Path, *, role: str, repo_root: Path) -> dict[str, Any]:
    """Inspect a DB or backup file with read-only compatibility checks."""
    metadata = _file_metadata(path)
    compatibility = inspect_schema_compatibility(db_path=path, repo_root=repo_root)
    return {
        "role": role,
        **metadata,
        "status": compatibility.get("status"),
        "severity": compatibility.get("severity"),
        "compatible": compatibility.get("compatible"),
        "schema_version": compatibility.get("schema_version"),
        "latest_migration_version": compatibility.get("latest_migration_version"),
        "read_only": compatibility.get("read_only") is True,
        "error": compatibility.get("error"),
        "guidance": compatibility.get("guidance", []),
    }


def _action_for(current: dict[str, Any], backups: list[dict[str, Any]]) -> dict[str, Any]:
    current_status = current.get("status")
    compatible_backups = [
        item
        for item in backups
        if item.get("exists") and item.get("status") in {"compatible", "migration_available"}
    ]

    if current_status == "blocked_newer_than_code":
        if compatible_backups:
            action = "use_compatible_checkout_or_review_backup_candidate"
            detail = (
                "Prefer a checkout with migrations greater than or equal to the current DB "
                "schema version. A compatible backup exists, but restoring it requires a "
                "separate explicit operator decision."
            )
        else:
            action = "use_compatible_checkout"
            detail = (
                "The current DB is newer than this checkout and no compatible local backup "
                "candidate was found. Use a checkout containing the newer migrations before "
                "attempting runtime bootstrap."
            )
    elif current_status == "migration_available":
        action = "backup_then_run_migrations_when_ready"
        detail = (
            "The current DB is older than this checkout. Create or verify a backup before "
            "running any mutating setup or bootstrap command."
        )
    elif current_status == "compatible":
        action = "no_recovery_needed"
        detail = "The current DB schema matches this checkout."
    elif current_status == "missing":
        action = "initialize_when_ready"
        detail = (
            "The current DB is missing. This dry-run did not create it; run setup or dashboard "
            "bootstrap only when initialization is intended."
        )
    else:
        action = "inspect_manually_before_recovery"
        detail = "Schema status is unknown or errored. Inspect the DB and backups before recovery."

    return {
        "action": action,
        "detail": detail,
        "compatible_backup_count": len(compatible_backups),
        "do_not": [
            "Do not edit _schema_version manually.",
            "Do not downgrade the current DB in place.",
            "Do not restore a backup without an explicit operator decision.",
            "Do not treat dashboard, telemetry, adapter, or preflight output as canonical state.",
        ],
    }


def run_recovery_dry_run(config: RecoveryConfig | None = None) -> dict[str, Any]:
    """Inspect runtime DB and backups without mutating local runtime state."""
    config = config or RecoveryConfig()
    db_path = canonical_db_path(config.home)
    current = inspect_candidate(db_path, role="current_runtime_db", repo_root=config.repo_root)
    backups = [
        inspect_candidate(item["path"], role=item["role"], repo_root=config.repo_root)
        for item in discover_backup_candidates(db_path)
    ]

    statuses = [current["severity"], *(item["severity"] for item in backups)]
    errors = sum(1 for status in statuses if status == "error")
    warnings = sum(1 for status in statuses if status == "warning")
    overall = "action_required" if errors else "review" if warnings else "ok"

    return {
        "dry_run": True,
        "notice": RECOVERY_NOTICE,
        "overall": overall,
        "repo_root": str(config.repo_root),
        "home": str(config.home),
        "current": current,
        "backup_candidates": backups,
        "recommendation": _action_for(current, backups),
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "backup_candidates": len(backups),
            "existing_backup_candidates": sum(1 for item in backups if item["exists"]),
        },
        "mutations_performed": False,
        "external_calls_made": False,
    }


def _schema_relation(current: dict[str, Any], source: dict[str, Any]) -> str:
    if not current.get("exists"):
        return "no_current_db"
    current_version = current.get("schema_version")
    source_version = source.get("schema_version")
    if current_version is None or source_version is None:
        return "unknown"
    if source_version < current_version:
        return "source_older_than_current"
    if source_version > current_version:
        return "source_newer_than_current"
    return "source_equal_to_current"


def _safety_copy_path(db_path: Path, current_hash: str | None) -> Path | None:
    if current_hash is None:
        return None
    return db_path.with_name(f"{db_path.name}.pre-restore.{current_hash[:12].lower()}.bak")


def _restore_plan_warnings(
    current: dict[str, Any], source: dict[str, Any], relation: str
) -> list[str]:
    warnings: list[str] = []
    current_version = current.get("schema_version")
    source_version = source.get("schema_version")
    if relation == "source_older_than_current":
        warnings.append(
            "Source backup schema version "
            f"{source_version} is older than current DB schema version {current_version}; "
            "a future restore would discard newer local runtime state."
        )
    if source.get("status") == "migration_available":
        warnings.append(
            "Source backup is older than this checkout; a future restore would require "
            "a normal migration step only after an explicit restore decision."
        )
    if source.get("status") == "blocked_newer_than_code":
        warnings.append(
            "Source backup is newer than this checkout; use a checkout with matching "
            "migrations before considering it for restore."
        )
    if current.get("status") == "blocked_newer_than_code":
        warnings.append(
            "Current runtime DB is newer than this checkout; this plan is inspection only "
            "and does not unblock runtime bootstrap."
        )
    return warnings


def _restore_plan_errors(source: dict[str, Any]) -> list[str]:
    if not source.get("exists"):
        return [f"Source backup does not exist: {source.get('path')}"]
    if source.get("status") == "error":
        detail = f": {source.get('error')}" if source.get("error") else ""
        return [f"Source backup is unreadable or not a valid SQLite DB{detail}"]
    if source.get("status") in {"unknown_missing_schema_version", "missing"}:
        return [
            f"Source backup schema status is not usable for restore planning: {source.get('status')}"
        ]
    if source.get("status") == "blocked_newer_than_code":
        return ["Source backup is newer than this checkout and is blocked for restore planning."]
    return []


def _future_restore_plan(
    *,
    db_path: Path,
    source_path: Path,
    safety_path: Path | None,
    current: dict[str, Any],
    source: dict[str, Any],
    current_hash: str | None,
    source_hash: str | None,
) -> dict[str, Any]:
    would_read = [str(source_path)]
    if current.get("exists"):
        would_read.append(str(db_path))

    would_write = [str(db_path)]
    if safety_path is not None:
        would_write.insert(0, str(safety_path))

    steps: list[dict[str, Any]] = [
        {
            "order": 1,
            "action": "verify_source_backup_readable",
            "read": str(source_path),
            "expected_sha256": source_hash,
            "expected_schema_version": source.get("schema_version"),
        }
    ]
    if safety_path is not None:
        steps.extend(
            [
                {
                    "order": 2,
                    "action": "create_pre_restore_safety_copy",
                    "read": str(db_path),
                    "write": str(safety_path),
                    "expected_source_sha256": current_hash,
                },
                {
                    "order": 3,
                    "action": "verify_safety_copy_hash",
                    "read": str(safety_path),
                    "expected_sha256": current_hash,
                },
            ]
        )
        next_order = 4
    else:
        steps.append(
            {
                "order": 2,
                "action": "skip_safety_copy_no_current_db",
                "reason": "No current runtime DB exists to preserve.",
            }
        )
        next_order = 3

    steps.extend(
        [
            {
                "order": next_order,
                "action": "copy_source_backup_to_runtime_db",
                "read": str(source_path),
                "write": str(db_path),
                "expected_source_sha256": source_hash,
            },
            {
                "order": next_order + 1,
                "action": "verify_restored_db_hash_and_schema",
                "read": str(db_path),
                "expected_sha256": source_hash,
                "expected_schema_version": source.get("schema_version"),
            },
            {
                "order": next_order + 2,
                "action": "run_read_only_preflight",
                "command": "python interfaces/cli/runtime_preflight.py --json",
            },
        ]
    )

    return {
        "will_execute": False,
        "requires_explicit_future_command": True,
        "pre_restore_safety_copy_path": str(safety_path) if safety_path else None,
        "would_read": would_read,
        "would_write": would_write,
        "steps": steps,
    }


def run_restore_plan_preview(
    *,
    source: Path,
    config: RecoveryConfig | None = None,
) -> dict[str, Any]:
    """Plan a future restore without copying, migrating, or mutating files."""
    config = config or RecoveryConfig()
    db_path = canonical_db_path(config.home)
    source_path = Path(source)

    current_hash_before = _sha256(db_path)
    source_hash_before = _sha256(source_path)
    current = inspect_candidate(db_path, role="current_runtime_db", repo_root=config.repo_root)
    source_candidate = inspect_candidate(
        source_path, role="source_backup", repo_root=config.repo_root
    )
    current_hash_after = _sha256(db_path)
    source_hash_after = _sha256(source_path)

    relation = _schema_relation(current, source_candidate)
    warnings = _restore_plan_warnings(current, source_candidate, relation)
    errors = _restore_plan_errors(source_candidate)
    safety_path = _safety_copy_path(db_path, current_hash_before)
    future_plan = _future_restore_plan(
        db_path=db_path,
        source_path=source_path,
        safety_path=safety_path,
        current=current,
        source=source_candidate,
        current_hash=current_hash_before,
        source_hash=source_hash_before,
    )

    source_compatible = source_candidate.get("status") in {"compatible", "migration_available"}
    overall = "blocked" if errors else "warning" if warnings else "ok"

    return {
        "plan_restore": True,
        "notice": RESTORE_PLAN_NOTICE,
        "overall": overall,
        "repo_root": str(config.repo_root),
        "home": str(config.home),
        "current": current,
        "source": source_candidate,
        "schema_relation": relation,
        "compatibility_impact": {
            "source_compatible_with_checkout": source_compatible,
            "source_would_require_migration_after_restore": source_candidate.get("status")
            == "migration_available",
            "restore_would_still_be_blocked": source_candidate.get("status")
            == "blocked_newer_than_code",
            "current_db_blocked_newer_than_code": current.get("status")
            == "blocked_newer_than_code",
            "restore_would_make_runtime_status": source_candidate.get("status"),
        },
        "warnings": warnings,
        "errors": errors,
        "future_mutation_plan": future_plan,
        "read_only_proof": {
            "current_db": {
                "path": str(db_path),
                "sha256_before": current_hash_before,
                "sha256_after": current_hash_after,
                "unchanged": current_hash_before == current_hash_after,
            },
            "source_backup": {
                "path": str(source_path),
                "sha256_before": source_hash_before,
                "sha256_after": source_hash_after,
                "unchanged": source_hash_before == source_hash_after,
            },
        },
        "mutations_performed": False,
        "external_calls_made": False,
    }


def format_text(report: dict[str, Any]) -> str:
    if report.get("plan_restore"):
        return format_restore_plan_text(report)

    lines = [
        "Dream Studio local runtime recovery dry-run",
        f"Overall: {report['overall']}",
        report["notice"],
        "",
        "Current runtime DB:",
        f"  path: {report['current']['path']}",
        f"  status: {report['current']['status']} ({report['current']['severity']})",
        f"  schema_version: {report['current']['schema_version']}",
        f"  latest_migration_version: {report['current']['latest_migration_version']}",
        "",
        "Backup candidates:",
    ]
    for item in report["backup_candidates"]:
        lines.extend(
            [
                f"  - {item['role']}: {item['path']}",
                f"    exists: {item['exists']}",
                f"    status: {item['status']} ({item['severity']})",
                f"    schema_version: {item['schema_version']}",
                f"    size_bytes: {item['size_bytes']}",
                f"    modified_at: {item['modified_at']}",
            ]
        )
    lines.extend(
        [
            "",
            f"Recommended action: {report['recommendation']['action']}",
            f"  {report['recommendation']['detail']}",
            "",
            "Guardrails:",
        ]
    )
    lines.extend(f"  - {item}" for item in report["recommendation"]["do_not"])
    return "\n".join(lines)


def format_restore_plan_text(report: dict[str, Any]) -> str:
    lines = [
        "Dream Studio local runtime restore-plan preview",
        f"Overall: {report['overall']}",
        report["notice"],
        "",
        "Current runtime DB:",
        f"  path: {report['current']['path']}",
        f"  status: {report['current']['status']} ({report['current']['severity']})",
        f"  schema_version: {report['current']['schema_version']}",
        "",
        "Source backup:",
        f"  path: {report['source']['path']}",
        f"  status: {report['source']['status']} ({report['source']['severity']})",
        f"  schema_version: {report['source']['schema_version']}",
        f"  source_vs_current: {report['schema_relation']}",
        "",
        "Future mutation plan (not executed):",
    ]
    for step in report["future_mutation_plan"]["steps"]:
        lines.append(f"  {step['order']}. {step['action']}")
        for key in ("read", "write", "command", "expected_sha256", "expected_schema_version"):
            if key in step:
                lines.append(f"     {key}: {step[key]}")
    if report["warnings"]:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  - {item}" for item in report["warnings"])
    if report["errors"]:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  - {item}" for item in report["errors"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Dream Studio local runtime recovery diagnostics"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Inspect only; never recover")
    mode.add_argument(
        "--plan-restore",
        action="store_true",
        help="Preview an explicit future restore plan without mutating files",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Backup path required for --plan-restore",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help="Override home directory for tests or isolated diagnostics",
    )
    args = parser.parse_args(argv)

    config = RecoveryConfig(home=args.home or Path.home(), repo_root=REPO_ROOT)
    if args.plan_restore:
        if args.source is None:
            parser.error("--plan-restore requires --source <backup-path>")
        report = run_restore_plan_preview(source=args.source, config=config)
    else:
        report = run_recovery_dry_run(config)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_text(report))

    return 1 if report.get("overall") == "blocked" else 0


if __name__ == "__main__":
    sys.exit(main())
