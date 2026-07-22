"""WO-SPLIT-HANDOFF: security review -> remediation-planning handoff builder."""

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
    _security_finding_ids,
    _security_finding_refs,
    _security_next_recommendation,
    _security_release_gate_decision,
    _target_branch_head_from_evidence,
    _target_untracked_entries,
)


def build_security_review_remediation_handoff_prompt(
    *,
    source_report_text: str,
    source_report_path: Path | str,
    security_report: dict[str, Any],
    security_report_path: Path | str,
    release_gate: dict[str, Any],
    release_gate_path: Path | str,
    finding_records: list[dict[str, Any]],
    findings_dir: Path | str,
    evidence_records: list[dict[str, Any]],
    evidence_dir: Path | str,
    dashboard_projection_path: Path | str,
    output_report_path: Path | str,
    dream_studio_repo_path: Path | str,
    baseline_dream_studio: str = "Unknown; capture exact current Dream Studio branch/HEAD before planning.",
) -> str:
    """Build a complete remediation-planning handoff from Security Review artifacts.

    This generator is intentionally filesystem-passive. Callers load artifacts
    and provide their paths; the generator only renders prompt text.
    """
    recommendation = _security_next_recommendation(security_report)
    next_work_order_id = str(
        recommendation.get("recommended_work_order_id")
        or "wo-dream-studio-018s12-bill-stack-tier0-security-remediation-planning"
    )
    phase_name = str(
        recommendation.get("recommended_phase_name")
        or "Phase 18S.12 - Bill Stack Tier 0 Security Remediation Planning"
    )
    handoff_type = str(
        recommendation.get("recommended_handoff_type") or HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER
    )
    phase_type = str(
        recommendation.get("recommended_phase_type") or PHASE_TYPE_NORMAL_NEXT_WORK_ORDER
    )
    taxonomy = _as_list(recommendation.get("decision_taxonomy")) or list(
        DECISION_TAXONOMIES[PHASE_TYPE_NORMAL_NEXT_WORK_ORDER]
    )
    final_decision = str(recommendation.get("recommended_decision") or HOLD)
    target_id = str(security_report.get("target_id") or "target").strip()
    target_path = _extract_target_path_from_report(source_report_text, target_id)
    target_branch, target_head = _target_branch_head_from_evidence(evidence_records)
    untracked_entries = _target_untracked_entries(evidence_records)
    release_decision = _security_release_gate_decision(security_report, release_gate)
    finding_refs = _security_finding_refs(finding_records)
    finding_ids = _security_finding_ids(finding_records)

    lines = [
        "# Handoff Packet",
        "",
        _section("Phase Name", phase_name),
        _section("Handoff Type", handoff_type),
        _section("Phase Type", phase_type),
        _section("Required Decision Taxonomy", taxonomy),
        _section("Final Decision", final_decision),
        _section(
            "Decision Rationale",
            (
                f"Phase 18S.11 produced a SecurityReviewReport with release gate "
                f"{release_decision}, verdict {security_report.get('verdict', 'unknown')}, "
                f"{len(finding_ids)} finding records, and {len(evidence_records)} evidence records. "
                "This next phase is remediation planning only and starts at HOLD until the receiver "
                "confirms scope, constraints, and the file-backed security artifacts."
            ),
        ),
        _section(
            "Transition Rationale",
            "Security review found release-blocking risks; the next safe step is observe-only remediation planning from file-backed artifacts.",
        ),
        _section("Fresh-Session Rule", FRESH_SESSION_RULE),
        _section(
            "Source Work Order ID", str(security_report.get("source_work_order_id", "unavailable"))
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
                f"Target HEAD is {target_head}.",
                "Current branch differs from the original intake default branch main; carry this forward as a constraint.",
                *[
                    f"Preserve pre-existing untracked entry: {entry}."
                    for entry in untracked_entries
                ],
                "Do not inspect untracked entries unless separately approved.",
                "Do not write artifacts inside the target repository.",
            ],
        ),
        _section(
            "Objective",
            (
                "Plan bounded remediation for the Phase 18S.11 Bill Stack Tier 0 findings. "
                "Do not mutate Bill Stack in this planning phase; actual remediation must be opened "
                "as a later approved mutation Work Order."
            ),
        ),
        _section(
            "Capability Boundary",
            [
                "This Handoff Packet is not an execution command.",
                "This phase is remediation planning only.",
                "Do not touch Bill Stack unless a later Work Order explicitly approves target access.",
                "Do not run scans.",
                "Do not run target validation.",
                "Do not mutate target repositories.",
                "Do not read production secrets, real .env values, private keys, or credentials.",
                "Future remediation must be a separate approved mutation Work Order.",
                *CONSTRAINT_TERMS,
            ],
        ),
        _section("Approval Mode", "observe_only"),
        _section("Risk Level", "medium"),
        _section(
            "Scope Include",
            [
                f"Phase 18S.11 report: {_artifact_path_label(source_report_path)}",
                f"SecurityReviewReport: {_artifact_path_label(security_report_path)}",
                f"ReleaseGateSummary: {_artifact_path_label(release_gate_path)}",
                f"Finding records directory: {_artifact_path_label(findings_dir)}",
                f"Evidence records directory: {_artifact_path_label(evidence_dir)}",
                f"Dashboard projection input: {_artifact_path_label(dashboard_projection_path)}",
                "Handoff Packet Contract: docs/contracts/handoff-packet-contract.md",
                "Security Review Report Artifact Contract: docs/contracts/security-review-report-artifact-contract.md",
            ],
        ),
        _section(
            "Scope Exclude",
            [
                "Bill Stack source inspection",
                "Bill Stack mutation",
                "security remediation execution",
                "security scan execution",
                "target validation",
                "dependency updates",
                "lockfile updates",
                "schema migrations",
                "generated artifacts inside Bill Stack",
                "runtime, CLI, dashboard, profile registry, DB/event, Docker, TORII, cloud, org, global, or enterprise work",
            ],
        ),
        _section(
            "Approved Files If Mutation-Gated",
            [
                "not applicable for observe-only remediation planning",
                "no Bill Stack files are approved for mutation in this phase",
            ],
        ),
        _section(
            "Forbidden Files",
            [
                "Any Bill Stack file unless a later Work Order separately approves read-only access",
                "billstack-api/migrate_direct.py",
                "billstack-web/dev-dist/",
                "production secrets",
                ".env files with real values",
                "private keys",
                "credentials",
                "dependency manifests or lockfiles for mutation",
                "DB/event ledger files",
                "schema migration files",
                "Docker files",
                "dashboard implementation files",
                "TORII/cloud/org/global/enterprise files",
            ],
        ),
        _section(
            "Allowed Actions",
            [
                "produce the Handoff Understanding Report before action",
                "inspect the Phase 18S.11 report and file-backed security artifacts",
                "summarize remediation options for the six finding records",
                "recommend a bounded approved mutation Work Order for actual Bill Stack fixes",
                "write planning output only under Dream Studio meta/audit or Work Order storage",
                "run Dream Studio status checks only if needed for the planning report",
            ],
        ),
        _section(
            "Forbidden Actions",
            [
                "touch Bill Stack",
                "inspect Bill Stack source files without separate approval",
                "run scans",
                "run target validation",
                "mutate target repositories",
                "write artifacts inside Bill Stack",
                "read production secrets, real .env values, private keys, or credentials",
                "inspect untracked entries",
                "stage, commit, or push",
                "install dependencies",
                "update dependencies or lockfiles",
                "implement remediation",
                "add runtime, CLI, dashboard, profile registry, DB/event/schema/Docker/TORII/cloud/org/global/enterprise surfaces",
            ],
        ),
        _section(
            "Approval Artifact Requirement",
            (
                "Not applicable for observe-only remediation planning. Create a new file-backed approval "
                "artifact before any later Bill Stack mutation, scan execution, target validation, dependency "
                "change, lockfile update, or source inspection beyond referenced artifacts."
            ),
        ),
        _section(
            "Before/After Evidence Requirements",
            [
                "Before planning: capture Dream Studio branch, HEAD, and status.",
                "Before planning: confirm Phase 18S.11 SecurityReviewReport, ReleaseGateSummary, finding records, evidence records, and dashboard projection input exist.",
                "Before planning: confirm release gate remains REMEDIATE_BEFORE_RELEASE.",
                "During planning: cite file-backed findings and evidence only.",
                "After planning: confirm no Bill Stack access, mutation, scan, validation, dependency change, lockfile update, or target artifact write occurred.",
                "After planning: list any recommended future approved mutation Work Orders.",
            ],
        ),
        _section(
            "Validation Commands",
            [
                "No Bill Stack validation is approved.",
                "No security scans are approved.",
                "Run Dream Studio checks only if tracked Dream Studio files change.",
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
                READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE,
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
                f"Remediation planning report: {output_report_path}",
                "Bounded approved mutation Work Order recommendation, if remediation remains required.",
                "No target-repo files, scans, validation outputs, commits, pushes, or runtime mutations.",
            ],
        ),
        _section(
            "Readiness Rules",
            [
                "Proceed only after producing the Handoff Understanding Report.",
                "Proceed only if Phase 18S.12 remains remediation planning only.",
                "Proceed only from file-backed Phase 18S.11 report, finding, evidence, release-gate, and dashboard artifacts.",
                "HOLD if Bill Stack access is required.",
                "HOLD if remediation implementation is required.",
                "HOLD if scans or target validation are required.",
                "FAIL if any forbidden action occurs.",
            ],
        ),
        _section(
            "Expected Verdict",
            [
                "PASS if a bounded remediation plan and next approved mutation Work Order recommendation are produced without forbidden action.",
                "PASS WITH RISKS if planning succeeds but unresolved security risks remain, including the RevenueCat finding.",
                "HOLD if target access, scan execution, validation, or mutation is required before planning can continue.",
                "FAIL if Bill Stack, scans, validation, runtime authority, dashboard authority, or forbidden surfaces are mutated.",
            ],
        ),
        _section(
            "Release-Gate Decision Rules",
            [
                f"Current release gate is {release_decision}.",
                "Release gate remains REMEDIATE_BEFORE_RELEASE until the high-severity RevenueCat finding is remediated or risk-accepted through a file-backed operator decision.",
                "SECURITY_CLEAR is forbidden in Phase 18S.12 because remediation has not occurred.",
                "ACCEPT_RISK_WITH_APPROVAL requires a file-backed operator decision artifact.",
                "Any actual fix must be proposed as a separate approved mutation Work Order.",
            ],
        ),
        _section(
            "Stop Conditions",
            [
                "Handoff Understanding Report is missing.",
                "Bill Stack access is requested.",
                "Bill Stack source inspection is requested without separate approval.",
                "Scan execution is requested.",
                "Target validation is requested.",
                "Target mutation is requested.",
                "Production secrets, real .env values, private keys, or credentials are needed.",
                "Untracked entries must be inspected.",
                "Dependency or lockfile changes are requested.",
                "Runtime/dashboard/DB/event/schema/Docker/TORII/cloud/org/global/enterprise expansion appears.",
                "Validation fails and the failure is not understood.",
            ],
        ),
        _section(
            "Final Response Must Include",
            [
                "final response summarizes reviewed artifacts, findings, release-gate status, and recommended next Work Order",
                "final response confirms no Bill Stack access, mutation, scan, validation, dependency change, or push occurred",
                "final response states whether release remains blocked",
            ],
        ),
        _section(
            "Next Handoff Requirements",
            [
                "next handoff must include required first action, approval artifact requirement, allowed commands, forbidden commands, output artifacts, readiness rules, stop conditions, final response, and next handoff sections",
                "next handoff must preserve finding IDs, release gate, target branch/head, and untracked-entry constraints",
            ],
        ),
        _section(
            "Phase-Specific Safety Constraints",
            [
                "required first action is a Handoff Understanding Report",
                "approval artifact is required before any future mutation, scan, target validation, dependency change, or source inspection beyond referenced artifacts",
                "allowed commands are limited to file-backed artifact review unless separately approved",
                "forbidden commands include target validation, scans, package managers, git stage, git commit, git push, Docker, and deploy",
                "output artifacts must stay under Dream Studio meta/audit or Work Order storage",
            ],
        ),
        _section(
            "Handoff Understanding Report Requirement",
            [
                "Before taking action, produce a Handoff Understanding Report.",
                *UNDERSTANDING_REQUIRED_TERMS,
            ],
        ),
        _section(
            "First Safe Action",
            (
                "Read the Phase 18S.11 report, SecurityReviewReport, ReleaseGateSummary, finding "
                "records, and evidence records, then produce the Handoff Understanding Report before "
                "any remediation planning."
            ),
        ),
        _section("Security Finding References", finding_refs),
    ]
    return "\n".join(lines).replace("\n\n\n", "\n\n").strip() + "\n"
