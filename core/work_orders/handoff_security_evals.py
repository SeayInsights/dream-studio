"""WO-SPLIT-HANDOFF: security handoff eval module."""

from __future__ import annotations
from typing import Any

from .handoff_constants import (
    HANDOFF_CONSTRAINT_PRESERVATION,
    HANDOFF_EXECUTION_READINESS,
    HANDOFF_FRESH_SESSION_SUFFICIENCY,
    HANDOFF_PROMPT_COMPLETENESS,
    READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE,
    READY_WITH_CONSTRAINTS,
    SECURITY_HANDOFF_FINDING_REFS_PRESENT,
    SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED,
    SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
    SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL,
    SECURITY_HANDOFF_RELEASE_GATE_PRESERVED,
    SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
    SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
    SECURITY_REMEDIATION_REQUIRED_SECTIONS,
)
from .handoff_helpers import _body_missing
from .handoff_validate import evaluate_handoff_prompt, parse_prompt_sections
from .handoff_security_shared import (
    _evaluate_security_no_commit_without_commit_phase,
    _finding_short_id,
    _security_eval_result,
)


def evaluate_security_review_next_handoff_prompt(
    prompt_text: str,
    *,
    expected_release_gate: str,
    expected_finding_ids: list[str],
    expected_target_branch: str,
    expected_target_head: str,
    expected_untracked_entries: list[str],
) -> dict[str, dict[str, Any]]:
    """Run deterministic security-remediation handoff evals."""
    base = evaluate_handoff_prompt(
        prompt_text,
        readiness=READY_WITH_CONSTRAINTS,
        can_continue=True,
        target_repo_required=True,
        approval_required=False,
    )
    sections = parse_prompt_sections(prompt_text)
    missing_sections = [
        section
        for section in SECURITY_REMEDIATION_REQUIRED_SECTIONS
        if section not in sections
        or _body_missing(sections.get(section, ""), allow_unknown=section.startswith("baseline_"))
    ]
    prompt_lower = prompt_text.lower()

    finding_missing = [
        finding_id
        for finding_id in expected_finding_ids
        if finding_id not in prompt_text and _finding_short_id(finding_id) not in prompt_text
    ]
    release_missing = expected_release_gate not in prompt_text
    target_missing = [
        value
        for value in (expected_target_branch, expected_target_head)
        if value and value not in prompt_text
    ]
    if "target_baseline_constraints" not in sections:
        target_missing.append("target_baseline_constraints")
    target_missing.extend(entry for entry in expected_untracked_entries if entry not in prompt_text)
    forbidden_terms = (
        "do not mutate target repositories",
        "do not run scans",
        "do not run target validation",
        "do not read production secrets",
        "real .env values",
        "private keys",
        "credentials",
        "future remediation must be a separate approved mutation work order",
    )
    forbidden_missing = [term for term in forbidden_terms if term not in prompt_lower]
    remediation_bounded = (
        "remediation planning only" in prompt_lower
        and "separate approved mutation work order" in prompt_lower
        and "do not touch bill stack" in prompt_lower
    )
    no_mutation_without_approval = (
        "no bill stack files are approved for mutation" in prompt_lower
        and "create a new file-backed approval artifact before any later bill stack mutation"
        in prompt_lower
    )

    results = {
        **base,
        SECURITY_HANDOFF_FINDING_REFS_PRESENT: _security_eval_result(
            "pass" if not finding_missing else "fail",
            (
                "security handoff preserves expected finding references"
                if not finding_missing
                else f"security handoff missing finding references: {', '.join(finding_missing)}"
            ),
            finding_missing or expected_finding_ids,
        ),
        SECURITY_HANDOFF_RELEASE_GATE_PRESERVED: _security_eval_result(
            "pass" if not release_missing else "fail",
            (
                "security handoff preserves release-gate decision"
                if not release_missing
                else f"security handoff missing release gate {expected_release_gate}"
            ),
            [expected_release_gate],
        ),
        SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED: _security_eval_result(
            "pass" if not target_missing else "fail",
            (
                "security handoff preserves target branch/head and untracked-entry constraints"
                if not target_missing
                else f"security handoff missing target constraints: {', '.join(target_missing)}"
            ),
            target_missing
            or [expected_target_branch, expected_target_head, *expected_untracked_entries],
        ),
        SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED: _security_eval_result(
            "pass" if remediation_bounded else "fail",
            (
                "security handoff keeps Phase 18S.12 to remediation planning"
                if remediation_bounded
                else "security handoff does not clearly bound remediation planning from mutation"
            ),
            [
                "remediation planning only",
                "separate approved mutation Work Order",
                "do not touch Bill Stack",
            ],
        ),
        SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED: _security_eval_result(
            "pass" if not forbidden_missing else "fail",
            (
                "security handoff preserves forbidden actions"
                if not forbidden_missing
                else f"security handoff missing forbidden actions: {', '.join(forbidden_missing)}"
            ),
            forbidden_missing or list(forbidden_terms),
        ),
        SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL: _security_eval_result(
            "pass" if no_mutation_without_approval else "fail",
            (
                "security handoff blocks target mutation without later file-backed approval"
                if no_mutation_without_approval
                else "security handoff does not clearly block target mutation without later approval"
            ),
            ["approved files", "approval artifact requirement"],
        ),
        SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE: _evaluate_security_no_commit_without_commit_phase(
            prompt_text,
            sections,
        ),
    }
    contract_pass = not missing_sections and all(
        results[key]["pass_fail"] == "pass"
        for key in (
            HANDOFF_PROMPT_COMPLETENESS,
            HANDOFF_CONSTRAINT_PRESERVATION,
            HANDOFF_EXECUTION_READINESS,
            HANDOFF_FRESH_SESSION_SUFFICIENCY,
            SECURITY_HANDOFF_FINDING_REFS_PRESENT,
            SECURITY_HANDOFF_RELEASE_GATE_PRESERVED,
            SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
            SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
            SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED,
            SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL,
            SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
        )
    )
    results[READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE] = _security_eval_result(
        "pass" if contract_pass else "fail",
        (
            "ready-to-copy security next handoff satisfies contract and security preservation checks"
            if contract_pass
            else "ready-to-copy security next handoff is incomplete or unsafe"
        ),
        missing_sections or ["security_handoff_required_sections"],
    )
    return results


