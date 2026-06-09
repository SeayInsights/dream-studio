from __future__ import annotations

import re
from pathlib import Path


def _work_order(target_path: Path, *, objective: str = "Evaluate a taxonomy handoff.") -> dict:
    return {
        "work_order_id": "wo-taxonomy-source-001",
        "project_name": "Decision Taxonomy Test",
        "target_path": str(target_path),
        "objective": objective,
        "approval_mode": "observe_only",
        "risk_level": "medium",
        "scope": {"include": ["src/app/a.ts"], "exclude": ["src/app/forbidden.ts"]},
        "allowed_skills": ["ds-core"],
        "allowed_agents": [],
        "workflow": "handoff taxonomy",
        "forbidden_actions": ["no push", "no commits", "no schema changes"],
        "validation_commands": ["python -m pytest tests/unit/test_example.py -q"],
        "expected_outputs": ["taxonomy handoff"],
        "stop_conditions": ["missing decision", "invalid taxonomy"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "reported",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
    }


def _metadata(recommendation: str) -> dict:
    return {
        "raw_output_ref": "result.md",
        "next_work_order_recommendation": recommendation,
    }


def _prompt(tmp_path: Path, recommendation: str, *, blocking: bool = False) -> tuple[str, dict]:
    from core.work_orders.handoff import build_handoff_sections

    sections = build_handoff_sections(
        work_order=_work_order(tmp_path / "target", objective=recommendation),
        result_metadata=_metadata(recommendation),
        eval_artifacts=[
            {
                "eval_type": "target_repo_mutation",
                "pass_fail": "fail" if blocking else "incomplete",
                "observed_behavior": "taxonomy test evidence",
            }
        ],
        report_path=tmp_path / "report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
    )
    return sections["prompt"], sections


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


def test_push_planning_prompt_with_valid_taxonomy_passes(tmp_path) -> None:
    prompt, sections = _prompt(
        tmp_path,
        "Phase 17P - DreamySuite Background Parity Push Planning; "
        "Next Work Order: wo-dreamysuite-014-background-parity-push-planning; "
        "Objective: prepare push planning; Risk: medium; Approval: observe_only; "
        "Non-goals: push; Validation: focused tests.",
    )
    results = _eval(prompt, sections)

    assert "## Phase Type\npush_planning" in prompt
    for decision in ("PUSH_READY_WITH_APPROVAL", "RUN_BROADER_VALIDATION_FIRST", "HOLD", "FAIL"):
        assert decision in prompt
    assert results["handoff_prompt_completeness"]["pass_fail"] == "pass"
    assert results["handoff_execution_readiness"]["pass_fail"] == "pass"


def test_push_planning_prompt_missing_taxonomy_fails(tmp_path) -> None:
    from core.work_orders.handoff import HANDOFF_PROMPT_COMPLETENESS

    prompt, sections = _prompt(
        tmp_path,
        "Phase 17P - Push Planning; Next Work Order: wo-push-001; Objective: push planning; "
        "Risk: medium; Approval: observe_only.",
    )
    results = _eval(_remove_section(prompt, "Required Decision Taxonomy"), sections)

    assert results[HANDOFF_PROMPT_COMPLETENESS]["pass_fail"] == "fail"


def test_push_planning_prompt_with_invalid_decision_fails(tmp_path) -> None:
    from core.work_orders.handoff import HANDOFF_EXECUTION_READINESS

    prompt, sections = _prompt(
        tmp_path,
        "Phase 17P - Push Planning; Next Work Order: wo-push-001; Objective: push planning; "
        "Risk: medium; Approval: observe_only.",
    )
    invalid = _replace_section(prompt, "Final Decision", "PUSH_NOW")
    results = _eval(invalid, sections)

    assert results[HANDOFF_EXECUTION_READINESS]["pass_fail"] == "fail"


def test_commit_planning_prompt_with_valid_taxonomy_passes(tmp_path) -> None:
    prompt, sections = _prompt(
        tmp_path,
        "Phase 17K - Background Parity Commit Planning; Next Work Order: wo-commit-plan-001; "
        "Objective: prepare commit planning; Risk: medium; Approval: observe_only.",
    )
    results = _eval(prompt, sections)

    assert "## Phase Type\ncommit_planning" in prompt
    assert "READY_FOR_COMMIT_PLANNING" in prompt
    assert "NEEDS_ONE_MORE_FIX" in prompt
    assert results["handoff_prompt_completeness"]["pass_fail"] == "pass"


def test_recovery_decision_prompt_with_recovery_options_passes(tmp_path) -> None:
    prompt, sections = _prompt(
        tmp_path,
        "Phase 17M - Commit Recovery Decision; Next Work Order: wo-recovery-001; "
        "Objective: choose recovery decision; Risk: medium; Approval: approval_required.",
        blocking=True,
    )
    results = _eval(prompt, sections)

    assert "## Phase Type\nrecovery_decision" in prompt
    for decision in ("LINT_REMEDIATION", "NO_VERIFY_CONTINUATION", "UNSTAGE_AND_HOLD", "ROLLBACK"):
        assert decision in prompt
    assert results["handoff_recovery_option_clarity"]["pass_fail"] == "pass"


def test_recovery_decision_prompt_missing_operator_options_fails(tmp_path) -> None:
    prompt, sections = _prompt(
        tmp_path,
        "Phase 17M - Commit Recovery Decision; Next Work Order: wo-recovery-001; "
        "Objective: choose recovery decision; Risk: medium; Approval: approval_required.",
        blocking=True,
    )
    results = _eval(_remove_section(prompt, "Recovery Options"), sections)

    assert results["handoff_recovery_option_clarity"]["pass_fail"] == "fail"


def test_product_closeout_prompt_with_valid_taxonomy_passes(tmp_path) -> None:
    prompt, sections = _prompt(
        tmp_path,
        "Phase 17J - Background Parity Closeout Audit; Next Work Order: wo-closeout-001; "
        "Objective: complete product closeout; Risk: medium; Approval: observe_only.",
    )
    results = _eval(prompt, sections)

    assert "## Phase Type\nproduct_closeout" in prompt
    assert "READY_FOR_HUMAN_REVIEW" in prompt
    assert "READY_FOR_COMMIT_PLANNING" in prompt
    assert results["handoff_prompt_completeness"]["pass_fail"] == "pass"


def test_product_closeout_prompt_includes_readiness_rules_and_expected_verdict(tmp_path) -> None:
    prompt, sections = _prompt(
        tmp_path,
        "Phase 17V - DreamySuite Background Parity Post-Push Retrospective Planning; "
        "Next Work Order: wo-retrospective-001; Objective: produce retrospective planning; "
        "Risk: medium; Approval: observe_only.",
    )
    results = _eval(prompt, sections)

    assert "## Phase Type\nproduct_closeout" in prompt
    assert "## Readiness Rules" in prompt
    assert (
        "Proceed only if the source report confirms completed work and no forbidden action."
        in prompt
    )
    assert "Future implementation work must be opened as separate Work Orders." in prompt
    assert "## Expected Verdict" in prompt
    assert (
        "PASS WITH RISKS if the artifact is produced but unresolved external risks remain" in prompt
    )
    assert results["handoff_prompt_completeness"]["pass_fail"] == "pass"


def test_product_closeout_prompt_missing_readiness_rules_fails(tmp_path) -> None:
    prompt, sections = _prompt(
        tmp_path,
        "Phase 17V - Post-Push Retrospective Planning; Next Work Order: wo-retrospective-001; "
        "Objective: produce retrospective planning; Risk: medium; Approval: observe_only.",
    )
    results = _eval(_remove_section(prompt, "Readiness Rules"), sections)

    assert results["handoff_prompt_completeness"]["pass_fail"] == "fail"


def test_product_closeout_prompt_missing_expected_verdict_fails(tmp_path) -> None:
    prompt, sections = _prompt(
        tmp_path,
        "Phase 17V - Post-Push Retrospective Planning; Next Work Order: wo-retrospective-001; "
        "Objective: produce retrospective planning; Risk: medium; Approval: observe_only.",
    )
    results = _eval(_remove_section(prompt, "Expected Verdict"), sections)

    assert results["handoff_prompt_completeness"]["pass_fail"] == "fail"


def test_regenerate_product_closeout_handoff_adds_readiness_and_verdict() -> None:
    from core.work_orders.handoff import evaluate_handoff_prompt, regenerate_handoff_prompt

    stale_prompt = "\n".join(
        [
            "# Handoff Packet",
            "",
            "## Phase Name",
            "Phase 17V - DreamySuite Background Parity Post-Push Retrospective Planning",
            "",
            "## Handoff Type",
            "normal_next_work_order",
            "",
            "## Phase Type",
            "product_closeout",
            "",
            "## Required Decision Taxonomy",
            "- READY_FOR_HUMAN_REVIEW",
            "- READY_FOR_COMMIT_PLANNING",
            "- NEEDS_ONE_MORE_FIX",
            "- HOLD",
            "- FAIL",
            "",
            "## Final Decision",
            "HOLD",
            "",
            "## Decision Rationale",
            "This post-push follow-up starts at HOLD.",
            "",
            "## Fresh-Session Rule",
            "Assume you have no prior conversation context. Use only this prompt and referenced artifacts.",
            "",
            "## Source Work Order ID",
            "wo-dreamysuite-019-background-parity-approved-push-execution",
            "",
            "## Next Work Order ID",
            "wo-dreamysuite-020-background-parity-post-push-retrospective-planning",
            "",
            "## Dream Studio Repo Path",
            "C:\\Users\\Example User\\builds\\dream-studio",
            "",
            "## Target Repo Path",
            "C:\\Users\\Example User\\builds\\dreamysuite",
            "",
            "## Baseline Dream Studio Branch/HEAD",
            "Branch: integration/phase3-plus-phase1-phase2",
            "",
            "## Baseline Target Repo Branch/HEAD",
            "Branch: fix/drag-and-selection-scaling",
            "",
            "## Objective",
            "Review the completed background parity push and decide whether to produce a retrospective or case-study planning artifact. Do not patch or push.",
            "",
            "## Capability Boundary",
            "This is observe-only planning.",
            "",
            "## Approval Mode",
            "observe_only",
            "",
            "## Risk Level",
            "medium",
            "",
            "## Scope Include",
            "- Phase 17U report",
            "- lessons from background parity Work Order chain",
            "",
            "## Scope Exclude",
            "- push execution",
            "- DreamySuite edits",
            "",
            "## Approved Files If Mutation-Gated",
            "not applicable",
            "",
            "## Forbidden Files",
            "- any DreamySuite file",
            "- generated artifacts inside DreamySuite",
            "",
            "## Allowed Actions",
            "- inspect Phase 17U report",
            "- write retrospective planning only under Dream Studio meta/audit paths",
            "",
            "## Forbidden Actions",
            "- push",
            "- edit files",
            "- stage files",
            "- commit files",
            "",
            "## Approval Artifact Requirement",
            "not applicable for observe_only planning",
            "",
            "## Before/After Evidence Requirements",
            "Capture read-only Dream Studio and DreamySuite status before and after review.",
            "",
            "## Validation Commands",
            "No validation commands are approved for this planning phase.",
            "",
            "## Eval Requirements",
            "- handoff_prompt_completeness",
            "",
            "## Report Path",
            "C:\\Users\\Example User\\.dream-studio\\meta\\audit\\phase17v-report.md",
            "",
            "## Stop Conditions",
            "- Handoff Understanding Report is missing",
            "- push/edit/stage/commit/validation is requested",
            "",
            "## Handoff Understanding Report Requirement",
            "Before taking action, produce a Handoff Understanding Report with objective, repositories involved, source Work Order ID, next Work Order ID, approval mode, risk level, approved files, forbidden files, allowed commands/actions, forbidden commands/actions, evidence required, validation required, eval requirements, stop conditions, first safe action, and missing context.",
            "",
            "## First Safe Action",
            "Read the Phase 17U report, then produce the Handoff Understanding Report before touching any repository.",
            "",
        ]
    )

    regenerated = regenerate_handoff_prompt(stale_prompt)
    results = evaluate_handoff_prompt(
        regenerated,
        readiness="READY_WITH_CONSTRAINTS",
        can_continue=True,
    )

    assert "## Phase Type\nproduct_closeout" in regenerated
    assert "## Readiness Rules" in regenerated
    assert (
        "Proceed only if the source report confirms completed work and no forbidden action."
        in regenerated
    )
    assert "any target repo file" in regenerated
    assert "generated artifacts inside the target repo" in regenerated
    assert "inspect referenced source report" in regenerated
    assert "## Expected Verdict" in regenerated
    assert (
        "PASS WITH RISKS if the artifact is produced but unresolved external risks remain"
        in regenerated
    )
    assert "Branch: integration/phase3-plus-phase1-phase2" in regenerated
    assert "any DreamySuite file" in regenerated
    assert "inspect Phase 17U report" in regenerated
    assert results["handoff_prompt_completeness"]["pass_fail"] == "pass"


def test_generated_phase17p_style_prompt_includes_decision_instruction(tmp_path) -> None:
    prompt, _ = _prompt(
        tmp_path,
        "Phase 17P - DreamySuite Background Parity Push Planning; "
        "Next Work Order: wo-dreamysuite-014-background-parity-push-planning; "
        "Objective: prepare push planning; Risk: medium; Approval: observe_only.",
    )

    assert "## Phase Type\npush_planning" in prompt
    assert "## Required Decision Taxonomy" in prompt
    assert "## Final Decision\nHOLD" in prompt
    assert "## Decision Rationale" in prompt
    for decision in ("PUSH_READY_WITH_APPROVAL", "RUN_BROADER_VALIDATION_FIRST", "HOLD", "FAIL"):
        assert decision in prompt
