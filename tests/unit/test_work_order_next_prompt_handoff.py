from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config.database import DB_PATH_ENV, DatabaseRuntime


@pytest.fixture(autouse=True)
def _isolate_telemetry_db(tmp_path, monkeypatch):
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "telemetry.db"))
    DatabaseRuntime.reset_instance()
    yield
    DatabaseRuntime.reset_instance()


def _work_order(
    target_path: Path,
    *,
    work_order_id: str = "wo-handoff-001",
    approval_mode: str = "observe_only",
) -> dict:
    return {
        "work_order_id": work_order_id,
        "project_name": "Handoff Test",
        "target_path": str(target_path),
        "objective": "Generate a fresh-session-safe handoff prompt.",
        "approval_mode": approval_mode,
        "risk_level": "low",
        "scope": {"include": ["src/app/a.ts"], "exclude": ["src/app/forbidden.ts"]},
        "allowed_skills": ["ds-core"],
        "allowed_agents": [],
        "workflow": "handoff",
        "forbidden_actions": [
            "no unapproved edits",
            "no commits",
            "no deletes or removes",
            "no schema changes",
            "no dependency changes",
            "no external actions",
            "no target repo mutation without approval",
        ],
        "validation_commands": ["python -m pytest tests/unit/test_example.py -q"],
        "expected_outputs": ["handoff report"],
        "stop_conditions": ["missing approval", "unapproved file changes"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "rendered",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
        "handoff_context": {
            "handoff_reason": "user_requested_export_or_continuation",
            "source_authority_refs": ["PRD", "stage gates"],
            "evidence_refs": ["result.md"],
            "validation_refs": ["focused tests"],
        },
    }


def _result_text(
    *, next_id: str = "wo-next-001", files_changed: str = "none", approval: str = "observe_only"
) -> str:
    return "\n".join(
        [
            "Summary: Handoff evidence recorded.",
            "Files inspected: src/app/a.ts",
            f"Files changed: {files_changed}",
            "Commands: python -m pytest tests/unit/test_example.py -q => PASS",
            "Forbidden actions: complied",
            "Target mutation: no",
            "Warnings: none",
            "Risks: none",
            f"Next Work Order: {next_id}; Objective: continue with a bounded handoff slice; Risk: low; Approval: {approval}; Non-goals: broad mutation; Validation: focused tests.",
            "",
        ]
    )


def _write_result_source(tmp_path: Path, text: str) -> Path:
    source = tmp_path / "result.md"
    source.write_text(text, encoding="utf-8")
    return source


def _write_approval(storage_root: Path, work_order_id: str) -> None:
    approval = {
        "approval_status": "approved",
        "approved_by": "operator",
        "approved_at": "2026-05-11T00:00:00Z",
        "approval_mode": "approval_required",
        "approved_files": ["src/app/a.ts"],
        "forbidden_files": ["src/app/forbidden.ts"],
        "approval_scope": "handoff approved mutation test",
    }
    path = storage_root / work_order_id / "approvals" / "approval.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")


def test_report_generates_fresh_session_handoff_prompt_and_evals(tmp_path) -> None:
    from core.work_orders.reporting import generate_report
    from core.work_orders.results import record_result
    from core.work_orders.storage import save_work_order

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    save_work_order(_work_order(target), storage_root=storage_root)
    record_result(
        "wo-handoff-001",
        source_path=_write_result_source(tmp_path, _result_text()),
        storage_root=storage_root,
    )

    result = generate_report("wo-handoff-001", storage_root=storage_root)
    report_text = Path(result["report_path"]).read_text(encoding="utf-8")
    prompt_eval = json.loads(
        (storage_root / "wo-handoff-001" / "evals" / "handoff_prompt_completeness.json").read_text(
            encoding="utf-8"
        )
    )
    path_eval = json.loads(
        (storage_root / "wo-handoff-001" / "evals" / "handoff_path_integrity.json").read_text(
            encoding="utf-8"
        )
    )

    assert "## Sequential Execution Readiness" in report_text
    assert "readiness: READY_WITH_CONSTRAINTS" in report_text
    assert "## Next Action Decision" in report_text
    assert "- phase_type: normal_next_work_order" in report_text
    assert "- required_decision_taxonomy:" in report_text
    assert "## Ready-To-Copy Next Prompt" in report_text
    assert "# Handoff Packet" in report_text
    assert "## Phase Type" in report_text
    assert "## Required Decision Taxonomy" in report_text
    assert "## Final Decision" in report_text
    assert (
        "Assume you have no prior conversation context. Use only this prompt and referenced artifacts."
        in report_text
    )
    assert "Handoff Understanding Report" in report_text
    assert prompt_eval["pass_fail"] == "pass"
    assert path_eval["pass_fail"] == "pass"