def evaluate_security_remediation_mutation_handoff_prompt(
    prompt_text: str,
    *,
    expected_release_gate: str,
    expected_finding_ids: list[str],
    expected_target_branch: str,
    expected_target_head: str,
    expected_untracked_entries: list[str],
) -> dict[str, dict[str, Any]]:
    """Run deterministic evals for approved security remediation mutation handoffs."""
    base = evaluate_handoff_prompt(
        prompt_text,
        readiness=READY_WITH_CONSTRAINTS,
        can_continue=True,
        target_repo_required=True,
        approval_required=True,
    )
    sections = parse_prompt_sections(prompt_text)
    missing_sections = [
        section
        for section in SECURITY_REMEDIATION_REQUIRED_SECTIONS
        if section not in sections
        or _body_missing(sections.get(section, ""), allow_unknown=section.startswith("baseline_"))
    ]
    prompt_lower = prompt_text.lower()

    finding_missing = [
        finding_id
        for finding_id in expected_finding_ids
        if finding_id not in prompt_text and _finding_short_id(finding_id) not in prompt_text
    ]
    release_missing = expected_release_gate not in prompt_text
    target_missing = [
        value
        for value in (expected_target_branch, expected_target_head)
        if value and value not in prompt_text
    ]
    if "target_baseline_constraints" not in sections:
        target_missing.append("target_baseline_constraints")
    target_missing.extend(entry for entry in expected_untracked_entries if entry not in prompt_text)
    forbidden_terms = (
        "do not stage, commit, or push",
        "commit planning must occur in a later separate work order",
        "do not run scans",
        "do not run target validation",
        "do not update dependencies or lockfiles",
        "do not add schema migrations",
        "do not implement browser token/session architecture changes",
        "do not implement durable auth-state storage",
        "do not inspect untracked entries",
        "real .env values",
        "private keys",
        "credentials",
    )
    forbidden_missing = [term for term in forbidden_terms if term not in prompt_lower]
    remediation_bounded = (
        "approved mutation work order" in prompt_lower
        and "revenuecat webhook authentication" in prompt_lower
        and "household invite-code" in prompt_lower
        and "server-side password policy" in prompt_lower
        and "later work orders" in prompt_lower
    )
    no_mutation_without_approval = (
        "approval artifact exists before bill stack source inspection or mutation" in prompt_lower
        or "before inspecting or mutating bill stack source, create a file-backed approval artifact"
        in prompt_lower
    )
    no_commit_result = _evaluate_security_no_commit_without_commit_phase(prompt_text, sections)

    results = {
        **base,
        SECURITY_HANDOFF_FINDING_REFS_PRESENT: _security_eval_result(
            "pass" if not finding_missing else "fail",
            (
                "security mutation handoff preserves expected finding references"
                if not finding_missing
                else f"security mutation handoff missing finding references: {', '.join(finding_missing)}"
            ),
            finding_missing or expected_finding_ids,
        ),
        SECURITY_HANDOFF_RELEASE_GATE_PRESERVED: _security_eval_result(
            "pass" if not release_missing else "fail",
            (
                "security mutation handoff preserves release-gate decision"
                if not release_missing
                else f"security mutation handoff missing release gate {expected_release_gate}"
            ),
            [expected_release_gate],
        ),
        SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED: _security_eval_result(
            "pass" if not target_missing else "fail",
            (
                "security mutation handoff preserves target branch/head and untracked-entry constraints"
                if not target_missing
                else f"security mutation handoff missing target constraints: {', '.join(target_missing)}"
            ),
            target_missing
            or [expected_target_branch, expected_target_head, *expected_untracked_entries],
        ),
        SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED: _security_eval_result(
            "pass" if remediation_bounded else "fail",
            (
                "security mutation handoff keeps remediation scope bounded to priority findings"
                if remediation_bounded
                else "security mutation handoff does not clearly bound priority remediation scope"
            ),
            [
                "RevenueCat webhook authentication",
                "household invite-code",
                "server-side password policy",
                "later Work Orders",
            ],
        ),
        SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED: _security_eval_result(
            "pass" if not forbidden_missing else "fail",
            (
                "security mutation handoff preserves forbidden actions"
                if not forbidden_missing
                else f"security mutation handoff missing forbidden actions: {', '.join(forbidden_missing)}"
            ),
            forbidden_missing or list(forbidden_terms),
        ),
        SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL: _security_eval_result(
            "pass" if no_mutation_without_approval else "fail",
            (
                "security mutation handoff requires approval artifact before target source inspection or mutation"
                if no_mutation_without_approval
                else "security mutation handoff does not require approval before target source inspection or mutation"
            ),
            ["approval artifact requirement", "before/after evidence requirements"],
        ),
        SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE: no_commit_result,
    }
    contract_pass = not missing_sections and all(
        results[key]["pass_fail"] == "pass"
        for key in (
            HANDOFF_PROMPT_COMPLETENESS,
            HANDOFF_CONSTRAINT_PRESERVATION,
            HANDOFF_EXECUTION_READINESS,
            HANDOFF_FRESH_SESSION_SUFFICIENCY,
            SECURITY_HANDOFF_FINDING_REFS_PRESENT,
            SECURITY_HANDOFF_RELEASE_GATE_PRESERVED,
            SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
            SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
            SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED,
            SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL,
            SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
        )
    )
    results[READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE] = _security_eval_result(
        "pass" if contract_pass else "fail",
        (
            "ready-to-copy security mutation handoff satisfies contract and commit-boundary checks"
            if contract_pass
            else "ready-to-copy security mutation handoff is incomplete or unsafe"
        ),
        missing_sections or ["security_mutation_handoff_required_sections"],
    )
    return results


