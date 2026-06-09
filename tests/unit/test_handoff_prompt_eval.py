from __future__ import annotations

import re
from pathlib import Path


def _work_order(target_path: Path, *, approval_mode: str = "observe_only") -> dict:
    return {
        "work_order_id": "wo-source-001",
        "project_name": "Handoff Eval Test",
        "target_path": str(target_path),
        "objective": "Evaluate generated handoff prompts.",
        "approval_mode": approval_mode,
        "risk_level": "low",
        "scope": {"include": ["src/app/a.ts"], "exclude": ["src/app/forbidden.ts"]},
        "allowed_skills": ["ds-core"],
        "allowed_agents": [],
        "workflow": "handoff eval",
        "forbidden_actions": ["no commits", "no schema changes", "no dependency changes"],
        "validation_commands": ["python -m pytest tests/unit/test_example.py -q"],
        "expected_outputs": ["handoff prompt"],
        "stop_conditions": ["missing context", "unapproved mutation"],
        "created_by": "pytest",
        "created_at": "2026-05-11T00:00:00Z",
        "status": "reported",
        "storage_class": "file_backed",
        "privacy_export_classification": "local_only",
        "handoff_context": {
            "handoff_reason": "user_requested_export_or_continuation",
            "source_authority_refs": ["PRD", "stage gates"],
            "evidence_refs": ["result.md"],
            "validation_refs": ["focused tests"],
        },
    }


def _metadata(*, approval: str = "observe_only") -> dict:
    return {
        "raw_output_ref": "result.md",
        "next_work_order_recommendation": (
            f"wo-next-001; Objective: continue safely; Risk: low; Approval: {approval}; "
            "Non-goals: broad mutation; Validation: focused tests."
        ),
    }


def _prompt(tmp_path: Path, *, approval_mode: str = "observe_only") -> tuple[str, dict]:
    from core.work_orders.handoff import build_handoff_sections

    work_order = _work_order(tmp_path / "target", approval_mode=approval_mode)
    sections = build_handoff_sections(
        work_order=work_order,
        result_metadata=_metadata(approval=approval_mode),
        eval_artifacts=[{"eval_type": "target_repo_mutation", "pass_fail": "incomplete"}],
        report_path=tmp_path / "report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
    )
    return sections["prompt"], sections


