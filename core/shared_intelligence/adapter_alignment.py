# DEPRECATED: Superseded by integrations/integration_alignment.py.
# Retained for backward compatibility during Slice 1-2 transition.
# Scheduled for deletion in Slice 2 after test suite green.
"""Adapter authority alignment helpers.

Adapters are projections over Dream Studio authority. This module registers and
checks adapter profiles in SQLite without editing adapter config files.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from core.shared_intelligence.authority import (
    record_adapter_authority_profile,
    require_shared_intelligence_tables,
)

EXPECTED_ADAPTER_IDS: tuple[str, ...] = (
    "claude",
    "codex",
    "cursor",
    "copilot",
    "chatgpt",
    "mcp",
    "local-model",
    "shell",
)


def default_adapter_authority_profiles() -> list[dict[str, Any]]:
    """Return the default adapter profiles as source-neutral projections."""

    return [
        _profile(
            "claude",
            "claude",
            "Claude Code",
            "adapter-projections/claude/CLAUDE.md",
            ["resume", "work_order_execution", "review"],
            ["decision", "code_change", "validation", "evidence"],
        ),
        _profile(
            "codex",
            "codex",
            "Codex",
            "adapter-projections/codex/AGENTS.md",
            ["resume", "work_order_execution", "review", "release_gate"],
            ["decision", "code_change", "validation", "evidence", "risk"],
        ),
        _profile(
            "cursor",
            "cursor",
            "Cursor",
            "adapter-projections/cursor/rules",
            ["editor_context", "resume"],
            ["code_change", "review", "evidence"],
        ),
        _profile(
            "copilot",
            "copilot",
            "GitHub Copilot",
            "adapter-projections/copilot/instructions.md",
            ["repo_instructions", "review"],
            ["code_suggestion", "review", "evidence"],
        ),
        _profile(
            "chatgpt",
            "chatgpt",
            "ChatGPT",
            "adapter-projections/chatgpt/context_packet.md",
            ["resume", "research", "review"],
            ["decision", "research", "review", "risk"],
        ),
        _profile(
            "mcp",
            "mcp",
            "MCP Tools",
            "adapter-projections/mcp/server-policy.json",
            ["tool_context", "authority_query"],
            ["tool_result", "evidence", "artifact"],
        ),
        _profile(
            "local-model",
            "local_model",
            "Local Model",
            "adapter-projections/local-model/context_packet.md",
            ["resume", "offline_analysis"],
            ["analysis", "validation", "risk"],
        ),
        _profile(
            "shell",
            "shell",
            "Local Shell",
            "adapter-projections/shell/command-policy.json",
            ["command_context", "validation"],
            ["command_result", "validation", "evidence"],
        ),
    ]


def register_default_adapter_authority_profiles(
    conn: sqlite3.Connection,
    profiles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Register adapter profiles into an injected SQLite connection."""

    require_shared_intelligence_tables(conn)
    registered: list[str] = []
    for profile in profiles or default_adapter_authority_profiles():
        record_adapter_authority_profile(conn, **profile)
        registered.append(str(profile["adapter_id"]))
    return {
        "model_name": "shared_intelligence_adapter_registration",
        "registered_adapter_ids": registered,
        "adapter_count": len(registered),
        "source_authority": "sqlite",
        "adapter_configs_mutated": False,
        "live_db_mutated": False,
    }


def adapter_alignment_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return a read-only alignment check for adapter authority profiles."""

    require_shared_intelligence_tables(conn)
    rows = conn.execute("""
        SELECT *
        FROM adapter_authority_profiles
        ORDER BY adapter_id ASC
        """).fetchall()
    profiles = [_decode_profile(row) for row in rows]
    by_id = {profile["adapter_id"]: profile for profile in profiles}
    missing = [adapter_id for adapter_id in EXPECTED_ADAPTER_IDS if adapter_id not in by_id]
    authority_violations = [
        profile["adapter_id"]
        for profile in profiles
        if profile["owns_source_of_truth"] != 0 or profile["authority_role"] != "projection"
    ]
    unsupported_projection_paths = [
        profile["adapter_id"]
        for profile in profiles
        if not str(profile.get("config_projection_path") or "").startswith("adapter-projections/")
    ]

    return {
        "model_name": "shared_intelligence_adapter_alignment_summary",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "source_tables": ["adapter_authority_profiles"],
        "expected_adapter_ids": list(EXPECTED_ADAPTER_IDS),
        "registered_adapter_ids": sorted(by_id),
        "missing_adapter_ids": missing,
        "authority_violations": authority_violations,
        "unsupported_projection_paths": unsupported_projection_paths,
        "all_adapters_are_projections": not authority_violations,
        "adapter_configs_mutated": False,
        "profiles": profiles,
        "empty_state": "No adapter profiles are registered in SQLite authority.",
    }


def adapter_projection_policy() -> dict[str, Any]:
    """Return the non-mutating policy for adapter config generation."""

    return {
        "policy_id": "adapter_projection_policy",
        "source_authority": "sqlite",
        "adapter_owns_source_of_truth": False,
        "configs_are_generated_projections": True,
        "config_mutation_authorized": False,
        "requires_future_explicit_approval_for_config_writes": True,
        "covered_adapters": list(EXPECTED_ADAPTER_IDS),
    }


def _profile(
    adapter_id: str,
    adapter_type: str,
    adapter_name: str,
    config_projection_path: str,
    supported_context_packets: list[str],
    supported_result_types: list[str],
) -> dict[str, Any]:
    return {
        "adapter_id": adapter_id,
        "adapter_type": adapter_type,
        "adapter_name": adapter_name,
        "authority_role": "projection",
        "config_projection_path": config_projection_path,
        "supported_context_packets": supported_context_packets,
        "supported_result_types": supported_result_types,
        "stale_detection_policy": {
            "compare_to": "sqlite_authority",
            "repair_requires_work_order": True,
            "write_requires_operator_approval": True,
        },
        "source_refs": ["sqlite:adapter_authority_profiles"],
        "evidence_refs": ["wo-dream-studio-cross-ai-adapter-authority-alignment"],
    }


def _decode_profile(row: sqlite3.Row) -> dict[str, Any]:
    profile = dict(row)
    profile["supported_context_packets"] = _loads(
        profile.pop("supported_context_packets_json"),
        [],
    )
    profile["supported_result_types"] = _loads(
        profile.pop("supported_result_types_json"),
        [],
    )
    profile["stale_detection_policy"] = _loads(
        profile.pop("stale_detection_policy_json"),
        {},
    )
    profile["source_refs"] = _loads(profile.pop("source_refs_json"), [])
    profile["evidence_refs"] = _loads(profile.pop("evidence_refs_json"), [])
    return profile


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
