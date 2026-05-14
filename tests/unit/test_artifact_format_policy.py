from __future__ import annotations

from pathlib import Path

POLICY = Path("docs/contracts/artifact-format-policy.md")

RELATED_CONTRACTS = (
    Path("docs/contracts/handoff-packet-contract.md"),
    Path("docs/contracts/security-review-report-artifact-contract.md"),
    Path("docs/contracts/work-order-paused-work-contract.md"),
    Path("docs/contracts/dashboard-projection-model-contract.md"),
    Path("docs/operations/work-orders.md"),
)


def _policy_text() -> str:
    return POLICY.read_text(encoding="utf-8")


def test_artifact_format_policy_documents_authoritative_formats() -> None:
    policy = _policy_text()

    for required in (
        "## Authoritative Source Formats",
        "Markdown",
        "Markdown with YAML frontmatter",
        "YAML",
        "JSON",
        "JSONL/NDJSON",
        "SQLite",
        "JSON Schema and Pydantic",
        "Mermaid",
        "CSV",
    ):
        assert required in policy


def test_artifact_format_policy_documents_generated_formats() -> None:
    policy = _policy_text()

    for required in (
        "## Generated And Rendered Projection Formats",
        "HTML",
        "PDF",
        "SVG",
        "PNG",
        "Parquet",
        "HTML, PDF, SVG, and PNG are generated/rendered outputs by default",
        "HTML is rendered output",
    ):
        assert required in policy


def test_artifact_format_policy_documents_artifact_family_rules() -> None:
    policy = _policy_text()

    for required in (
        "Handoff packets",
        "Audit reports",
        "Security review reports",
        "Release gates",
        "Paused-work artifacts",
        "Event exports",
        "Projection outputs",
        "Adapter payloads",
        "Do not convert Markdown to HTML as canonical source.",
        "Does this artifact use the correct authority format",
    ):
        assert required in policy


def test_related_contracts_do_not_make_html_canonical_source() -> None:
    forbidden_phrases = (
        "html is canonical",
        "html becomes canonical",
        "html should become canonical",
        "html source of truth",
        "html as source of truth",
        "html must be canonical",
        "make html canonical",
        "replace markdown with html",
    )

    for path in RELATED_CONTRACTS:
        text = path.read_text(encoding="utf-8").lower()
        for phrase in forbidden_phrases:
            assert phrase not in text, f"{path} contains forbidden phrase: {phrase}"
