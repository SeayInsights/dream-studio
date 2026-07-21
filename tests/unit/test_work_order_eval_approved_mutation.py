from __future__ import annotations

import json
from pathlib import Path


def _work_order(
    target_path: Path,
    *,
    work_order_id: str = "wo-approved-001",
    approval_mode: str = "approval_required",
) -> dict:
    return {
        "work_order_id": work_order_id,
        "project_name": "Approved Mutation Test",
        "target_path": str(target_path),
        "objective": "Evaluate approved mutation evidence.",
        "approval_mode": approval_mode,
        "risk_level": "low",
        "scope": {"include": ["src/app/a.ts"], "exclude": ["src/app/forbidden.ts"]},
        "allowed_skills": ["ds-core"],
        "allowed_agents": [],
        "workflow": "approved mutation",
        "forbidden_actions": ["no forbidden files", "no schema changes"],
        "validation_commands": ["python -m pytest -q"],
        "expected_outputs": ["approved mutation eval"],
        "stop_conditions": ["unapproved file changes"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "rendered",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def _approval(*, approved_files: list[str] | None = None) -> dict:
    return {
        "approval_status": "approved",
        "approved_by": "operator",
        "approved_at": "2026-05-11T00:00:00Z",
        "approval_mode": "approval_required",
        "approved_files": approved_files or ["src/app/a.ts", "src/app/a.test.ts"],
        "forbidden_files": ["src/app/forbidden.ts"],
        "approval_scope": "approved mutation test",
    }


def _write_approval(storage_root: Path, work_order_id: str, approval: dict | None = None) -> Path:
    path = storage_root / work_order_id / "approvals" / "approval.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(approval or _approval(), indent=2) + "\n", encoding="utf-8")
    return path


def _result_text(files_changed: str) -> str:
    return "\n".join(
        [
            "Summary: Approved mutation evidence recorded.",
            "Files inspected: src/app/a.ts",
            f"Files changed: {files_changed}",
            "Commands: python -m pytest -q => PASS",
            "Forbidden actions: complied",
            "Warnings: none",
            "Risks: none",
            "Next Work Order: Objective: continue narrowly; Risk: low; Approval: approval_required; Non-goals: broad mutation; Validation: focused tests.",
            "",
        ]
    )


def test_approved_mutation_passes_with_valid_approval_and_in_scope_changes(tmp_path) -> None:
    from core.work_orders.evals import create_approved_mutation_compliance_eval

    target = tmp_path / "target"
    target.mkdir()
    work_order = _work_order(target)

    artifact, _ = create_approved_mutation_compliance_eval(
        work_order=work_order,
        approval_evidence=_approval(),
        changed_files=["src/app/a.ts", "src/app/a.test.ts"],
        storage_root=tmp_path / "store",
    )

    assert artifact["eval_type"] == "approved_mutation_compliance"
    assert artifact["pass_fail"] == "pass"


def test_approved_mutation_fails_when_forbidden_or_unapproved_file_changes(tmp_path) -> None:
    from core.work_orders.evals import create_approved_mutation_compliance_eval

    target = tmp_path / "target"
    target.mkdir()
    work_order = _work_order(target)

    forbidden, _ = create_approved_mutation_compliance_eval(
        work_order=work_order,
        approval_evidence=_approval(),
        changed_files=["src/app/forbidden.ts"],
        storage_root=tmp_path / "store-forbidden",
    )
    unapproved, _ = create_approved_mutation_compliance_eval(
        work_order=work_order,
        approval_evidence=_approval(),
        changed_files=["src/app/unapproved.ts"],
        storage_root=tmp_path / "store-unapproved",
    )

    assert forbidden["pass_fail"] == "fail"
    assert "forbidden file changed" in forbidden["observed_behavior"]
    assert unapproved["pass_fail"] == "fail"
    assert "unapproved file changed" in unapproved["observed_behavior"]


def test_approved_mutation_is_incomplete_when_changed_file_evidence_missing(tmp_path) -> None:
    from core.work_orders.evals import create_approved_mutation_compliance_eval

    target = tmp_path / "target"
    target.mkdir()
    artifact, _ = create_approved_mutation_compliance_eval(
        work_order=_work_order(target),
        approval_evidence=_approval(),
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "incomplete"
    assert "changed-file evidence unavailable" in artifact["observed_behavior"]


def test_mutation_without_approval_evidence_never_passes(tmp_path) -> None:
    from core.work_orders.evals import create_approved_mutation_compliance_eval

    target = tmp_path / "target"
    target.mkdir()
    artifact, _ = create_approved_mutation_compliance_eval(
        work_order=_work_order(target),
        changed_files=["src/app/a.ts"],
        storage_root=tmp_path / "store",
    )

    assert artifact["pass_fail"] == "fail"
    assert "without valid approval evidence" in artifact["observed_behavior"]


def test_record_result_for_approval_required_emits_approved_mutation_not_observe_only(
    tmp_path,
) -> None:
    from core.work_orders.packet_store import get_packet_artifact, list_packet_artifacts
    from core.work_orders.results import record_result
    from core.work_orders.storage import save_work_order

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    save_work_order(_work_order(target), storage_root=storage_root)
    _write_approval(storage_root, "wo-approved-001")
    source = tmp_path / "result.md"
    source.write_text(_result_text("src/app/a.ts, src/app/a.test.ts"), encoding="utf-8")

    result = record_result("wo-approved-001", source_path=source, storage_root=storage_root)

    # WO-FILESDB-C3: the 3 evals live in the packet store (kind='eval'), not on disk.
    assert result["eval_paths"] == []
    assert len(list_packet_artifacts("wo-approved-001", "eval", storage_root=storage_root)) == 3
    assert (
        get_packet_artifact(
            "wo-approved-001",
            "eval",
            instance_key="approved_mutation_compliance",
            storage_root=storage_root,
        )
        is not None
    )
    assert (
        get_packet_artifact(
            "wo-approved-001",
            "eval",
            instance_key="observe_only_compliance",
            storage_root=storage_root,
        )
        is None
    )
    approved_eval = json.loads(
        get_packet_artifact(
            "wo-approved-001",
            "eval",
            instance_key="approved_mutation_compliance",
            storage_root=storage_root,
        )
    )
    target_eval = json.loads(
        get_packet_artifact(
            "wo-approved-001",
            "eval",
            instance_key="target_repo_mutation",
            storage_root=storage_root,
        )
    )
    assert approved_eval["pass_fail"] == "pass"
    assert target_eval["pass_fail"] == "pass"


def test_historical_observe_only_artifact_remains_readable(tmp_path) -> None:
    artifact = {
        "eval_id": "wo-old.observe_only_compliance",
        "eval_type": "observe_only_compliance",
        "subject_type": "work_order",
        "subject_id": "wo-old",
        "linked_work_order_id": "wo-old",
        "input_artifact": "result.md",
        "expected_behavior": "old observe-only behavior",
        "observed_behavior": "explicit observe-only evidence reports no mutation.",
        "score": 1,
        "pass_fail": "pass",
        "evaluator": "deterministic",
        "evidence": ["result.md"],
        "privacy_export_classification": "local_only",
        "created_at": "2026-05-11T00:00:00Z",
    }
    path = tmp_path / "observe_only_compliance.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    loaded = json.loads(path.read_text(encoding="utf-8"))

    assert loaded["eval_type"] == "observe_only_compliance"
    assert loaded["pass_fail"] == "pass"
    assert loaded["observed_behavior"]


def test_report_includes_approved_mutation_status_without_overclaiming(tmp_path) -> None:
    from core.work_orders.packet_store import get_packet_artifact
    from core.work_orders.reporting import generate_report
    from core.work_orders.results import record_result
    from core.work_orders.storage import save_work_order

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    save_work_order(
        _work_order(target, work_order_id="wo-approved-report-001"), storage_root=storage_root
    )
    _write_approval(storage_root, "wo-approved-report-001")
    source = tmp_path / "result.md"
    source.write_text(_result_text("src/app/a.ts"), encoding="utf-8")
    record_result("wo-approved-report-001", source_path=source, storage_root=storage_root)

    generate_report("wo-approved-report-001", storage_root=storage_root)
    report_text = get_packet_artifact("wo-approved-report-001", "report", storage_root=storage_root)
    assert report_text is not None

    assert "## Approved Mutation Compliance" in report_text
    assert "status: pass" in report_text
    assert "claim: approved mutation compliance proven" in report_text
