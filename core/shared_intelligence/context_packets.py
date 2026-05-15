"""Adapter-specific context packet generation from SQLite authority."""

from __future__ import annotations

import sqlite3
from typing import Any

from core.shared_intelligence.adapter_alignment import (
    adapter_alignment_summary,
    adapter_projection_policy,
)
from core.shared_intelligence.authority import (
    build_adapter_context_packet,
    record_shared_context_packet,
    require_shared_intelligence_tables,
)
from core.shared_intelligence.model_registry import model_provider_registry_summary
from core.shared_intelligence.prd_authority import context_packet_prd_authority
from core.shared_intelligence.read_models import (
    component_learning_health,
    learning_event_summary,
    learning_promotion_queue,
)


def generate_shared_context_packet(
    conn: sqlite3.Connection,
    *,
    packet_id: str,
    adapter_id: str,
    packet_type: str,
    project_id: str | None = None,
    milestone_id: str | None = None,
    task_id: str | None = None,
    process_run_id: str | None = None,
    limit: int = 20,
    persist: bool = True,
) -> dict[str, Any]:
    """Generate a resume/review packet from SQLite, optionally persisting it."""

    require_shared_intelligence_tables(conn)
    authority_context = build_adapter_context_packet(
        conn,
        adapter_id=adapter_id,
        project_id=project_id,
        limit=limit,
    )
    learning_summary = learning_event_summary(
        conn,
        project_id=project_id,
        milestone_id=milestone_id,
        task_id=task_id,
        limit=limit,
    )
    component_health = component_learning_health(
        conn,
        project_id=project_id,
        milestone_id=milestone_id,
        task_id=task_id,
    )
    promotion_queue = learning_promotion_queue(
        conn,
        project_id=project_id,
        milestone_id=milestone_id,
        task_id=task_id,
    )
    prd_project_authority = context_packet_prd_authority(
        conn,
        project_id=project_id,
        milestone_id=milestone_id,
        task_id=task_id,
    )
    payload = {
        "packet_schema": "dream_studio.shared_context.v2",
        "packet_id": packet_id,
        "packet_type": packet_type,
        "adapter_id": adapter_id,
        "project_id": project_id,
        "milestone_id": milestone_id,
        "task_id": task_id,
        "process_run_id": process_run_id,
        "source_authority": "sqlite",
        "model_private_memory_required": False,
        "adapter_config_write_required": False,
        "authority_boundary": {
            "sqlite_is_source_authority": True,
            "files_are_exports": True,
            "adapters_are_projections": True,
            "dashboard_is_derived_view": True,
        },
        "adapter_projection_policy": adapter_projection_policy(),
        "adapter_alignment": adapter_alignment_summary(conn),
        "model_provider_registry": model_provider_registry_summary(conn),
        "authority_context": authority_context,
        "prd_project_authority": prd_project_authority,
        "learning_event_summary": learning_summary,
        "component_learning_health": component_health,
        "learning_promotion_queue": promotion_queue,
        "resume_instructions": [
            "Use SQLite authority and evidence refs as the source of truth.",
            "Use current PRD, milestone, Work Order, change-order, and route reconciliation authority before relying on chat context.",
            "Do not rely on private model memory for task state.",
            "Treat adapter configs and dashboard output as projections.",
            "Do not mutate live state without an approved Work Order boundary.",
        ],
    }
    if persist:
        record_shared_context_packet(
            conn,
            packet_id=packet_id,
            adapter_id=adapter_id,
            project_id=project_id,
            milestone_id=milestone_id,
            task_id=task_id,
            process_run_id=process_run_id,
            packet_type=packet_type,
            payload=payload,
            source_refs=["sqlite:shared_context_packets"],
            evidence_refs=["wo-dream-studio-shared-context-packet-generation"],
        )
    return payload


def shared_context_packet_policy() -> dict[str, Any]:
    """Return the packet generation policy for adapter-neutral continuity."""

    return {
        "policy_id": "shared_context_packet_policy",
        "source_authority": "sqlite",
        "model_private_memory_required": False,
        "adapter_config_write_required": False,
        "supports_adapter_specific_projection": True,
        "packet_persistence_table": "shared_context_packets",
        "live_db_write_requires_explicit_approval": True,
    }