def test_approval_required_handoff_prompt_preserves_approval_requirements(tmp_path) -> None:
    from core.work_orders.reporting import generate_report
    from core.work_orders.results import record_result
    from core.work_orders.storage import save_work_order

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    save_work_order(
        _work_order(
            target, work_order_id="wo-handoff-approved-001", approval_mode="approval_required"
        ),
        storage_root=storage_root,
    )
    _write_approval(storage_root, "wo-handoff-approved-001")
    record_result(
        "wo-handoff-approved-001",
        source_path=_write_result_source(
            tmp_path,
            _result_text(
                next_id="wo-next-approved-001",
                files_changed="src/app/a.ts",
                approval="approval_required",
            ),
        ),
        storage_root=storage_root,
    )

    result = generate_report("wo-handoff-approved-001", storage_root=storage_root)
    report_text = Path(result["report_path"]).read_text(encoding="utf-8")
    prompt_eval = json.loads(
        (
            storage_root / "wo-handoff-approved-001" / "evals" / "handoff_prompt_completeness.json"
        ).read_text(encoding="utf-8")
    )

    assert "next_work_order_mode: approval_required" in report_text
    assert "Create file-backed approvals/approval.json before mutation" in report_text
    assert "src/app/a.ts" in report_text
    assert prompt_eval["pass_fail"] == "pass"


def test_hold_report_uses_recovery_decision_handoff_not_execution_handoff(tmp_path) -> None:
    from core.work_orders.reporting import generate_report
    from core.work_orders.storage import save_work_order

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    save_work_order(
        _work_order(target, work_order_id="wo-handoff-hold-001"), storage_root=storage_root
    )

    result = generate_report("wo-handoff-hold-001", storage_root=storage_root)
    report_text = Path(result["report_path"]).read_text(encoding="utf-8")

    assert "readiness: HOLD" in report_text
    assert "# Handoff Packet" in report_text
    assert "## Handoff Type\nrecovery_decision" in report_text
    assert "## Operator Decision Required\ntrue" in report_text
    assert "this is a recovery decision handoff, not a recovery execution prompt" in report_text


def test_failed_target_repo_mutation_blocks_sequential_execution(tmp_path) -> None:
    from core.work_orders.evals import create_target_repo_mutation_eval
    from core.work_orders.reporting import generate_report
    from core.work_orders.results import record_result
    from core.work_orders.storage import save_work_order

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    work_order = _work_order(target, work_order_id="wo-handoff-target-fail-001")
    save_work_order(work_order, storage_root=storage_root)
    record_result(
        "wo-handoff-target-fail-001",
        source_path=_write_result_source(tmp_path, _result_text(next_id="wo-next-target-001")),
        storage_root=storage_root,
    )
    create_target_repo_mutation_eval(
        work_order=work_order,
        before_snapshot={"src/app/a.ts": "before"},
        after_snapshot={"src/app/a.ts": "after"},
        storage_root=storage_root,
    )

    result = generate_report("wo-handoff-target-fail-001", storage_root=storage_root)
    report_text = Path(result["report_path"]).read_text(encoding="utf-8")

    assert "readiness: HOLD" in report_text
    assert "target_repo_mutation failed" in report_text
    assert "## Handoff Type\nrecovery_decision" in report_text


def test_failed_approved_mutation_blocks_sequential_execution(tmp_path) -> None:
    from core.work_orders.reporting import generate_report
    from core.work_orders.results import record_result
    from core.work_orders.storage import save_work_order

    target = tmp_path / "target"
    target.mkdir()
    storage_root = tmp_path / "store"
    save_work_order(
        _work_order(
            target, work_order_id="wo-handoff-approved-fail-001", approval_mode="approval_required"
        ),
        storage_root=storage_root,
    )
    _write_approval(storage_root, "wo-handoff-approved-fail-001")
    record_result(
        "wo-handoff-approved-fail-001",
        source_path=_write_result_source(
            tmp_path,
            _result_text(
                next_id="wo-next-approved-fail-001",
                files_changed="src/app/unapproved.ts",
                approval="approval_required",
            ),
        ),
        storage_root=storage_root,
    )

    result = generate_report("wo-handoff-approved-fail-001", storage_root=storage_root)
    report_text = Path(result["report_path"]).read_text(encoding="utf-8")

    assert "readiness: HOLD" in report_text
    assert "approved_mutation_compliance failed" in report_text
    assert "## Handoff Type\nrecovery_decision" in report_text


