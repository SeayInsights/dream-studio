"""Generate adapter config projections from SQLite authority."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from core.shared_intelligence.adapter_alignment import (
    adapter_alignment_summary,
    adapter_projection_policy,
)
from core.shared_intelligence.authority import require_shared_intelligence_tables

ADAPTER_CONFIG_PROJECTION_SCHEMA = "dream_studio.adapter_config_projection.v1"


def adapter_config_projection(
    conn: sqlite3.Connection,
    *,
    adapter_id: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Generate one adapter config projection without writing config files."""

    require_shared_intelligence_tables(conn)
    profile = _adapter_profile(conn, adapter_id)
    if profile is None:
        raise ValueError(f"unknown adapter_id: {adapter_id}")

    content = _projection_content(profile, project_id=project_id)
    return {
        "schema": ADAPTER_CONFIG_PROJECTION_SCHEMA,
        "adapter_id": adapter_id,
        "adapter_type": profile["adapter_type"],
        "adapter_name": profile["adapter_name"],
        "project_id": project_id,
        "projection_path": profile["config_projection_path"],
        "content": content,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "source_authority": "sqlite",
        "source_tables": ["adapter_authority_profiles"],
        "adapter_owns_source_of_truth": False,
        "config_write_authorized": False,
        "requires_future_explicit_approval_for_config_writes": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def adapter_config_projection_report(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Generate adapter config projections for all registered adapters."""

    require_shared_intelligence_tables(conn)
    alignment = adapter_alignment_summary(conn)
    projections = [
        adapter_config_projection(conn, adapter_id=profile["adapter_id"], project_id=project_id)
        for profile in alignment["profiles"]
    ]
    return {
        "model_name": "shared_intelligence_adapter_config_projection_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "source_tables": ["adapter_authority_profiles"],
        "project_id": project_id,
        "adapter_projection_policy": adapter_projection_policy(),
        "adapter_count": len(projections),
        "projections": projections,
        "config_write_authorized": False,
        "empty_state": "No adapter authority profiles are available for config projection.",
    }


def validate_adapter_config_projection_report(report: dict[str, Any]) -> list[str]:
    """Validate that adapter config projection output remains non-mutating."""

    errors: list[str] = []
    if report.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if report.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    if report.get("routing_authority") is not False:
        errors.append("routing_authority must be false")
    if report.get("config_write_authorized") is not False:
        errors.append("config_write_authorized must be false")
    for projection in report.get("projections", []):
        if projection.get("config_write_authorized") is not False:
            errors.append(f"projection {projection.get('adapter_id')} authorizes config writes")
        if projection.get("adapter_owns_source_of_truth") is not False:
            errors.append(f"projection {projection.get('adapter_id')} owns source of truth")
        if not projection.get("content_sha256"):
            errors.append(f"projection {projection.get('adapter_id')} is missing content hash")
    return errors


def _adapter_profile(conn: sqlite3.Connection, adapter_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM adapter_authority_profiles
        WHERE adapter_id = ?
        """,
        (adapter_id,),
    ).fetchone()
    if row is None:
        return None
    return _decode_profile(row)


def _decode_profile(row: sqlite3.Row) -> dict[str, Any]:
    profile = dict(row)
    profile["supported_context_packets"] = _loads(profile.pop("supported_context_packets_json"), [])
    profile["supported_result_types"] = _loads(profile.pop("supported_result_types_json"), [])
    profile["stale_detection_policy"] = _loads(profile.pop("stale_detection_policy_json"), {})
    profile["source_refs"] = _loads(profile.pop("source_refs_json"), [])
    profile["evidence_refs"] = _loads(profile.pop("evidence_refs_json"), [])
    return profile


def _projection_content(profile: dict[str, Any], *, project_id: str | None) -> str:
    if profile["adapter_type"] in {"mcp", "shell"}:
        payload = {
            "schema": ADAPTER_CONFIG_PROJECTION_SCHEMA,
            "adapter_id": profile["adapter_id"],
            "adapter_role": "projection",
            "project_id": project_id,
            "supported_context_packets": profile["supported_context_packets"],
            "supported_result_types": profile["supported_result_types"],
            "authority": {
                "source": "dream_studio_sqlite",
                "adapter_owns_source_of_truth": False,
                "config_is_projection": True,
            },
        }
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"

    lines = [
        f"# {profile['adapter_name']} Dream Studio Projection",
        "",
        f"adapter_id: {profile['adapter_id']}",
        f"adapter_type: {profile['adapter_type']}",
        f"project_id: {project_id or 'global'}",
        "",
        "Authority:",
        "- Dream Studio SQLite authority is the source of truth.",
        "- This adapter config is a generated projection.",
        "- The adapter must not own canonical decisions, evidence, routes, or state.",
        "- Config writes require a future explicit approval boundary.",
        "",
        "Supported Context Packets:",
        *_bullet_list(profile["supported_context_packets"]),
        "",
        "Supported Result Types:",
        *_bullet_list(profile["supported_result_types"]),
        "",
        "Resume Rules:",
        "- Use shared context packets and evidence refs.",
        "- Normalize results back into Dream Studio records.",
        "- Do not rely on private model memory as authority.",
    ]
    if profile["adapter_type"] == "claude":
        lines += [
            "",
            "## Skill Routing",
            "",
            "When the user's intent matches a dream-studio skill, invoke it via the Skill tool — never fall back to built-in Claude behavior.",
            "",
            "<!-- BEGIN AUTO-ROUTING -->",
            "<!-- ROUTING TABLE GENERATED BY COMPILER -->",
            "<!-- END AUTO-ROUTING -->",
        ]
    return "\n".join(lines) + "\n"


def _bullet_list(values: list[Any]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {value}" for value in values]


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