def _remove_section(prompt: str, title: str) -> str:
    pattern = re.compile(rf"^## {re.escape(title)}\n.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    return pattern.sub("", prompt)


def test_complete_observe_only_handoff_prompt_passes(tmp_path) -> None:
    from core.work_orders.handoff import evaluate_handoff_prompt

    prompt, sections = _prompt(tmp_path)
    results = evaluate_handoff_prompt(
        prompt,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
    )

    assert all(result["pass_fail"] == "pass" for result in results.values())


def test_complete_approval_required_handoff_prompt_passes(tmp_path) -> None:
    from core.work_orders.handoff import evaluate_handoff_prompt

    prompt, sections = _prompt(tmp_path, approval_mode="approval_required")
    results = evaluate_handoff_prompt(
        prompt,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
    )

    assert "Create file-backed approvals/approval.json before mutation" in prompt
    assert all(result["pass_fail"] == "pass" for result in results.values())


def test_missing_critical_context_fields_fail(tmp_path) -> None:
    from core.work_orders.handoff import HANDOFF_PROMPT_COMPLETENESS, evaluate_handoff_prompt

    prompt, sections = _prompt(tmp_path)
    missing_cases = [
        "Dream Studio Repo Path",
        "Target Repo Path",
        "Next Work Order ID",
        "Objective",
        "Phase Type",
        "Required Decision Taxonomy",
        "Stop Conditions",
        "Readiness Rules",
        "Expected Verdict",
        "Output Artifacts",
        "Final Response Must Include",
        "Next Handoff Requirements",
        "Phase-Specific Safety Constraints",
        "Fresh-Session Rule",
        "Handoff Understanding Report Requirement",
    ]

    for title in missing_cases:
        results = evaluate_handoff_prompt(
            _remove_section(prompt, title),
            readiness=sections["readiness"]["readiness"],
            can_continue=sections["readiness"]["can_continue"],
        )
        assert results[HANDOFF_PROMPT_COMPLETENESS]["pass_fail"] == "fail", title


def test_approval_required_missing_approval_fields_fail(tmp_path) -> None:
    from core.work_orders.handoff import HANDOFF_PROMPT_COMPLETENESS, evaluate_handoff_prompt

    prompt, sections = _prompt(tmp_path, approval_mode="approval_required")
    for title in (
        "Approved Files If Mutation-Gated",
        "Forbidden Files",
        "Approval Artifact Requirement",
    ):
        results = evaluate_handoff_prompt(
            _remove_section(prompt, title),
            readiness=sections["readiness"]["readiness"],
            can_continue=sections["readiness"]["can_continue"],
        )
        assert results[HANDOFF_PROMPT_COMPLETENESS]["pass_fail"] == "fail", title


def test_constraint_preservation_and_first_safe_action_are_required(tmp_path) -> None:
    from core.work_orders.handoff import (
        HANDOFF_CONSTRAINT_PRESERVATION,
        evaluate_handoff_prompt,
    )

    prompt, sections = _prompt(tmp_path)
    assert "Do not add DB/event ledger integration" in prompt
    assert "Do not add schema migrations" in prompt
    assert "Do not expand Docker" in prompt
    assert "Do not add TORII integration" in prompt
    assert "Do not add cloud/org/global sync" in prompt
    assert "Do not recreate hooks/lib" in prompt
    assert "## First Safe Action" in prompt

    weakened = prompt.replace("Do not add schema migrations", "")
    results = evaluate_handoff_prompt(
        weakened,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
    )
    assert results[HANDOFF_CONSTRAINT_PRESERVATION]["pass_fail"] == "fail"


def test_dry_run_simulation_extracts_fields_and_reports_missing_fields(tmp_path) -> None:
    from core.work_orders.handoff import dry_run_handoff_prompt

    prompt, _ = _prompt(tmp_path)
    simulation = dry_run_handoff_prompt(prompt)
    missing = dry_run_handoff_prompt(_remove_section(prompt, "Objective"))

    assert simulation["readiness"] == "pass"
    assert simulation["extracted_fields"]["source_work_order_id"] == "wo-source-001"
    assert simulation["extracted_fields"]["next_work_order_id"] == "wo-next-001"
    assert missing["readiness"] == "fail"
    assert "objective" in missing["missing_fields"]


def test_handoff_path_integrity_preserves_dream_studio_meta_separator(tmp_path) -> None:
    from core.work_orders.handoff import (
        HANDOFF_PATH_INTEGRITY,
        build_handoff_sections,
        evaluate_handoff_prompt,
    )

    correct_report_path = r"C:\Users\Example User\.dream-studio\meta\audit\phase-report.md"
    malformed_report_path = correct_report_path.replace(r"\.dream-studio", ".dream-studio")
    sections = build_handoff_sections(
        work_order=_work_order(tmp_path / "target"),
        result_metadata=_metadata(),
        eval_artifacts=[{"eval_type": "target_repo_mutation", "pass_fail": "incomplete"}],
        report_path=correct_report_path,
        dream_studio_repo_path=r"C:\Users\Example User\builds\dream-studio",
    )
    prompt = sections["prompt"]

    assert correct_report_path in prompt
    assert malformed_report_path not in prompt

    results = evaluate_handoff_prompt(
        prompt,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
    )
    assert results[HANDOFF_PATH_INTEGRITY]["pass_fail"] == "pass"


def test_handoff_path_integrity_fails_malformed_dream_studio_meta_root(tmp_path) -> None:
    from core.work_orders.handoff import (
        HANDOFF_PATH_INTEGRITY,
        build_handoff_sections,
        evaluate_handoff_prompt,
        self_validate_generated_handoff,
    )

    correct_report_path = r"C:\Users\Example User\.dream-studio\meta\audit\phase-report.md"
    malformed_report_path = correct_report_path.replace(r"\.dream-studio", ".dream-studio")
    sections = build_handoff_sections(
        work_order=_work_order(tmp_path / "target"),
        result_metadata=_metadata(),
        eval_artifacts=[{"eval_type": "target_repo_mutation", "pass_fail": "incomplete"}],
        report_path=correct_report_path,
        dream_studio_repo_path=r"C:\Users\Example User\builds\dream-studio",
    )
    malformed_prompt = sections["prompt"].replace(correct_report_path, malformed_report_path)

    results = evaluate_handoff_prompt(
        malformed_prompt,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
    )

    assert results[HANDOFF_PATH_INTEGRITY]["pass_fail"] == "fail"
    assert "generated" not in results[HANDOFF_PATH_INTEGRITY]["observed_behavior"].lower()
    assert (
        "malformed_dream_studio_meta_root" in results[HANDOFF_PATH_INTEGRITY]["observed_behavior"]
    )

    self_validation = self_validate_generated_handoff(
        malformed_prompt,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
    )

    assert self_validation["pass_fail"] == "fail"
    assert any(
        "malformed_dream_studio_meta_root" in problem for problem in self_validation["problems"]
    )


def test_generated_handoff_self_validation_requires_database_relationship_context(tmp_path) -> None:
    from core.work_orders.handoff import build_handoff_sections, self_validate_generated_handoff

    work_order = _work_order(tmp_path / "target")
    work_order["handoff_context"] = {"requires_database_relationship_context": True}
    sections = build_handoff_sections(
        work_order=work_order,
        result_metadata=_metadata(),
        eval_artifacts=[{"eval_type": "target_repo_mutation", "pass_fail": "incomplete"}],
        report_path=tmp_path / "report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
    )

    self_validation = self_validate_generated_handoff(
        sections["prompt"],
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
        handoff_context=work_order["handoff_context"],
    )

    assert self_validation["pass_fail"] == "fail"
    assert any(
        "database_relationship_context" in problem for problem in self_validation["problems"]
    )


def test_next_work_order_without_stop_gate_fails_handoff_self_validation(tmp_path) -> None:
    from core.work_orders.handoff import build_handoff_sections

    work_order = _work_order(tmp_path / "target")
    work_order.pop("handoff_context")
    sections = build_handoff_sections(
        work_order=work_order,
        result_metadata=_metadata(),
        eval_artifacts=[{"eval_type": "target_repo_mutation", "pass_fail": "incomplete"}],
        report_path=tmp_path / "report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
    )

    assert sections["decision"]["handoff_required"] is False
    assert "# Continuation Packet" in sections["prompt"]


def test_generated_handoff_without_why_internal_continuation_fails_validation(tmp_path) -> None:
    from core.work_orders.handoff import build_handoff_sections, self_validate_generated_handoff

    prompt, sections = _prompt(tmp_path)
    weakened = prompt.replace(
        "Internal continuation is blocked because route policy requires handoff reason: user_requested_export_or_continuation.",
        "report_written",
    )

    self_validation = self_validate_generated_handoff(
        weakened,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
        handoff_context=_work_order(tmp_path / "target")["handoff_context"],
    )

    assert self_validation["pass_fail"] == "fail"
    assert any("why_internal_continuation" in problem for problem in self_validation["problems"])


def test_generated_handoff_self_validation_accepts_relationship_context_and_design_boundary(
    tmp_path,
) -> None:
    from core.work_orders.handoff import build_handoff_sections, self_validate_generated_handoff

    work_order = _work_order(tmp_path / "target")
    work_order["handoff_context"] = {
        "handoff_reason": "user_requested_export_or_continuation",
        "requires_database_relationship_context": True,
        "database_relationship_context": {
            "current_authority": "structured state",
            "proposed_authority": "canonical milestone state",
            "source_objects": "work_orders",
            "target_objects": "handoffs",
            "relationship_keys": "work_order_id",
            "unresolved_decisions": "none",
            "redaction_boundaries": "no secrets",
            "validation_refs": "focused evals",
        },
        "executable_design_artifact": True,
    }
    sections = build_handoff_sections(
        work_order=work_order,
        result_metadata=_metadata(),
        eval_artifacts=[{"eval_type": "target_repo_mutation", "pass_fail": "incomplete"}],
        report_path=tmp_path / "report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
    )

    assert "## Database Relationship Context" in sections["prompt"]
    assert "## Executable Design Artifact Boundary" in sections["prompt"]
    assert "DRAFT / DO NOT EXECUTE" in sections["prompt"]

    self_validation = self_validate_generated_handoff(
        sections["prompt"],
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
        handoff_context=work_order["handoff_context"],
    )

    assert self_validation["pass_fail"] == "pass"


def test_commit_execution_contract_requires_exact_path_staging_guards(tmp_path) -> None:
    from core.work_orders.handoff import (
        HANDOFF_PROMPT_COMPLETENESS,
        build_handoff_sections,
        evaluate_handoff_prompt,
    )

    work_order = _work_order(tmp_path / "target", approval_mode="approval_required")
    work_order["scope"] = {
        "include": ["src/app/a.ts", "tests/test_a.py"],
        "exclude": ["src/app/forbidden.ts", "tests/"],
    }
    sections = build_handoff_sections(
        work_order=work_order,
        result_metadata={
            "raw_output_ref": "result.md",
            "next_work_order_recommendation": (
                "Phase 99 - Commit Execution; Next Work Order: wo-commit-001; "
                "Objective: commit execution for exact staged files; Risk: medium; "
                "Approval: approval_required; Validation: staged diff checks."
            ),
        },
        eval_artifacts=[{"eval_type": "target_repo_mutation", "pass_fail": "incomplete"}],
        report_path=tmp_path / "report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
    )
    prompt = sections["prompt"]

    assert "exact staged file list" in prompt
    assert "stage exact file paths only" in prompt
    assert "do not stage parent directories wholesale" in prompt
    assert "git diff --cached --name-only" in prompt
    assert "git diff --cached --stat" in prompt
    assert "git diff --cached --check" in prompt
    assert "no push unless separately approved" in prompt

    weakened = prompt.replace("do not stage parent directories wholesale", "")
    results = evaluate_handoff_prompt(
        weakened,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
        approval_required=True,
    )
    assert results[HANDOFF_PROMPT_COMPLETENESS]["pass_fail"] == "fail"
    assert (
        "commit_execution_contract.do not stage parent directories wholesale"
        in results[HANDOFF_PROMPT_COMPLETENESS]["observed_behavior"]
    )


def test_pause_return_contract_preserves_deferred_work_requirements(tmp_path) -> None:
    from core.work_orders.handoff import (
        HANDOFF_PROMPT_COMPLETENESS,
        build_handoff_sections,
        evaluate_handoff_prompt,
    )

    sections = build_handoff_sections(
        work_order=_work_order(tmp_path / "target"),
        result_metadata={
            "raw_output_ref": "result.md",
            "next_work_order_recommendation": (
                "Phase 99A - Pause + Return; Next Work Order: wo-pause-return-001; "
                "Objective: pause return continuity for paused work; Risk: medium; "
                "Approval: observe_only; Validation: artifact review."
            ),
        },
        eval_artifacts=[{"eval_type": "target_repo_mutation", "pass_fail": "incomplete"}],
        report_path=tmp_path / "report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
    )
    prompt = sections["prompt"]

    assert "paused work artifact reference required" in prompt
    assert "completed commit hashes required when applicable" in prompt
    assert "current release gate required" in prompt
    assert "remaining deferred work required" in prompt
    assert "resume requirements required" in prompt
    assert "do not run deferred phases without separate approval" in prompt

    weakened = prompt.replace("remaining deferred work required", "")
    results = evaluate_handoff_prompt(
        weakened,
        readiness=sections["readiness"]["readiness"],
        can_continue=sections["readiness"]["can_continue"],
    )
    assert results[HANDOFF_PROMPT_COMPLETENESS]["pass_fail"] == "fail"
    assert (
        "pause_return_contract.remaining deferred work"
        in results[HANDOFF_PROMPT_COMPLETENESS]["observed_behavior"]
    )


def test_incomplete_non_blocking_eval_allows_ready_with_constraints(tmp_path) -> None:
    from core.work_orders.handoff import READY_WITH_CONSTRAINTS, determine_sequential_readiness

    readiness = determine_sequential_readiness(
        work_order=_work_order(tmp_path / "target"),
        result_metadata=_metadata(),
        eval_artifacts=[{"eval_type": "target_repo_mutation", "pass_fail": "incomplete"}],
    )

    assert readiness["readiness"] == READY_WITH_CONSTRAINTS
    assert readiness["can_continue"] is True
