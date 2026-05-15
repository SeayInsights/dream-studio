"""Reusable GitHub PR + CI/CD release gate helpers.

The gate is intentionally policy-first.  It describes and evaluates the release
path, but it does not force-push, bypass checks, mutate secrets, or deploy.
Callers can use these decisions to drive GitHub adapter actions safely.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MERGE_POLICY_AUTO = "auto_merge_when_required_checks_pass_and_no_release_blockers"
DEPLOYMENT_SEPARATE_APPROVAL = "separate_approval_required"

BLOCKED_CI_ANNOTATION_MARKERS = (
    "payments have failed",
    "spending limit needs to be increased",
    "job was not started",
)


@dataclass(frozen=True)
class CICDProfile:
    """Project release profile for a GitHub PR-based release gate."""

    project_id: str
    repo_path: str
    github_remote: str
    default_branch: str
    release_branch_naming: str
    workflow_files: tuple[str, ...]
    required_checks: tuple[str, ...]
    optional_checks: tuple[str, ...]
    manual_workflows: tuple[str, ...]
    release_workflows: tuple[str, ...]
    local_preflight_commands: tuple[str, ...]
    github_actions_role: str
    heavy_validation_layer: str
    github_actions_minutes_policy: str
    github_actions_unavailable_policy: str
    merge_policy: str
    deployment_policy: str
    rollback_notes: tuple[str, ...]
    project_validation_commands: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "repo_path": self.repo_path,
            "github_remote": self.github_remote,
            "default_branch": self.default_branch,
            "release_branch_naming": self.release_branch_naming,
            "workflow_files": list(self.workflow_files),
            "required_checks": list(self.required_checks),
            "optional_checks": list(self.optional_checks),
            "manual_workflows": list(self.manual_workflows),
            "release_workflows": list(self.release_workflows),
            "local_preflight_commands": list(self.local_preflight_commands),
            "github_actions_role": self.github_actions_role,
            "heavy_validation_layer": self.heavy_validation_layer,
            "github_actions_minutes_policy": self.github_actions_minutes_policy,
            "github_actions_unavailable_policy": self.github_actions_unavailable_policy,
            "merge_policy": self.merge_policy,
            "deployment_policy": self.deployment_policy,
            "rollback_notes": list(self.rollback_notes),
            "project_validation_commands": list(self.project_validation_commands),
        }


def load_cicd_profile(path: Path | str) -> CICDProfile:
    """Load a CI/CD profile from JSON without touching git or GitHub."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return profile_from_mapping(data)


def profile_from_mapping(data: Mapping[str, Any]) -> CICDProfile:
    """Create a profile from a mapping while normalizing sequence fields."""

    return CICDProfile(
        project_id=_required_text(data, "project_id"),
        repo_path=_required_text(data, "repo_path"),
        github_remote=_required_text(data, "github_remote"),
        default_branch=_required_text(data, "default_branch"),
        release_branch_naming=_required_text(data, "release_branch_naming"),
        workflow_files=tuple(_text_sequence(data.get("workflow_files"))),
        required_checks=tuple(_text_sequence(data.get("required_checks"))),
        optional_checks=tuple(_text_sequence(data.get("optional_checks"))),
        manual_workflows=tuple(_text_sequence(data.get("manual_workflows"))),
        release_workflows=tuple(_text_sequence(data.get("release_workflows"))),
        local_preflight_commands=tuple(_text_sequence(data.get("local_preflight_commands"))),
        github_actions_role=_required_text(data, "github_actions_role"),
        heavy_validation_layer=_required_text(data, "heavy_validation_layer"),
        github_actions_minutes_policy=_required_text(data, "github_actions_minutes_policy"),
        github_actions_unavailable_policy=_required_text(data, "github_actions_unavailable_policy"),
        merge_policy=_required_text(data, "merge_policy"),
        deployment_policy=_required_text(data, "deployment_policy"),
        rollback_notes=tuple(_text_sequence(data.get("rollback_notes"))),
        project_validation_commands=tuple(_text_sequence(data.get("project_validation_commands"))),
    )


