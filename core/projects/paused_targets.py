"""Non-mutating project target pause/resume policy helpers.

The project registry can describe Dream Studio itself, paused external targets,
or evidence-only validation targets.  This module turns those plain mappings
into explicit route decisions without inspecting or mutating the target repos.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

BOUNDARY_LOCAL_REPO = "local_repo"
BOUNDARY_EXTERNAL_PROJECT = "external_project"
BOUNDARY_EVIDENCE_ONLY = "evidence_only"
BOUNDARY_UNKNOWN = "unknown"

ROUTE_ACTIVE_INTERNAL = "active_internal"
ROUTE_KEEP_PAUSED = "keep_paused"
ROUTE_RESUME_AFTER_OPERATOR_APPROVAL = "resume_after_operator_approval"
ROUTE_EXTERNAL_VALIDATION_APPROVAL_REQUIRED = "external_validation_approval_required"
ROUTE_MANUAL_REVIEW_REQUIRED = "manual_review_required"

PAUSED_STATUSES = frozenset({"paused", "hold", "blocked", "external_paused", "resume_required"})
ACTIVE_STATUSES = frozenset({"active", "current", "ready"})

DEFAULT_FORBIDDEN_FOR_PAUSED = (
    "target_repo_mutation",
    "target_validation",
    "stage",
    "commit",
    "push",
    "dependency_changes",
    "schema_migrations",
)


@dataclass(frozen=True)
class ProjectTargetPolicy:
    """Route-safe policy for one project registry target."""

    target_id: str
    status: str
    source_boundary: str
    validation_profile: str
    resume_allowed: bool
    mutation_allowed: bool
    external_validation_allowed: bool
    requires_operator_approval: bool
    recommended_route: str
    reasons: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    approval_refs: tuple[str, ...]
    source_evidence_refs: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "status": self.status,
            "source_boundary": self.source_boundary,
            "validation_profile": self.validation_profile,
            "resume_allowed": self.resume_allowed,
            "mutation_allowed": self.mutation_allowed,
            "external_validation_allowed": self.external_validation_allowed,
            "requires_operator_approval": self.requires_operator_approval,
            "recommended_route": self.recommended_route,
            "reasons": list(self.reasons),
            "forbidden_actions": list(self.forbidden_actions),
            "approval_refs": list(self.approval_refs),
            "source_evidence_refs": list(self.source_evidence_refs),
        }


def classify_project_target(target: Mapping[str, Any]) -> dict[str, Any]:
    """Classify one project target without touching the target.

    The input is intentionally a mapping so YAML/JSON registry rows can feed the
    policy directly.  Resume is allowed only when approval, clean-state evidence,
    and source-boundary evidence are all present.
    """

    if not isinstance(target, Mapping):
        raise TypeError("project target must be a mapping")

    target_id = (
        _text(target.get("target_id") or target.get("id") or target.get("name")) or "unknown"
    )
    status = _normal_status(target)
    boundary = _normal_boundary(target)
    profile = _normal_validation_profile(target.get("validation_profile"))
    approval_refs = tuple(
        _sequence_text(target.get("operator_approval_refs") or target.get("approval_refs"))
    )
    evidence_refs = tuple(
        _sequence_text(target.get("source_evidence_refs") or target.get("boundary_evidence_refs"))
    )
    repo_clean = _truthy(target.get("repo_clean"))
    paused = status in PAUSED_STATUSES or _truthy(target.get("paused"))
    external = boundary == BOUNDARY_EXTERNAL_PROJECT
    evidence_only = boundary == BOUNDARY_EVIDENCE_ONLY
    approval_present = bool(approval_refs) or _truthy(target.get("operator_approval_granted"))
    boundary_evidence_present = bool(evidence_refs) or _truthy(
        target.get("boundary_evidence_present")
    )
    resume_ready = approval_present and repo_clean and boundary_evidence_present

    reasons: list[str] = []
    forbidden: list[str] = []
    if paused:
        reasons.append("target_paused")
        forbidden.extend(DEFAULT_FORBIDDEN_FOR_PAUSED)
    if external:
        reasons.append("external_project_boundary")
    if evidence_only:
        reasons.append("evidence_only_boundary")
        forbidden.append("runtime_mutation")
    if not repo_clean:
        reasons.append("repo_clean_state_not_proven")
    if not boundary_evidence_present:
        reasons.append("source_boundary_evidence_missing")
    if not approval_present and (paused or external or evidence_only):
        reasons.append("operator_approval_missing")

    if paused:
        route = ROUTE_RESUME_AFTER_OPERATOR_APPROVAL if resume_ready else ROUTE_KEEP_PAUSED
        policy = ProjectTargetPolicy(
            target_id=target_id,
            status=status,
            source_boundary=boundary,
            validation_profile=profile,
            resume_allowed=resume_ready,
            mutation_allowed=False,
            external_validation_allowed=False,
            requires_operator_approval=not resume_ready,
            recommended_route=route,
            reasons=tuple(dict.fromkeys(reasons)),
            forbidden_actions=tuple(dict.fromkeys(forbidden)),
            approval_refs=approval_refs,
            source_evidence_refs=evidence_refs,
        )
        return policy.as_dict()

    if external or evidence_only:
        external_validation_allowed = resume_ready and _truthy(
            target.get("external_validation_approved")
        )
        route = (
            ROUTE_ACTIVE_INTERNAL
            if external_validation_allowed and not evidence_only
            else ROUTE_EXTERNAL_VALIDATION_APPROVAL_REQUIRED
        )
        policy = ProjectTargetPolicy(
            target_id=target_id,
            status=status,
            source_boundary=boundary,
            validation_profile=profile,
            resume_allowed=resume_ready,
            mutation_allowed=False,
            external_validation_allowed=external_validation_allowed,
            requires_operator_approval=not external_validation_allowed,
            recommended_route=route,
            reasons=tuple(dict.fromkeys(reasons)),
            forbidden_actions=tuple(dict.fromkeys(forbidden or ("target_repo_mutation",))),
            approval_refs=approval_refs,
            source_evidence_refs=evidence_refs,
        )
        return policy.as_dict()

    route = (
        ROUTE_ACTIVE_INTERNAL
        if status in ACTIVE_STATUSES and repo_clean
        else ROUTE_MANUAL_REVIEW_REQUIRED
    )
    policy = ProjectTargetPolicy(
        target_id=target_id,
        status=status,
        source_boundary=boundary,
        validation_profile=profile,
        resume_allowed=status in ACTIVE_STATUSES and repo_clean,
        mutation_allowed=status in ACTIVE_STATUSES
        and repo_clean
        and boundary == BOUNDARY_LOCAL_REPO,
        external_validation_allowed=False,
        requires_operator_approval=route != ROUTE_ACTIVE_INTERNAL,
        recommended_route=route,
        reasons=tuple(dict.fromkeys(reasons)),
        forbidden_actions=tuple(dict.fromkeys(forbidden)),
        approval_refs=approval_refs,
        source_evidence_refs=evidence_refs,
    )
    return policy.as_dict()


def build_project_target_registry_policy(targets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build an aggregate policy summary for a registry target list."""

    policies = [classify_project_target(target) for target in targets]
    return {
        "derived_view": True,
        "primary_authority": False,
        "source_authority": "project_registry_targets",
        "targets": policies,
        "summary": {
            "target_count": len(policies),
            "paused_count": sum(
                1 for item in policies if item["recommended_route"] == ROUTE_KEEP_PAUSED
            ),
            "resume_ready_count": sum(
                1
                for item in policies
                if item["recommended_route"] == ROUTE_RESUME_AFTER_OPERATOR_APPROVAL
            ),
            "manual_review_count": sum(
                1 for item in policies if item["recommended_route"] == ROUTE_MANUAL_REVIEW_REQUIRED
            ),
            "external_validation_approval_required_count": sum(
                1
                for item in policies
                if item["recommended_route"] == ROUTE_EXTERNAL_VALIDATION_APPROVAL_REQUIRED
            ),
        },
    }


