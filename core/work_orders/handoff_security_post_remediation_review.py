"""WO-SPLIT-HANDOFF: security post-remediation observe-only review handoff builder."""

from __future__ import annotations
from pathlib import Path
from typing import Any

from .handoff_constants import (
    CONSTRAINT_TERMS,
    DECISION_TAXONOMIES,
    FRESH_SESSION_RULE,
    HANDOFF_CONSTRAINT_PRESERVATION,
    HANDOFF_EXECUTION_READINESS,
    HANDOFF_FRESH_SESSION_SUFFICIENCY,
    HANDOFF_PROMPT_COMPLETENESS,
    HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER,
    HOLD,
    PHASE_TYPE_NORMAL_NEXT_WORK_ORDER,
    READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE,
    SECURITY_HANDOFF_FINDING_REFS_PRESENT,
    SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED,
    SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
    SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL,
    SECURITY_HANDOFF_RELEASE_GATE_PRESERVED,
    SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
    SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
    UNDERSTANDING_REQUIRED_TERMS,
)
from .handoff_helpers import _as_list, _section
from .handoff_security_shared import (
    _artifact_path_label,
    _extract_target_path_from_report,
    _mutation_validation_lines,
    _security_finding_refs,
    _security_release_gate_decision,
    _selected_security_findings,
)


