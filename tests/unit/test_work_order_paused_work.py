from __future__ import annotations

from pathlib import Path

import yaml

CONTRACT = Path("docs/contracts/work-order-paused-work-contract.md")
OPERATIONS = Path("docs/operations/work-orders.md")

REQUIRED_FIELDS = [
    "paused_work_id",
    "paused_phase_name",
    "paused_work_order_id",
    "paused_from_phase",
    "paused_from_work_order_id",
    "pause_reason",
    "blocking_condition",
    "resume_condition",
    "current_status",
    "resume_allowed",
    "target_id",
    "target_path",
    "target_branch",
    "target_head",
    "release_gate",
    "priority_findings",
    "forbidden_until_resume",
    "source_artifact_refs",
    "required_resume_artifacts",
    "resume_handoff_ref",
    "created_at",
    "updated_at",
]

RESOLUTION_FIELDS = [
    "resumed_by_work_order_id",
    "resumed_by_phase",
    "resume_result",
    "completion_report_ref",
    "mutation_evidence_ref",
    "next_recommended_phase",
    "next_handoff_ref",
]


def _contract() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def _sample_paused_work() -> dict:
    raw = """
paused_work_id: paused-18s13-bill-stack-tier0-priority-security-remediation
paused_phase_name: Phase 18S.13 - Bill Stack Tier 0 Priority Security Remediation
paused_work_order_id: wo-dream-studio-018s13-bill-stack-tier0-priority-security-remediation
paused_from_phase: Phase 18S.12A - Security Remediation Handoff Commit Boundary Fix
paused_from_work_order_id: wo-dream-studio-018s12a-security-remediation-handoff-commit-boundary-fix
pause_reason: Prior generated mutation handoff contained ambiguous commit/stage authority; Phase 18S.12A regenerated a mutation-only handoff and this artifact records resume state.
blocking_condition: Confirm regenerated mutation-only Phase 18S.13 handoff passed deterministic evals and forbids stage, commit, and push.
resume_condition: Resume Phase 18S.13 using regenerated handoff after paused_work.yaml records resume_allowed true.
current_status: paused
resume_allowed: true
target_id: bill-stack
target_path: C:\\Users\\Example User\\builds\\family-bill-organizer
target_branch: master
target_head: e24fac5ee0d1d2fe843bb617da7700a681bbd99b
release_gate: REMEDIATE_BEFORE_RELEASE
priority_findings:
  - revenuecat_webhook_unsigned
  - household_invite_code_exposure
  - server_password_policy_gap
forbidden_until_resume:
  - stage
  - commit
  - push
  - scans
  - target_validation
  - untracked_entry_inspection
  - dependency_changes
  - lockfile_changes
  - schema_migrations
  - browser_session_architecture_work
  - durable_auth_state_work
source_artifact_refs:
  - C:\\Users\\Example User\\.dream-studio\\meta\\audit\\2026-05-11-phase18s12a-security-remediation-handoff-commit-boundary-fix-report.md
  - C:\\Users\\Example User\\.dream-studio\\meta\\audit\\2026-05-11-phase18s13-bill-stack-tier0-priority-security-remediation-prompt.md
required_resume_artifacts:
  - C:\\Users\\Example User\\.dream-studio\\meta\\audit\\2026-05-11-phase18s13-bill-stack-tier0-priority-security-remediation-prompt.md
resume_handoff_ref: C:\\Users\\Example User\\.dream-studio\\meta\\audit\\2026-05-11-phase18s13-bill-stack-tier0-priority-security-remediation-prompt.md
created_at: "2026-05-12T00:00:00-04:00"
updated_at: "2026-05-12T00:00:00-04:00"
"""
    data = yaml.safe_load(raw)
    assert isinstance(data, dict)
    return data


