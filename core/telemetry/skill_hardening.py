"""Skill hardening recommendation helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def evaluate_skill_hardening_signals(skill_id: str, signals: Mapping[str, Any]) -> dict[str, Any]:
    """Return non-executing hardening recommendations for one skill."""
    invocations = int(signals.get("invocation_count", 0) or 0)
    failures = int(signals.get("failure_count", 0) or 0)
    security_findings = int(signals.get("security_finding_count", 0) or 0)
    validation_failures = int(signals.get("validation_failure_count", 0) or 0)
    token_total = int(signals.get("token_total", 0) or 0)
    version = signals.get("version") or "unversioned"
    failure_rate = failures / invocations if invocations else 0.0
    recommendations: list[dict[str, Any]] = []

    if version == "unversioned":
        recommendations.append(
            _recommendation("add_version", "medium", "Skill has no version metadata.")
        )
    if failure_rate >= 0.25 and invocations >= 4:
        recommendations.append(
            _recommendation(
                "review_failure_patterns", "high", "Failure rate exceeds hardening threshold."
            )
        )
    if validation_failures:
        recommendations.append(
            _recommendation(
                "add_validation_fixture",
                "high",
                "Validation failures are attributed to this skill.",
            )
        )
    if security_findings:
        recommendations.append(
            _recommendation(
                "security_review", "high", "Security findings are attributed to this skill."
            )
        )
    if token_total >= 10000:
        recommendations.append(
            _recommendation(
                "optimize_context", "medium", "Token usage suggests context slimming review."
            )
        )

    return {
        "skill_id": skill_id,
        "invocation_count": invocations,
        "failure_count": failures,
        "failure_rate": round(failure_rate, 4),
        "security_finding_count": security_findings,
        "validation_failure_count": validation_failures,
        "token_total": token_total,
        "version": version,
        "recommendations": recommendations,
        "execution_authorized": False,
        "requires_future_work_order": bool(recommendations),
    }


def evaluate_skill_registry_hardening(
    skill_signals: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate multiple skill signal rows without mutating skill registry state."""
    skills = [
        evaluate_skill_hardening_signals(str(row.get("skill_id", "unknown")), row)
        for row in skill_signals
    ]
    return {
        "artifact_type": "skill_registry_hardening_recommendations",
        "read_only": True,
        "skill_runtime_changed": False,
        "registry_write_required": False,
        "execution_authorized": False,
        "skills": skills,
        "recommended_work_order_candidates": [
            item for item in skills if item["requires_future_work_order"]
        ],
    }


def validate_skill_hardening_report(report: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("read_only",):
        if report.get(key) is not True:
            errors.append(f"{key} must be true")
    for key in ("skill_runtime_changed", "registry_write_required", "execution_authorized"):
        if report.get(key) is not False:
            errors.append(f"{key} must be false")
    for skill in report.get("skills", []):
        if skill.get("execution_authorized") is not False:
            errors.append(f"skill hardening must not authorize execution: {skill.get('skill_id')}")
    return errors


def _recommendation(kind: str, severity: str, reason: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "severity": severity,
        "reason": reason,
        "execution_authorized": False,
        "requires_future_work_order": True,
    }
