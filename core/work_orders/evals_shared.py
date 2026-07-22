"""Shared constants and eval-artifact plumbing for file-backed Work Order evals.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/evals.py``. Holds the eval
type identifiers, the Phase16/Phase17 eval-type groupings, the required
packet/report term tuples, the eval-artifact writer (packet store + best-
effort telemetry dual-write), and the base artifact builder shared by every
eval-creation sibling. No logic changes — extracted verbatim from the
original module.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from compat import UTC

from .handoff import HANDOFF_EVAL_TYPES

RENDER_COMPLETENESS = "work_order_render_completeness"
SKILL_IDENTIFIER_SAFETY = "skill_identifier_safety"
OBSERVE_ONLY_COMPLIANCE = "observe_only_compliance"
FORBIDDEN_ACTION_COMPLIANCE = "forbidden_action_compliance"
TARGET_REPO_MUTATION = "target_repo_mutation"
APPROVED_MUTATION_COMPLIANCE = "approved_mutation_compliance"
RESULT_REPORT_COMPLETENESS = "result_report_completeness"
NEXT_WORK_ORDER_RECOMMENDATION = "next_work_order_recommendation"
OPERATOR_DECISION_REQUEST_COMPLETENESS = "operator_decision_request_completeness"
OPERATOR_DECISION_VALIDITY = "operator_decision_validity"
OPERATOR_DECISION_REQUIRED_BEFORE_EXECUTION = "operator_decision_required_before_execution"
OPERATOR_DECISION_REASON_COMPLETENESS = "operator_decision_reason_completeness"
PHASE16_RENDER_EVALS = frozenset({RENDER_COMPLETENESS, SKILL_IDENTIFIER_SAFETY})
PHASE16_RESULT_EVALS = frozenset(
    {
        OBSERVE_ONLY_COMPLIANCE,
        APPROVED_MUTATION_COMPLIANCE,
        FORBIDDEN_ACTION_COMPLIANCE,
        TARGET_REPO_MUTATION,
        RESULT_REPORT_COMPLETENESS,
        NEXT_WORK_ORDER_RECOMMENDATION,
    }
)
PHASE17_HANDOFF_EVALS = HANDOFF_EVAL_TYPES
PHASE17_OPERATOR_DECISION_EVALS = frozenset(
    {
        OPERATOR_DECISION_REQUEST_COMPLETENESS,
        OPERATOR_DECISION_VALIDITY,
        OPERATOR_DECISION_REQUIRED_BEFORE_EXECUTION,
        OPERATOR_DECISION_REASON_COMPLETENESS,
    }
)

REQUIRED_PACKET_TERMS = (
    "Work Order ID",
    "Project Name",
    "Target Project Path",
    "Objective",
    "Approval Mode",
    "Risk Level",
    "Render-Only Posture",
    "Scope Include",
    "Scope Exclude",
    "Allowed Skills",
    "Workflow",
    "Forbidden Actions",
    "Validation Commands",
    "Stop Conditions",
    "Expected Output",
    "Do not edit",
    "Do not delete",
    "Do not commit",
    "Do not change dependencies",
    "Do not change schema",
)

REQUIRED_REPORT_TERMS = (
    "Objective",
    "Project Name",
    "Target Path",
    "Approval Mode",
    "Risk Level",
    "Scope Include",
    "Scope Exclude",
    "Rendered Packet Paths",
    "Raw Result Reference",
    "Structured Result Metadata",
    "Files Inspected",
    "Files Changed",
    "Commands And Tests",
    "Risks And Warnings",
    "Eval Artifact Summary",
    "Approved Mutation Compliance",
    "Next Recommended Work Order",
    "Remaining Gaps",
    "Proven",
    "Failed",
    "Incomplete / Unavailable",
    "Sequential Execution Readiness",
    "Next Action Decision",
    "Ready-To-Copy Next Prompt",
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_eval(
    artifact: dict[str, Any],
    *,
    storage_root: Path | str | None = None,
) -> None:
    """Persist an eval artifact into the packet store (WO-FILESDB-C3).

    The file-backed WO packet system is authority-free; its multi-instance evals are
    stored in the packet store (``packets.db``, kind='eval', instance_key=<eval_type>)
    co-located with the packet storage root — never in loose ``evals/<eval_type>.json``
    files and never in the Dream Studio authority. Returns None (no disk path).
    """
    from core.work_orders.packet_store import set_packet_artifact

    work_order_id = str(artifact["linked_work_order_id"])
    eval_type = str(artifact["eval_type"])
    payload = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    set_packet_artifact(
        work_order_id, "eval", payload, instance_key=eval_type, storage_root=storage_root
    )
    _emit_eval_telemetry(artifact, f"packet:{work_order_id}/eval/{eval_type}")
    return None


def _emit_eval_telemetry(artifact: dict[str, Any], target_ref: str) -> None:
    """Best-effort dual-write telemetry for eval artifacts (ref: packet-store row)."""

    if os.environ.get(
        "DREAM_STUDIO_ENABLE_WORK_ORDER_EVAL_TELEMETRY"
    ) != "1" and not os.environ.get("DREAM_STUDIO_TELEMETRY_DB"):
        return
    try:
        from core.telemetry.emitters import TelemetryContext, emit_validation_result

        pass_fail = str(artifact.get("pass_fail", "unknown"))
        evidence = [target_ref, *[str(item) for item in artifact.get("evidence", [])]]
        emit_validation_result(
            validation_type=str(artifact.get("eval_type", "work_order_eval")),
            status=pass_fail,
            command=None,
            scope=str(artifact.get("subject_type", "work_order")),
            summary=str(artifact.get("observed_behavior", "")) or None,
            pass_count=1 if pass_fail == "pass" else 0,
            fail_count=1 if pass_fail == "fail" else 0,
            error_count=0,
            warning_count=0,
            context=TelemetryContext(
                project_id="dream-studio",
                milestone_id=str(artifact.get("milestone_id", "work_order_eval"))
                or "work_order_eval",
                task_id=str(artifact.get("linked_work_order_id", "")) or None,
                process_run_id=str(artifact.get("linked_work_order_id", "")) or None,
                source_refs=("core/work_orders/evals.py",),
                evidence_refs=tuple(evidence),
            ),
        )
    except Exception:
        return


def _base_artifact(
    *,
    work_order: dict[str, Any],
    eval_type: str,
    expected_behavior: str,
    observed_behavior: str,
    pass_fail: str,
    evidence: list[str],
    score: int | str,
) -> dict[str, Any]:
    work_order_id = str(work_order.get("work_order_id", "unknown"))
    return {
        "eval_id": f"{work_order_id}.{eval_type}",
        "eval_type": eval_type,
        "subject_type": "work_order",
        "subject_id": work_order_id,
        "linked_work_order_id": work_order_id,
        "input_artifact": evidence[0] if evidence else "unavailable",
        "expected_behavior": expected_behavior,
        "observed_behavior": observed_behavior,
        "score": score,
        "pass_fail": pass_fail,
        "evaluator": "deterministic",
        "evidence": evidence or ["unavailable"],
        "privacy_export_classification": "local_only",
        "created_at": _now(),
    }


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)