def evaluate_security_post_remediation_review_handoff_prompt(
    prompt_text: str,
    *,
    expected_release_gate: str,
    expected_finding_ids: list[str],
    expected_target_branch: str,
    expected_target_head: str,
    expected_untracked_entries: list[str],
    expected_changed_files: list[str],
    expected_validation_terms: list[str],
) -> dict[str, dict[str, Any]]:
    """Run deterministic evals for post-remediation security review handoffs."""
    base = evaluate_handoff_prompt(
        prompt_text,
        readiness=READY_WITH_CONSTRAINTS,
        can_continue=True,
        target_repo_required=True,
        approval_required=True,
    )
    sections = parse_prompt_sections(prompt_text)
    missing_sections = [
        section
        for section in SECURITY_REMEDIATION_REQUIRED_SECTIONS
        if section not in sections
        or _body_missing(sections.get(section, ""), allow_unknown=section.startswith("baseline_"))
    ]
    prompt_lower = prompt_text.lower()

    finding_missing = [
        finding_id
        for finding_id in expected_finding_ids
        if finding_id not in prompt_text and _finding_short_id(finding_id) not in prompt_text
    ]
    release_missing = expected_release_gate not in prompt_text
    target_missing = [
        value
        for value in (expected_target_branch, expected_target_head)
        if value and value not in prompt_text
    ]
    if "target_baseline_constraints" not in sections:
        target_missing.append("target_baseline_constraints")
    target_missing.extend(entry for entry in expected_untracked_entries if entry not in prompt_text)
    changed_missing = [
        changed_file for changed_file in expected_changed_files if changed_file not in prompt_text
    ]
    validation_missing = [
        term for term in expected_validation_terms if term and term not in prompt_text
    ]
    forbidden_terms = (
        "do not mutate bill stack",
        "do not mutate target repositories",
        "do not stage, commit, or push",
        "do not run scans unless a later work order separately approves them",
        "do not run broad target validation",
        "do not read production secrets",
        "real .env values",
        "private keys",
        "credentials",
        "commit planning must remain a later separate work order",
        "do not inspect untracked entries unless separately approved",
    )
    forbidden_missing = [term for term in forbidden_terms if term not in prompt_lower]
    review_bounded = (
        "observe-only post-remediation security review" in prompt_lower
        and "determine whether each finding can be marked remediated" in prompt_lower
        and "run_additional_security_review" in prompt_lower
    )
    no_mutation_without_approval = (
        "no bill stack files are approved for mutation" in prompt_lower
        and "approval artifact" in prompt_lower
        and "read-only" in prompt_lower
    )

    results = {
        **base,
        SECURITY_HANDOFF_FINDING_REFS_PRESENT: _security_eval_result(
            "pass" if not finding_missing else "fail",
            (
                "post-remediation handoff preserves expected finding references"
                if not finding_missing
                else f"post-remediation handoff missing finding references: {', '.join(finding_missing)}"
            ),
            finding_missing or expected_finding_ids,
        ),
        SECURITY_HANDOFF_RELEASE_GATE_PRESERVED: _security_eval_result(
            "pass" if not release_missing else "fail",
            (
                "post-remediation handoff preserves release-gate decision"
                if not release_missing
                else f"post-remediation handoff missing release gate {expected_release_gate}"
            ),
            [expected_release_gate],
        ),
        SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED: _security_eval_result(
            "pass" if not target_missing else "fail",
            (
                "post-remediation handoff preserves target branch/head and untracked-entry constraints"
                if not target_missing
                else f"post-remediation handoff missing target constraints: {', '.join(target_missing)}"
            ),
            target_missing
            or [expected_target_branch, expected_target_head, *expected_untracked_entries],
        ),
        SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED: _security_eval_result(
            "pass" if review_bounded and not changed_missing and not validation_missing else "fail",
            (
                "post-remediation handoff bounds review to remediated findings and preserves mutation evidence"
                if review_bounded and not changed_missing and not validation_missing
                else "post-remediation handoff is missing review scope, changed files, or validation evidence"
            ),
            changed_missing + validation_missing
            or [
                "observe-only post-remediation security review",
                "changed files",
                "focused validation",
            ],
        ),
        SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED: _security_eval_result(
            "pass" if not forbidden_missing else "fail",
            (
                "post-remediation handoff preserves forbidden actions"
                if not forbidden_missing
                else f"post-remediation handoff missing forbidden actions: {', '.join(forbidden_missing)}"
            ),
            forbidden_missing or list(forbidden_terms),
        ),
        SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL: _security_eval_result(
            "pass" if no_mutation_without_approval else "fail",
            (
                "post-remediation handoff forbids mutation and requires approval before read-only inspection"
                if no_mutation_without_approval
                else "post-remediation handoff does not clearly forbid mutation before approval"
            ),
            ["approved files", "approval artifact requirement", "read-only"],
        ),
        SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE: _evaluate_security_no_commit_without_commit_phase(
            prompt_text,
            sections,
        ),
    }
    contract_pass = not missing_sections and all(
        results[key]["pass_fail"] == "pass"
        for key in (
            HANDOFF_PROMPT_COMPLETENESS,
            HANDOFF_CONSTRAINT_PRESERVATION,
            HANDOFF_EXECUTION_READINESS,
            HANDOFF_FRESH_SESSION_SUFFICIENCY,
            SECURITY_HANDOFF_FINDING_REFS_PRESENT,
            SECURITY_HANDOFF_RELEASE_GATE_PRESERVED,
            SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
            SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
            SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED,
            SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL,
            SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
        )
    )
    results[READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE] = _security_eval_result(
        "pass" if contract_pass else "fail",
        (
            "ready-to-copy post-remediation security review handoff satisfies contract"
            if contract_pass
            else "ready-to-copy post-remediation security review handoff is incomplete or unsafe"
        ),
        missing_sections or ["security_post_remediation_review_required_sections"],
    )
    return results
