"""Validate model/adapter-independent resume capability."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from core.shared_intelligence.authority import require_shared_intelligence_tables
from core.shared_intelligence.context_packets import generate_shared_context_packet

REQUIRED_RESUME_SECTIONS: tuple[str, ...] = (
    "authority_boundary",
    "adapter_alignment",
    "model_provider_registry",
    "authority_context",
    "learning_event_summary",
    "component_learning_health",
    "learning_promotion_queue",
    "resume_instructions",
)


def agent_model_independence_validation(
    conn: sqlite3.Connection,
    *,
    source_adapter_id: str,
    target_adapter_id: str,
    project_id: str,
    milestone_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Validate that a second adapter can resume from Dream Studio authority."""

    require_shared_intelligence_tables(conn)
    source_packet = generate_shared_context_packet(
        conn,
        packet_id=f"independence-source-{source_adapter_id}",
        adapter_id=source_adapter_id,
        packet_type="resume_validation",
        project_id=project_id,
        milestone_id=milestone_id,
        task_id=task_id,
        persist=False,
    )
    target_packet = generate_shared_context_packet(
        conn,
        packet_id=f"independence-target-{target_adapter_id}",
        adapter_id=target_adapter_id,
        packet_type="resume_validation",
        project_id=project_id,
        milestone_id=milestone_id,
        task_id=task_id,
        persist=False,
    )
    source_missing = _missing_sections(source_packet)
    target_missing = _missing_sections(target_packet)
    private_memory_required = bool(
        source_packet.get("model_private_memory_required")
        or target_packet.get("model_private_memory_required")
    )

    return {
        "model_name": "shared_intelligence_agent_model_independence_validation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "source_tables": [
            "adapter_authority_profiles",
            "shared_context_packets",
            "learning_event_records",
            "hardening_candidate_records",
            "model_provider_profiles",
        ],
        "project_id": project_id,
        "milestone_id": milestone_id,
        "task_id": task_id,
        "source_adapter_id": source_adapter_id,
        "target_adapter_id": target_adapter_id,
        "required_resume_sections": list(REQUIRED_RESUME_SECTIONS),
        "source_missing_sections": source_missing,
        "target_missing_sections": target_missing,
        "model_private_memory_required": private_memory_required,
        "adapter_config_write_required": False,
        "external_model_call_performed": False,
        "independence_passed": not source_missing
        and not target_missing
        and not private_memory_required,
        "source_packet": source_packet,
        "target_packet": target_packet,
    }


def validate_agent_model_independence_report(report: dict[str, Any]) -> list[str]:
    """Validate that independence evidence is authority-backed and non-external."""

    errors: list[str] = []
    if report.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if report.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    if report.get("routing_authority") is not False:
        errors.append("routing_authority must be false")
    if report.get("external_model_call_performed") is not False:
        errors.append("external_model_call_performed must be false")
    if report.get("adapter_config_write_required") is not False:
        errors.append("adapter_config_write_required must be false")
    if report.get("model_private_memory_required") is not False:
        errors.append("model_private_memory_required must be false")
    if report.get("source_missing_sections"):
        errors.append("source packet is missing required sections")
    if report.get("target_missing_sections"):
        errors.append("target packet is missing required sections")
    return errors


def _missing_sections(packet: dict[str, Any]) -> list[str]:
    return [section for section in REQUIRED_RESUME_SECTIONS if section not in packet]
