from __future__ import annotations

import json
from pathlib import Path

import yaml

from core.work_orders.dashboard_projection import build_dashboard_projection_snapshot


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_dashboard_projection_snapshot_summarizes_file_backed_work_order(tmp_path: Path) -> None:
    root = tmp_path / "work-orders"
    work_order_dir = root / "wo-demo"
    _write_json(
        work_order_dir / "work_order.json",
        {
            "work_order_id": "wo-demo",
            "phase": "Phase Demo",
            "approval_mode": "approval_required",
            "risk_level": "medium",
            "status": "reported",
        },
    )
    _write_json(
        work_order_dir / "approvals" / "approval.json",
        {
            "work_order_id": "wo-demo",
            "approval_mode": "approval_required",
            "risk_level": "medium",
        },
    )
    _write_json(
        work_order_dir / "evals" / "result_report_completeness.json",
        {
            "eval_type": "result_report_completeness",
            "pass_fail": "pass",
            "score": 1,
            "evidence": ["report.md"],
        },
    )
    _write_yaml(
        work_order_dir / "evidence" / "mutation_evidence.yaml",
        {
            "decision": "MUTATION_COMPLETE",
            "next_phase_recommendation": "Phase Demo Commit Planning",
            "forbidden_actions_observed": False,
        },
    )
    _write_yaml(
        work_order_dir / "security" / "release_gate_review.yaml",
        {
            "recommended_release_gate": "RUN_ADDITIONAL_SECURITY_REVIEW",
            "next_phase_recommendation": "Phase Demo Security Review",
        },
    )
    _write_yaml(
        work_order_dir / "security" / "review_report.yaml",
        {
            "decision": "PASS_WITH_RISKS",
            "target_id": "demo",
            "security_pack_id": "security_review_profile_pack",
        },
    )
    _write_yaml(
        work_order_dir / "security" / "findings" / "finding.yaml",
        {
            "finding_id": "sec.demo.finding",
            "severity": "high",
            "release_gate_impact": "block_release",
        },
    )
    (work_order_dir / "rendered").mkdir(parents=True)
    (work_order_dir / "rendered" / "handoff.md").write_text("handoff", encoding="utf-8")
    (work_order_dir / "report.md").write_text("# Demo Report\n", encoding="utf-8")

    snapshot = build_dashboard_projection_snapshot(
        work_order_root=root,
        generated_at="2026-05-12T00:00:00Z",
    )

    assert snapshot["artifact_kind"] == "DashboardProjectionSnapshot"
    assert snapshot["artifact_schema_version"] == "dashboard_projection_model.v0"
    assert snapshot["projection_id"] == "dashboard.projection.work_orders"
    assert snapshot["generated_at"] == "2026-05-12T00:00:00Z"
    assert "read-only views over file-backed artifacts" in snapshot["non_authority_notice"]
    assert snapshot["projection_scope"]["target_repo_access"] == "not_authorized"
    assert len(snapshot["work_orders"]) == 1
    assert snapshot["work_orders"][0]["work_order_id"] == "wo-demo"
    assert snapshot["work_orders"][0]["phase_name"] == "Phase Demo"
    assert snapshot["work_orders"][0]["approval_mode"] == "approval_required"
    assert snapshot["work_orders"][0]["final_decision"] == "MUTATION_COMPLETE"
    assert snapshot["work_orders"][0]["next_action"] == "Phase Demo Commit Planning"
    assert snapshot["work_orders"][0]["blocking_risks"] == ["none"]
    assert snapshot["evals"][0]["pass_fail"] == "pass"
    assert snapshot["evals"][0]["blocking"] is False
    assert snapshot["approvals_and_operator_decisions"][0]["approval_status"] == "present"
    assert snapshot["approvals_and_operator_decisions"][0]["execution_allowed"] is True
    assert (
        snapshot["security_reviews"][0]["release_gate_decision"] == "RUN_ADDITIONAL_SECURITY_REVIEW"
    )
    assert snapshot["security_reviews"][0]["findings_by_severity"] == {"high": 1}
    assert snapshot["security_reviews"][0]["blocking_findings"] == ["sec.demo.finding"]
    assert any("work_order.json" in ref for ref in snapshot["source_artifact_refs"])
    assert any("approval.json" in ref for ref in snapshot["source_artifact_refs"])


def test_dashboard_projection_records_missing_root_as_evidence_gap(tmp_path: Path) -> None:
    snapshot = build_dashboard_projection_snapshot(work_order_root=tmp_path / "missing")

    assert snapshot["work_orders"] == []
    assert snapshot["evals"] == []
    assert snapshot["approvals_and_operator_decisions"] == []
    assert snapshot["security_reviews"] == []
    assert snapshot["stale_or_missing_evidence"] == [
        {
            "evidence_ref": str(tmp_path / "missing"),
            "status": "missing",
            "impact": "Work Order root is missing or is not a directory.",
        }
    ]


def test_dashboard_projection_keeps_malformed_eval_visible(tmp_path: Path) -> None:
    root = tmp_path / "work-orders"
    work_order_dir = root / "wo-bad-eval"
    _write_json(
        work_order_dir / "work_order.json",
        {
            "work_order_id": "wo-bad-eval",
            "phase": "Bad Eval Demo",
            "approval_mode": "observe_only",
            "risk_level": "low",
        },
    )
    (work_order_dir / "evals").mkdir(parents=True)
    bad_eval = work_order_dir / "evals" / "bad.json"
    bad_eval.write_text("{not valid json", encoding="utf-8")

    snapshot = build_dashboard_projection_snapshot(work_order_root=root)

    assert snapshot["evals"] == [
        {
            "eval_artifact_ref": str(bad_eval),
            "eval_type": "bad",
            "pass_fail": "incomplete",
            "score": "not_applicable",
            "evidence_refs": [str(bad_eval)],
            "blocking": True,
            "limitations": ["Eval artifact could not be parsed."],
        }
    ]
    assert any(
        item["status"] == "invalid" and item["evidence_ref"] == str(bad_eval)
        for item in snapshot["stale_or_missing_evidence"]
    )


def test_dashboard_projection_module_stays_file_backed_and_non_runtime() -> None:
    source = Path("core/work_orders/dashboard_projection.py").read_text(encoding="utf-8")

    forbidden_terms = [
        "get_connection",
        "transaction(",
        "sqlite3",
        "uvicorn",
        "APIRouter",
        "subprocess",
        "webbrowser",
        "git add",
        "git commit",
        "git push",
    ]

    assert [term for term in forbidden_terms if term in source] == []
