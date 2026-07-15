"""Secure production readiness controls and SQLite authority helpers."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from core.security.lifecycle import build_security_lifecycle_gate

CONTROL_STATES = ("pass", "fail", "warn", "not_applicable", "manual_review", "unknown")
FULL_REVIEW_EVENTS = {
    "project_intake",
    "release",
    "merge",
    "release_merge",
    "publication",
    "deployment",
    "live_cutover",
    "dependency_change",
    "runtime_change",
    "database_change",
    "security_change",
    "docker_change",
    "major_architecture_change",
    "external_project_onboarding",
    "scheduled_dogfood_gate",
}


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


FILE_CATEGORY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("database_change", ("migration", ".sql", "database", "sqlite", "schema", "db")),
    ("api_surface", ("projections/api", "routes", "api", "webhook", "endpoint")),
    ("cache_change", ("cache", "ttl", "redis", "memo", "cached")),
    ("dashboard_runtime", ("dashboard", "frontend", "templates", ".html", ".css", ".tsx")),
    ("frontend_change", ("frontend", ".html", ".css", ".tsx", ".jsx")),
    ("observability_change", ("logging", "telemetry", "observability", "alert", "audit")),
    ("performance_change", ("performance", "scalability", "load", "concurrency", "timeout")),
    ("dependency_supply_chain", ("requirements", "package.json", "lock", "pyproject.toml")),
    ("security_change", ("security", "auth", "secret", "credential", "crypto", "token")),
    ("runtime_change", ("runtime/", "hooks/", "interfaces/cli", "installed_runtime")),
    ("release_change", ("release", "ci_gate", ".github", "publication", "readme")),
    ("architecture_change", ("architecture", "contract", "atlas", "boundary")),
    ("privacy_change", ("privacy", "pii", "retention", "compliance", "legal")),
    ("code_change", (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs")),
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


def build_secure_production_readiness_gate(
    *,
    project_id: str = "dream-studio",
    lifecycle_event: str = "code_change",
    changed_files: list[str] | None = None,
    repo_root: Path | None = None,
    conn: sqlite3.Connection | None = None,
    persist: bool = False,
    assessment_id: str | None = None,
) -> dict[str, Any]:
    """Build and optionally persist a secure production readiness gate result."""

    now = datetime.now(UTC).isoformat()
    changed = changed_files or []
    impact = classify_production_readiness_impact(changed, lifecycle_event=lifecycle_event)
    security_gate = build_security_lifecycle_gate(
        repo_root=repo_root,
        conn=conn,
        project_id=project_id,
        lifecycle_event=lifecycle_event,
        changed_files=changed,
    )
    catalog = production_readiness_control_catalog(repo_root=repo_root)
    full_review_required = bool(
        lifecycle_event in FULL_REVIEW_EVENTS
        or security_gate["full_review_required"]
        or impact["full_review_required"]
    )
    control_results = _control_results(
        controls=catalog["controls"],
        impact_categories=set(impact["impact_categories"]),
        lifecycle_event=lifecycle_event,
        full_review_required=full_review_required,
        now=now,
        project_id=project_id,
        assessment_id=assessment_id or _assessment_id(project_id, lifecycle_event),
    )
    summary = Counter(result["status"] for result in control_results)
    blockers = [item for item in control_results if item["blocking"]]
    manual_review = [item for item in control_results if item["status"] == "manual_review"]
    unknown = [item for item in control_results if item["status"] == "unknown"]
    missing_evidence = sorted(
        {
            evidence
            for result in control_results
            if result["status"] in {"manual_review", "unknown"}
            for evidence in result["required_evidence"]
        }
    )
    readiness_score = _score_model(
        control_results,
        score_kind="project_readiness",
        missing_evidence=missing_evidence,
        blockers=blockers,
    )
    health_score = _score_model(
        control_results,
        score_kind="project_health",
        missing_evidence=missing_evidence,
        blockers=blockers,
    )
    compliance_flags = _compliance_flags(control_results)
    release_effect = _release_effect(
        blockers=blockers, manual_review=manual_review, unknown=unknown
    )
    gate = {
        "model_name": "secure_production_readiness_gate",
        "assessment_id": assessment_id or _assessment_id(project_id, lifecycle_event),
        "project_id": project_id,
        "workflow_id": "production_readiness_workflow",
        "lifecycle_event": lifecycle_event,
        "changed_files": changed,
        "derived_view": True,
        "primary_authority": False,
        "execution_authorized": False,
        "db_write_authorized": bool(persist),
        "persisted": False,
        "impact_classification": impact,
        "full_review_required": full_review_required,
        "run_policy": {
            "lightweight_impact_classification": "always",
            "targeted_checks": "normal_development",
            "full_review_events": sorted(FULL_REVIEW_EVENTS),
            "all_47_on_tiny_changes": False,
        },
        "security_lifecycle_gate": security_gate,
        "control_catalog_summary": {
            "control_count": catalog["control_count"],
            "control_families": catalog["control_families"],
            "canonical_security_framework": catalog["canonical_security_framework"],
        },
        "control_results": control_results,
        "control_summary": {
            "total": len(control_results),
            "applicable": sum(
                1 for result in control_results if result["applicability"] == "applicable"
            ),
            "not_applicable": summary["not_applicable"],
            "manual_review": summary["manual_review"],
            "unknown": summary["unknown"],
            "pass": summary["pass"],
            "fail": summary["fail"],
            "warn": summary["warn"],
        },
        "findings": _findings_from_results(control_results),
        "remediation_work_orders": _remediation_work_orders(control_results),
        "compliance_review_flags": compliance_flags,
        "project_health_score": health_score,
        "project_readiness_score": readiness_score,
        "release_readiness": {
            "status": "hold" if release_effect != "pass" else "ready",
            "release_readiness_effect": release_effect,
            "blocker_count": len(blockers),
            "manual_review_count": len(manual_review),
            "evidence_refs": [],
        },
        "overlap_matrix": catalog["overlap_matrix"],
        "created_at": now,
    }
    if persist:
        if conn is None:
            raise ValueError("conn is required when persist=True")
        gate["persisted"] = record_production_readiness_assessment(conn, gate)
    return gate


def classify_production_readiness_impact(
    changed_files: list[str],
    *,
    lifecycle_event: str = "code_change",
) -> dict[str, Any]:
    """Classify production-readiness impact using paths and lifecycle event only."""

    categories: set[str] = set()
    matched_files: list[dict[str, str]] = []
    for raw in changed_files:
        lowered = raw.replace("\\", "/").lower()
        for category, patterns in FILE_CATEGORY_PATTERNS:
            if any(pattern in lowered for pattern in patterns):
                categories.add(category)
                matched_files.append({"file": raw, "impact_category": category})
    if lifecycle_event in FULL_REVIEW_EVENTS:
        categories.add("release_change" if "release" in lifecycle_event else "runtime_change")
    if lifecycle_event == "database_change":
        categories.add("database_change")
    if lifecycle_event == "dependency_change":
        categories.add("dependency_supply_chain")
    if lifecycle_event == "security_change":
        categories.add("security_change")
    return {
        "classification": "production_relevant" if categories else "lightweight_no_direct_signal",
        "changed_file_count": len(changed_files),
        "impact_categories": sorted(categories),
        "matched_files": matched_files,
        "full_review_required": lifecycle_event in FULL_REVIEW_EVENTS,
    }


def record_production_readiness_assessment(
    conn: sqlite3.Connection,
    gate: dict[str, Any],
) -> bool:
    """Persist a gate result to SQLite authority using an injected connection.

    Returns False (no-op) if production_readiness_assessment_runs has been retired (migration 112+).
    """
    if not _table_exists(conn, "production_readiness_assessment_runs"):
        return False

    assessment_id = gate["assessment_id"]
    created_at = gate["created_at"]
    conn.execute(
        """
        INSERT OR REPLACE INTO production_readiness_assessment_runs(
            assessment_id, project_id, workflow_id, lifecycle_event, status,
            confidence, full_review_required, release_readiness_effect,
            health_score_json, readiness_score_json, missing_evidence_json,
            blocking_factors_json, source_refs_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            assessment_id,
            gate["project_id"],
            gate["workflow_id"],
            gate["lifecycle_event"],
            gate["release_readiness"]["status"],
            gate["project_readiness_score"]["confidence"],
            int(gate["full_review_required"]),
            gate["release_readiness"]["release_readiness_effect"],
            _json(gate["project_health_score"]),
            _json(gate["project_readiness_score"]),
            _json(gate["project_readiness_score"]["missing_evidence"]),
            _json(gate["project_readiness_score"]["blocking_factors"]),
            _json(["core/production_readiness/controls.py"]),
            created_at,
        ),
    )
    for result in gate["control_results"]:
        conn.execute(
            """
            INSERT OR REPLACE INTO production_readiness_control_results(
                result_id, assessment_id, project_id, control_id, control_family,
                name, skill_owner, workflow_owner, applicability, status,
                severity, blocking, score_impact, evidence_refs_json,
                source_refs_json, file_path, line, remediation_work_order,
                reason_not_applicable, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["result_id"],
                assessment_id,
                gate["project_id"],
                result["control_id"],
                result["control_family"],
                result["name"],
                result["skill_owner"],
                result["workflow_owner"],
                result["applicability"],
                result["status"],
                result["severity"],
                int(result["blocking"]),
                result["score_impact"],
                _json(result["evidence_refs"]),
                _json(result["source_refs"]),
                result.get("file_path"),
                result.get("line"),
                result.get("remediation_work_order"),
                result.get("reason_not_applicable"),
                created_at,
            ),
        )
    for finding in gate["findings"]:
        conn.execute(
            """
            INSERT OR REPLACE INTO production_readiness_findings(
                finding_id, project_id, assessment_id, control_id, control_family,
                skill_owner, workflow_owner, applicability, status, severity,
                blocking, score_impact, evidence_refs_json, source_refs_json,
                file_path, line, remediation_work_order, reason_not_applicable, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding["finding_id"],
                gate["project_id"],
                assessment_id,
                finding["control_id"],
                finding["control_family"],
                finding["skill_owner"],
                finding["workflow_owner"],
                finding["applicability"],
                finding["status"],
                finding["severity"],
                int(finding["blocking"]),
                finding["score_impact"],
                _json(finding["evidence_refs"]),
                _json(finding["source_refs"]),
                finding.get("file_path"),
                finding.get("line"),
                finding.get("remediation_work_order"),
                finding.get("reason_not_applicable"),
                created_at,
            ),
        )
    for work_order in gate["remediation_work_orders"]:
        conn.execute(
            """
            INSERT OR REPLACE INTO production_readiness_remediation_work_orders(
                remediation_work_order_id, project_id, assessment_id, control_id,
                finding_id, status, recommended_phase_type, objective,
                evidence_refs_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                work_order["remediation_work_order_id"],
                gate["project_id"],
                assessment_id,
                work_order["control_id"],
                work_order.get("finding_id"),
                work_order["status"],
                work_order["recommended_phase_type"],
                work_order["objective"],
                _json(work_order["evidence_refs"]),
                created_at,
            ),
        )
    for mapping in gate["overlap_matrix"]:
        mapping_id = _stable_id(
            "pr-map",
            mapping["existing_skill_control_name"],
            mapping["proposed_canonical_owner"],
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO production_readiness_skill_control_mappings(
                mapping_id, control_id, control_family, existing_skill_or_check,
                proposed_canonical_owner, overlap_reason, decision, evidence_json,
                validation_requirement, rollback_or_supersession_plan,
                dashboard_project_health_impact, contract_atlas_impact, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mapping_id,
                mapping["proposed_canonical_owner"],
                mapping["proposed_canonical_owner"],
                mapping["existing_skill_control_name"],
                mapping["proposed_canonical_owner"],
                mapping["overlap_reason"],
                mapping["decision"],
                _json(mapping["evidence"]),
                mapping["validation_requirement"],
                mapping["rollback_supersession_plan"],
                mapping["dashboard_project_health_impact"],
                mapping["contract_atlas_impact"],
                created_at,
            ),
        )
    _record_scorecards(conn, gate, created_at)
    # _record_compliance_flags removed — compliance_review_flags dropped in migration 133.
    conn.commit()
    return True


def production_readiness_dashboard_summary(
    conn: sqlite3.Connection,
    *,
    project_id: str,
) -> dict[str, Any]:
    """Read the latest SQLite-backed production readiness summary for a project."""

    # WO-SCHEMALEAN: the normalized production_readiness_* tables were dropped in
    # migration 112; `ds analytics-ingest` now writes the readiness_events spine
    # (assessment.started + control_result.recorded events). This reader was
    # repointed to it — the summary is reconstructed from the latest assessment
    # event plus its child control events for the project.
    if not _table_exists(conn, "readiness_events"):
        return _empty_summary(project_id, ["readiness_events"])
    latest = conn.execute(
        """
        SELECT event_id, body, created_at FROM readiness_events
        WHERE project_id = ? AND event_kind = 'assessment.started'
        ORDER BY created_at DESC, event_id DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    if latest is None:
        return _empty_summary(project_id, [])
    assessment_id = latest["event_id"]
    body = json.loads(latest["body"] or "{}")
    status = body.get("status") or "partial"
    confidence = body.get("confidence") or "medium"
    missing_evidence = body.get("missing_evidence") or []
    blocking_factors = body.get("blocking_factors") or []
    controls = []
    for row in conn.execute(
        """
        SELECT control_id, result, body FROM readiness_events
        WHERE parent_event_id = ? AND event_kind = 'control_result.recorded'
        ORDER BY control_id
        """,
        (assessment_id,),
    ).fetchall():
        cbody = json.loads(row["body"] or "{}")
        controls.append(
            {
                "control_id": row["control_id"],
                "status": row["result"],
                "control_family": cbody.get("control_family"),
                "severity": cbody.get("severity"),
                "applicability": cbody.get("applicability"),
            }
        )
    summary = Counter(control["status"] for control in controls)

    def _score_dict(raw: Any) -> dict[str, Any]:
        # readiness_events stores the health/readiness score as whatever the
        # analytics payload provided (a scalar in practice); wrap a scalar into
        # the dashboard's expected {score,status,confidence,...} shape.
        if isinstance(raw, dict):
            return raw
        return {
            "score": raw,
            "status": status,
            "confidence": confidence,
            "missing_evidence": missing_evidence,
            "blocking_factors": blocking_factors,
        }

    return {
        "model_name": "production_readiness_dashboard_summary",
        "project_id": project_id,
        "assessment_id": assessment_id,
        "derived_view": True,
        "primary_authority": False,
        "source_tables": ["readiness_events"],
        "readiness_score": _score_dict(body.get("readiness_score")),
        "health_score": _score_dict(body.get("health_score")),
        "release_readiness_effect": body.get("release_readiness_effect"),
        "status": status,
        "confidence": confidence,
        "control_summary": {
            "total": len(controls),
            "pass": summary["pass"],
            "warn": summary["warn"],
            "fail": summary["fail"],
            "not_applicable": summary["not_applicable"],
            "manual_review": summary["manual_review"],
            "unknown": summary["unknown"],
        },
        "controls": controls,
        # The retired normalized findings / remediation / compliance tables are not
        # part of the readiness_events spine; blocking_factors + missing_evidence on
        # the score dicts carry the equivalent signal. Honestly empty, not fabricated.
        "findings": [],
        "remediation_work_orders": [],
        "compliance_review_flags": [],
        "empty_state": None,
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


def _control_results(
    *,
    controls: list[dict[str, Any]],
    impact_categories: set[str],
    lifecycle_event: str,
    full_review_required: bool,
    now: str,
    project_id: str,
    assessment_id: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for control in controls:
        rules = control["applicability_rules"]
        category_match = bool(impact_categories.intersection(rules["impact_categories"]))
        event_match = lifecycle_event in rules["lifecycle_events"]
        applicable = full_review_required or category_match or event_match
        if not applicable:
            status = "not_applicable"
            reason = "No lifecycle event or changed-file signal matched this control."
            severity = "info"
            blocking = False
            applicability = "not_applicable"
        else:
            status = "manual_review"
            reason = None
            severity = "medium"
            blocking = control["category"] in {
                "47_enterprise_security_controls",
                "privacy_compliance_applicability",
                "release_readiness",
            }
            applicability = "applicable"
        if control["category"] == "privacy_compliance_applicability" and applicable:
            status = "manual_review"
            severity = "medium"
            blocking = True
        result = {
            "result_id": _stable_id("pr-result", assessment_id, control["control_id"]),
            "assessment_id": assessment_id,
            "project_id": project_id,
            "control_id": control["control_id"],
            "control_family": control["control_family"],
            "name": control["name"],
            "skill_owner": control["skill_owner"],
            "workflow_owner": control["workflow_owner"],
            "applicability": applicability,
            "status": status,
            "severity": severity,
            "blocking": blocking,
            "score_impact": 0.0 if status == "not_applicable" else 1.0,
            "required_evidence": list(control["required_evidence"]),
            "evidence_refs": [],
            "source_refs": ["core/production_readiness/controls.py"],
            "file_path": None,
            "line": None,
            "remediation_work_order": (
                _stable_id("wo-production-readiness", assessment_id, control["control_id"])
                if status in {"manual_review", "unknown", "fail", "warn"}
                else None
            ),
            "reason_not_applicable": reason,
            "created_at": now,
        }
        results.append(result)
    return results


def _score_model(
    control_results: list[dict[str, Any]],
    *,
    score_kind: str,
    missing_evidence: list[str],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    applicable = [item for item in control_results if item["applicability"] == "applicable"]
    passed = [item for item in applicable if item["status"] == "pass"]
    if not applicable:
        return {
            "score_kind": score_kind,
            "score": None,
            "status": "unavailable",
            "confidence": "none",
            "reason": "No applicable controls were identified for this lifecycle event.",
            "missing_evidence": [],
            "blocking_factors": [],
            "stale_or_partial": False,
        }
    if not passed:
        return {
            "score_kind": score_kind,
            "score": None,
            "status": "partial",
            "confidence": "low",
            "reason": "Applicable controls require evidence or manual review before scoring.",
            "missing_evidence": missing_evidence,
            "blocking_factors": [item["control_id"] for item in blockers],
            "stale_or_partial": True,
        }
    score = round((len(passed) / len(applicable)) * 100, 1)
    return {
        "score_kind": score_kind,
        "score": score,
        "status": "scored",
        "confidence": "medium",
        "reason": "Score is derived only from evidence-backed passing controls.",
        "missing_evidence": missing_evidence,
        "blocking_factors": [item["control_id"] for item in blockers],
        "stale_or_partial": bool(missing_evidence),
    }


def _findings_from_results(control_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for result in control_results:
        if result["status"] not in {"fail", "unknown"}:
            continue
        findings.append(
            {
                "finding_id": _stable_id(
                    "pr-finding", result["assessment_id"], result["control_id"]
                ),
                **{
                    key: result[key]
                    for key in (
                        "project_id",
                        "assessment_id",
                        "control_id",
                        "control_family",
                        "skill_owner",
                        "workflow_owner",
                        "applicability",
                        "status",
                        "severity",
                        "blocking",
                        "score_impact",
                        "evidence_refs",
                        "source_refs",
                        "file_path",
                        "line",
                        "remediation_work_order",
                        "reason_not_applicable",
                        "created_at",
                    )
                },
            }
        )
    return findings


def _remediation_work_orders(control_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "remediation_work_order_id": result["remediation_work_order"],
            "control_id": result["control_id"],
            "finding_id": None,
            "status": "proposed",
            "recommended_phase_type": "normal_next_work_order",
            "objective": f"Collect evidence or remediate {result['control_id']} ({result['name']}).",
            "evidence_refs": result["evidence_refs"],
        }
        for result in control_results
        if result.get("remediation_work_order")
    ]


def _compliance_flags(control_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "control_id": result["control_id"],
            "flag_type": "legal_review_required",
            "status": "open",
            "reason": "Privacy/compliance applicability cannot be claimed without evidence-backed classification.",
            "evidence_refs": result["evidence_refs"],
        }
        for result in control_results
        if result["control_family"] == "privacy_compliance_applicability"
        and result["applicability"] == "applicable"
    ]


def _record_scorecards(conn: sqlite3.Connection, gate: dict[str, Any], created_at: str) -> None:
    # release_readiness_records dropped in migration 133 (persist=False dead gate — no
    # production caller ever passes persist=True). Only writes to project_readiness_scorecards
    # and project_health_scorecards remain; release_readiness_records write removed.
    if not _table_exists(conn, "project_readiness_scorecards"):
        return
    for table, prefix, score_key, score_column in (
        (
            "project_readiness_scorecards",
            "readiness-scorecard",
            "project_readiness_score",
            "readiness_score",
        ),
        ("project_health_scorecards", "health-scorecard", "project_health_score", "health_score"),
    ):
        score = gate[score_key]
        conn.execute(
            f"""
            INSERT OR REPLACE INTO {table}(
                scorecard_id, project_id, assessment_id, {score_column},
                confidence, status, missing_evidence_json,
                blocking_factors_json, evidence_refs_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _stable_id(prefix, gate["assessment_id"]),
                gate["project_id"],
                gate["assessment_id"],
                score["score"],
                score["confidence"],
                score["status"],
                _json(score["missing_evidence"]),
                _json(score["blocking_factors"]),
                _json([]),
                created_at,
            ),
        )
    # release_readiness_records write removed — table dropped migration 133.


def _release_effect(
    *,
    blockers: list[dict[str, Any]],
    manual_review: list[dict[str, Any]],
    unknown: list[dict[str, Any]],
) -> str:
    if blockers:
        return "block_or_hold_applicable_controls"
    if unknown:
        return "hold_unknown_controls"
    if manual_review:
        return "hold_manual_review"
    return "pass"


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


def _assessment_id(project_id: str, lifecycle_event: str) -> str:
    return _stable_id("assessment", project_id, lifecycle_event)


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "-".join(str(part).strip().lower().replace(" ", "-") for part in parts if part)
    sanitized = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in raw)
    return f"{prefix}-{sanitized[:120]}"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _decode_json_fields(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    for key in list(decoded):
        if key.endswith("_json") and isinstance(decoded[key], str):
            decoded[key[:-5]] = json.loads(decoded[key])
    return decoded


def _empty_summary(project_id: str, missing: list[str]) -> dict[str, Any]:
    return {
        "model_name": "production_readiness_dashboard_summary",
        "project_id": project_id,
        "derived_view": True,
        "primary_authority": False,
        "status": "unavailable",
        "readiness_score": {
            "score": None,
            "status": "unavailable",
            "confidence": "none",
            "reason": "No SQLite-backed production readiness assessment exists for this project.",
            "missing_evidence": ["production readiness assessment"],
            "blocking_factors": [],
        },
        "health_score": {
            "score": None,
            "status": "unavailable",
            "confidence": "none",
            "reason": "No SQLite-backed production readiness assessment exists for this project.",
            "missing_evidence": ["production readiness assessment"],
            "blocking_factors": [],
        },
        "control_summary": {},
        "controls": [],
        "findings": [],
        "remediation_work_orders": [],
        "compliance_review_flags": [],
        "source_status": {
            "classification": "empty by design" if not missing else "missing schema",
            "missing": missing,
            "derived_view": True,
            "primary_authority": False,
        },
    }
