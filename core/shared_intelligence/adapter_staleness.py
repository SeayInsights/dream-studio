"""Detect stale adapter config projections without repairing them."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.shared_intelligence.adapter_config_projection import adapter_config_projection_report
from core.shared_intelligence.authority import require_shared_intelligence_tables

ACTIVE_REPO_SURFACES: dict[str, str] = {
    "claude": "CLAUDE.md",
    "codex": "AGENTS.md",
}

LOCAL_USER_SURFACES: dict[str, str] = {
    "claude": "~/.claude/CLAUDE.md",
    "codex": "~/.codex/AGENTS.md",
}

LOCAL_HOOK_SURFACES: dict[str, str] = {
    "claude": "~/.claude/settings.json",
    "codex": "~/.codex/hooks.json",
}

AUTHORITY_MARKERS: tuple[str, ...] = (
    "Dream Studio",
    "projection",
    "SQLite",
)

CURRENT_HOOK_LAUNCHER_MARKERS: tuple[str, ...] = (
    "hooks/run.py",
    "hooks/run.cmd",
)

STALE_HOOK_LAUNCHER_MARKERS: tuple[str, ...] = ("${CLAUDE_PLUGIN_ROOT}/hooks/run.sh",)


def adapter_staleness_report(
    conn: sqlite3.Connection,
    *,
    config_root: Path,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Compare projected adapter configs to files under an explicit config root."""

    require_shared_intelligence_tables(conn)
    root = Path(config_root).resolve()
    projection_report = adapter_config_projection_report(conn, project_id=project_id)
    checks = [_staleness_check(root, projection) for projection in projection_report["projections"]]
    stale = [check for check in checks if _check_is_stale(check)]
    missing = [check for check in checks if check["status"] == "missing"]
    aligned = [check for check in checks if check["status"] == "aligned"]
    active_repo_surfaces = [
        check["active_repo_surface"]
        for check in checks
        if check.get("active_repo_surface") is not None
    ]
    synced = [
        check for check in active_repo_surfaces if check.get("state_classification") == "synced"
    ]

    return {
        "model_name": "shared_intelligence_adapter_staleness_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "source_tables": ["adapter_authority_profiles"],
        "config_root": str(root),
        "project_id": project_id,
        "adapter_count": len(checks),
        "aligned_count": len(aligned),
        "stale_count": len(stale),
        "missing_count": len(missing),
        "active_repo_surface_count": len(active_repo_surfaces),
        "synced_active_surface_count": len(synced),
        "live_execution_proven": False,
        "checks": checks,
        "repair_work_order_candidates": [
            _repair_candidate(check) for check in checks if _check_needs_repair(check)
        ],
        "config_write_authorized": False,
        "repair_execution_authorized": False,
        "state_classification_legend": {
            "generated_projection": "The authority-generated adapter-projections artifact exists and matches generated content.",
            "active_repo_surface": "A repo-root adapter file exists and contains Dream Studio authority markers, but is not proven byte-synced to the generated artifact.",
            "local_user_surface": "A user-local adapter surface exists and was checked by path metadata only.",
            "synced": "The active repo surface exactly matches the generated projection artifact.",
            "stale": "A generated or active surface exists but does not match/consume Dream Studio authority.",
            "manual_review": "The surface cannot be safely classified without manual review.",
            "live_execution_unproven": "No real Claude/Codex execution consumed this surface during this validation.",
            "hook_surface_current_compatible": "A local hook config uses a current-compatible launcher command.",
            "hook_surface_stale": "A local hook config still uses a stale launcher command.",
        },
        "empty_state": "No adapter projections are registered for staleness detection.",
    }


def validate_adapter_staleness_report(report: dict[str, Any]) -> list[str]:
    """Validate that staleness detection does not authorize repairs."""

    errors: list[str] = []
    if report.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if report.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    if report.get("routing_authority") is not False:
        errors.append("routing_authority must be false")
    if report.get("config_write_authorized") is not False:
        errors.append("config_write_authorized must be false")
    if report.get("repair_execution_authorized") is not False:
        errors.append("repair_execution_authorized must be false")
    for candidate in report.get("repair_work_order_candidates", []):
        if candidate.get("execution_authorized") is not False:
            errors.append(f"repair candidate {candidate.get('adapter_id')} authorizes execution")
    if report.get("live_execution_proven") not in {False, None}:
        errors.append("live_execution_proven must not be true without explicit runtime evidence")
    return errors


