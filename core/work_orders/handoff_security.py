"""WO-SPLIT-HANDOFF: handoff security module."""

from __future__ import annotations
import re
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
    HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION,
    HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER,
    HOLD,
    PHASE_TYPE_APPROVED_MUTATION,
    PHASE_TYPE_NORMAL_NEXT_WORK_ORDER,
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
    UNDERSTANDING_REQUIRED_TERMS,
)
from .handoff_helpers import _as_list, _body_missing, _section
from .handoff_validate import evaluate_handoff_prompt, parse_prompt_sections


def _artifact_path_label(path: Path | str | None) -> str:
    return str(path) if path else "unavailable"


def _security_next_recommendation(security_report: dict[str, Any]) -> dict[str, Any]:
    value = security_report.get("next_work_order_recommendation")
    return value if isinstance(value, dict) else {}


def _finding_short_id(finding_id: str) -> str:
    marker = "sec.finding.bill_stack."
    if finding_id.startswith(marker):
        return finding_id[len(marker) :]  # noqa: E203
    return finding_id.split(".")[-1]


def _security_finding_refs(finding_records: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for finding in finding_records:
        finding_id = str(finding.get("finding_id", "")).strip()
        if not finding_id:
            continue
        refs.append(f"{_finding_short_id(finding_id)} ({finding_id})")
    return refs or ["unavailable"]


def _security_finding_ids(finding_records: list[dict[str, Any]]) -> list[str]:
    ids = [str(finding.get("finding_id", "")).strip() for finding in finding_records]
    return [finding_id for finding_id in ids if finding_id]


def _extract_target_path_from_report(source_report_text: str, target_id: str) -> str:
    target_label = re.escape(target_id.replace("-", " "))
    patterns = (
        rf"{target_label}\s+target:\s*([^\n]+)",
        r"Target Repo Path\s*\n([^\n]+)",
        r"Target Repo Path\s*:\s*([^\n]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, source_report_text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip().strip("`")
            candidate = re.split(r"`?,\s+", candidate, maxsplit=1)[0].strip().strip("`")
            return candidate
    return "not supplied; confirm before any target access"


def _target_branch_head_from_evidence(
    evidence_records: list[dict[str, Any]],
) -> tuple[str, str]:
    for evidence in evidence_records:
        branch_head = evidence.get("branch_head")
        if not isinstance(branch_head, dict):
            continue
        branch = str(branch_head.get("target_branch") or branch_head.get("branch") or "").strip()
        head = str(branch_head.get("target_head") or branch_head.get("head") or "").strip()
        if branch or head:
            return branch or "unknown", head or "unknown"
    return "unknown", "unknown"


def _target_untracked_entries(evidence_records: list[dict[str, Any]]) -> list[str]:
    entries: list[str] = []
    for evidence in evidence_records:
        for key in ("before_status", "after_status", "no_target_mutation_proof"):
            body = str(evidence.get(key, ""))
            for line in body.splitlines():
                match = re.match(r"\s*\?\?\s+(.+?)\s*$", line)
                if match:
                    entries.append(match.group(1).strip())
    deduped: list[str] = []
    for entry in entries:
        if entry and entry not in deduped:
            deduped.append(entry)
    return deduped


def _security_release_gate_decision(
    security_report: dict[str, Any],
    release_gate: dict[str, Any],
) -> str:
    decision = str(release_gate.get("decision", "")).strip()
    if decision:
        return decision
    embedded = security_report.get("release_gate_decision")
    if isinstance(embedded, dict):
        return str(embedded.get("decision", "")).strip() or "HOLD"
    return "HOLD"


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


def _finding_matches(finding: dict[str, Any], wanted: set[str]) -> bool:
    finding_id = str(finding.get("finding_id", "")).strip()
    return finding_id in wanted or _finding_short_id(finding_id) in wanted


def _selected_security_findings(
    finding_records: list[dict[str, Any]],
    included_finding_ids: list[str] | None,
) -> list[dict[str, Any]]:
    wanted = {item.strip() for item in included_finding_ids or [] if item.strip()}
    if not wanted:
        return finding_records
    return [finding for finding in finding_records if _finding_matches(finding, wanted)]


def _finding_assets(finding_records: list[dict[str, Any]]) -> list[str]:
    assets: list[str] = []
    for finding in finding_records:
        for asset in _as_list(finding.get("affected_assets")):
            text = str(asset).strip()
            if text and text not in assets:
                assets.append(text)
    return assets


def _finding_titles(finding_records: list[dict[str, Any]]) -> list[str]:
    titles: list[str] = []
    for finding in finding_records:
        finding_id = str(finding.get("finding_id", "")).strip()
        title = str(finding.get("title", "")).strip()
        label = _finding_short_id(finding_id)
        if title:
            titles.append(f"{label}: {title}")
        elif label:
            titles.append(label)
    return titles or ["unavailable"]


def build_security_remediation_mutation_handoff_prompt(
    *,
    planning_report_text: str,
    planning_report_path: Path | str,
    security_report: dict[str, Any],
    security_report_path: Path | str,
    release_gate: dict[str, Any],
    release_gate_path: Path | str,
    finding_records: list[dict[str, Any]],
    findings_dir: Path | str,
    evidence_records: list[dict[str, Any]],
    evidence_dir: Path | str,
    output_report_path: Path | str,
    dream_studio_repo_path: Path | str,
    baseline_dream_studio: str = "Unknown; capture exact current Dream Studio branch/HEAD before mutation.",
    included_finding_ids: list[str] | None = None,
) -> str:
    """Build a mutation-only security remediation handoff from planning artifacts."""
    target_id = str(security_report.get("target_id") or "target").strip()
    target_path = _extract_target_path_from_report(planning_report_text, target_id)
    target_branch, target_head = _target_branch_head_from_evidence(evidence_records)
    untracked_entries = _target_untracked_entries(evidence_records)
    release_decision = _security_release_gate_decision(security_report, release_gate)
    all_finding_refs = _security_finding_refs(finding_records)
    selected_findings = _selected_security_findings(finding_records, included_finding_ids)
    selected_refs = _security_finding_refs(selected_findings)
    selected_assets = _finding_assets(selected_findings)
    selected_titles = _finding_titles(selected_findings)
    phase_name = "Phase 18S.13 - Bill Stack Tier 0 Priority Security Remediation"
    next_work_order_id = "wo-dream-studio-018s13-bill-stack-tier0-priority-security-remediation"

    lines = [
        "# Handoff Packet",
        "",
        _section("Phase Name", phase_name),
        _section("Handoff Type", HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION),
        _section("Phase Type", PHASE_TYPE_APPROVED_MUTATION),
        _section(
            "Required Decision Taxonomy", list(DECISION_TAXONOMIES[PHASE_TYPE_APPROVED_MUTATION])
        ),
        _section("Final Decision", HOLD),
        _section(
            "Decision Rationale",
            (
                "Phase 18S.12 completed observe-only remediation planning from Phase 18S.11 "
                "file-backed Security Review artifacts. The receiving phase must perform only a "
                "bounded approved mutation for the priority Bill Stack findings, must not stage, "
                "commit, or push, and must defer commit planning to a later Work Order."
            ),
        ),
        _section(
            "Transition Rationale",
            "Remediation planning selected a bounded approved mutation slice; commit and push remain separate later phases.",
        ),
        _section("Fresh-Session Rule", FRESH_SESSION_RULE),
        _section(
            "Source Work Order ID", "wo-dream-studio-018s12-bill-stack-tier0-remediation-planning"
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
                "Do not write generated artifacts inside Bill Stack.",
                "Do not stage, commit, or push.",
                "Commit planning must occur in a later separate Work Order after mutation evidence exists.",
            ],
        ),
        _section(
            "Objective",
            (
                "Implement a bounded Bill Stack security remediation slice for file-backed Phase 18S.11 "
                "findings: require RevenueCat webhook authentication before premium entitlement mutation, "
                "remove or split general household invite-code exposure, and enforce server-side password "
                "policy for registration/reset. Leave other findings for later Work Orders."
            ),
        ),
        _section(
            "Capability Boundary",
            [
                "This Handoff Packet is not an execution command.",
                "This is an approved mutation Work Order for a narrow Bill Stack security remediation slice.",
                "Do not stage, commit, or push.",
                "Commit planning must occur in a later separate Work Order after mutation evidence exists.",
                "Do not run scans.",
                "Do not run target validation unless a focused command is explicitly selected and documented after approved test-surface inspection.",
                "Do not mutate unapproved files.",
                "Do not inspect untracked entries.",
                "Do not read production secrets, real .env values, private keys, or credentials.",
                "Do not update dependencies or lockfiles.",
                "Do not add schema migrations.",
                "Do not implement browser token/session architecture changes.",
                "Do not implement durable auth-state storage.",
                *CONSTRAINT_TERMS,
            ],
        ),
        _section("Approval Mode", "approval_required"),
        _section("Risk Level", "medium"),
        _section(
            "Scope Include",
            [
                f"Phase 18S.12 remediation planning report: {_artifact_path_label(planning_report_path)}",
                f"SecurityReviewReport: {_artifact_path_label(security_report_path)}",
                f"ReleaseGateSummary: {_artifact_path_label(release_gate_path)}",
                f"Finding records directory: {_artifact_path_label(findings_dir)}",
                f"Evidence records directory: {_artifact_path_label(evidence_dir)}",
                "Priority finding: revenuecat_webhook_unsigned",
                "Secondary candidate finding: household_invite_code_exposure",
                "Secondary candidate finding: server_password_policy_gap",
                *[f"Selected finding: {item}" for item in selected_titles],
                *[
                    f"Candidate approved target file from finding evidence: {asset}"
                    for asset in selected_assets
                ],
            ],
        ),
        _section(
            "Scope Exclude",
            [
                "browser token/localStorage/SSE session architecture changes",
                "durable reset/verification/revocation state implementation",
                "dependency updates",
                "lockfile updates",
                "schema migrations",
                "security scans",
                "broad target validation",
                "untracked entries",
                "production secrets, real .env values, private keys, credentials",
                "runtime dashboard/API work",
                "DB/event/schema/Docker/TORII/cloud/org/global/enterprise work",
                "stage, commit, and push",
            ],
        ),
        _section(
            "Approved Files If Mutation-Gated",
            [
                "billstack-api/app/routers/purchases.py",
                "billstack-api/app/routers/household.py",
                "billstack-api/app/schemas/schemas.py",
                "billstack-api/app/routers/auth.py",
                "narrowly scoped Bill Stack test files needed for the approved fixes",
                "non-secret example environment file only if required for a RevenueCat verification placeholder",
                "Dream Studio meta/audit report for this phase",
                "Dream Studio Work Order approval/evidence artifacts for this phase",
            ],
        ),
        _section(
            "Forbidden Files",
            [
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
                "Produce Handoff Understanding Report before mutation.",
                "Create file-backed approval artifact before Bill Stack source inspection or mutation.",
                "Capture Dream Studio branch, HEAD, and status.",
                "Capture Bill Stack branch, HEAD, and status.",
                "Confirm target branch/head and pre-existing untracked entries.",
                "Inspect only approved finding/evidence artifacts.",
                "Inspect approved Bill Stack files only after approval artifact exists.",
                "Implement the bounded RevenueCat webhook authentication fix if source evidence confirms the finding.",
                "Implement household invite-code response boundary fix if source evidence confirms the finding.",
                "Implement server-side password policy enforcement if source evidence confirms the finding.",
                "Add or update narrowly scoped tests for these fixes.",
                "Run only explicitly selected focused validation commands after inspecting the target test surface.",
                "Run git diff/status checks.",
                "Write the phase report under Dream Studio meta/audit.",
            ],
        ),
        _section(
            "Forbidden Actions",
            [
                "Do not stage, commit, or push.",
                "Do not inspect untracked entries.",
                "Do not run scans.",
                "Do not run target validation before selecting and documenting the exact focused command.",
                "Do not read production secrets, real .env values, private keys, or credentials.",
                "Do not update dependencies or lockfiles.",
                "Do not add schema migrations.",
                "Do not implement browser token/session architecture changes.",
                "Do not implement durable reset/verification/revocation storage.",
                "Do not add DB/event/schema/Docker/dashboard/TORII/cloud/org/global/enterprise surfaces.",
                "Do not write generated artifacts inside Bill Stack.",
                "Do not mutate unrelated files.",
                "Do not claim release gate clearance without follow-up evidence or file-backed operator decision.",
            ],
        ),
        _section(
            "Approval Artifact Requirement",
            (
                "Before inspecting or mutating Bill Stack source, create a file-backed approval artifact under "
                "Dream Studio Work Order storage for Phase 18S.13. The approval scope must be limited to the "
                "approved Bill Stack source/test files and Dream Studio evidence/report artifacts. It must "
                "explicitly forbid scans, target validation until named, dependency changes, lockfile changes, "
                "secrets, untracked entry inspection, schema migrations, browser session architecture changes, "
                "durable auth-state storage, dashboard/runtime/DB/event/Docker/TORII/cloud/org/global/enterprise "
                "expansion, stage, commit, push, and unrelated mutation."
            ),
        ),
        _section(
            "Before/After Evidence Requirements",
            [
                "Before mutation: capture Dream Studio branch, HEAD, and status.",
                "Before mutation: capture Bill Stack branch, HEAD, and status.",
                f"Before mutation: confirm Bill Stack branch is {target_branch} or record drift.",
                f"Before mutation: confirm Bill Stack HEAD is {target_head} or record drift.",
                "Before mutation: confirm pre-existing untracked entries are preserved.",
                "Before mutation: confirm approval artifact exists before Bill Stack source inspection or mutation.",
                f"Before mutation: confirm release gate is {release_decision}.",
                "During mutation: record every Bill Stack file inspected.",
                "During mutation: record every Bill Stack file changed.",
                "During mutation: keep the mutation limited to the three included findings.",
                "During mutation: HOLD if implementation requires secrets, dependency changes, lockfile changes, schema migrations, browser session architecture, durable auth-state storage, scans, or untracked entry inspection.",
                "After mutation: capture Bill Stack branch, HEAD, status, and diff summary.",
                "After mutation: capture Dream Studio branch, HEAD, and status.",
                "After mutation: list changed files.",
                "After mutation: confirm pre-existing untracked entries remain uninspected and preserved.",
                "After mutation: confirm no stage, commit, or push occurred.",
                "After mutation: confirm no scans were run unless separately approved.",
                "After mutation: confirm no dependency or lockfile changes occurred.",
                "After mutation: confirm no schema migrations occurred.",
                "After mutation: confirm no target artifacts were written outside approved tracked changes.",
                f"After mutation: confirm release gate remains {release_decision} pending follow-up review or operator decision.",
            ],
        ),
        _section(
            "Validation Commands",
            [
                "No scans are approved by default.",
                "No broad target validation is approved by default.",
                "After approved test-surface inspection, select the narrowest existing test commands for changed backend files.",
                "HOLD if no safe focused command can be identified without package installation, dependency changes, broad target execution, staging, or committing.",
                "Run git status --short in Dream Studio.",
                f'Run git -C "{target_path}" status --short --branch.',
                "Run git diff --check for changed repositories before reporting completion.",
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
                "forbidden_action_compliance",
                "target_repo_mutation",
                "approved_mutation_compliance",
                "result_report_completeness",
                "next_work_order_recommendation",
            ],
        ),
        _section("Report Path", str(output_report_path)),
        _section(
            "Output Artifacts",
            [
                f"Mutation evidence/report: {output_report_path}",
                "Changed-file evidence limited to approved files.",
                "Focused validation evidence if a safe command is identified.",
                "No stage, commit, push, cleanup, scans, dependency changes, or runtime authority changes.",
            ],
        ),
        _section(
            "Readiness Rules",
            [
                "Proceed only after Handoff Understanding Report.",
                "Proceed only after approval artifact exists.",
                "Proceed only if Bill Stack branch/head/status can be captured.",
                "Proceed only if mutation remains limited to the approved files/findings.",
                "Proceed only if staging, committing, and pushing remain forbidden.",
                "HOLD if target branch/head drift makes the baseline unclear.",
                "HOLD if secrets, scans, broad validation, dependency changes, lockfile changes, migrations, untracked entries, or broader architecture work are required.",
                "HOLD if commit planning is requested inside this mutation Work Order.",
                "FAIL if any forbidden action occurs.",
            ],
        ),
        _section(
            "Expected Verdict",
            [
                "MUTATION_COMPLETE if the three scoped remediations are implemented, focused validation passes, evidence is recorded, no stage/commit/push occurs, and no forbidden action occurs.",
                "NEEDS_REMEDIATION if some scoped findings remain open but no forbidden action occurs.",
                "HOLD if target drift, missing approval, secrets, broader architecture, scans, dependency changes, migrations, unsafe validation, staging, committing, or pushing block completion.",
                "FAIL if any forbidden action occurs.",
            ],
        ),
        _section(
            "Release-Gate Decision Rules",
            [
                f"Current release gate is {release_decision}.",
                "The release gate remains REMEDIATE_BEFORE_RELEASE until the high-severity RevenueCat finding is remediated and verified, or risk-accepted through a file-backed operator decision.",
                "This mutation Work Order may produce remediation evidence, but it must not declare final security clearance by itself.",
                "A follow-up observe-only review, release-gate review, or operator decision is required before any release-gate upgrade.",
            ],
        ),
        _section(
            "Stop Conditions",
            [
                "Handoff Understanding Report is missing.",
                "Approval artifact is missing before Bill Stack source inspection or mutation.",
                "Bill Stack branch/HEAD/status cannot be captured.",
                "Target branch/head drift is not understood.",
                "Untracked entries must be inspected.",
                "Secrets, real .env values, private keys, or credentials are needed.",
                "Scans are requested.",
                "Dependency or lockfile changes are requested.",
                "Schema migrations are required.",
                "Browser token/session architecture changes are required.",
                "Durable auth-state storage is required.",
                "Stage, commit, or push is requested.",
                "Commit planning is requested inside this mutation Work Order.",
                "Dashboard/runtime/DB/event/Docker/TORII/cloud/org/global/enterprise expansion appears.",
                "Validation fails and the failure is not understood.",
            ],
        ),
        _section(
            "Final Response Must Include",
            [
                "final response lists files inspected, files changed, focused validation, and unresolved findings",
                "final response confirms no stage, commit, push, scan, dependency change, lockfile change, or schema migration occurred",
                "final response recommends the next handoff, normally post-remediation review or commit planning only after review accepts the mutation evidence",
            ],
        ),
        _section(
            "Next Handoff Requirements",
            [
                "next handoff must include required first action, approval artifact, allowed commands, forbidden commands, output artifacts, readiness rules, stop conditions, final response, and next handoff sections",
                "next handoff must preserve release gate, changed-file evidence, validation evidence, and stage/commit/push prohibition until an explicit commit phase",
            ],
        ),
        _section(
            "Phase-Specific Safety Constraints",
            [
                "required first action is a Handoff Understanding Report",
                "approval artifact is required before source inspection or mutation",
                "allowed commands are limited to exact focused validation selected after approved test-surface inspection",
                "forbidden commands include scans, package managers, git stage, git commit, git push, Docker, deploy, and broad validation",
                "output artifacts must stay under Dream Studio meta/audit or Work Order storage",
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
                "Read the Phase 18S.12 remediation planning report, Phase 18S.11 SecurityReviewReport, "
                "ReleaseGateSummary, and the three included finding/evidence records, then produce the "
                "Handoff Understanding Report before creating the approval artifact."
            ),
        ),
        _section("Security Finding References", all_finding_refs),
        _section("Included Remediation Findings", selected_refs),
        _section(
            "Deferred Security Findings",
            [
                "browser_token_exposure_window remains deferred to a later session/auth architecture Work Order.",
                "in_memory_auth_state remains deferred to a later durable auth-state Work Order.",
                "dependency_reproducibility_gap remains deferred to a later dependency review and reproducibility Work Order.",
            ],
        ),
    ]
    return "\n".join(lines).replace("\n\n\n", "\n\n").strip() + "\n"


def _mutation_validation_lines(mutation_evidence: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in _as_list(mutation_evidence.get("focused_validation")):
        if not isinstance(item, dict):
            continue
        command = str(item.get("command", "")).strip()
        result = str(item.get("result", "")).strip()
        if command and result:
            lines.append(f"{command} -> {result}")
    return lines or ["unavailable"]


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


def _security_eval_result(pass_fail: str, observed: str, evidence: list[str]) -> dict[str, Any]:
    return {
        "pass_fail": pass_fail,
        "observed_behavior": observed,
        "score": 1 if pass_fail == "pass" else 0,
        "evidence": evidence,
    }


def _allowed_commit_authority_leaks(sections: dict[str, str]) -> list[str]:
    allowed_body = sections.get("allowed_actions", "").lower()
    leak_patterns = (
        "commit only",
        "commit scoped",
        "commit changes",
        "stage changes",
        "stage only",
        "stage scoped",
        "stage and commit",
        "stage or commit",
        "git commit",
        "git add",
        "may commit",
        "can commit",
    )
    return [pattern for pattern in leak_patterns if pattern in allowed_body]


def _evaluate_security_no_commit_without_commit_phase(
    prompt_text: str,
    sections: dict[str, str],
) -> dict[str, Any]:
    handoff_type = sections.get("handoff_type", "").strip()
    phase_type = sections.get("phase_type", "").strip()
    is_approved_mutation = (
        handoff_type == HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION
        and phase_type == PHASE_TYPE_APPROVED_MUTATION
    )
    if not is_approved_mutation:
        return _security_eval_result(
            "pass",
            "security commit-boundary eval is not applicable to this non-approved-mutation handoff",
            ["handoff_type", "phase_type"],
        )

    prompt_lower = prompt_text.lower()
    boundary_body = "\n".join(
        sections.get(section, "").lower()
        for section in (
            "capability_boundary",
            "forbidden_actions",
            "approval_artifact_requirement",
            "readiness_rules",
            "before_after_evidence_requirements",
        )
    )
    leaks = _allowed_commit_authority_leaks(sections)
    forbids_stage_commit_push = (
        "do not stage, commit, or push" in boundary_body
        or "forbid stage, commit, and push" in boundary_body
        or (
            "do not stage" in boundary_body
            and "do not commit" in boundary_body
            and "do not push" in boundary_body
        )
    )
    defers_commit_planning = (
        "commit planning" in prompt_lower
        and "later" in prompt_lower
        and "work order" in prompt_lower
    )
    passes = forbids_stage_commit_push and defers_commit_planning and not leaks
    evidence = []
    if not forbids_stage_commit_push:
        evidence.append("missing explicit stage/commit/push prohibition")
    if not defers_commit_planning:
        evidence.append("missing later commit-planning Work Order boundary")
    evidence.extend(f"allowed action leak: {leak}" for leak in leaks)
    return _security_eval_result(
        "pass" if passes else "fail",
        (
            "approved security mutation handoff forbids stage/commit/push and defers commit planning"
            if passes
            else "approved security mutation handoff leaks or omits commit-boundary authority"
        ),
        evidence or ["stage_commit_push_forbidden", "commit_planning_deferred"],
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