def build_security_post_remediation_review_handoff_prompt(
    *,
    mutation_report_text: str,
    mutation_report_path: Path | str,
    mutation_evidence: dict[str, Any],
    mutation_evidence_path: Path | str,
    paused_work_path: Path | str,
    security_report: dict[str, Any],
    security_report_path: Path | str,
    release_gate: dict[str, Any],
    release_gate_path: Path | str,
    finding_records: list[dict[str, Any]],
    findings_dir: Path | str,
    output_report_path: Path | str,
    dream_studio_repo_path: Path | str,
    baseline_dream_studio: str = "Unknown; capture exact current Dream Studio branch/HEAD before review.",
) -> str:
    """Build an observe-only post-remediation review handoff from mutation artifacts."""
    target_id = str(
        mutation_evidence.get("target_id") or security_report.get("target_id") or "target"
    )
    target_path = str(
        mutation_evidence.get("target_path") or ""
    ).strip() or _extract_target_path_from_report(
        mutation_report_text,
        target_id,
    )
    target_branch = str(mutation_evidence.get("target_branch") or "unknown").strip()
    target_head = str(mutation_evidence.get("target_head") or "unknown").strip()
    changed_files = [str(item) for item in _as_list(mutation_evidence.get("files_changed"))]
    preserved_untracked = [
        str(item) for item in _as_list(mutation_evidence.get("preserved_untracked_entries"))
    ]
    included_ids = [str(item) for item in _as_list(mutation_evidence.get("included_findings"))]
    selected_findings = _selected_security_findings(finding_records, included_ids)
    selected_refs = _security_finding_refs(selected_findings)
    all_finding_refs = _security_finding_refs(finding_records)
    release_decision = str(
        mutation_evidence.get("release_gate_after") or ""
    ).strip() or _security_release_gate_decision(security_report, release_gate)
    validation_lines = _mutation_validation_lines(mutation_evidence)
    phase_name = "Phase 18S.14 - Bill Stack Post-Remediation Security Review"
    next_work_order_id = "wo-dream-studio-018s14-bill-stack-post-remediation-security-review"

    lines = [
        "# Handoff Packet",
        "",
        _section("Phase Name", phase_name),
        _section("Handoff Type", HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER),
        _section("Phase Type", PHASE_TYPE_NORMAL_NEXT_WORK_ORDER),
        _section(
            "Required Decision Taxonomy",
            list(DECISION_TAXONOMIES[PHASE_TYPE_NORMAL_NEXT_WORK_ORDER]),
        ),
        _section("Final Decision", HOLD),
        _section(
            "Decision Rationale",
            (
                "Phase 18S.13 completed a bounded approved mutation for the priority Bill Stack "
                "Tier 0 security findings. This next phase is an observe-only post-remediation "
                "security review that must verify the file-backed mutation evidence before any "
                "release-gate or commit-planning recommendation changes."
            ),
        ),
        _section(
            "Transition Rationale",
            "A bounded mutation produced evidence; the next safe step is observe-only review before any commit planning or release-gate upgrade.",
        ),
        _section("Fresh-Session Rule", FRESH_SESSION_RULE),
        _section(
            "Source Work Order ID", str(mutation_evidence.get("work_order_id", "unavailable"))
        ),
        _section("Next Work Order ID", next_work_order_id),
        _section("Dream Studio Repo Path", str(dream_studio_repo_path)),
        _section("Target Repo Path", target_path),
        _section("Baseline Dream Studio Branch/HEAD", baseline_dream_studio),
        _section(
            "Baseline Target Repo Branch/HEAD",
            f"Branch: {target_branch}\nHEAD: {target_head}",
        ),
        _section(
            "Target Baseline Constraints",
            [
                f"Target branch is {target_branch}.",
                f"Target HEAD before the Phase 18S.13 mutation slice was {target_head}.",
                "Current branch differs from the original intake default branch main; carry this forward as a constraint.",
                *[
                    f"Preserve pre-existing untracked entry: {entry}."
                    for entry in preserved_untracked
                ],
                "Do not inspect untracked entries unless separately approved.",
                "Do not stage, commit, or push.",
                "Commit planning must remain a later separate Work Order after post-remediation review evidence exists.",
            ],
        ),
        _section(
            "Objective",
            (
                "Perform an observe-only post-remediation security review of the three Phase 18S.13 "
                "remediated findings. Determine whether each finding can be marked remediated from "
                "file-backed evidence, and recommend whether the release gate remains "
                "REMEDIATE_BEFORE_RELEASE, moves to RUN_ADDITIONAL_SECURITY_REVIEW, or requires "
                "follow-up commit planning."
            ),
        ),
        _section(
            "Capability Boundary",
            [
                "This Handoff Packet is not an execution command.",
                "This phase is observe-only post-remediation security review.",
                "Do not mutate Bill Stack.",
                "Do not mutate target repositories.",
                "Do not stage, commit, or push.",
                "Do not run scans unless a later Work Order separately approves them.",
                "Do not run broad target validation.",
                "Do not read production secrets, real .env values, private keys, or credentials.",
                "Do not inspect untracked entries unless separately approved.",
                "Commit planning must remain a later separate Work Order.",
                *CONSTRAINT_TERMS,
            ],
        ),
        _section("Approval Mode", "approval_required"),
        _section("Risk Level", "medium"),
        _section(
            "Scope Include",
            [
                f"Phase 18S.13 report: {_artifact_path_label(mutation_report_path)}",
                f"Phase 18S.13 mutation evidence: {_artifact_path_label(mutation_evidence_path)}",
                f"PausedWork continuity artifact: {_artifact_path_label(paused_work_path)}",
                f"SecurityReviewReport: {_artifact_path_label(security_report_path)}",
                f"ReleaseGateSummary: {_artifact_path_label(release_gate_path)}",
                f"Finding records directory: {_artifact_path_label(findings_dir)}",
                *[
                    f"Phase 18S.13 changed file for read-only review: {item}"
                    for item in changed_files
                ],
                *[f"Phase 18S.13 focused validation result: {item}" for item in validation_lines],
            ],
        ),
        _section(
            "Scope Exclude",
            [
                "Bill Stack mutation",
                "security remediation execution",
                "security scan execution unless separately approved",
                "broad target validation",
                "dependency updates",
                "lockfile updates",
                "schema migrations",
                "generated artifacts inside Bill Stack",
                "stage, commit, and push",
                "commit planning execution",
                "runtime, CLI, dashboard, profile registry, DB/event, Docker, TORII, cloud, org, global, or enterprise work",
            ],
        ),
        _section(
            "Approved Files If Mutation-Gated",
            [
                "observe-only post-remediation review approves no Bill Stack mutation",
                "no Bill Stack files are approved for mutation in this phase",
                "read-only Bill Stack inspection, if needed, is limited to Phase 18S.13 changed files after a file-backed approval artifact exists",
            ],
        ),
        _section(
            "Forbidden Files",
            [
                "Bill Stack files outside the Phase 18S.13 changed-file review set unless separately approved",
                "billstack-api/migrate_direct.py",
                "billstack-web/dev-dist/",
                "production secrets",
                "real .env values",
                "private keys",
                "credentials",
                "dependency manifests or lockfiles for mutation",
                "schema migration files",
                "runtime dashboard implementation files",
                "DB/event ledger files",
                "Docker files",
                "TORII/cloud/org/global/enterprise files",
                "unrelated Bill Stack files",
                "unrelated Dream Studio files",
            ],
        ),
        _section(
            "Allowed Actions",
            [
                "Produce Handoff Understanding Report before action.",
                "Create a file-backed approval artifact before any Bill Stack read-only inspection.",
                "Inspect Phase 18S.13 report and mutation evidence.",
                "Inspect Phase 18S.11 SecurityReviewReport, ReleaseGateSummary, and included finding records.",
                "Inspect Phase 18S.13 changed files read-only only after approval artifact exists.",
                "Determine whether the three included findings can be marked remediated from evidence.",
                "Recommend whether release gate remains REMEDIATE_BEFORE_RELEASE, moves to RUN_ADDITIONAL_SECURITY_REVIEW, or requires follow-up commit planning.",
                "Write review output only under Dream Studio meta/audit or Work Order storage.",
                "Run Dream Studio status checks.",
            ],
        ),
        _section(
            "Forbidden Actions",
            [
                "Do not mutate Bill Stack.",
                "Do not mutate target repositories.",
                "Do not stage, commit, or push.",
                "Do not run scans unless separately approved.",
                "Do not run broad target validation.",
                "Do not read production secrets, real .env values, private keys, or credentials.",
                "Do not inspect untracked entries unless separately approved.",
                "Do not update dependencies or lockfiles.",
                "Do not add schema migrations.",
                "Do not implement remediation.",
                "Do not perform commit planning inside this review Work Order.",
                "Do not add DB/event/schema/Docker/dashboard/TORII/cloud/org/global/enterprise surfaces.",
            ],
        ),
        _section(
            "Approval Artifact Requirement",
            (
                "Before any Bill Stack read-only inspection, create a file-backed approval artifact under "
                "Dream Studio Work Order storage for Phase 18S.14. The approval scope must be limited to "
                "observe-only review of Phase 18S.13 artifacts and, if needed, read-only inspection of "
                "the Phase 18S.13 changed files. It must explicitly forbid mutation, scans unless "
                "separately approved, broad validation, dependency changes, lockfile changes, secrets, "
                "untracked-entry inspection, stage, commit, push, dashboard/runtime/DB/event/Docker/"
                "TORII/cloud/org/global/enterprise expansion, and commit planning execution."
            ),
        ),
        _section(
            "Before/After Evidence Requirements",
            [
                "Before review: capture Dream Studio branch, HEAD, and status.",
                "Before review: confirm Phase 18S.13 report and mutation evidence exist.",
                "Before review: confirm paused_work.yaml records Phase 18S.13 as completed or resolved.",
                f"Before review: confirm release gate remains {release_decision}.",
                "Before any Bill Stack read-only inspection: confirm approval artifact exists.",
                "During review: cite Phase 18S.13 changed files and validation evidence.",
                "During review: do not claim findings remediated without file-backed evidence.",
                "After review: record finding status recommendations for the three included findings.",
                "After review: record release-gate recommendation.",
                "After review: confirm no target mutation, scans, broad validation, stage, commit, or push occurred.",
                "After review: list any recommended follow-up Work Orders, including commit planning if appropriate.",
            ],
        ),
        _section(
            "Validation Commands",
            [
                "No scans are approved by default.",
                "No broad target validation is approved.",
                "No target mutation, stage, commit, or push is approved.",
                "Run Dream Studio status checks.",
                "Run only explicitly scoped read-only checks named by the Phase 18S.14 reviewer after approval artifact exists.",
            ],
        ),
        _section(
            "Eval Requirements",
            [
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
                READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE,
                "post_remediation_changed_files_preserved",
                "post_remediation_validation_results_preserved",
                "forbidden_action_compliance",
                "target_repo_mutation",
                "result_report_completeness",
                "next_work_order_recommendation",
            ],
        ),
        _section("Report Path", str(output_report_path)),
        _section(
            "Output Artifacts",
            [
                f"Post-remediation review report: {output_report_path}",
                "Finding status recommendations for reviewed remediation items.",
                "Release-gate recommendation with evidence references.",
                "No target mutation, scan execution, broad validation, stage, commit, push, or cleanup.",
            ],
        ),
        _section(
            "Readiness Rules",
            [
                "Proceed only after Handoff Understanding Report.",
                "Proceed only after approval artifact exists before any Bill Stack read-only inspection.",
                "Proceed only if Phase 18S.14 remains observe-only post-remediation review.",
                "Proceed only from file-backed Phase 18S.13 report and mutation evidence.",
                "HOLD if Bill Stack mutation is required.",
                "HOLD if scans or broad validation are required.",
                "HOLD if commit planning or commit execution is requested inside this review Work Order.",
                "FAIL if any forbidden action occurs.",
            ],
        ),
        _section(
            "Expected Verdict",
            [
                "PASS if post-remediation review artifacts are produced, the three finding status recommendations are evidence-backed, release-gate recommendation is bounded, and no forbidden action occurs.",
                "PASS WITH RISKS if review completes but evidence remains incomplete or release gate cannot be upgraded.",
                "HOLD if mutation, scans, broad validation, commit planning, or forbidden target access is required.",
                "FAIL if target mutation, scans without approval, broad validation, stage, commit, push, runtime authority, dashboard authority, or forbidden surfaces are mutated.",
            ],
        ),
        _section(
            "Release-Gate Decision Rules",
            [
                f"Current release gate is {release_decision}.",
                "Decide whether the release gate remains REMEDIATE_BEFORE_RELEASE.",
                "Decide whether the release gate should move to RUN_ADDITIONAL_SECURITY_REVIEW.",
                "Decide whether follow-up commit planning is required before any release-gate upgrade.",
                "SECURITY_CLEAR is not available from this review unless all blocking findings and required approval/evidence gaps are resolved by file-backed evidence.",
                "Commit planning must remain a later separate Work Order.",
            ],
        ),
        _section(
            "Stop Conditions",
            [
                "Handoff Understanding Report is missing.",
                "Approval artifact is missing before Bill Stack read-only inspection.",
                "Bill Stack mutation is requested.",
                "Scan execution is requested without separate approval.",
                "Broad target validation is requested.",
                "Stage, commit, or push is requested.",
                "Commit planning is requested inside this review Work Order.",
                "Production secrets, real .env values, private keys, or credentials are needed.",
                "Untracked entries must be inspected.",
                "Dependency or lockfile changes are requested.",
                "Schema migrations are required.",
                "Dashboard/runtime/DB/event/Docker/TORII/cloud/org/global/enterprise expansion appears.",
                "Validation fails and the failure is not understood.",
            ],
        ),
        _section(
            "Final Response Must Include",
            [
                "final response summarizes reviewed mutation evidence, changed files, finding status recommendations, and release-gate recommendation",
                "final response confirms no mutation, scan, broad validation, stage, commit, push, dependency change, or schema migration occurred",
                "final response states the next handoff, usually commit planning only if review accepts the remediation evidence",
            ],
        ),
        _section(
            "Next Handoff Requirements",
            [
                "next handoff must include required first action, approval artifact, allowed commands, forbidden commands, output artifacts, readiness rules, stop conditions, final response, and next handoff sections",
                "next handoff must preserve mutation evidence, release gate, changed-file list, and explicit cleanup/deletion/archive prohibition unless separately approved",
            ],
        ),
        _section(
            "Phase-Specific Safety Constraints",
            [
                "required first action is a Handoff Understanding Report",
                "approval artifact is required before any Bill Stack read-only inspection",
                "allowed commands are limited to read-only artifact review and explicitly scoped status checks",
                "forbidden commands include scans, broad validation, package managers, git stage, git commit, git push, Docker, and deploy",
                "output artifacts must stay under Dream Studio meta/audit or Work Order storage",
                "exact staged file list is unavailable because this is not a commit execution phase",
                "stage exact file paths only is a future commit execution requirement, not approval for this review",
                "do not stage parent directories wholesale in any later commit execution phase",
                "git diff --cached --name-only is required only in a later approved commit execution phase",
                "git diff --cached --stat is required only in a later approved commit execution phase",
                "git diff --cached --check is required only in a later approved commit execution phase",
                "no push unless separately approved",
                "paused work artifact must be preserved as review evidence",
                "remaining deferred work must stay paused unless a future Work Order explicitly resumes it",
                "do not run deferred phases from this review packet",
                "resume requirements must be carried in any later continuity packet",
                "completed commit hashes are unavailable because this review must not commit",
            ],
        ),
        _section(
            "Handoff Understanding Report Requirement",
            [
                "Before taking action, produce a Handoff Understanding Report with:",
                *UNDERSTANDING_REQUIRED_TERMS,
            ],
        ),
        _section(
            "First Safe Action",
            (
                "Read the Phase 18S.13 report, mutation evidence, paused_work.yaml, Phase 18S.11 "
                "SecurityReviewReport, ReleaseGateSummary, and the three included finding records; "
                "then produce the Handoff Understanding Report before creating any approval artifact "
                "or inspecting Bill Stack."
            ),
        ),
        _section("Reviewed Remediation Findings", selected_refs),
        _section("All Phase 18S.11 Security Finding References", all_finding_refs),
    ]
    return "\n".join(lines).replace("\n\n\n", "\n\n").strip() + "\n"
