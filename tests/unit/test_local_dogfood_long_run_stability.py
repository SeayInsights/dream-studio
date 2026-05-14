from __future__ import annotations

from core.release.local_dogfood_stability import evaluate_local_dogfood_stability


def test_local_dogfood_stability_passes_for_multiple_clean_sessions() -> None:
    result = evaluate_local_dogfood_stability(
        [
            {"validation_passed": True, "evidence_refs": ["e1.yaml"]},
            {"validation_passed": True, "evidence_refs": ["e2.yaml"]},
        ]
    )

    assert result["stable"] is True
    assert result["issues"] == []
    assert result["summary"]["validation_passed_count"] == 2
    assert result["primary_authority"] is False


def test_local_dogfood_stability_flags_regressions() -> None:
    result = evaluate_local_dogfood_stability(
        [
            {
                "prompt_chaining_detected": True,
                "hidden_mutation_detected": True,
                "dashboard_authority_drift_detected": True,
                "evidence_sprawl_detected": True,
                "validation_passed": False,
                "evidence_refs": [],
            }
        ]
    )

    assert result["stable"] is False
    assert "insufficient_session_count" in result["issues"]
    assert "session_0_prompt_chaining_detected" in result["issues"]
    assert "session_0_hidden_mutation_detected" in result["issues"]
    assert "session_0_dashboard_authority_drift_detected" in result["issues"]
    assert "session_0_evidence_sprawl_detected" in result["issues"]
    assert "session_0_validation_not_passed" in result["issues"]
    assert "session_0_missing_evidence_refs" in result["issues"]