def validate_project_target_policy(policy: Mapping[str, Any]) -> list[str]:
    """Return invariant violations for a target policy."""

    issues: list[str] = []
    route = _text(policy.get("recommended_route"))
    boundary = _text(policy.get("source_boundary"))

    if route == ROUTE_KEEP_PAUSED and _truthy(policy.get("mutation_allowed")):
        issues.append("paused_target_allows_mutation")
    if boundary in {BOUNDARY_EXTERNAL_PROJECT, BOUNDARY_EVIDENCE_ONLY} and _truthy(
        policy.get("mutation_allowed")
    ):
        issues.append("external_or_evidence_target_allows_mutation")
    if _truthy(policy.get("external_validation_allowed")) and not _truthy(
        policy.get("resume_allowed")
    ):
        issues.append("external_validation_without_resume_authority")
    if route == ROUTE_RESUME_AFTER_OPERATOR_APPROVAL and not policy.get("approval_refs"):
        issues.append("resume_ready_without_file_backed_approval_ref")
    return issues


def _normal_status(target: Mapping[str, Any]) -> str:
    return _text(target.get("status") or target.get("current_status") or "unknown").lower()


def _normal_boundary(target: Mapping[str, Any]) -> str:
    boundary = _text(target.get("source_boundary") or target.get("boundary")).lower()
    if boundary in {"local", "local_repo", "repo_local", "dream_studio_repo"}:
        return BOUNDARY_LOCAL_REPO
    if boundary in {"external", "external_project", "external_repo", "target_repo"}:
        return BOUNDARY_EXTERNAL_PROJECT
    if boundary in {"evidence", "evidence_only", "read_only", "metadata_only"}:
        return BOUNDARY_EVIDENCE_ONLY
    if _truthy(target.get("external_project")):
        return BOUNDARY_EXTERNAL_PROJECT
    if _truthy(target.get("evidence_only")):
        return BOUNDARY_EVIDENCE_ONLY
    return BOUNDARY_UNKNOWN


def _normal_validation_profile(value: Any) -> str:
    if isinstance(value, Mapping):
        return _text(value.get("id") or value.get("name") or value.get("profile")) or "unspecified"
    return _text(value) or "unspecified"


def _sequence_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence):
        return [_text(item) for item in value if _text(item)]
    return []


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "approved", "present"}
    return bool(value)