def _staleness_check(root: Path, projection: dict[str, Any]) -> dict[str, Any]:
    relative = Path(str(projection["projection_path"]))
    target = (root / relative).resolve()
    _ensure_under_root(root, target)
    active = _active_repo_surface_check(root, projection)
    adapter_id = str(projection["adapter_id"])
    local = _local_user_surface_check(adapter_id)
    local_hook = _local_hook_surface_check(adapter_id)
    if not target.exists():
        return _check(
            projection,
            target,
            status="missing",
            current_sha256=None,
            active_repo_surface=active,
            local_user_surface=local,
            local_hook_surface=local_hook,
        )
    if not target.is_file():
        return _check(
            projection,
            target,
            status="manual_review_required",
            current_sha256=None,
            active_repo_surface=active,
            local_user_surface=local,
            local_hook_surface=local_hook,
        )
    current = target.read_text(encoding="utf-8")
    current_hash = hashlib.sha256(current.encode("utf-8")).hexdigest()
    status = "aligned" if current_hash == projection["content_sha256"] else "stale"
    return _check(
        projection,
        target,
        status=status,
        current_sha256=current_hash,
        active_repo_surface=active,
        local_user_surface=local,
        local_hook_surface=local_hook,
    )


def _check(
    projection: dict[str, Any],
    target: Path,
    *,
    status: str,
    current_sha256: str | None,
    active_repo_surface: dict[str, Any] | None,
    local_user_surface: dict[str, Any] | None,
    local_hook_surface: dict[str, Any] | None,
) -> dict[str, Any]:
    classifications = _state_classifications(
        generated_status=status,
        active_repo_surface=active_repo_surface,
        local_user_surface=local_user_surface,
        local_hook_surface=local_hook_surface,
    )
    return {
        "adapter_id": projection["adapter_id"],
        "adapter_type": projection["adapter_type"],
        "projection_path": projection["projection_path"],
        "resolved_path": str(target),
        "status": status,
        "expected_sha256": projection["content_sha256"],
        "current_sha256": current_sha256,
        "requires_repair_work_order": status in {"stale", "missing"},
        "config_write_authorized": False,
        "execution_authorized": False,
        "state_classifications": classifications,
        "generated_projection": {
            "path": projection["projection_path"],
            "status": status,
            "classification": "generated_projection" if status == "aligned" else status,
            "content_sha256": current_sha256,
        },
        "active_repo_surface": active_repo_surface,
        "local_user_surface": local_user_surface,
        "local_hook_surface": local_hook_surface,
        "live_execution_state": {
            "classification": "live_execution_unproven",
            "execution_observed": False,
            "reason": "Staleness detection reads files and SQLite authority only; it does not execute Claude or Codex.",
        },
    }


def _active_repo_surface_check(root: Path, projection: dict[str, Any]) -> dict[str, Any] | None:
    adapter_id = str(projection["adapter_id"])
    relative = ACTIVE_REPO_SURFACES.get(adapter_id)
    if relative is None:
        return None
    target = (root / relative).resolve()
    _ensure_under_root(root, target)
    base = {
        "path": relative,
        "resolved_path": str(target),
        "contents_inspected": True,
        "live_execution_observed": False,
        "execution_authorized": False,
    }
    if not target.exists():
        return {
            **base,
            "exists": False,
            "status": "missing",
            "state_classification": "stale",
            "consumes_dream_studio_authority": False,
            "active_matches_generated_sha256": False,
        }
    if not target.is_file():
        return {
            **base,
            "exists": True,
            "status": "manual_review_required",
            "state_classification": "manual_review",
            "consumes_dream_studio_authority": False,
            "active_matches_generated_sha256": False,
        }
    current = target.read_text(encoding="utf-8")
    current_hash = hashlib.sha256(current.encode("utf-8")).hexdigest()
    consumes_authority = all(marker in current for marker in AUTHORITY_MARKERS)
    explicit_reference = str(projection["projection_path"]) in current
    exact_match = current_hash == projection["content_sha256"]
    synced = exact_match
    state = "synced" if synced else "active_repo_surface" if consumes_authority else "stale"
    return {
        **base,
        "exists": True,
        "status": state,
        "state_classification": state,
        "consumes_dream_studio_authority": consumes_authority,
        "active_matches_generated_sha256": exact_match,
        "active_references_generated_projection": explicit_reference,
        "current_sha256": current_hash,
    }


def _local_user_surface_check(adapter_id: str) -> dict[str, Any] | None:
    logical = LOCAL_USER_SURFACES.get(adapter_id)
    if logical is None:
        return None
    target = Path(logical.replace("~/", str(Path.home()) + "/")).resolve()
    return {
        "path": logical,
        "exists": target.exists(),
        "state_classification": "local_user_surface" if target.exists() else "manual_review",
        "contents_inspected": False,
        "secret_contents_read": False,
        "manual_review_required": target.exists(),
        "live_execution_observed": False,
    }


