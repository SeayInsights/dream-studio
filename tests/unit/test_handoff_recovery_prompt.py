from __future__ import annotations

import re
from pathlib import Path


def _work_order(target_path: Path) -> dict:
    return {
        "work_order_id": "wo-dreamysuite-010-background-parity-approved-commit-execution",
        "project_name": "Recovery Handoff Test",
        "target_path": str(target_path),
        "objective": "Recover after a failed approved commit execution.",
        "approval_mode": "approval_required",
        "risk_level": "medium",
        "scope": {
            "include": [
                "src/app/[slug]/styles.ts",
                "src/app/[slug]/styles.test.ts",
                "src/app/[slug]/scripts.ts",
                "src/app/[slug]/scripts.test.ts",
            ],
            "exclude": ["prod-backup.sql", "package.json", "schema/migration files"],
        },
        "allowed_skills": ["ds-core"],
        "allowed_agents": [],
        "workflow": "recovery handoff",
        "forbidden_actions": ["push", "stage forbidden files", "run broad formatters"],
        "validation_commands": [
            'npm test -- "src/app/[slug]/styles.test.ts"',
            'npm test -- "src/app/[slug]/scripts.test.ts"',
        ],
        "expected_outputs": ["recovery decision report"],
        "stop_conditions": ["operator decision missing", "forbidden file staged"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "reported",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def _metadata() -> dict:
    return {
        "raw_output_ref": "result.md",
        "summary": "Commit group 2 failed pre-commit lint; lint-staged hook failed and staged files remain.",
        "structured_findings": {
            "files_changed": [
                "src/app/[slug]/styles.ts",
                "src/app/[slug]/styles.test.ts",
                "src/app/[slug]/scripts.ts",
                "src/app/[slug]/scripts.test.ts",
            ],
            "commands_or_tests": ["pre-commit lint-staged hook failed"],
        },
        "warnings": ["pre-commit/lint-staged may modify files"],
        "risks": ["branch is ahead by one local commit", "group 2 files remain staged"],
        "next_work_order_recommendation": (
            "Phase 17M - DreamySuite Background Parity Commit Recovery Decision; "
            "Next Work Order: wo-dreamysuite-011-background-parity-commit-recovery-decision; "
            "Objective: choose a safe recovery path after pre-commit failure; "
            "Risk: medium; Approval: approval_required; Non-goals: push; Validation: focused tests."
        ),
    }


def _sections(tmp_path: Path) -> dict:
    from core.work_orders.handoff import build_handoff_sections

    return build_handoff_sections(
        work_order=_work_order(tmp_path / "target"),
        result_metadata=_metadata(),
        eval_artifacts=[
            {
                "eval_type": "target_repo_mutation",
                "pass_fail": "fail",
                "observed_behavior": "pre-commit hook failed; staged files remain.",
            }
        ],
        report_path=tmp_path / "report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
    )


def _remove_section(prompt: str, title: str) -> str:
    pattern = re.compile(rf"^## {re.escape(title)}\n.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    return pattern.sub("", prompt)


def _replace_section(prompt: str, title: str, body: str) -> str:
    pattern = re.compile(rf"^## {re.escape(title)}\n.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    return pattern.sub(f"## {title}\n{body}\n", prompt)


def _eval(prompt: str, sections: dict) -> dict:
    from core.work_orders.handoff import evaluate_handoff_prompt

    return evaluate_handoff_prompt(
        prompt,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
    )


def test_hold_report_generates_recovery_decision_handoff(tmp_path) -> None:
    sections = _sections(tmp_path)
    prompt = sections["prompt"]

    assert sections["readiness"]["readiness"] == "HOLD"
    assert "## Handoff Type\nrecovery_decision" in prompt
    assert "recovery execution prompt" in prompt
    assert "commit_execution" not in prompt


def test_recovery_prompt_includes_failure_state_options_and_decision_gate(tmp_path) -> None:
    prompt = _sections(tmp_path)["prompt"]

    assert "## Source Failure" in prompt
    assert "pre-commit" in prompt
    assert "## Current State" in prompt
    assert "local commit exists" in prompt
    assert "branch is ahead" in prompt
    assert "staged files remain" in prompt
    assert "no push occurred" in prompt
    assert "forbidden files were not staged or committed" in prompt
    assert "lint remediation" in prompt
    assert "no-verify continuation" in prompt
    assert "unstage-and-hold" in prompt
    assert "rollback" in prompt
    assert "operator must choose one recovery path" in prompt


def test_recovery_prompt_eval_passes_for_complete_recovery_packet(tmp_path) -> None:
    sections = _sections(tmp_path)
    results = _eval(sections["prompt"], sections)

    for eval_type in (
        "handoff_recovery_mode_completeness",
        "handoff_current_state_completeness",
        "handoff_recovery_option_clarity",
        "handoff_operator_decision_gate",
        "handoff_index_state_requirements",
        "handoff_hook_behavior_awareness",
    ):
        assert results[eval_type]["pass_fail"] == "pass", eval_type


def test_recovery_prompt_fails_if_decision_and_execution_are_blended(tmp_path) -> None:
    sections = _sections(tmp_path)
    prompt = _replace_section(
        sections["prompt"],
        "Allowed Actions",
        "- run git commit immediately\n- create local commits",
    )
    prompt = _remove_section(prompt, "Operator Decision Required")

    results = _eval(prompt, sections)

    assert results["handoff_recovery_mode_completeness"]["pass_fail"] == "fail"
    assert results["handoff_operator_decision_gate"]["pass_fail"] == "fail"


def test_recovery_prompt_fails_if_index_state_requirements_are_missing(tmp_path) -> None:
    sections = _sections(tmp_path)
    results = _eval(_remove_section(sections["prompt"], "Index State Requirements"), sections)

    assert results["handoff_index_state_requirements"]["pass_fail"] == "fail"


def test_recovery_prompt_fails_if_hook_risk_is_missing_after_hook_failure(tmp_path) -> None:
    sections = _sections(tmp_path)
    results = _eval(_remove_section(sections["prompt"], "Hook Behavior Risks"), sections)

    assert results["handoff_hook_behavior_awareness"]["pass_fail"] == "fail"