def discover_workflow_files(repo_path: Path | str) -> tuple[str, ...]:
    """Return GitHub workflow files present in a repository checkout."""

    workflow_root = Path(repo_path) / ".github" / "workflows"
    if not workflow_root.is_dir():
        return ()
    files = sorted(
        path.relative_to(Path(repo_path)).as_posix()
        for path in workflow_root.iterdir()
        if path.suffix.lower() in {".yml", ".yaml"}
    )
    return tuple(files)


def validate_cicd_profile(
    profile: CICDProfile, *, discovered_workflows: Sequence[str] = ()
) -> list[str]:
    """Return profile completeness and boundary issues."""

    issues: list[str] = []
    if not profile.github_remote.startswith(("https://github.com/", "git@github.com:")):
        issues.append("github_remote_required")
    if profile.default_branch != "main":
        issues.append("default_branch_must_be_main_for_dream_studio_release_gate")
    if profile.release_branch_naming.strip() in {"main", "master"}:
        issues.append("release_branch_must_not_be_default_branch")
    if not profile.workflow_files:
        issues.append("workflow_files_required")
    if not profile.required_checks:
        issues.append("required_checks_required")
    if not profile.manual_workflows:
        issues.append("manual_workflows_required")
    if not profile.release_workflows:
        issues.append("release_workflows_required")
    if not profile.local_preflight_commands:
        issues.append("local_preflight_commands_required")
    if profile.github_actions_role != "lightweight_remote_confidence_layer":
        issues.append("github_actions_must_remain_lightweight_confidence_layer")
    if profile.heavy_validation_layer != "local_dream_studio_release_gate":
        issues.append("heavy_validation_must_remain_local_release_gate")
    if "avoid_full_matrix_on_push" not in profile.github_actions_minutes_policy:
        issues.append("github_actions_minutes_policy_must_avoid_full_matrix_on_push")
    if "local_release_gate" not in profile.github_actions_unavailable_policy:
        issues.append("github_actions_unavailable_policy_must_preserve_local_gate")
    if profile.merge_policy != MERGE_POLICY_AUTO:
        issues.append("unsupported_merge_policy")
    if profile.deployment_policy != DEPLOYMENT_SEPARATE_APPROVAL:
        issues.append("deployment_must_require_separate_approval")
    if not profile.rollback_notes:
        issues.append("rollback_notes_required")

    discovered = set(discovered_workflows)
    for workflow in profile.workflow_files:
        if discovered and workflow not in discovered:
            issues.append(f"workflow_missing:{workflow}")
    for workflow in (*profile.manual_workflows, *profile.release_workflows):
        if workflow not in profile.workflow_files:
            issues.append(f"workflow_not_declared:{workflow}")

    if any(
        _is_direct_main_command(command, profile.default_branch)
        for command in profile.local_preflight_commands
    ):
        issues.append("local_preflight_must_not_push_or_merge")
    return issues


def build_dream_studio_cicd_profile(repo_path: str) -> CICDProfile:
    """Build Dream Studio's default profile for PR-based release."""

    return CICDProfile(
        project_id="dream-studio",
        repo_path=repo_path,
        github_remote="https://github.com/SeayInsights/dream-studio.git",
        default_branch="main",
        release_branch_naming="integration/{milestone_or_release}",
        workflow_files=(
            ".github/workflows/ci.yml",
            ".github/workflows/full-ci.yml",
            ".github/workflows/release-validation.yml",
            ".github/workflows/validate-skills.yml",
        ),
        required_checks=("pr-smoke",),
        optional_checks=("validate-skills", "full-ci", "release-validation"),
        manual_workflows=(".github/workflows/full-ci.yml",),
        release_workflows=(".github/workflows/release-validation.yml",),
        local_preflight_commands=(
            "python scripts/runtime_state_hash_guard.py --label local_release_gate -- python interfaces/cli/ci_gate.py",
            "git diff --check",
        ),
        github_actions_role="lightweight_remote_confidence_layer",
        heavy_validation_layer="local_dream_studio_release_gate",
        github_actions_minutes_policy=(
            "avoid_full_matrix_on_push; run cheap pr-smoke on pull_request; "
            "full-ci is workflow_dispatch only"
        ),
        github_actions_unavailable_policy=(
            "do_not_block_development; preserve local_release_gate as primary; "
            "manual review required before merge if required remote smoke is unavailable"
        ),
        merge_policy=MERGE_POLICY_AUTO,
        deployment_policy=DEPLOYMENT_SEPARATE_APPROVAL,
        rollback_notes=(
            "Do not force-push or rewrite release history.",
            "If a PR update fails, revert the bounded repair commit on the release branch.",
            "Deployment remains a separate operator-approved boundary.",
        ),
        project_validation_commands=(
            "python interfaces/cli/ci_gate.py",
            "python interfaces/cli/contract_docs_drift_gate.py",
            "python interfaces/cli/contract_atlas_lifecycle_gate.py",
            "python scripts/runtime_state_hash_guard.py --help",
        ),
    )


