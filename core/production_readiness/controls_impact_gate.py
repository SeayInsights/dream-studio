"""Impact classification and secure production-readiness gate orchestration.

WO-GF-READINESS-INSIGHTS: split from ``core/production_readiness/controls.py``.
No logic changes — extracted verbatim.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.security.lifecycle import build_security_lifecycle_gate

from .controls_catalog import production_readiness_control_catalog
from .controls_persistence import record_production_readiness_assessment
from .controls_shared import FULL_REVIEW_EVENTS, _stable_id

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


def _assessment_id(project_id: str, lifecycle_event: str) -> str:
    return _stable_id("assessment", project_id, lifecycle_event)
