from __future__ import annotations

import re
from pathlib import Path

DREAMY_TARGET = "C:\\Users\\Example User\\builds\\dreamysuite"
PUSH_COMMAND = (
    'git -C "C:\\Users\\Example User\\builds\\dreamysuite" push origin '
    "fix/drag-and-selection-scaling"
)


def _work_order() -> dict:
    return {
        "work_order_id": "wo-push-source-001",
        "project_name": "Push Execution Handoff Test",
        "target_path": DREAMY_TARGET,
        "objective": "Prepare push planning for verified local commits.",
        "approval_mode": "observe_only",
        "risk_level": "medium",
        "scope": {
            "include": ["DreamySuite push exception decision"],
            "exclude": ["push execution", "unrelated dirty files"],
        },
        "allowed_skills": ["ds-core"],
        "allowed_agents": [],
        "workflow": "push handoff",
        "forbidden_actions": ["no push", "no edits", "no staging", "no commits"],
        "validation_commands": ["no validation commands are approved"],
        "expected_outputs": ["push execution handoff"],
        "stop_conditions": ["missing approval", "wrong remote", "wrong branch"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "reported",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
        "handoff_context": {
            "push_execution": {
                "phase_name": "Phase 17U - DreamySuite Background Parity Approved Push Execution",
                "baseline_dream_studio": (
                    "Branch: integration/phase3-plus-phase1-phase2\n"
                    "HEAD: f1af04d feat(work-orders): add operator decision gate"
                ),
                "baseline_target": (
                    "Branch: fix/drag-and-selection-scaling\n"
                    "HEAD: 3163323 fix(editor): align background image layer preview"
                ),
                "remote": "origin",
                "branch": "fix/drag-and-selection-scaling",
                "expected_head": "3163323",
                "expected_ahead_behind": "0 3",
                "local_commits": ["04c5ddc", "9034648", "3163323"],
                "approval_artifact_path": (
                    "C:\\Users\\Example User\\.dream-studio\\meta\\work-orders\\"
                    "wo-dreamysuite-019-background-parity-approved-push-execution\\"
                    "approvals\\approval.json"
                ),
                "report_path": (
                    "C:\\Users\\Example User\\.dream-studio\\meta\\audit\\"
                    "2026-05-11-phase17u-dreamysuite-background-parity-approved-"
                    "push-execution-report.md"
                ),
                "scope_include": [
                    "push exactly the three local background parity commits",
                    "remote origin",
                    "branch fix/drag-and-selection-scaling",
                ],
                "scope_exclude": [
                    "force push",
                    "tags",
                    "other branches",
                    "edits",
                    "staging",
                    "commits",
                ],
                "validation_commands": ["no validation reruns are approved in Phase 17U"],
            }
        },
    }


def _metadata() -> dict:
    return {
        "raw_output_ref": "result.md",
        "next_work_order_recommendation": (
            "Phase 17U - DreamySuite Background Parity Approved Push Execution; "
            "Next Work Order: wo-dreamysuite-019-background-parity-approved-push-execution; "
            "Objective: execute the approved push of the three local DreamySuite background "
            "parity commits after confirming branch, index, no-push, and approval evidence; "
            "Risk: medium; Approval: approval_required; Non-goals: patching, staging unrelated "
            "files, committing, validation reruns, schema/dependency/Docker/dashboard/TORII/"
            "cloud/org/global/enterprise changes; Validation: read-only pre-push checks."
        ),
    }


def _request() -> dict:
    return {
        "decision_request_id": "wo-push-source-001.push_planning.decision",
        "work_order_id": "wo-push-source-001",
        "phase_type": "push_planning",
        "required_decision_taxonomy": [
            "PUSH_READY_WITH_APPROVAL",
            "RUN_BROADER_VALIDATION_FIRST",
            "HOLD",
            "FAIL",
        ],
        "status": "pending_operator_decision",
        "question": "Approve push execution?",
        "allowed_decisions": [
            "PUSH_READY_WITH_APPROVAL",
            "RUN_BROADER_VALIDATION_FIRST",
            "HOLD",
            "FAIL",
        ],
        "recommended_decision": "PUSH_READY_WITH_APPROVAL",
        "risk_summary": "operator accepted push exception risk",
        "required_evidence": ["Phase 17T report"],
        "requires_reason": True,
        "created_at": "2026-05-11T00:00:00Z",
        "_path": "/tmp/request.json",
    }


def _decision() -> dict:
    return {
        "decision_request_id": "wo-push-source-001.push_planning.decision",
        "work_order_id": "wo-push-source-001",
        "decision": "PUSH_READY_WITH_APPROVAL",
        "decided_by": "operator",
        "decided_at": "2026-05-11T00:00:00Z",
        "reason": "Push exception accepted after unrelated broad test failure review.",
        "approved_next_handoff_type": "approved_mutation_execution",
        "constraints": ["no force push", "no tags", "no other branch"],
        "privacy_export_classification": "local_only",
        "_path": "/tmp/operator_decision.json",
    }


def _prompt(tmp_path: Path) -> tuple[str, dict]:
    from core.work_orders.handoff import build_handoff_sections

    sections = build_handoff_sections(
        work_order=_work_order(),
        result_metadata=_metadata(),
        eval_artifacts=[],
        report_path=tmp_path / "source-report.md",
        dream_studio_repo_path="C:\\Users\\Example User\\builds\\dream-studio",
        decision_request=_request(),
        operator_decision=_decision(),
    )
    return sections["prompt"], sections


def _replace_section(prompt: str, title: str, body: str) -> str:
    pattern = re.compile(rf"^## {re.escape(title)}\n.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    return pattern.sub(f"## {title}\n{body}\n", prompt)


def test_push_ready_with_approval_generates_push_execution_handoff(tmp_path) -> None:
    prompt, sections = _prompt(tmp_path)

    assert sections["decision"]["final_decision"] == "PUSH_READY_WITH_APPROVAL"
    assert sections["decision"]["handoff_type"] == "approved_mutation_execution"
    assert "## Handoff Type\napproved_mutation_execution" in prompt
    assert "## Phase Type\npush_planning" in prompt


def test_generated_push_handoff_includes_required_push_sections(tmp_path) -> None:
    prompt, _ = _prompt(tmp_path)

    for section in (
        "## Approved Push Target",
        "## Forbidden Push Targets",
        "## Before-Push Evidence Requirements",
        "## Push Command",
        "## After-Push Evidence Requirements",
        "## Sequential Readiness Rules",
        "## Expected Verdict",
        "## Next Prompt/Report Requirement",
    ):
        assert section in prompt


def test_generated_push_handoff_includes_exact_push_target_constraints(tmp_path) -> None:
    prompt, _ = _prompt(tmp_path)

    for expected in (
        "remote: origin",
        "branch: fix/drag-and-selection-scaling",
        PUSH_COMMAND,
        "force push",
        "tags",
        "pushing any other branch",
        "pushing any other remote",
        "delete remote branch",
        "push with extra refspecs",
    ):
        assert expected in prompt


def test_generated_push_handoff_requires_before_push_gates(tmp_path) -> None:
    prompt, _ = _prompt(tmp_path)

    for expected in (
        "create approval artifact before push",
        "fetch origin before push",
        "ahead/behind is exactly 0 3",
        "confirm HEAD is 3163323",
        "local commit: 04c5ddc",
        "local commit: 9034648",
        "local commit: 3163323",
        "confirm index is empty",
    ):
        assert expected in prompt


def test_generated_push_handoff_includes_after_push_evidence_and_outcome_rules(tmp_path) -> None:
    prompt, _ = _prompt(tmp_path)

    for expected in (
        "capture push output",
        "capture ahead/behind after push",
        "READY_WITH_CONSTRAINTS if push succeeds, ahead/behind becomes 0 0",
        "HOLD if remote state changed before push",
        "FAIL if wrong branch/remote is pushed",
        "PASS WITH RISKS if push succeeds and no forbidden action occurs.",
        "create the push execution report",
    ):
        assert expected in prompt


def test_generated_push_handoff_passes_push_specific_evals(tmp_path) -> None:
    from core.work_orders.handoff import evaluate_handoff_prompt

    prompt, sections = _prompt(tmp_path)
    results = evaluate_handoff_prompt(
        prompt,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
    )

    assert results["handoff_push_execution_completeness"]["pass_fail"] == "pass"
    assert results["handoff_push_target_constraints"]["pass_fail"] == "pass"
    assert results["handoff_push_evidence_requirements"]["pass_fail"] == "pass"


def test_push_handoff_eval_fails_if_exact_push_command_is_missing(tmp_path) -> None:
    from core.work_orders.handoff import HANDOFF_PUSH_TARGET_CONSTRAINTS, evaluate_handoff_prompt

    prompt, sections = _prompt(tmp_path)
    weakened = _replace_section(prompt, "Push Command", "git push")
    results = evaluate_handoff_prompt(
        weakened,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
    )

    assert results[HANDOFF_PUSH_TARGET_CONSTRAINTS]["pass_fail"] == "fail"


def test_push_handoff_eval_fails_if_force_push_prohibition_is_missing(tmp_path) -> None:
    from core.work_orders.handoff import HANDOFF_PUSH_TARGET_CONSTRAINTS, evaluate_handoff_prompt

    prompt, sections = _prompt(tmp_path)
    weakened = prompt.replace("no force push", "")
    results = evaluate_handoff_prompt(
        weakened,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
    )

    assert results[HANDOFF_PUSH_TARGET_CONSTRAINTS]["pass_fail"] == "fail"


def test_push_handoff_eval_fails_if_ahead_behind_gate_is_missing(tmp_path) -> None:
    from core.work_orders.handoff import HANDOFF_PUSH_EVIDENCE_REQUIREMENTS, evaluate_handoff_prompt

    prompt, sections = _prompt(tmp_path)
    weakened = prompt.replace("ahead/behind is exactly 0 3", "")
    results = evaluate_handoff_prompt(
        weakened,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
    )

    assert results[HANDOFF_PUSH_EVIDENCE_REQUIREMENTS]["pass_fail"] == "fail"


def test_push_handoff_eval_fails_if_approval_artifact_gate_is_missing(tmp_path) -> None:
    from core.work_orders.handoff import HANDOFF_PUSH_EVIDENCE_REQUIREMENTS, evaluate_handoff_prompt

    prompt, sections = _prompt(tmp_path)
    weakened = prompt.replace("approval artifact", "approval evidence")
    results = evaluate_handoff_prompt(
        weakened,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
    )

    assert results[HANDOFF_PUSH_EVIDENCE_REQUIREMENTS]["pass_fail"] == "fail"
