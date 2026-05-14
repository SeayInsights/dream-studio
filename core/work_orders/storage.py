"""File-backed Work Order storage.

This module intentionally avoids Dream Studio runtime DB helpers. Storage root
resolution is pure path calculation until a caller explicitly saves a file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .models import (
    WORK_ORDER_ID_RE,
    WORK_ORDER_ROOT_ENV,
    WorkOrderError,
    dump_work_order_json,
    load_work_order_file,
    normalize_work_order,
)

CANONICAL_JSON = "work_order.json"
LEGACY_YAML = "work_order.yaml"
LEGACY_YML = "work_order.yml"


def default_storage_root(*, home: Path | None = None) -> Path:
    """Return the Work Order storage root without creating it."""
    override = os.environ.get(WORK_ORDER_ROOT_ENV)
    if override:
        return Path(override).expanduser()
    return (home or Path.home()) / ".dream-studio" / "meta" / "work-orders"


def _safe_work_order_id(work_order_id: str) -> str:
    if not isinstance(work_order_id, str) or not WORK_ORDER_ID_RE.fullmatch(work_order_id):
        raise WorkOrderError("work_order_id must be a safe local identifier.")
    return work_order_id


def work_order_dir(work_order_id: str, *, storage_root: Path | str | None = None) -> Path:
    root = Path(storage_root) if storage_root is not None else default_storage_root()
    return root / _safe_work_order_id(work_order_id)


def save_work_order(
    data: dict[str, Any],
    *,
    storage_root: Path | str | None = None,
) -> Path:
    """Save the canonical Work Order JSON under the file-backed store."""
    normalized = normalize_work_order(data)
    work_order_id = _safe_work_order_id(str(normalized.get("work_order_id", "")))
    target_dir = work_order_dir(work_order_id, storage_root=storage_root)
    if target_dir.exists():
        raise WorkOrderError(f"Work Order already exists: {work_order_id}")
    target_dir.mkdir(parents=True, exist_ok=False)
    target_path = target_dir / CANONICAL_JSON
    tmp_path = target_dir / f".{CANONICAL_JSON}.tmp"
    tmp_path.write_text(dump_work_order_json(normalized), encoding="utf-8")
    tmp_path.replace(target_path)
    return target_path


def write_existing_work_order(
    data: dict[str, Any],
    *,
    storage_root: Path | str | None = None,
) -> Path:
    """Replace an existing stored Work Order JSON artifact."""
    normalized = normalize_work_order(data)
    work_order_id = _safe_work_order_id(str(normalized.get("work_order_id", "")))
    target_dir = work_order_dir(work_order_id, storage_root=storage_root)
    target_path = target_dir / CANONICAL_JSON
    if not target_path.is_file():
        raise WorkOrderError(f"Work Order not found: {work_order_id}")
    tmp_path = target_dir / f".{CANONICAL_JSON}.tmp"
    tmp_path.write_text(dump_work_order_json(normalized), encoding="utf-8")
    tmp_path.replace(target_path)
    return target_path


def _candidate_paths(work_order_id: str, *, storage_root: Path | str | None = None) -> list[Path]:
    target_dir = work_order_dir(work_order_id, storage_root=storage_root)
    return [
        target_dir / CANONICAL_JSON,
        target_dir / LEGACY_YAML,
        target_dir / LEGACY_YML,
    ]


def load_work_order(
    work_order_id: str,
    *,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Load a stored Work Order by ID from file-backed storage only."""
    for candidate in _candidate_paths(work_order_id, storage_root=storage_root):
        if candidate.is_file():
            return load_work_order_file(candidate), candidate
    raise WorkOrderError(f"Work Order not found: {work_order_id}")


def status_summary(
    work_order_id: str,
    *,
    storage_root: Path | str | None = None,
) -> dict[str, Any]:
    """Return status details without inspecting target repo files."""
    data, path = load_work_order(work_order_id, storage_root=storage_root)
    status = data.get("status", "unknown")
    next_action = {
        "draft": "run validate",
        "validated": "render in Phase 16C",
        "rendered": "record result in a later Phase 16 slice",
        "observed": "record result in a later Phase 16 slice",
        "result_recorded": "report in a later Phase 16 slice",
        "reported": "complete",
        "blocked": "resolve stop condition",
        "cancelled": "no action",
    }.get(str(status), "run validate")
    return {
        "work_order_id": data.get("work_order_id"),
        "status": status,
        "approval_mode": data.get("approval_mode"),
        "risk_level": data.get("risk_level"),
        "target_path": data.get("target_path"),
        "storage_root": str(path.parent.parent),
        "work_order_path": str(path),
        "next_required_action": next_action,
    }