def build_release_branch_name(profile: CICDProfile, milestone_or_release: str) -> str:
    """Return a release branch name that cannot resolve to the default branch."""

    safe = re.sub(r"[^A-Za-z0-9._/-]+", "-", milestone_or_release.strip()).strip("-/")
    branch = profile.release_branch_naming.format(milestone_or_release=safe or "release")
    if branch in {profile.default_branch, "master"}:
        raise ValueError("release branch must not be the default branch")
    return branch


def build_release_gate_packet(
    *,
    profile: CICDProfile,
    current_branch: str,
    target_branch: str,
    pr_url: str | None = None,
    checks: Sequence[Mapping[str, Any]] = (),
    release_blockers: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a dashboard/evidence-ready release-gate packet."""

    merge = evaluate_merge_decision(
        profile=profile,
        current_branch=current_branch,
        target_branch=target_branch,
        checks=checks,
        release_blockers=release_blockers,
    )
    return {
        "packet_type": "github_pr_cicd_release_gate",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "project_id": profile.project_id,
        "repo_path": profile.repo_path,
        "github_remote": profile.github_remote,
        "current_branch": current_branch,
        "target_branch": target_branch,
        "default_branch": profile.default_branch,
        "pr_url": pr_url,
        "workflow_files": list(profile.workflow_files),
        "required_checks": list(profile.required_checks),
        "optional_checks": list(profile.optional_checks),
        "manual_workflows": list(profile.manual_workflows),
        "release_workflows": list(profile.release_workflows),
        "local_preflight_commands": list(profile.local_preflight_commands),
        "github_actions_role": profile.github_actions_role,
        "heavy_validation_layer": profile.heavy_validation_layer,
        "github_actions_minutes_policy": profile.github_actions_minutes_policy,
        "github_actions_unavailable_policy": profile.github_actions_unavailable_policy,
        "release_branch_required": True,
        "direct_to_main_allowed": False,
        "merge_decision": merge,
    }


def evaluate_merge_decision(
    *,
    profile: CICDProfile,
    current_branch: str,
    target_branch: str,
    checks: Sequence[Mapping[str, Any]],
    release_blockers: Sequence[str] = (),
) -> dict[str, Any]:
    """Decide whether a PR can be merged under the configured policy."""

    if current_branch == profile.default_branch:
        return _blocked("direct_to_main_release_path_forbidden")
    if target_branch != profile.default_branch:
        return _blocked("release_pr_must_target_default_branch")
    if profile.merge_policy != MERGE_POLICY_AUTO:
        return _blocked("unsupported_merge_policy")
    if release_blockers:
        return _blocked("release_blockers_present", release_blockers=list(release_blockers))

    check_map = {_text(check.get("name")): check for check in checks}
    missing = [name for name in profile.required_checks if name not in check_map]
    if missing:
        if not checks:
            return _blocked(
                "github_actions_unavailable_or_disabled",
                missing_required_checks=missing,
                development_blocked=False,
                local_release_gate_remains_primary=True,
                unavailable_policy=profile.github_actions_unavailable_policy,
            )
        return _blocked(
            "required_checks_missing",
            missing_required_checks=missing,
            development_blocked=False,
            local_release_gate_remains_primary=True,
        )

    blocked_external = [
        _text(check.get("name")) for check in checks if is_external_ci_blocker(check)
    ]
    if blocked_external:
        return _blocked("ci_infrastructure_or_billing_blocked", blocked_checks=blocked_external)

    failed = [
        name
        for name in profile.required_checks
        if _normal_conclusion(check_map[name]) not in {"success", "skipped_neutral"}
        and _normal_status(check_map[name]) == "completed"
    ]
    pending = [
        name for name in profile.required_checks if _normal_status(check_map[name]) != "completed"
    ]
    if failed:
        return _blocked("required_checks_failed", failed_required_checks=failed)
    if pending:
        return _blocked("required_checks_pending", pending_required_checks=pending)

    return {
        "can_merge": True,
        "reason": "required_checks_passed_and_no_release_blockers",
        "merge_policy": profile.merge_policy,
        "merge_method": "merge",
        "deployment_allowed": False,
        "deployment_policy": profile.deployment_policy,
        "heavy_validation_layer": profile.heavy_validation_layer,
    }


def is_external_ci_blocker(check: Mapping[str, Any]) -> bool:
    """Return True for GitHub infrastructure/account blockers, not repo failures."""

    text = " ".join(
        _text(check.get(key))
        for key in ("annotation", "message", "details", "failure_summary", "summary")
    ).lower()
    return any(marker in text for marker in BLOCKED_CI_ANNOTATION_MARKERS)


def build_failure_work_orders(
    *,
    profile: CICDProfile,
    checks: Sequence[Mapping[str, Any]],
    work_order_prefix: str = "wo-dream-studio-ci",
) -> list[dict[str, Any]]:
    """Generate Work Order drafts from failed CI checks."""

    work_orders: list[dict[str, Any]] = []
    for check in checks:
        name = _text(check.get("name"))
        if not name:
            continue
        conclusion = _normal_conclusion(check)
        if conclusion not in {"failure", "timed_out", "cancelled", "startup_failure"}:
            continue
        external = is_external_ci_blocker(check)
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "check"
        work_orders.append(
            {
                "work_order_id": f"{work_order_prefix}-{slug}",
                "project_name": profile.project_id,
                "objective": f"Diagnose and repair CI check: {name}",
                "source_check": name,
                "source_conclusion": conclusion,
                "source_details_url": _text(check.get("detailsUrl") or check.get("details_url")),
                "release_readiness_blocker": True,
                "external_blocker": external,
                "recommended_route": (
                    "require_operator_action" if external else "continue_internal_bounded_repair"
                ),
                "forbidden_actions": [
                    "force_push",
                    "direct_push_to_main",
                    "bypass_ci",
                    "deploy",
                    "secret_mutation",
                ],
                "expected_outputs": [
                    "failure_diagnosis_evidence",
                    "bounded_fix_if_repo_issue",
                    "local_validation_evidence",
                    "pr_update_evidence",
                ],
            }
        )
    return work_orders


def _blocked(reason: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "can_merge": False,
        "reason": reason,
        "merge_method": None,
        "deployment_allowed": False,
        "requires_operator_action": reason == "ci_infrastructure_or_billing_blocked",
    }
    payload.update(extra)
    return payload


def _is_direct_main_command(command: str, default_branch: str) -> bool:
    lowered = command.lower()
    return (
        "git push" in lowered
        and re.search(rf"\b{re.escape(default_branch.lower())}\b", lowered) is not None
    )


def _normal_status(check: Mapping[str, Any]) -> str:
    return _text(check.get("status")).lower()


def _normal_conclusion(check: Mapping[str, Any]) -> str:
    conclusion = _text(check.get("conclusion")).lower()
    if conclusion in {"success", "failure", "cancelled", "timed_out", "skipped"}:
        return "skipped_neutral" if conclusion == "skipped" else conclusion
    return conclusion or "unknown"


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = _text(data.get(key))
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _text_sequence(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)]
