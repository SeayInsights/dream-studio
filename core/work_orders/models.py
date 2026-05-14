"""Work Order model constants and document loading."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import yaml

WORK_ORDER_ROOT_ENV = "DREAM_STUDIO_WORK_ORDER_ROOT"
STORAGE_CLASS = "file_backed"

APPROVAL_MODES = frozenset(
    {
        "observe_only",
        "render_only",
        "manual_execute",
        "approval_required",
        "blocked",
    }
)

RISK_LEVELS = frozenset({"low", "medium", "high", "critical"})

STATUSES = frozenset(
    {
        "draft",
        "validated",
        "rendered",
        "observed",
        "result_recorded",
        "reported",
        "blocked",
        "cancelled",
    }
)

PRIVACY_EXPORT_CLASSES = frozenset(
    {
        "local_only",
        "exportable_with_redaction",
        "aggregate_only",
        "non_exportable",
    }
)

REQUIRED_FIELDS = (
    "work_order_id",
    "project_name",
    "target_path",
    "objective",
    "approval_mode",
    "risk_level",
    "scope.include",
    "scope.exclude",
    "allowed_skills",
    "allowed_agents",
    "workflow",
    "forbidden_actions",
    "validation_commands",
    "expected_outputs",
    "stop_conditions",
    "created_by",
    "created_at",
    "status",
    "privacy_export_classification",
)

WORK_ORDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SKILL_ID_RE = re.compile(r"^ds-[a-z0-9][a-z0-9-]*$")


class WorkOrderError(ValueError):
    """Raised when a Work Order file cannot be loaded or stored safely."""


def normalize_work_order(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with Phase 16 defaults applied."""
    if not isinstance(data, dict):
        raise WorkOrderError("Work Order document must be a mapping.")
    normalized = copy.deepcopy(data)
    normalized.setdefault("storage_class", STORAGE_CLASS)
    return normalized


def load_work_order_file(path: Path | str) -> dict[str, Any]:
    """Load a JSON/YAML Work Order file without touching runtime state."""
    source = Path(path)
    if not source.is_file():
        raise WorkOrderError(f"Work Order source file not found: {source}")

    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorkOrderError(f"Unable to read Work Order source file: {exc}") from exc

    suffix = source.suffix.lower()
    try:
        if suffix == ".json":
            data = json.loads(raw)
        elif suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(raw)
        else:
            raise WorkOrderError("Work Order source must be .json, .yaml, or .yml.")
    except yaml.YAMLError as exc:
        raise WorkOrderError(f"Unable to parse Work Order YAML: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WorkOrderError(f"Unable to parse Work Order JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise WorkOrderError("Work Order source must contain a mapping.")
    return normalize_work_order(data)


def dump_work_order_json(data: dict[str, Any]) -> str:
    """Serialize canonical file-backed Work Order JSON."""
    return json.dumps(normalize_work_order(data), indent=2, sort_keys=True) + "\n"
