"""Work Order validation for Phase 16 file-backed storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    APPROVAL_MODES,
    PRIVACY_EXPORT_CLASSES,
    REQUIRED_FIELDS,
    RISK_LEVELS,
    SKILL_ID_RE,
    STATUSES,
    STORAGE_CLASS,
    WORK_ORDER_ID_RE,
    normalize_work_order,
)


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    work_order: dict[str, Any]
    issues: tuple[ValidationIssue, ...]

    def format(self) -> str:
        if self.ok:
            return "valid"
        return "\n".join(f"{issue.field}: {issue.message}" for issue in self.issues)


def _value(data: dict[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _list_issue(field: str) -> ValidationIssue:
    return ValidationIssue(field, "must be a list.")


def _legacy_skill_prefixes() -> tuple[str, str]:
    return ("dream" "-studio" + ":", "d" "s" + ":")


OBSERVE_ONLY_FORBIDDEN_CATEGORIES = {
    "edits": ("edit", "write", "patch", "format", "move"),
    "commits": ("commit", "stage", "push"),
    "deletes": ("delete", "remove"),
    "schema changes": ("schema change", "schema"),
    "dependency changes": ("dependency", "package"),
    "external actions": ("external", "network", "publish", "deploy", "cloud"),
    "target repo mutation": ("target repo mutation", "repo mutation", "mutate target"),
}


def _missing_observe_only_forbidden_actions(actions: list[Any]) -> list[str]:
    text = "\n".join(str(item).lower() for item in actions)
    missing: list[str] = []
    for category, markers in OBSERVE_ONLY_FORBIDDEN_CATEGORIES.items():
        if not any(marker in text for marker in markers):
            missing.append(category)
    return missing


def validate_work_order(
    data: dict[str, Any],
    *,
    allow_missing_target: bool = False,
) -> ValidationResult:
    """Validate a Work Order without opening runtime DB or target files."""
    normalized = normalize_work_order(data)
    issues: list[ValidationIssue] = []

    for field in REQUIRED_FIELDS:
        if _is_blank(_value(normalized, field)):
            issues.append(ValidationIssue(field, "is required."))

    work_order_id = normalized.get("work_order_id")
    if isinstance(work_order_id, str) and not WORK_ORDER_ID_RE.fullmatch(work_order_id):
        issues.append(ValidationIssue("work_order_id", "must be a safe local identifier."))

    approval_mode = normalized.get("approval_mode")
    if approval_mode not in APPROVAL_MODES:
        issues.append(
            ValidationIssue(
                "approval_mode",
                f"must be one of {', '.join(sorted(APPROVAL_MODES))}.",
            )
        )

    risk_level = normalized.get("risk_level")
    if risk_level not in RISK_LEVELS:
        issues.append(
            ValidationIssue("risk_level", f"must be one of {', '.join(sorted(RISK_LEVELS))}.")
        )

    status = normalized.get("status")
    if status not in STATUSES:
        issues.append(ValidationIssue("status", f"must be one of {', '.join(sorted(STATUSES))}."))

    storage_class = normalized.get("storage_class")
    if storage_class != STORAGE_CLASS:
        issues.append(ValidationIssue("storage_class", f"must be {STORAGE_CLASS}."))

    privacy = normalized.get("privacy_export_classification")
    if privacy not in PRIVACY_EXPORT_CLASSES:
        issues.append(
            ValidationIssue(
                "privacy_export_classification",
                f"must be one of {', '.join(sorted(PRIVACY_EXPORT_CLASSES))}.",
            )
        )

    created_at = normalized.get("created_at")
    if isinstance(created_at, str) and created_at.strip():
        try:
            datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            issues.append(ValidationIssue("created_at", "must be ISO-8601 parseable."))

    target_path = normalized.get("target_path")
    if isinstance(target_path, str) and target_path.strip():
        target = Path(target_path)
        if not target.is_absolute():
            issues.append(ValidationIssue("target_path", "must be an explicit absolute path."))
        elif not allow_missing_target and not target.exists():
            issues.append(ValidationIssue("target_path", "does not exist."))

    for field in (
        "scope.include",
        "scope.exclude",
        "allowed_skills",
        "allowed_agents",
        "forbidden_actions",
        "validation_commands",
        "expected_outputs",
        "stop_conditions",
    ):
        if _value(normalized, field) is not None and not isinstance(
            _value(normalized, field), list
        ):
            issues.append(_list_issue(field))

    skills = normalized.get("allowed_skills")
    if isinstance(skills, list):
        legacy_product, legacy_ds = _legacy_skill_prefixes()
        for index, skill in enumerate(skills):
            field = f"allowed_skills[{index}]"
            if not isinstance(skill, str):
                issues.append(ValidationIssue(field, "must be a string."))
                continue
            if skill.startswith(legacy_product) or skill.startswith(legacy_ds):
                issues.append(ValidationIssue(field, "must use ds-<slug>, not legacy forms."))
            elif not SKILL_ID_RE.fullmatch(skill):
                issues.append(ValidationIssue(field, "must use ds-<slug> form."))

    forbidden_actions = normalized.get("forbidden_actions")
    if approval_mode == "observe_only" and isinstance(forbidden_actions, list):
        missing = _missing_observe_only_forbidden_actions(forbidden_actions)
        for category in missing:
            issues.append(
                ValidationIssue(
                    "forbidden_actions",
                    f"observe_only must explicitly forbid {category}.",
                )
            )

    return ValidationResult(ok=not issues, work_order=normalized, issues=tuple(issues))
