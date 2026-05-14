from __future__ import annotations

import re
from pathlib import Path

FINDING_IDS = [
    "sec.finding.bill_stack.revenuecat_webhook_unsigned",
    "sec.finding.bill_stack.household_invite_code_exposure",
    "sec.finding.bill_stack.browser_token_exposure_window",
    "sec.finding.bill_stack.server_password_policy_gap",
    "sec.finding.bill_stack.in_memory_auth_state",
    "sec.finding.bill_stack.dependency_reproducibility_gap",
]


def _source_report(target_path: Path) -> str:
    return "\n".join(
        [
            "# Phase 18S.11",
            "Bill Stack target: " + str(target_path),
            "Decision: REMEDIATE_BEFORE_RELEASE.",
        ]
    )


def _security_report() -> dict:
    return {
        "source_work_order_id": "wo-dream-studio-018s11-first-observe-only-tier0-security-review-bill-stack",
        "target_id": "bill-stack",
        "verdict": "PASS WITH RISKS",
        "release_gate_decision": {"decision": "REMEDIATE_BEFORE_RELEASE"},
        "next_work_order_recommendation": {
            "recommended_work_order_id": "wo-dream-studio-018s12-bill-stack-tier0-security-remediation-planning",
            "recommended_phase_name": "Phase 18S.12 - Bill Stack Tier 0 Security Remediation Planning",
            "recommended_handoff_type": "normal_next_work_order",
            "recommended_phase_type": "normal_next_work_order",
            "decision_taxonomy": [
                "CONTINUE_TO_NEXT_WORK_ORDER",
                "REQUEST_HUMAN_APPROVAL",
                "HOLD",
                "FAIL",
            ],
            "recommended_decision": "HOLD",
        },
    }


def _release_gate() -> dict:
    return {
        "decision": "REMEDIATE_BEFORE_RELEASE",
        "blocking_findings": ["sec.finding.bill_stack.revenuecat_webhook_unsigned"],
    }


def _findings() -> list[dict]:
    return [{"finding_id": finding_id} for finding_id in FINDING_IDS]


def _evidence() -> list[dict]:
    return [
        {
            "evidence_id": "sec.evidence.bill_stack.baseline_git_metadata",
            "branch_head": {
                "target_branch": "master",
                "target_head": "e24fac5ee0d1d2fe843bb617da7700a681bbd99b",
            },
            "before_status": "\n".join(
                [
                    "## master...origin/master",
                    "?? billstack-api/migrate_direct.py",
                    "?? billstack-web/dev-dist/",
                ]
            ),
        }
    ]


def _prompt(tmp_path: Path) -> str:
    from core.work_orders.handoff import build_security_review_remediation_handoff_prompt

    target_path = tmp_path / "family-bill-organizer"
    return build_security_review_remediation_handoff_prompt(
        source_report_text=_source_report(target_path),
        source_report_path=tmp_path / "phase18s11-report.md",
        security_report=_security_report(),
        security_report_path=tmp_path / "review_report.yaml",
        release_gate=_release_gate(),
        release_gate_path=tmp_path / "release_gate.yaml",
        finding_records=_findings(),
        findings_dir=tmp_path / "findings",
        evidence_records=_evidence(),
        evidence_dir=tmp_path / "evidence",
        dashboard_projection_path=tmp_path / "projection_inputs.yaml",
        output_report_path=tmp_path / "phase18s12-report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
        baseline_dream_studio="Branch: integration/phase3-plus-phase1-phase2\nHEAD: abc123",
    )


def _mutation_prompt(tmp_path: Path) -> str:
    from core.work_orders.handoff import build_security_remediation_mutation_handoff_prompt

    target_path = tmp_path / "family-bill-organizer"
    return build_security_remediation_mutation_handoff_prompt(
        planning_report_text="\n".join(
            [
                "# Phase 18S.12",
                "Target Repo Path",
                str(target_path),
            ]
        ),
        planning_report_path=tmp_path / "phase18s12-report.md",
        security_report=_security_report(),
        security_report_path=tmp_path / "review_report.yaml",
        release_gate=_release_gate(),
        release_gate_path=tmp_path / "release_gate.yaml",
        finding_records=[
            {
                "finding_id": finding_id,
                "title": finding_id.split(".")[-1].replace("_", " "),
                "affected_assets": ["billstack-api/app/routers/purchases.py"],
            }
            for finding_id in FINDING_IDS
        ],
        findings_dir=tmp_path / "findings",
        evidence_records=_evidence(),
        evidence_dir=tmp_path / "evidence",
        output_report_path=tmp_path / "phase18s13-report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
        baseline_dream_studio="Branch: integration/phase3-plus-phase1-phase2\nHEAD: abc123",
        included_finding_ids=[
            "revenuecat_webhook_unsigned",
            "household_invite_code_exposure",
            "server_password_policy_gap",
        ],
    )


