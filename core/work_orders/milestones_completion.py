"""PRD authority-pack and milestone-completion-criteria validation.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/milestones.py``. No logic
changes — extracted verbatim from the original module.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .milestones_shared import _mapping, _sequence, _text, _truthy


def validate_authority_pack(authority: Mapping[str, Any]) -> list[str]:
    """Return missing PRD authority-pack fields.

    This validates structured authority data, not live files or runtime state.
    """

    required = (
        "product_identity",
        "primary_user",
        "problem_statement",
        "product_goals",
        "non_goals",
        "active_objective",
        "end_to_end_loop_definition",
        "success_criteria",
        "strategic_constraints",
        "paused_validation_targets",
    )
    return [field for field in required if not authority.get(field)]


def validate_milestone_completion_criteria(milestone: Mapping[str, Any]) -> dict[str, Any]:
    """Validate deterministic evidence gates before a milestone is declared complete."""

    criteria = _mapping(milestone.get("completion_criteria"))
    evidence_refs = _sequence(criteria.get("evidence_refs") or milestone.get("evidence_refs"))
    validation = _mapping(criteria.get("validation") or milestone.get("validation"))
    boundary = _mapping(
        criteria.get("boundary_confirmation") or milestone.get("boundary_confirmation")
    )
    route_state = _mapping(criteria.get("route_state") or milestone.get("route_state"))
    known_gaps = _sequence(criteria.get("known_gaps") or milestone.get("known_gaps"))

    missing: list[str] = []
    failed: list[str] = []
    if not evidence_refs:
        missing.append("evidence_refs")
    if not validation:
        missing.append("validation")
    elif _text(validation.get("status")).lower() not in {"passed", "pass", "success"}:
        failed.append("validation")
    if not boundary:
        missing.append("boundary_confirmation")
    elif not _truthy(boundary.get("confirmed")):
        failed.append("boundary_confirmation")
    if not route_state:
        missing.append("route_state")
    elif (
        _text(route_state.get("handoff_required")).lower()
        not in {
            "false",
            "0",
            "no",
        }
        and route_state.get("handoff_required") is not False
    ):
        failed.append("route_state")

    unclassified = [
        _text(gap.get("id") or gap.get("name") or index)
        for index, gap in enumerate(_mapping(item) for item in known_gaps)
        if _text(gap.get("classification")).lower()
        not in {
            "none",
            "release_blocker",
            "cutover_rehearsal_blocker",
            "post_cutover_backlog",
            "dashboard_polish",
            "future_module_work",
            "external_validation_work",
            "non_blocking_empty_state",
            "defer",
            "accepted_non_blocker",
        }
    ]
    if unclassified:
        failed.append("known_gaps")

    return {
        "complete": not missing and not failed,
        "missing": missing,
        "failed": failed,
        "unclassified_gaps": unclassified,
        "checks": {
            "evidence_refs_present": bool(evidence_refs),
            "validation_passed": "validation" not in missing and "validation" not in failed,
            "boundary_confirmed": "boundary_confirmation" not in missing
            and "boundary_confirmation" not in failed,
            "route_state_allows_completion": "route_state" not in missing
            and "route_state" not in failed,
            "known_gaps_classified": "known_gaps" not in failed,
        },
    }
