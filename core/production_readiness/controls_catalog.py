"""Control-definition data and catalog assembly.

WO-GF-READINESS-INSIGHTS: split from ``core/production_readiness/controls.py``.
No logic changes — extracted verbatim.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.security.lifecycle import build_security_lifecycle_gate

from .controls_shared import FULL_REVIEW_EVENTS

CONTROL_STATES = ("pass", "fail", "warn", "not_applicable", "manual_review", "unknown")


PRODUCTION_CONTROL_SEEDS: tuple[
    tuple[str, str, str, str, tuple[str, ...], tuple[str, ...]], ...
] = (
    (
        "database_readiness",
        "database_readiness",
        "Database Readiness",
        "Check schema, migration, rollback, transaction, backup, and data-boundary readiness.",
        ("database_change",),
        ("project_intake", "release_merge", "database_change", "live_cutover"),
    ),
    (
        "api_resilience",
        "api_resilience",
        "API Resilience",
        "Check auth, object authorization, validation, rate limiting, error handling, and abuse controls.",
        ("api_surface", "runtime_change", "security_change"),
        ("project_intake", "release_merge", "deployment", "live_cutover"),
    ),
    (
        "caching_correctness",
        "caching_correctness",
        "Caching Correctness",
        "Check cache scoping, invalidation, stale behavior, poisoning risk, and sensitive data isolation.",
        ("cache_change", "runtime_change", "api_surface"),
        ("release_merge", "deployment", "live_cutover"),
    ),
    (
        "accessibility_review",
        "accessibility_review",
        "Accessibility Review",
        "Check keyboard, focus, contrast, labels, forms, screen reader semantics, and responsive states.",
        ("dashboard_runtime", "frontend_change"),
        ("project_intake", "release_merge", "publication"),
    ),
    (
        "observability_logging",
        "observability_logging",
        "Observability And Logging",
        "Check redaction, auditability, alerts, incident handoff, and operational visibility.",
        ("observability_change", "runtime_change", "api_surface"),
        ("project_intake", "release_merge", "deployment", "live_cutover"),
    ),
    (
        "performance_scalability",
        "performance_scalability",
        "Performance And Scalability",
        "Check query/API latency risk, concurrency, timeouts, resource use, and load-test evidence.",
        ("performance_change", "database_change", "api_surface", "runtime_change"),
        ("project_intake", "release_merge", "deployment", "live_cutover"),
    ),
    (
        "dependency_supply_chain",
        "dependency_supply_chain",
        "Dependency And Supply Chain",
        "Check vulnerable dependencies, provenance, SBOM evidence, lockfiles, and update policy.",
        ("dependency_supply_chain",),
        ("release_merge", "dependency_change", "publication"),
    ),
    (
        "code_quality_architecture",
        "code_quality_architecture",
        "Code Quality And Architecture",
        "Check dead code, duplication, boundaries, lint/type/test gates, and maintainability risk.",
        ("code_change", "architecture_change", "dashboard_runtime"),
        ("project_intake", "release_merge", "major_architecture_change"),
    ),
    (
        "privacy_compliance_applicability",
        "privacy_compliance_applicability",
        "Privacy And Compliance Applicability",
        "Classify sensitive data, legal review needs, retention, deletion, and external sharing.",
        ("privacy_change", "security_change", "api_surface", "database_change"),
        ("project_intake", "release_merge", "publication", "external_project_onboarding"),
    ),
    (
        "release_readiness",
        "release_readiness",
        "Release Readiness",
        "Check release gate evidence, rollback, publication boundary, docs drift, and unresolved blockers.",
        ("release_change", "publication", "runtime_change"),
        ("release_merge", "publication", "deployment", "live_cutover"),
    ),
    (
        "backup_restore_rollback",
        "backup_restore_rollback",
        "Backup, Restore, And Rollback",
        "Check backup, restore rehearsal, rollback evidence, and destructive-change containment.",
        ("database_change", "runtime_change", "release_change"),
        ("release_merge", "database_change", "deployment", "live_cutover"),
    ),
)


OVERLAP_DECISIONS: tuple[dict[str, Any], ...] = (
    {
        "existing_skill_control_name": "skills/security:modes/review",
        "proposed_canonical_owner": "security_review",
        "overlap_reason": "Existing review mode already covers high-confidence static security review.",
        "decision": "map_existing_skill_to_control",
        "evidence": ["skills/security/modes/review/SKILL.md", "core/security/lifecycle.py"],
        "validation_requirement": "47-control catalog and lifecycle gate tests must pass.",
        "rollback_supersession_plan": "Keep security lifecycle gate data-only; revert mapping without deleting skill metadata.",
        "dashboard_project_health_impact": "Security findings and manual review controls affect health/readiness.",
        "contract_atlas_impact": "Security lifecycle gate remains an atlas section.",
    },
    {
        "existing_skill_control_name": "skills/quality:modes/secure",
        "proposed_canonical_owner": "security_review",
        "overlap_reason": "Quality secure provides OWASP/STRIDE process guidance; security catalog remains canonical.",
        "decision": "keep_existing",
        "evidence": ["skills/quality/modes/secure/SKILL.md"],
        "validation_requirement": "No duplicate security skill family is introduced.",
        "rollback_supersession_plan": "No supersession; mapping can be removed from production readiness catalog.",
        "dashboard_project_health_impact": "Used as evidence for security review owner mapping.",
        "contract_atlas_impact": "Listed as an existing capability, not a new authority.",
    },
    {
        "existing_skill_control_name": "skills/quality:modes/harden",
        "proposed_canonical_owner": "code_quality_architecture",
        "overlap_reason": "Hardening mode covers maintainability, robustness, and release-quality concerns.",
        "decision": "map_existing_skill_to_control",
        "evidence": ["skills/quality/modes/harden/SKILL.md"],
        "validation_requirement": "Production readiness targeted checks include code/architecture changes.",
        "rollback_supersession_plan": "Retain original harden mode and remove only the readiness mapping.",
        "dashboard_project_health_impact": "Architecture/code blockers can reduce readiness confidence.",
        "contract_atlas_impact": "Production readiness workflow maps existing quality capability.",
    },
    {
        "existing_skill_control_name": "skills/quality:modes/structure-audit",
        "proposed_canonical_owner": "code_quality_architecture",
        "overlap_reason": "Structure audit covers unowned files and architecture boundary risk.",
        "decision": "map_existing_skill_to_control",
        "evidence": ["skills/quality/modes/structure-audit/SKILL.md"],
        "validation_requirement": "Architecture controls expose evidence requirements and manual review states.",
        "rollback_supersession_plan": "Mapping can be reverted without changing structure-audit behavior.",
        "dashboard_project_health_impact": "Boundary violations become readiness blockers only with evidence.",
        "contract_atlas_impact": "Adds control-family mapping to Contract Atlas maturity.",
    },
    {
        "existing_skill_control_name": "interfaces/cli/ci_gate.py",
        "proposed_canonical_owner": "release_readiness",
        "overlap_reason": "Existing release gate already runs tests, format, lint baseline, docs drift, and pip-audit.",
        "decision": "strengthen_existing_skill",
        "evidence": ["interfaces/cli/ci_gate.py", "core/release/versioning.py"],
        "validation_requirement": "Guarded release gate must pass with live SQLite unchanged.",
        "rollback_supersession_plan": "Revert release-readiness integration while keeping CI gate intact.",
        "dashboard_project_health_impact": "Release blockers affect readiness, not synthetic health.",
        "contract_atlas_impact": "Release gate remains a release-blocking domain.",
    },
    {
        "existing_skill_control_name": "projections/api/routes/project_intelligence.py",
        "proposed_canonical_owner": "project_health_and_readiness",
        "overlap_reason": "Project health already derives current condition from SQLite evidence.",
        "decision": "strengthen_existing_skill",
        "evidence": ["tests/unit/test_project_portfolio_authority_security_hydration.py"],
        "validation_requirement": "Project detail view must separate health and readiness.",
        "rollback_supersession_plan": "Remove readiness detail wiring without changing existing health route.",
        "dashboard_project_health_impact": "Health remains current condition; readiness becomes deployment posture.",
        "contract_atlas_impact": "Dashboard runtime and production readiness domains are both impacted.",
    },
    {
        "existing_skill_control_name": "new:database_readiness",
        "proposed_canonical_owner": "database_readiness",
        "overlap_reason": "No existing specialized skill fully owns schema, migration, rollback, data, and query readiness.",
        "decision": "create_new_skill",
        "evidence": ["docs/DATABASE.md", "docs/MIGRATION_AUTHORITY.md"],
        "validation_requirement": "Database change classification must target database readiness controls.",
        "rollback_supersession_plan": "Keep control definitions data-only until specialized skill docs are expanded.",
        "dashboard_project_health_impact": "Database evidence gaps lower readiness confidence, not fake scores.",
        "contract_atlas_impact": "Production readiness control family added.",
    },
    {
        "existing_skill_control_name": "new:api_resilience",
        "proposed_canonical_owner": "api_resilience",
        "overlap_reason": "API abuse/resilience spans security and production behavior; separate owner is clearer.",
        "decision": "create_new_skill",
        "evidence": ["projections/api/routes"],
        "validation_requirement": "API route changes must target API resilience controls.",
        "rollback_supersession_plan": "Remove control owner mapping; leave security controls intact.",
        "dashboard_project_health_impact": "API readiness affects readiness and release blockers.",
        "contract_atlas_impact": "Production readiness control family added.",
    },
    {
        "existing_skill_control_name": "new:privacy_compliance_applicability",
        "proposed_canonical_owner": "privacy_compliance_applicability",
        "overlap_reason": "Compliance applicability requires classification and legal review flags, not compliance claims.",
        "decision": "create_new_skill",
        "evidence": ["docs/contracts/security-review-profile-pack-contract.md"],
        "validation_requirement": "Insufficient evidence must produce legal_review_required.",
        "rollback_supersession_plan": "Remove readiness mapping; do not delete historical compliance flags.",
        "dashboard_project_health_impact": "Legal review flags affect readiness and dashboard attention.",
        "contract_atlas_impact": "Compliance applicability becomes maturity input.",
    },
)


def production_readiness_control_catalog(*, repo_root: Path | None = None) -> dict[str, Any]:
    """Return reusable control definitions and skill/control overlap decisions."""

    security_gate = build_security_lifecycle_gate(
        repo_root=repo_root, lifecycle_event="release_merge"
    )
    controls = [_security_control_definition(row) for row in security_gate["applicability"]]
    controls.extend(_production_control_definitions())
    return {
        "model_name": "secure_production_readiness_control_catalog",
        "derived_view": True,
        "primary_authority": False,
        "canonical_security_framework": "47_enterprise_security_controls",
        "control_count": len(controls),
        "control_families": sorted({control["category"] for control in controls}),
        "controls": controls,
        "overlap_matrix": list(OVERLAP_DECISIONS),
        "allowed_states": list(CONTROL_STATES),
        "no_duplicate_skill_policy": True,
    }


def _security_control_definition(row: dict[str, Any]) -> dict[str, Any]:
    category = row["category_id"]
    return {
        "control_id": row["control_id"],
        "name": row["name"],
        "category": "47_enterprise_security_controls",
        "control_family": category,
        "skill_owner": _skill_owner_for_category(category),
        "workflow_owner": "production_readiness_workflow",
        "applicability_rules": {
            "impact_categories": [category, "security_change"],
            "lifecycle_events": sorted(FULL_REVIEW_EVENTS),
        },
        "required_evidence": ["control applicability record", "security review evidence refs"],
        "states": list(CONTROL_STATES),
        "blocking_policy": "fail_or_unknown_blocks_release; deferred controls require manual review",
        "remediation_path": "security remediation Work Order or accepted-risk decision",
        "dashboard_visibility": "project_detail_and_security_dashboard",
        "project_health_impact": "open findings and unknown controls degrade health",
        "project_readiness_impact": "manual review/open findings hold readiness",
        "release_readiness_impact": "blocks or holds release until resolved",
        "contract_atlas_maturity_impact": "security_lifecycle_gate",
        "overlap_mapping": "skills/security plus skills/quality secure where applicable",
        "supersession_status": "map_existing_skill_to_control",
    }


def _production_control_definitions() -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for index, (control_id, family, name, purpose, categories, events) in enumerate(
        PRODUCTION_CONTROL_SEEDS,
        start=1,
    ):
        controls.append(
            {
                "control_id": f"PR-{index:03d}",
                "name": name,
                "category": family,
                "control_family": family,
                "skill_owner": control_id,
                "workflow_owner": "production_readiness_workflow",
                "applicability_rules": {
                    "impact_categories": list(categories),
                    "lifecycle_events": list(events),
                },
                "required_evidence": _required_evidence_for_family(family),
                "states": list(CONTROL_STATES),
                "blocking_policy": _blocking_policy_for_family(family),
                "remediation_path": f"{family} remediation Work Order",
                "dashboard_visibility": "project_detail_and_production_readiness_dashboard",
                "project_health_impact": "current blockers affect health only when evidence-backed",
                "project_readiness_impact": "missing or failed applicable evidence holds readiness",
                "release_readiness_impact": "release held when applicable evidence is missing or failed",
                "contract_atlas_maturity_impact": "production_readiness_workflow",
                "overlap_mapping": _overlap_for_family(family),
                "supersession_status": _decision_for_family(family),
                "purpose": purpose,
            }
        )
    return controls


def _required_evidence_for_family(family: str) -> list[str]:
    common = ["control applicability record", "evidence refs"]
    family_specific = {
        "database_readiness": ["migration/rollback evidence", "schema/index/constraint review"],
        "api_resilience": ["route/API evidence", "auth/input/error handling review"],
        "caching_correctness": ["cache key/invalidation/TTL evidence"],
        "accessibility_review": ["keyboard/focus/contrast/semantic evidence"],
        "observability_logging": ["logging redaction and alert evidence"],
        "performance_scalability": ["latency/concurrency/resource evidence"],
        "dependency_supply_chain": ["dependency audit or SBOM/provenance evidence"],
        "code_quality_architecture": ["lint/type/test/architecture-boundary evidence"],
        "privacy_compliance_applicability": ["data classification and legal review evidence"],
        "release_readiness": ["release gate, rollback, docs drift, and publication evidence"],
        "backup_restore_rollback": ["backup/restore rehearsal and rollback evidence"],
    }
    return common + family_specific.get(family, [])


def _blocking_policy_for_family(family: str) -> str:
    if family in {
        "privacy_compliance_applicability",
        "release_readiness",
        "backup_restore_rollback",
    }:
        return "missing_applicable_evidence_holds_release"
    return "failed_applicable_control_blocks; missing_evidence_marks_partial"


def _overlap_for_family(family: str) -> str:
    mapping = {
        "dependency_supply_chain": "security catalog plus ci_gate pip-audit",
        "code_quality_architecture": "quality harden, structure-audit, lint/format gates",
        "release_readiness": "ci_gate, release versioning, docs drift gate",
        "accessibility_review": "skills/domains/quality/accessibility.yml",
    }
    return mapping.get(family, "new specialized readiness owner")


def _decision_for_family(family: str) -> str:
    if family in {"dependency_supply_chain", "code_quality_architecture", "release_readiness"}:
        return "map_existing_skill_to_control"
    if family == "accessibility_review":
        return "strengthen_existing_skill"
    return "create_new_skill"


def _skill_owner_for_category(category: str) -> str:
    if category == "dependency_supply_chain":
        return "dependency_supply_chain"
    if category == "dynamic_runtime_testing":
        return "api_resilience"
    if category == "compliance_governance_operational":
        return "privacy_compliance_applicability"
    return "security_review"
