"""Multi-agent shared intelligence demo packets."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from core.shared_intelligence.agent_independence import agent_model_independence_validation
from core.shared_intelligence.authority import require_shared_intelligence_tables
from core.shared_intelligence.dashboard_views import learning_hardening_dashboard_view
from core.shared_intelligence.result_normalization import adapter_result_summary


def multi_agent_shared_intelligence_demo_packet(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    first_adapter_id: str,
    second_adapter_id: str,
    milestone_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Build a demo packet proving adapter-to-adapter continuity via authority."""

    require_shared_intelligence_tables(conn)
    independence = agent_model_independence_validation(
        conn,
        source_adapter_id=first_adapter_id,
        target_adapter_id=second_adapter_id,
        project_id=project_id,
        milestone_id=milestone_id,
        task_id=task_id,
    )
    results = adapter_result_summary(conn, project_id=project_id)
    dashboard = learning_hardening_dashboard_view(conn, project_id=project_id)
    first_results = [
        result for result in results["results"] if result["adapter_id"] == first_adapter_id
    ]
    second_can_resume = independence["independence_passed"]

    return {
        "model_name": "shared_intelligence_multi_agent_demo_packet",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "source_tables": [
            "adapter_result_records",
            "adapter_authority_profiles",
            "learning_event_records",
            "hardening_candidate_records",
            "model_provider_profiles",
        ],
        "project_id": project_id,
        "milestone_id": milestone_id,
        "task_id": task_id,
        "first_adapter_id": first_adapter_id,
        "second_adapter_id": second_adapter_id,
        "demo_steps": [
            {
                "step": "first_adapter_records_result",
                "adapter_id": first_adapter_id,
                "evidence_count": len(first_results),
                "satisfied": bool(first_results),
            },
            {
                "step": "second_adapter_can_resume_from_packet",
                "adapter_id": second_adapter_id,
                "satisfied": second_can_resume,
            },
            {
                "step": "dashboard_surfaces_learning_and_hardening",
                "satisfied": dashboard["sections"]["lessons_learned"]["count"] > 0
                or dashboard["sections"]["hardening_candidates"]["count"] > 0,
            },
        ],
        "demo_passed": bool(first_results) and second_can_resume,
        "external_model_calls_performed": False,
        "adapter_private_memory_required": False,
        "execution_authorized": False,
        "independence_validation": independence,
        "adapter_result_summary": results,
        "dashboard_learning_hardening_view": dashboard,
    }


def validate_multi_agent_shared_intelligence_demo_packet(report: dict[str, Any]) -> list[str]:
    """Validate the demo packet remains evidence-only and authority-backed."""

    errors: list[str] = []
    if report.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if report.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    if report.get("routing_authority") is not False:
        errors.append("routing_authority must be false")
    if report.get("external_model_calls_performed") is not False:
        errors.append("external_model_calls_performed must be false")
    if report.get("adapter_private_memory_required") is not False:
        errors.append("adapter_private_memory_required must be false")
    if report.get("execution_authorized") is not False:
        errors.append("execution_authorized must be false")
    if not report.get("demo_steps"):
        errors.append("demo_steps must be present")
    return errors