def _remove_section(prompt: str, title: str) -> str:
    pattern = re.compile(rf"^## {re.escape(title)}\n.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    return pattern.sub("", prompt)


def _eval(prompt: str) -> dict:
    from core.work_orders.handoff import evaluate_security_review_next_handoff_prompt

    return evaluate_security_review_next_handoff_prompt(
        prompt,
        expected_release_gate="REMEDIATE_BEFORE_RELEASE",
        expected_finding_ids=FINDING_IDS,
        expected_target_branch="master",
        expected_target_head="e24fac5ee0d1d2fe843bb617da7700a681bbd99b",
        expected_untracked_entries=[
            "billstack-api/migrate_direct.py",
            "billstack-web/dev-dist/",
        ],
    )


def _mutation_eval(prompt: str) -> dict:
    from core.work_orders.handoff import evaluate_security_remediation_mutation_handoff_prompt

    return evaluate_security_remediation_mutation_handoff_prompt(
        prompt,
        expected_release_gate="REMEDIATE_BEFORE_RELEASE",
        expected_finding_ids=FINDING_IDS,
        expected_target_branch="master",
        expected_target_head="e24fac5ee0d1d2fe843bb617da7700a681bbd99b",
        expected_untracked_entries=[
            "billstack-api/migrate_direct.py",
            "billstack-web/dev-dist/",
        ],
    )


def _mutation_evidence() -> dict:
    return {
        "work_order_id": "wo-dream-studio-018s13-bill-stack-tier0-priority-security-remediation",
        "target_id": "bill-stack",
        "target_path": r"C:\Users\Example User\builds\family-bill-organizer",
        "target_branch": "master",
        "target_head": "e24fac5ee0d1d2fe843bb617da7700a681bbd99b",
        "release_gate_after": "REMEDIATE_BEFORE_RELEASE",
        "included_findings": [
            "sec.finding.bill_stack.revenuecat_webhook_unsigned",
            "sec.finding.bill_stack.household_invite_code_exposure",
            "sec.finding.bill_stack.server_password_policy_gap",
        ],
        "files_changed": [
            "billstack-api/.env.example",
            "billstack-api/app/routers/auth.py",
            "billstack-api/app/routers/household.py",
            "billstack-api/app/routers/purchases.py",
            "billstack-api/app/schemas/schemas.py",
            "billstack-api/tests/test_security_remediation.py",
        ],
        "focused_validation": [
            {
                "command": "python -B -m unittest tests.test_security_remediation -v",
                "result": "passed",
            }
        ],
        "preserved_untracked_entries": [
            "billstack-api/migrate_direct.py",
            "billstack-web/dev-dist/",
        ],
    }


def _post_remediation_prompt(tmp_path: Path) -> str:
    from core.work_orders.handoff import build_security_post_remediation_review_handoff_prompt

    return build_security_post_remediation_review_handoff_prompt(
        mutation_report_text="# Phase 18S.13\nMUTATION_COMPLETE",
        mutation_report_path=tmp_path / "phase18s13-report.md",
        mutation_evidence=_mutation_evidence(),
        mutation_evidence_path=tmp_path / "mutation_validation_evidence.yaml",
        paused_work_path=tmp_path / "paused_work.yaml",
        security_report=_security_report(),
        security_report_path=tmp_path / "review_report.yaml",
        release_gate=_release_gate(),
        release_gate_path=tmp_path / "release_gate.yaml",
        finding_records=[
            {
                "finding_id": finding_id,
                "title": finding_id.split(".")[-1].replace("_", " "),
            }
            for finding_id in FINDING_IDS
        ],
        findings_dir=tmp_path / "findings",
        output_report_path=tmp_path / "phase18s14-report.md",
        dream_studio_repo_path=tmp_path / "dream-studio",
        baseline_dream_studio="Branch: integration/phase3-plus-phase1-phase2\nHEAD: abc123",
    )


def _post_remediation_eval(prompt: str) -> dict:
    from core.work_orders.handoff import evaluate_security_post_remediation_review_handoff_prompt

    evidence = _mutation_evidence()
    return evaluate_security_post_remediation_review_handoff_prompt(
        prompt,
        expected_release_gate="REMEDIATE_BEFORE_RELEASE",
        expected_finding_ids=[
            "sec.finding.bill_stack.revenuecat_webhook_unsigned",
            "sec.finding.bill_stack.household_invite_code_exposure",
            "sec.finding.bill_stack.server_password_policy_gap",
        ],
        expected_target_branch="master",
        expected_target_head="e24fac5ee0d1d2fe843bb617da7700a681bbd99b",
        expected_untracked_entries=evidence["preserved_untracked_entries"],
        expected_changed_files=evidence["files_changed"],
        expected_validation_terms=["python -B -m unittest tests.test_security_remediation -v"],
    )


def test_security_review_remediation_handoff_preserves_artifacts_and_constraints(tmp_path) -> None:
    from core.work_orders.handoff import READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE

    prompt = _prompt(tmp_path)
    results = _eval(prompt)

    assert "## Target Baseline Constraints" in prompt
    assert "## Release-Gate Decision Rules" in prompt
    assert "REMEDIATE_BEFORE_RELEASE" in prompt
    assert "Branch: master" in prompt
    assert "e24fac5ee0d1d2fe843bb617da7700a681bbd99b" in prompt
    assert "billstack-api/migrate_direct.py" in prompt
    assert "billstack-web/dev-dist/" in prompt
    for finding_id in FINDING_IDS:
        assert finding_id in prompt
    assert "Future remediation must be a separate approved mutation Work Order." in prompt
    assert all(result["pass_fail"] == "pass" for result in results.values())
    assert results[READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE]["pass_fail"] == "pass"


def test_abbreviated_security_next_prompt_fails_completeness_evals(tmp_path) -> None:
    from core.work_orders.handoff import READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE

    abbreviated = "\n".join(
        [
            "# Handoff Packet",
            "",
            "## Phase Name",
            "Phase 18S.12 - Bill Stack Tier 0 Security Remediation Planning",
            "",
            "## Handoff Type",
            "normal_next_work_order",
            "",
            "## Phase Type",
            "normal_next_work_order",
            "",
            "## Required Decision Taxonomy",
            "- CONTINUE_TO_NEXT_WORK_ORDER",
            "- REQUEST_HUMAN_APPROVAL",
            "- HOLD",
            "- FAIL",
            "",
            "## Final Decision",
            "HOLD",
            "",
            "## Objective",
            "Plan bounded remediation.",
            "",
        ]
    )
    results = _eval(abbreviated)

    assert results["handoff_prompt_completeness"]["pass_fail"] == "fail"
    assert results[READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE]["pass_fail"] == "fail"


def test_security_remediation_mutation_handoff_forbids_stage_commit_and_push(tmp_path) -> None:
    from core.work_orders.handoff import (
        READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE,
        SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
    )

    prompt = _mutation_prompt(tmp_path)
    results = _mutation_eval(prompt)

    assert "## Handoff Type\napproved_mutation_execution" in prompt
    assert "## Phase Type\napproved_mutation" in prompt
    assert "Do not stage, commit, or push." in prompt
    assert "Commit planning must occur in a later separate Work Order" in prompt
    assert "RevenueCat webhook authentication" in prompt
    assert "household invite-code" in prompt
    assert "server-side password policy" in prompt
    assert "browser_token_exposure_window remains deferred" in prompt
    assert "REMEDIATE_BEFORE_RELEASE" in prompt
    assert results[SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE]["pass_fail"] == "pass"
    assert results[READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE]["pass_fail"] == "pass"
    assert all(result["pass_fail"] == "pass" for result in results.values())


def test_security_remediation_mutation_handoff_with_commit_authority_fails(tmp_path) -> None:
    from core.work_orders.handoff import (
        READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE,
        SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
    )

    leaky_prompt = _mutation_prompt(tmp_path).replace(
        "- Run git diff/status checks.",
        "- Run git diff/status checks.\n- Commit only scoped Bill Stack changes if validation passes.",
    )
    results = _mutation_eval(leaky_prompt)

    assert results[SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE]["pass_fail"] == "fail"
    assert results[READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE]["pass_fail"] == "fail"


def test_security_handoff_with_missing_target_constraints_cannot_pass_contract(tmp_path) -> None:
    from core.work_orders.handoff import (
        READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE,
        SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
    )

    prompt = _remove_section(_prompt(tmp_path), "Target Baseline Constraints")
    results = _eval(prompt)

    assert results[SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED]["pass_fail"] == "fail"
    assert results[READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE]["pass_fail"] == "fail"


def test_post_remediation_review_handoff_preserves_mutation_evidence(tmp_path) -> None:
    from core.work_orders.handoff import READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE

    prompt = _post_remediation_prompt(tmp_path)
    results = _post_remediation_eval(prompt)

    assert "Phase 18S.14 - Bill Stack Post-Remediation Security Review" in prompt
    assert "observe-only post-remediation security review" in prompt
    assert "REMEDIATE_BEFORE_RELEASE" in prompt
    assert "RUN_ADDITIONAL_SECURITY_REVIEW" in prompt
    assert "Commit planning must remain a later separate Work Order" in prompt
    for changed_file in _mutation_evidence()["files_changed"]:
        assert changed_file in prompt
    assert "python -B -m unittest tests.test_security_remediation -v" in prompt
    assert "Do not stage, commit, or push." in prompt
    assert "Do not mutate Bill Stack." in prompt
    assert "Do not run broad target validation." in prompt
    assert all(result["pass_fail"] == "pass" for result in results.values())
    assert results[READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE]["pass_fail"] == "pass"


def test_post_remediation_review_handoff_missing_changed_file_fails(tmp_path) -> None:
    from core.work_orders.handoff import (
        READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE,
        SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
    )

    prompt = _post_remediation_prompt(tmp_path).replace(
        "billstack-api/app/routers/purchases.py", ""
    )
    results = _post_remediation_eval(prompt)

    assert results[SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED]["pass_fail"] == "fail"
    assert results[READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE]["pass_fail"] == "fail"