def _sample_resolved_paused_work() -> dict:
    data = _sample_paused_work()
    data.update(
        {
            "current_status": "completed",
            "resume_allowed": False,
            "resumed_by_work_order_id": "wo-dream-studio-018s13-bill-stack-tier0-priority-security-remediation",
            "resumed_by_phase": "Phase 18S.13 - Bill Stack Tier 0 Priority Security Remediation",
            "resume_result": "MUTATION_COMPLETE",
            "completion_report_ref": r"C:\Users\Example User\.dream-studio\meta\audit\2026-05-11-phase18s13-bill-stack-tier0-priority-security-remediation-report.md",
            "mutation_evidence_ref": r"C:\Users\Example User\.dream-studio\meta\work-orders\wo-dream-studio-018s13-bill-stack-tier0-priority-security-remediation\evidence\mutation_validation_evidence.yaml",
            "next_recommended_phase": "Phase 18S.14 - Bill Stack Post-Remediation Security Review",
            "next_handoff_ref": r"C:\Users\Example User\.dream-studio\meta\audit\2026-05-11-phase18s14-bill-stack-post-remediation-security-review-prompt.md",
        }
    )
    return data


def test_paused_work_contract_documents_required_fields() -> None:
    text = _contract()

    missing = [field for field in REQUIRED_FIELDS if f"`{field}`" not in text]

    assert missing == []
    assert "`completed`" in text
    assert "`resolved`" in text
    for field in RESOLUTION_FIELDS:
        assert f"`{field}`" in text


def test_paused_work_contract_keeps_continuity_file_backed_not_chat_memory() -> None:
    text = _contract()
    required_terms = [
        "file-backed continuity records",
        "without relying on chat memory or narrative report prose",
        "must not require previous chat context",
        "not the continuity source of truth unless backed by `paused_work.yaml`",
        "PausedWork artifacts are not execution commands",
        "must not run Work Orders",
        "mutate repositories",
        "stage files",
        "commit files",
        "push",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_phase18s13_paused_work_shape_is_file_backed_and_resume_gated() -> None:
    data = _sample_paused_work()

    missing = [field for field in REQUIRED_FIELDS if field not in data]

    assert missing == []
    assert data["current_status"] == "paused"
    assert data["resume_allowed"] is True
    assert data["release_gate"] == "REMEDIATE_BEFORE_RELEASE"
    assert data["target_branch"] == "master"
    assert data["target_head"] == "e24fac5ee0d1d2fe843bb617da7700a681bbd99b"
    assert set(data["priority_findings"]) == {
        "revenuecat_webhook_unsigned",
        "household_invite_code_exposure",
        "server_password_policy_gap",
    }
    assert {"stage", "commit", "push", "scans", "target_validation"}.issubset(
        set(data["forbidden_until_resume"])
    )
    assert data["source_artifact_refs"]
    assert data["required_resume_artifacts"]
    assert data["resume_handoff_ref"].endswith(
        "2026-05-11-phase18s13-bill-stack-tier0-priority-security-remediation-prompt.md"
    )


def test_phase18s13_paused_work_can_record_completed_resolution() -> None:
    data = _sample_resolved_paused_work()

    missing = [field for field in REQUIRED_FIELDS if field not in data]
    resolution_missing = [field for field in RESOLUTION_FIELDS if field not in data]

    assert missing == []
    assert resolution_missing == []
    assert data["current_status"] == "completed"
    assert data["resume_allowed"] is False
    assert data["resume_result"] == "MUTATION_COMPLETE"
    assert data["completion_report_ref"].endswith(
        "2026-05-11-phase18s13-bill-stack-tier0-priority-security-remediation-report.md"
    )
    assert data["mutation_evidence_ref"].endswith("mutation_validation_evidence.yaml")
    assert data["next_handoff_ref"].endswith(
        "2026-05-11-phase18s14-bill-stack-post-remediation-security-review-prompt.md"
    )


def test_operations_doc_explains_paused_work_references_and_non_authority() -> None:
    text = OPERATIONS.read_text(encoding="utf-8")
    required_terms = [
        "Paused Work Continuity",
        "docs/contracts/work-order-paused-work-contract.md",
        "paused_work.yaml",
        "not chat memory or report prose alone",
        "resume_handoff_ref",
        "resume_allowed: true",
        "does not grant mutation",
        "stage, commit, push",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []
