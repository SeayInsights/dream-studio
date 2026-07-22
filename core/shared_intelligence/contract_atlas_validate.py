"""Contract Atlas public-export sanitization and validation.

WO-GF-SHARED-INTEL-SPLIT: extracted from contract_atlas.py. Holds the
detector-pattern strings used to scrub absolute local paths from public
atlas exports. Kept in sync with `_PRIVATE_LEAK_PATTERNS` in
core/shared_intelligence/contract_atlas_lifecycle.py — the lifecycle gate
validates that no sanitized public atlas contains any of them.

core/release/repo_publication_readiness.py exempts this file's path from the
private-content literal-detector scan (it legitimately contains the
detector-pattern strings themselves, e.g. "AppData", "Dream Studio Live
Backups").
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


def sanitize_contract_atlas_for_public_export(atlas: Mapping[str, Any]) -> dict[str, Any]:
    """Return a public-safe Contract Atlas export.

    Sanitization removes absolute local paths and local user-surface metadata but
    preserves the contract graph, source-table references, maturity state, and
    non-authoritative boundary notes.
    """

    sanitized = _sanitize_value(dict(atlas))
    sanitized["export_scope"] = "public"
    sanitized["sanitized_public_export"] = True
    sanitized["repo_root"] = "<sanitized-local-path>"
    for contract in sanitized.get("adapter_projection_contracts", []):
        contract.pop("local_user_surface", None)
        local_hook = contract.get("local_hook_surface")
        if isinstance(local_hook, dict):
            contract["local_hook_surface"] = {
                "exists": local_hook.get("exists"),
                "status": local_hook.get("status"),
                "state_classification": local_hook.get("state_classification"),
                "live_execution_observed": False,
                "secret_contents_read": False,
            }
    return sanitized


def validate_contract_atlas(atlas: Mapping[str, Any]) -> list[str]:
    """Validate Contract Atlas authority and boundary guarantees."""

    errors: list[str] = []
    if atlas.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if atlas.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    if atlas.get("routing_authority") is not False:
        errors.append("routing_authority must be false")
    if atlas.get("execution_authorized") is not False:
        errors.append("execution_authorized must be false")
    if atlas.get("db_write_authorized") is not False:
        errors.append("db_write_authorized must be false")
    required = (
        "whole_system_contract",
        "layer_contracts",
        "module_contracts",
        "telemetry_module_contracts",
        "interface_contracts",
        "runtime_profiles",
        "installed_runtime_model",
        "installed_module_profiles",
        "analytics_only_profile",
        "analytics_only_ingestion",
        "security_lifecycle_gate",
        "production_readiness_control_catalog",
        "secure_production_readiness_gate",
        "adapter_usage_accounting",
        "task_attribution_model",
        "prd_authority_lifecycle",
        "github_cicd_profile",
        "expert_workflow_system",
        "capability_center",
        "scoped_agent_execution",
        "github_repo_intake",
        "platform_hardening",
        "contract_registry",
        "docs_freshness_tracking",
        "current_maturity_ledger",
        "adapter_projection_contracts",
        "dashboard_private_export_boundaries",
        "maturity_scorecard",
        "confirmed_dependency_graph",
        "boundary_violation_report",
    )
    for section in required:
        if not atlas.get(section):
            errors.append(f"missing atlas section: {section}")
    if atlas.get("export_scope") == "public":
        payload = json.dumps(atlas, sort_keys=True)
        if _contains_absolute_path(payload):
            errors.append("public atlas export contains an absolute local path")
    graph = atlas.get("confirmed_dependency_graph") or {}
    for edge in graph.get("edges", []):
        if edge.get("edge_status") != "confirmed":
            errors.append(
                f"unconfirmed dependency edge: {edge.get('source')}->{edge.get('target')}"
            )
    return errors


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"resolved_path", "config_root"}:
                sanitized[key] = "<sanitized-local-path>"
            else:
                sanitized[key] = _sanitize_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str) and _contains_absolute_path(value):
        return _sanitize_absolute_paths(value)
    return value


# Private-path patterns the public atlas export must scrub. Kept in sync with
# `_PRIVATE_LEAK_PATTERNS` in core/shared_intelligence/contract_atlas_lifecycle.py
# — the lifecycle gate validates that no sanitized public atlas contains any of
# them. Each entry is (detector_regex, replacement_regex). The detector decides
# whether a string needs sanitization; the replacement_regex strips the
# offending fragment back to a token boundary. Detector and replacement differ
# because we want to detect even an unanchored hit (e.g. `.dream-studio/` mid-
# token) but replace the entire surrounding path token, not just the match.
# Token boundary for path sanitization. Must allow spaces — Windows user
# paths legitimately contain them (e.g. paths with spaces in usernames), and
# stopping at the first space would leave a tail fragment
# in the JSON-encoded output where the UNC-style leak pattern picks it up.
_SANITIZE_TOKEN_CHARS = r"[^\"'\n\r,}\]]"
_PRIVATE_PATH_RULES: tuple[tuple[re.Pattern[str], re.Pattern[str]], ...] = (
    (
        re.compile(r"[A-Za-z]:[\\/]"),
        re.compile(rf"[A-Za-z]:[\\/]{_SANITIZE_TOKEN_CHARS}*"),
    ),
    (
        re.compile(r"\\\\[^\\/\s]+[\\/]"),
        re.compile(rf"\\\\[^\\/\s]+[\\/]{_SANITIZE_TOKEN_CHARS}*"),
    ),
    (
        re.compile(r"/(?:home|Users|root|tmp|opt|var|mnt|srv)/[^/\s]+", re.IGNORECASE),
        re.compile(
            rf"/(?:home|Users|root|tmp|opt|var|mnt|srv)/{_SANITIZE_TOKEN_CHARS}*",
            re.IGNORECASE,
        ),
    ),
    (
        re.compile(r"\.dream-studio[\\/]", re.IGNORECASE),
        re.compile(
            rf"{_SANITIZE_TOKEN_CHARS}*\.dream-studio{_SANITIZE_TOKEN_CHARS}*", re.IGNORECASE
        ),
    ),
    (
        re.compile(r"Dream Studio Live Backups", re.IGNORECASE),
        re.compile(
            rf"{_SANITIZE_TOKEN_CHARS}*Dream Studio Live Backups{_SANITIZE_TOKEN_CHARS}*",
            re.IGNORECASE,
        ),
    ),
    (
        re.compile(r"\bAppData[\\/]", re.IGNORECASE),
        re.compile(rf"{_SANITIZE_TOKEN_CHARS}*\bAppData{_SANITIZE_TOKEN_CHARS}*", re.IGNORECASE),
    ),
)


def _contains_absolute_path(value: str) -> bool:
    return any(detector.search(value) for detector, _ in _PRIVATE_PATH_RULES)


def _sanitize_absolute_paths(value: str) -> str:
    sanitized = value
    for _, replacement in _PRIVATE_PATH_RULES:
        sanitized = replacement.sub("<sanitized-local-path>", sanitized)
    return sanitized
