"""Local-first repo versus runtime-state packaging boundaries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import PurePath
from typing import Any

REPO_SOURCE = "repo_source"
USER_LOCAL_STATE = "user_local_state"
RUNTIME_GENERATED = "runtime_generated"
IGNORED_TEMP = "ignored_temp"
EXTERNAL_TARGET = "external_target"
MANUAL_REVIEW = "manual_review"


def classify_packaging_path(path: str, *, repo_name: str = "dream-studio") -> dict[str, Any]:
    """Classify where a path belongs in local-first Dream Studio packaging."""

    normalized = path.replace("\\", "/")
    parts = PurePath(normalized).parts
    lower = normalized.lower()
    if "/.dream-studio/" in lower or lower.endswith("/.dream-studio"):
        category = USER_LOCAL_STATE
        ship_in_repo = False
    elif (
        f"/builds/{repo_name.lower()}/.tmp/" in lower
        or f"/builds/{repo_name.lower()}/.pytest_cache/" in lower
    ):
        category = IGNORED_TEMP
        ship_in_repo = False
    elif f"/builds/{repo_name.lower()}/" in lower:
        category = _repo_category(parts)
        ship_in_repo = category == REPO_SOURCE
    elif "/builds/" in lower:
        category = EXTERNAL_TARGET
        ship_in_repo = False
    else:
        category = MANUAL_REVIEW
        ship_in_repo = False
    return {
        "path": path,
        "category": category,
        "ship_in_repo": ship_in_repo,
        "runtime_generated": category in {USER_LOCAL_STATE, RUNTIME_GENERATED, IGNORED_TEMP},
        "requires_manual_review": category in {MANUAL_REVIEW, EXTERNAL_TARGET},
    }


def validate_packaging_boundary_manifest(items: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return boundary violations in classified packaging items."""

    issues: list[str] = []
    for index, item in enumerate(items):
        category = str(item.get("category") or "")
        if category in {USER_LOCAL_STATE, IGNORED_TEMP, EXTERNAL_TARGET} and item.get(
            "ship_in_repo"
        ):
            issues.append(f"item_{index}_{category}_must_not_ship_in_repo")
        if category == MANUAL_REVIEW and not item.get("requires_manual_review"):
            issues.append(f"item_{index}_manual_review_not_marked")
    return issues


def _repo_category(parts: Sequence[str]) -> str:
    lower_parts = [part.lower() for part in parts]
    if ".tmp" in lower_parts or "__pycache__" in lower_parts:
        return IGNORED_TEMP
    if any(part in lower_parts for part in ("runtime", "logs", "cache")):
        return RUNTIME_GENERATED
    return REPO_SOURCE