def _transition_sections(tmp_path: Path, metadata: dict) -> dict:
    from core.work_orders.handoff import build_handoff_sections

    return build_handoff_sections(
        work_order=_work_order(tmp_path / "target", approval_mode="approval_required"),
        result_metadata={
            "raw_output_ref": "result.md",
            "next_work_order_recommendation": (
                "Phase 99 - Dashboard Projection Planning; Next Work Order: wo-dashboard-001; "
                "Objective: dashboard/projection planning; Risk: medium; Approval: approval_required."
            ),
            **metadata,
        },
        eval_artifacts=[{"eval_type": "target_repo_mutation", "pass_fail": "incomplete"}],
        report_path=tmp_path / "report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
    )


def test_completed_uncommitted_mutation_routes_to_commit_preparation_before_dashboard(
    tmp_path,
) -> None:
    sections = _transition_sections(
        tmp_path,
        {
            "phase_type": "bounded_approved_mutation",
            "decision": "MUTATION_COMPLETE",
            "changed_files_after": ["core/work_orders/handoff.py"],
            "stage_performed": False,
            "commit_performed": False,
        },
    )

    prompt = sections["prompt"]
    decision = sections["decision"]

    assert decision["phase_type"] == "commit_planning"
    assert "wo-commit-preparation" in prompt
    assert (
        "Because the prior phase completed a bounded mutation and left scoped source changes uncommitted"
        in prompt
    )
    assert "before dashboard/projection planning" in prompt


def test_commit_planning_ready_routes_to_commit_execution(tmp_path) -> None:
    sections = _transition_sections(
        tmp_path,
        {
            "phase_type": "commit_planning",
            "decision": "COMMIT_PLAN_READY",
        },
    )

    prompt = sections["prompt"]

    assert sections["decision"]["handoff_type"] == "commit_execution"
    assert "wo-commit-execution" in prompt
    assert "Because commit planning is ready" in prompt


def test_commit_execution_complete_routes_to_post_commit_review(tmp_path) -> None:
    sections = _transition_sections(
        tmp_path,
        {
            "phase_type": "commit_execution",
            "decision": "COMMIT_COMPLETE",
            "release_gate": "REMEDIATE_BEFORE_RELEASE",
        },
    )

    prompt = sections["prompt"]

    assert "wo-post-commit-review" in prompt
    assert "Because commit execution is complete" in prompt
    assert "post-commit release-gate/security review" in prompt


def test_post_mutation_review_acceptance_routes_to_commit_planning_when_uncommitted(
    tmp_path,
) -> None:
    sections = _transition_sections(
        tmp_path,
        {
            "phase_type": "post_mutation_review",
            "decision": "POST_MUTATION_REVIEW_COMPLETE",
            "changed_files_after": ["core/work_orders/handoff.py"],
            "commit_performed": False,
        },
    )

    prompt = sections["prompt"]

    assert sections["decision"]["phase_type"] == "commit_planning"
    assert "wo-commit-planning" in prompt
    assert "post-mutation review accepted the remediation" in prompt


def test_observe_only_blockers_route_to_remediation_planning(tmp_path) -> None:
    sections = _transition_sections(
        tmp_path,
        {
            "phase_type": "observe_only_security_review",
            "decision": "NEEDS_REMEDIATION",
        },
    )

    prompt = sections["prompt"]

    assert "wo-remediation-planning" in prompt
    assert "Because observe-only review found blockers" in prompt


def test_remediation_plan_ready_routes_to_bounded_mutation(tmp_path) -> None:
    sections = _transition_sections(
        tmp_path,
        {
            "phase_type": "bounded_remediation_planning",
            "decision": "REMEDIATION_PLAN_READY",
        },
    )

    prompt = sections["prompt"]

    assert sections["decision"]["phase_type"] == "approved_mutation"
    assert "wo-bounded-approved-mutation" in prompt
    assert "Because remediation planning is ready" in prompt


def test_pause_return_transition_preserves_pause_rationale(tmp_path) -> None:
    sections = _transition_sections(
        tmp_path,
        {
            "next_work_order_recommendation": (
                "Phase 99A - Pause Return; Next Work Order: wo-return-001; "
                "Objective: operator chose return to core work; Risk: medium; Approval: approval_required."
            ),
        },
    )

    prompt = sections["prompt"]

    assert "wo-paused-work-continuity" in prompt
    assert "operator chose pause or return-to-core-work" in prompt
    assert "do not run deferred remediation automatically" in prompt
