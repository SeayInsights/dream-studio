from __future__ import annotations

from pathlib import Path

POLICY = Path("docs/contracts/file-structure-authority-policy.md")


def _policy_text() -> str:
    return POLICY.read_text(encoding="utf-8")


def test_file_structure_policy_documents_repo_and_meta_locations() -> None:
    policy = _policy_text()

    for required in (
        "## Canonical Repo-Owned Locations",
        "`docs/contracts/`",
        "`docs/operations/`",
        "`docs/architecture/`",
        "`core/`",
        "`interfaces/`",
        "`tests/`",
        "`schemas/`",
        "## Generated Local Meta Locations",
        "`~/.dream-studio/meta/audit/`",
        "`~/.dream-studio/meta/work-orders/`",
        "`~/.dream-studio/meta/work-orders/<work-order-id>/`",
        "Generic public docs should use portable paths.",
    ):
        assert required in policy


def test_file_structure_policy_documents_work_order_artifact_locations() -> None:
    policy = _policy_text()

    for required in (
        "`approvals/`",
        "`evidence/`",
        "`continuity/`",
        "`security/`",
        "`security/findings/`",
        "`security/evidence/`",
        "`security/accepted_risks/`",
        "`dashboard/`",
        "`projections/`",
        "`evals/`",
        "`approval.json`",
        "`paused_work.yaml`",
        "`review_report.yaml`",
        "`release_gate.yaml`",
        "`projection_inputs.yaml`",
    ):
        assert required in policy


def test_file_structure_policy_documents_authority_guardrails() -> None:
    policy = _policy_text()

    for required in (
        "## Generated-Vs-Canonical Authority Rules",
        "## Duplicate Contract Location Rules",
        "## Target-Repo Artifact Leakage Rules",
        "## Dashboard, Runtime, And Projection Guardrails",
        "A generated artifact in a canonical source location does not become canonical by placement alone.",
        "Do not create parallel contract trees.",
        "must not leak target repository artifacts",
        "Dashboard/report output must not approve risk",
    ):
        assert required in policy


def test_file_structure_policy_documents_future_work_order_checklist() -> None:
    policy = _policy_text()

    for required in (
        "Is this artifact canonical source or generated projection?",
        "Does the artifact use the correct format?",
        "Does the artifact live in the correct location?",
        "Is the artifact allowed to be committed?",
        "Is this repo-owned, local-meta-owned, target-repo-owned, or generated?",
        "Does this create a duplicate authority path?",
        "Does this accidentally make dashboard/report output authoritative?",
        "Does this leak target-repo artifacts into Dream Studio?",
        "Does this require schema validation now or later?",
        "Are forbidden paths excluded?",
    ):
        assert required in policy


def test_file_structure_policy_aligns_with_referenced_contracts() -> None:
    policy = _policy_text()

    for required_ref in (
        "docs/contracts/artifact-format-policy.md",
        "docs/contracts/handoff-packet-contract.md",
        "docs/contracts/work-order-paused-work-contract.md",
        "docs/contracts/security-review-report-artifact-contract.md",
    ):
        assert required_ref in policy
        assert Path(required_ref).is_file()
