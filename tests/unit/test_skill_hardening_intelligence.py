from __future__ import annotations

from core.telemetry.skill_hardening import (
    evaluate_skill_hardening_signals,
    evaluate_skill_registry_hardening,
    validate_skill_hardening_report,
)


def test_skill_hardening_recommends_version_and_failure_review_without_execution() -> None:
    result = evaluate_skill_hardening_signals(
        "ds-core",
        {
            "invocation_count": 8,
            "failure_count": 3,
            "validation_failure_count": 1,
            "security_finding_count": 0,
            "token_total": 1200,
        },
    )

    kinds = {item["kind"] for item in result["recommendations"]}
    assert result["failure_rate"] == 0.375
    assert "add_version" in kinds
    assert "review_failure_patterns" in kinds
    assert "add_validation_fixture" in kinds
    assert result["execution_authorized"] is False
    assert result["requires_future_work_order"] is True


def test_skill_hardening_recommends_security_and_context_review() -> None:
    result = evaluate_skill_hardening_signals(
        "ds-quality",
        {
            "invocation_count": 10,
            "failure_count": 0,
            "validation_failure_count": 0,
            "security_finding_count": 2,
            "token_total": 12000,
            "version": "1.2.0",
        },
    )

    kinds = {item["kind"] for item in result["recommendations"]}
    assert "security_review" in kinds
    assert "optimize_context" in kinds
    assert "add_version" not in kinds


def test_skill_registry_hardening_report_is_read_only() -> None:
    report = evaluate_skill_registry_hardening(
        [
            {"skill_id": "ds-core", "invocation_count": 1, "failure_count": 0},
            {"skill_id": "ds-quality", "invocation_count": 6, "failure_count": 2},
        ]
    )

    assert validate_skill_hardening_report(report) == []
    assert report["read_only"] is True
    assert report["skill_runtime_changed"] is False
    assert report["registry_write_required"] is False
    assert report["execution_authorized"] is False
    assert report["recommended_work_order_candidates"]


def test_validation_rejects_authorized_hardening_execution() -> None:
    report = evaluate_skill_registry_hardening([{"skill_id": "ds-core"}])
    unsafe = {**report, "execution_authorized": True}

    errors = validate_skill_hardening_report(unsafe)

    assert "execution_authorized must be false" in errors
