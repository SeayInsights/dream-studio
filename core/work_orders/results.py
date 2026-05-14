"""File-backed Work Result recording."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from compat import UTC

from .evals import (
    create_approved_mutation_compliance_eval,
    create_forbidden_action_compliance_eval,
    create_observe_only_compliance_eval,
    create_target_repo_mutation_eval,
)
from .models import WorkOrderError
from .storage import load_work_order, work_order_dir, write_existing_work_order
from .validation import validate_work_order

RESULT_MD = "result.md"
RESULT_JSON = "result.json"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _split_values(value: str) -> list[str]:
    cleaned = value.strip()
    if not cleaned:
        return ["unavailable"]
    if cleaned.lower() in {"none", "n/a", "not run", "unavailable"}:
        return [cleaned]
    return [item.strip() for item in cleaned.split(",") if item.strip()] or ["unavailable"]


def _extract_prefixed(lines: list[str], *prefixes: str) -> str:
    lowered = tuple(prefix.lower() for prefix in prefixes)
    for line in lines:
        if ":" not in line:
            continue
        prefix, value = line.split(":", 1)
        if prefix.strip().lower() in lowered:
            return value.strip() or "unavailable"
    return "unavailable"


def extract_result_metadata(
    *,
    work_order: dict[str, Any],
    raw_text: str,
    raw_output_ref: str,
) -> dict[str, Any]:
    """Conservatively extract structured metadata from operator-supplied text."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    summary = _extract_prefixed(lines, "summary")
    next_recommendation = _extract_prefixed(
        lines,
        "next work order",
        "next recommended work order",
        "next recommendation",
    )
    warnings = _split_values(_extract_prefixed(lines, "warnings"))
    risks = _split_values(_extract_prefixed(lines, "risks"))
    files_inspected = _split_values(_extract_prefixed(lines, "files inspected"))
    files_changed = _split_values(_extract_prefixed(lines, "files changed"))
    commands = _split_values(_extract_prefixed(lines, "commands", "tests"))

    return {
        "result_id": f"{work_order['work_order_id']}.result",
        "linked_work_order_id": work_order["work_order_id"],
        "status": "manual_result_recorded",
        "summary": summary,
        "raw_output_ref": raw_output_ref,
        "structured_findings": {
            "files_inspected": files_inspected,
            "files_changed": files_changed,
            "commands_or_tests": commands,
            "notes": "unavailable",
        },
        "validation_results": commands,
        "eval_artifacts": [],
        "warnings": warnings,
        "risks": risks,
        "next_work_order_recommendation": next_recommendation,
        "created_by": "ds_work_order record-result",
        "created_at": _now(),
        "privacy_export_classification": "local_only",
    }


def result_paths(
    work_order_id: str,
    *,
    storage_root: Path | str | None = None,
) -> tuple[Path, Path]:
    results_dir = work_order_dir(work_order_id, storage_root=storage_root) / "results"
    return results_dir / RESULT_MD, results_dir / RESULT_JSON


def load_result_metadata(
    work_order_id: str,
    *,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any] | None, Path]:
    _, metadata_path = result_paths(work_order_id, storage_root=storage_root)
    if not metadata_path.is_file():
        return None, metadata_path
    return json.loads(metadata_path.read_text(encoding="utf-8")), metadata_path


def load_result_text(
    work_order_id: str,
    *,
    storage_root: Path | str | None = None,
) -> tuple[str | None, Path]:
    raw_path, _ = result_paths(work_order_id, storage_root=storage_root)
    if not raw_path.is_file():
        return None, raw_path
    return raw_path.read_text(encoding="utf-8"), raw_path


def record_result(
    work_order_id: str,
    *,
    source_path: Path | str,
    storage_root: Path | str | None = None,
) -> dict[str, Any]:
    """Record a file-backed Work Result without inspecting target_path."""
    work_order, _ = load_work_order(work_order_id, storage_root=storage_root)
    validation = validate_work_order(work_order)
    if not validation.ok:
        raise WorkOrderError(validation.format())

    source = Path(source_path)
    if not source.is_file():
        raise WorkOrderError(f"Result source file not found: {source}")

    raw_text = source.read_text(encoding="utf-8")
    raw_path, metadata_path = result_paths(work_order_id, storage_root=storage_root)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_tmp = raw_path.parent / f".{RESULT_MD}.tmp"
    raw_tmp.write_text(raw_text, encoding="utf-8")
    raw_tmp.replace(raw_path)

    metadata = extract_result_metadata(
        work_order=validation.work_order,
        raw_text=raw_text,
        raw_output_ref=str(raw_path),
    )
    meta_tmp = metadata_path.parent / f".{RESULT_JSON}.tmp"
    meta_tmp.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    meta_tmp.replace(metadata_path)

    changed_files = metadata["structured_findings"].get("files_changed")
    updated = dict(validation.work_order)
    updated["status"] = "result_recorded"
    write_existing_work_order(updated, storage_root=storage_root)

    eval_paths: list[str] = []
    evals: list[dict[str, Any]] = []
    if updated.get("approval_mode") == "approval_required":
        approved_eval, approved_path = create_approved_mutation_compliance_eval(
            work_order=updated,
            changed_files=changed_files,
            storage_root=storage_root,
        )
        eval_paths.append(str(approved_path))
        evals.append(approved_eval)
    else:
        observe_eval, observe_path = create_observe_only_compliance_eval(
            work_order=updated,
            result_text=raw_text,
            result_metadata=metadata,
            storage_root=storage_root,
        )
        eval_paths.append(str(observe_path))
        evals.append(observe_eval)

    forbidden_eval, forbidden_path = create_forbidden_action_compliance_eval(
        work_order=updated,
        result_text=raw_text,
        result_metadata=metadata,
        storage_root=storage_root,
    )
    mutation_eval, mutation_path = create_target_repo_mutation_eval(
        work_order=updated,
        changed_files=changed_files,
        storage_root=storage_root,
    )

    eval_paths.extend([str(forbidden_path), str(mutation_path)])
    evals.extend([forbidden_eval, mutation_eval])
    metadata["eval_artifacts"] = eval_paths
    meta_tmp.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    meta_tmp.replace(metadata_path)

    return {
        "work_order_id": work_order_id,
        "result_path": str(raw_path),
        "metadata_path": str(metadata_path),
        "eval_paths": eval_paths,
        "evals": evals,
        "status": "result_recorded",
    }
