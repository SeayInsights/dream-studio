"""WO-SPLIT-HANDOFF: handoff dry-run (field extraction/contract checks) module."""

from __future__ import annotations
from typing import Any

from .handoff_constants import (
    DECISION_TAXONOMIES,
    FRESH_SESSION_RULE,
    HANDOFF_PATH_INTEGRITY,
    HANDOFF_TYPES,
    HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION,
    HANDOFF_TYPE_COMMIT_EXECUTION,
    HANDOFF_TYPE_RECOVERY_DECISION,
    PHASE_TYPE_PUSH_PLANNING,
    PUSH_EXECUTION_REQUIRED_SECTIONS,
    RECOVERY_DECISION_REQUIRED_SECTIONS,
    REQUIRED_HANDOFF_SECTIONS,
    UNDERSTANDING_REQUIRED_TERMS,
    _MALFORMED_DREAM_STUDIO_META_ROOT_RE,
    _WINDOWS_ABSOLUTE_PATH_RE,
)
from .handoff_helpers import _body_missing
from .handoff_validate_sections import parse_prompt_sections


def _is_push_execution_sections(sections: dict[str, str]) -> bool:
    return (
        sections.get("handoff_type", "").strip() == HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION
        and sections.get("phase_type", "").strip() == PHASE_TYPE_PUSH_PLANNING
        and sections.get("final_decision", "").strip() == "PUSH_READY_WITH_APPROVAL"
    )


def _profile_contract_missing(sections: dict[str, str], prompt_text: str) -> list[str]:
    combined = "\n".join(
        [
            prompt_text,
            sections.get("phase_name", ""),
            sections.get("handoff_type", ""),
            sections.get("phase_type", ""),
            sections.get("objective", ""),
            sections.get("phase_specific_safety_constraints", ""),
            sections.get("final_response_must_include", ""),
            sections.get("next_handoff_requirements", ""),
        ]
    ).lower()
    missing: list[str] = []

    required_contract_terms = (
        "required first action",
        "approval artifact",
        "allowed commands",
        "forbidden commands",
        "output artifacts",
        "readiness rules",
        "stop conditions",
        "final response",
        "next handoff",
    )
    for term in required_contract_terms:
        if term not in combined:
            missing.append(f"phase_specific_contract.{term}")

    if (
        sections.get("handoff_type", "").strip() == HANDOFF_TYPE_COMMIT_EXECUTION
        or "commit execution" in combined
    ):
        commit_terms = (
            "exact staged file list",
            "stage exact file paths only",
            "do not stage parent directories wholesale",
            "git diff --cached --name-only",
            "git diff --cached --stat",
            "git diff --cached --check",
            "no push unless separately approved",
        )
        for term in commit_terms:
            if term not in combined:
                missing.append(f"commit_execution_contract.{term}")

    if "pause" in combined or "return" in combined or "paused work" in combined:
        pause_terms = (
            "paused work artifact",
            "completed commit hashes",
            "current release gate",
            "remaining deferred work",
            "resume requirements",
            "do not run deferred phases",
        )
        for term in pause_terms:
            if term not in combined:
                missing.append(f"pause_return_contract.{term}")

    return missing


def _handoff_path_integrity_problems(prompt_text: str) -> list[str]:
    problems: list[str] = []
    malformed_roots = sorted(set(_MALFORMED_DREAM_STUDIO_META_ROOT_RE.findall(prompt_text)))
    problems.extend(f"malformed_dream_studio_meta_root:{root}" for root in malformed_roots)

    for path in sorted(set(_WINDOWS_ABSOLUTE_PATH_RE.findall(prompt_text))):
        if ".dream-studio" not in path:
            continue
        if "\\.dream-studio" in path or "/.dream-studio" in path:
            continue
        problems.append(f"missing_separator_before_dream_studio_segment:{path}")

    return sorted(set(problems))


def dry_run_handoff_prompt(
    prompt_text: str,
    *,
    target_repo_required: bool = True,
    approval_required: bool | None = None,
) -> dict[str, Any]:
    """Extract required fields from a Handoff Packet without executing it."""
    sections = parse_prompt_sections(prompt_text)
    extracted = {field: sections.get(field, "") for field in REQUIRED_HANDOFF_SECTIONS}
    missing: list[str] = []
    for field in REQUIRED_HANDOFF_SECTIONS:
        if field == "target_repo_path" and not target_repo_required:
            continue
        allow_unknown = field.startswith("baseline_")
        if field not in sections or _body_missing(
            sections.get(field, ""), allow_unknown=allow_unknown
        ):
            missing.append(field)

    prompt_approval_required = (
        approval_required
        if approval_required is not None
        else "approval_required" in sections.get("approval_mode", "")
    )
    if prompt_approval_required:
        approved_body = sections.get("approved_files_if_mutation_gated", "")
        approval_body = sections.get("approval_artifact_requirement", "")
        if "not applicable" in approved_body.lower():
            missing.append("approved_files_if_mutation_gated")
        if "not applicable" in approval_body.lower():
            missing.append("approval_artifact_requirement")

    handoff_type = sections.get("handoff_type", "").strip()
    if handoff_type and handoff_type not in HANDOFF_TYPES:
        missing.append("handoff_type")
    phase_type = sections.get("phase_type", "").strip()
    if phase_type and phase_type not in DECISION_TAXONOMIES:
        missing.append("phase_type")
    required_taxonomy_body = sections.get("required_decision_taxonomy", "")
    allowed_decisions = DECISION_TAXONOMIES.get(phase_type, ())
    if phase_type in DECISION_TAXONOMIES:
        missing_decisions = [
            decision for decision in allowed_decisions if decision not in required_taxonomy_body
        ]
        if missing_decisions:
            missing.append("required_decision_taxonomy")
    if handoff_type == HANDOFF_TYPE_RECOVERY_DECISION:
        for field in RECOVERY_DECISION_REQUIRED_SECTIONS:
            if field not in sections or _body_missing(sections.get(field, "")):
                missing.append(field)
    if _is_push_execution_sections(sections):
        for field in PUSH_EXECUTION_REQUIRED_SECTIONS:
            if field not in sections or _body_missing(sections.get(field, "")):
                missing.append(field)

    if FRESH_SESSION_RULE not in prompt_text:
        missing.append("fresh_session_rule")
    understanding = sections.get("handoff_understanding_report_requirement", "")
    for term in UNDERSTANDING_REQUIRED_TERMS:
        if term not in understanding:
            missing.append(f"handoff_understanding_report_requirement.{term}")
    missing.extend(_profile_contract_missing(sections, prompt_text))
    path_integrity_problems = _handoff_path_integrity_problems(prompt_text)
    if path_integrity_problems:
        missing.append(HANDOFF_PATH_INTEGRITY)

    unique_missing = sorted(set(missing))
    readiness = "fail" if unique_missing else "pass"
    return {
        "extracted_fields": extracted,
        "missing_fields": unique_missing,
        "path_integrity_problems": path_integrity_problems,
        "readiness": readiness,
    }
