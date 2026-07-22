"""WO-SPLIT-HANDOFF: security remediation-planning -> approved-mutation handoff builder."""

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
    HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION,
    HOLD,
    PHASE_TYPE_APPROVED_MUTATION,
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
from .handoff_helpers import _section
from .handoff_security_shared import (
    _artifact_path_label,
    _extract_target_path_from_report,
    _finding_assets,
    _finding_titles,
    _security_finding_refs,
    _security_release_gate_decision,
    _selected_security_findings,
    _target_branch_head_from_evidence,
    _target_untracked_entries,
)


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
