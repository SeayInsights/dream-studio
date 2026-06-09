from __future__ import annotations

from core.telemetry.human_loop_gate import (
    evaluate_dashboard_human_loop_gate,
    validate_dashboard_human_loop_gate,
)


def test_dashboard_human_loop_gate_passes_when_required_surfaces_are_present() -> None:
    gate = evaluate_dashboard_human_loop_gate(
        {
            "derived_view": True,
            "primary_authority": False,
            "routing_authority": False,
            "surfaces": {
                "approvals": True,
                "blockers": True,
                "attention_items": True,
                "operator_decisions": True,
                "route_state": True,
                "evidence_refs": True,
            },
        }
    )

    assert gate["passed"] is True
    assert gate["decision"] == "dashboard_primary_human_loop_ready"
    assert gate["prompt_fallback_required"] is False
    assert validate_dashboard_human_loop_gate(gate) == []


def test_dashboard_human_loop_gate_keeps_prompt_fallback_for_missing_or_stale_surfaces() -> None:
    gate = evaluate_dashboard_human_loop_gate(
        {
            "derived_view": True,
            "primary_authority": False,
            "routing_authority": False,
            "stale": True,
            "surfaces": {"attention_items": True},
        }
    )

    assert gate["passed"] is False
    assert "approvals" in gate["missing_surfaces"]
    assert gate["stale"] is True
    assert gate["prompt_fallback_required"] is True


def test_dashboard_human_loop_gate_validator_rejects_inconsistent_pass_state() -> None:
    issues = validate_dashboard_human_loop_gate(
        {
            "passed": True,
            "missing_surfaces": ["approvals"],
            "authority_ok": False,
            "prompt_fallback_required": True,
        }
    )

    assert "passed_gate_has_missing_surfaces" in issues
    assert "passed_gate_without_authority_ok" in issues
    assert "passed_gate_requires_prompt_fallback" in issues