def _local_hook_surface_check(adapter_id: str) -> dict[str, Any] | None:
    logical = LOCAL_HOOK_SURFACES.get(adapter_id)
    if logical is None:
        return None
    target = Path(logical.replace("~/", str(Path.home()) + "/")).resolve()
    base: dict[str, Any] = {
        "path": logical,
        "exists": target.exists(),
        "contents_inspected": "hook_commands_only",
        "secret_contents_read": False,
        "live_execution_observed": False,
        "execution_authorized": False,
        "config_write_authorized": False,
    }
    if not target.exists():
        return {
            **base,
            "status": "missing",
            "state_classification": "manual_review",
            "prompt_command_count": 0,
            "manual_review_required": True,
            "reason": "Local hook config file is missing.",
        }
    if not target.is_file():
        return {
            **base,
            "status": "manual_review_required",
            "state_classification": "manual_review",
            "prompt_command_count": 0,
            "manual_review_required": True,
            "reason": "Local hook config path is not a file.",
        }
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            **base,
            "status": "manual_review_required",
            "state_classification": "manual_review",
            "prompt_command_count": 0,
            "manual_review_required": True,
            "reason": "Local hook config could not be parsed as JSON.",
        }

    commands = _user_prompt_submit_commands(data)
    if not commands:
        return {
            **base,
            "status": "missing",
            "state_classification": "manual_review",
            "prompt_command_count": 0,
            "manual_review_required": True,
            "reason": "UserPromptSubmit hook command is not configured.",
        }

    stale = any(
        any(marker in command for marker in STALE_HOOK_LAUNCHER_MARKERS) for command in commands
    )
    current = any(
        any(marker in command for marker in CURRENT_HOOK_LAUNCHER_MARKERS) for command in commands
    )
    if stale:
        status = "stale"
        classification = "hook_surface_stale"
        reason = "UserPromptSubmit uses stale env-only launcher command."
        manual_review_required = False
    elif current:
        status = "aligned"
        classification = "hook_surface_current_compatible"
        reason = "UserPromptSubmit uses a current-compatible launcher command."
        manual_review_required = False
    else:
        status = "manual_review_required"
        classification = "manual_review"
        reason = "UserPromptSubmit command exists but does not match a known launcher pattern."
        manual_review_required = True

    return {
        **base,
        "status": status,
        "state_classification": classification,
        "prompt_command_count": len(commands),
        "manual_review_required": manual_review_required,
        "reason": reason,
    }


def _user_prompt_submit_commands(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return []
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = data
    event = hooks.get("UserPromptSubmit") if isinstance(hooks, dict) else None
    commands: list[str] = []
    _collect_commands(event, commands)
    return commands


def _collect_commands(value: Any, commands: list[str]) -> None:
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, str):
            commands.append(command)
        for child in value.values():
            _collect_commands(child, commands)
    elif isinstance(value, list):
        for child in value:
            _collect_commands(child, commands)


def _state_classifications(
    *,
    generated_status: str,
    active_repo_surface: dict[str, Any] | None,
    local_user_surface: dict[str, Any] | None,
    local_hook_surface: dict[str, Any] | None,
) -> list[str]:
    states: list[str] = []
    if generated_status == "aligned":
        states.append("generated_projection")
    elif generated_status in {"stale", "missing", "manual_review_required"}:
        states.append("stale" if generated_status != "manual_review_required" else "manual_review")
    if active_repo_surface is not None:
        state = str(active_repo_surface.get("state_classification") or "manual_review")
        if state not in states:
            states.append(state)
    if local_user_surface is not None and local_user_surface.get("exists"):
        if "local_user_surface" not in states:
            states.append("local_user_surface")
    if local_hook_surface is not None:
        state = str(local_hook_surface.get("state_classification") or "manual_review")
        if state not in states:
            states.append(state)
    if "live_execution_unproven" not in states:
        states.append("live_execution_unproven")
    return states


def _check_needs_repair(check: dict[str, Any]) -> bool:
    if check["status"] in {"stale", "missing"}:
        return True
    local_hook = check.get("local_hook_surface") or {}
    return local_hook.get("status") == "stale"


def _check_is_stale(check: dict[str, Any]) -> bool:
    if check["status"] == "stale":
        return True
    local_hook = check.get("local_hook_surface") or {}
    return local_hook.get("status") == "stale"


def _repair_candidate(check: dict[str, Any]) -> dict[str, Any]:
    local_hook = check.get("local_hook_surface") or {}
    if local_hook.get("status") == "stale":
        reason = "Local UserPromptSubmit hook surface is stale relative to current launcher policy."
        action = "create_adapter_hook_surface_repair_work_order"
    else:
        reason = f"Adapter projection is {check['status']} relative to SQLite authority."
        action = "create_adapter_config_projection_repair_work_order"
    return {
        "adapter_id": check["adapter_id"],
        "projection_path": check["projection_path"],
        "status": check["status"],
        "reason": reason,
        "recommended_action": action,
        "requires_operator_approval": True,
        "execution_authorized": False,
    }


def _ensure_under_root(root: Path, target: Path) -> None:
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"projection path escapes config root: {target}") from exc
