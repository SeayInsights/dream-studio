"""File-backed Work Order CLI — argparse wiring and main() entrypoint.

Split from interfaces/cli/ds_work_order.py (WO-GF-CLI-split). ``build_parser()``
moves as one atomic unit (it wires the entire subparser tree and every
``set_defaults(func=cmd_X)``); ``main()`` stays alongside it since it is a
thin ``build_parser().parse_args() -> args.func(args)`` shell.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from core.work_orders import SUPPORTED_RENDER_TARGETS
from interfaces.cli.ds_work_order_core import (
    cmd_create,
    cmd_decide,
    cmd_decision_request,
    cmd_record_result,
    cmd_regenerate_handoff,
    cmd_render,
    cmd_report,
    cmd_request_decision,
    cmd_status,
    cmd_validate,
)
from interfaces.cli.ds_work_order_security import (
    cmd_generate_security_mutation_handoff,
    cmd_generate_security_next_handoff,
    cmd_generate_security_post_remediation_review_handoff,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="File-backed Dream Studio Work Order utility")
    parser.add_argument(
        "--storage-root",
        help="Explicit Work Order storage root for tests or operator-selected local state.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a file-backed Work Order")
    create.add_argument("--from-file", required=True, help="Work Order JSON/YAML source")
    create.add_argument(
        "--allow-missing-target",
        action="store_true",
        help="Allow target_path to be missing during initial file-backed creation.",
    )
    create.set_defaults(func=cmd_create)

    validate = subparsers.add_parser("validate", help="Validate a stored Work Order")
    validate.add_argument("--id", required=True, help="Work Order ID")
    validate.set_defaults(func=cmd_validate)

    status = subparsers.add_parser("status", help="Read stored Work Order status")
    status.add_argument("--id", required=True, help="Work Order ID")
    status.set_defaults(func=cmd_status)

    render = subparsers.add_parser("render", help="Render a Work Order packet")
    render.add_argument("--id", required=True, help="Work Order ID")
    render.add_argument(
        "--target",
        required=True,
        choices=sorted(SUPPORTED_RENDER_TARGETS),
        help="Render target",
    )
    render.set_defaults(func=cmd_render)

    record_result = subparsers.add_parser("record-result", help="Record a file-backed Work Result")
    record_result.add_argument("--id", required=True, help="Work Order ID")
    record_result.add_argument("--from-file", required=True, help="Result markdown source")
    record_result.set_defaults(func=cmd_record_result)

    report = subparsers.add_parser("report", help="Generate a file-backed Work Order report")
    report.add_argument("--id", required=True, help="Work Order ID")
    report.set_defaults(func=cmd_report)

    regenerate_handoff = subparsers.add_parser(
        "regenerate-handoff",
        help="Regenerate a standalone Handoff Packet through the current generator",
    )
    regenerate_handoff.add_argument("--from-file", required=True, help="Existing Handoff Packet")
    regenerate_handoff.add_argument(
        "--to-file",
        required=True,
        help="Output path under Work Order storage or the sibling audit path",
    )
    regenerate_handoff.set_defaults(func=cmd_regenerate_handoff)

    security_handoff = subparsers.add_parser(
        "generate-security-next-handoff",
        help="Generate a Security Review remediation-planning Handoff Packet from file-backed artifacts",
    )
    security_handoff.add_argument(
        "--source-report", required=True, help="Security review meta/audit report"
    )
    security_handoff.add_argument(
        "--security-report", required=True, help="SecurityReviewReport YAML"
    )
    security_handoff.add_argument("--release-gate", required=True, help="ReleaseGateSummary YAML")
    security_handoff.add_argument(
        "--findings-dir", required=True, help="Directory of SecurityFindingRecord YAML files"
    )
    security_handoff.add_argument(
        "--evidence-dir", required=True, help="Directory of SecurityEvidenceRecord YAML files"
    )
    security_handoff.add_argument(
        "--dashboard-projection", required=True, help="Dashboard projection input YAML"
    )
    security_handoff.add_argument(
        "--to-file",
        required=True,
        help="Output path under Work Order storage or the sibling audit path",
    )
    security_handoff.add_argument(
        "--output-report-path",
        required=True,
        help="Report path to embed for the generated next Work Order",
    )
    security_handoff.add_argument(
        "--dream-studio-repo-path",
        default=str(REPO_ROOT),
        help="Dream Studio repo path to embed in the generated handoff",
    )
    security_handoff.add_argument(
        "--baseline-dream-studio",
        default="Unknown; capture exact current Dream Studio branch/HEAD before planning.",
        help="Dream Studio branch/HEAD text to embed",
    )
    security_handoff.add_argument(
        "--expected-release-gate",
        default="REMEDIATE_BEFORE_RELEASE",
        help="Release-gate value required by deterministic security handoff evals",
    )
    security_handoff.add_argument(
        "--expected-finding-id",
        action="append",
        default=[],
        help="Finding ID or short finding ID expected in the generated handoff",
    )
    security_handoff.add_argument(
        "--expected-target-branch",
        default="master",
        help="Target branch expected in the generated handoff",
    )
    security_handoff.add_argument(
        "--expected-target-head",
        default="e24fac5ee0d1d2fe843bb617da7700a681bbd99b",
        help="Target HEAD expected in the generated handoff",
    )
    security_handoff.add_argument(
        "--expected-untracked-entry",
        action="append",
        default=[],
        help="Pre-existing untracked target entry expected in the generated handoff",
    )
    security_handoff.set_defaults(func=cmd_generate_security_next_handoff)

    security_mutation_handoff = subparsers.add_parser(
        "generate-security-mutation-handoff",
        help="Generate an approved security remediation mutation Handoff Packet from file-backed planning artifacts",
    )
    security_mutation_handoff.add_argument(
        "--planning-report", required=True, help="Security remediation planning report"
    )
    security_mutation_handoff.add_argument(
        "--security-report", required=True, help="SecurityReviewReport YAML"
    )
    security_mutation_handoff.add_argument(
        "--release-gate", required=True, help="ReleaseGateSummary YAML"
    )
    security_mutation_handoff.add_argument(
        "--findings-dir", required=True, help="Directory of SecurityFindingRecord YAML files"
    )
    security_mutation_handoff.add_argument(
        "--evidence-dir", required=True, help="Directory of SecurityEvidenceRecord YAML files"
    )
    security_mutation_handoff.add_argument(
        "--to-file",
        required=True,
        help="Output path under Work Order storage or the sibling audit path",
    )
    security_mutation_handoff.add_argument(
        "--output-report-path",
        required=True,
        help="Report path to embed for the generated mutation Work Order",
    )
    security_mutation_handoff.add_argument(
        "--dream-studio-repo-path",
        default=str(REPO_ROOT),
        help="Dream Studio repo path to embed in the generated handoff",
    )
    security_mutation_handoff.add_argument(
        "--baseline-dream-studio",
        default="Unknown; capture exact current Dream Studio branch/HEAD before mutation.",
        help="Dream Studio branch/HEAD text to embed",
    )
    security_mutation_handoff.add_argument(
        "--included-finding-id",
        action="append",
        default=[],
        help="Finding ID or short finding ID included in this mutation handoff",
    )
    security_mutation_handoff.add_argument(
        "--expected-release-gate",
        default="REMEDIATE_BEFORE_RELEASE",
        help="Release-gate value required by deterministic security handoff evals",
    )
    security_mutation_handoff.add_argument(
        "--expected-finding-id",
        action="append",
        default=[],
        help="Finding ID or short finding ID expected in the generated mutation handoff",
    )
    security_mutation_handoff.add_argument(
        "--expected-target-branch",
        default="master",
        help="Target branch expected in the generated handoff",
    )
    security_mutation_handoff.add_argument(
        "--expected-target-head",
        default="e24fac5ee0d1d2fe843bb617da7700a681bbd99b",
        help="Target HEAD expected in the generated handoff",
    )
    security_mutation_handoff.add_argument(
        "--expected-untracked-entry",
        action="append",
        default=[],
        help="Pre-existing untracked target entry expected in the generated handoff",
    )
    security_mutation_handoff.set_defaults(func=cmd_generate_security_mutation_handoff)

    security_post_review_handoff = subparsers.add_parser(
        "generate-security-post-remediation-review-handoff",
        help="Generate an observe-only post-remediation Security Review Handoff Packet from mutation artifacts",
    )
    security_post_review_handoff.add_argument(
        "--mutation-report", required=True, help="Security remediation mutation report"
    )
    security_post_review_handoff.add_argument(
        "--mutation-evidence", required=True, help="Security remediation mutation evidence YAML"
    )
    security_post_review_handoff.add_argument(
        "--paused-work", required=True, help="PausedWork continuity artifact"
    )
    security_post_review_handoff.add_argument(
        "--security-report", required=True, help="SecurityReviewReport YAML"
    )
    security_post_review_handoff.add_argument(
        "--release-gate", required=True, help="ReleaseGateSummary YAML"
    )
    security_post_review_handoff.add_argument(
        "--findings-dir", required=True, help="Directory of SecurityFindingRecord YAML files"
    )
    security_post_review_handoff.add_argument(
        "--to-file",
        required=True,
        help="Output path under Work Order storage or the sibling audit path",
    )
    security_post_review_handoff.add_argument(
        "--output-report-path",
        required=True,
        help="Report path to embed for the generated post-remediation review Work Order",
    )
    security_post_review_handoff.add_argument(
        "--dream-studio-repo-path",
        default=str(REPO_ROOT),
        help="Dream Studio repo path to embed in the generated handoff",
    )
    security_post_review_handoff.add_argument(
        "--baseline-dream-studio",
        default="Unknown; capture exact current Dream Studio branch/HEAD before review.",
        help="Dream Studio branch/HEAD text to embed",
    )
    security_post_review_handoff.add_argument(
        "--expected-release-gate",
        default="REMEDIATE_BEFORE_RELEASE",
        help="Release-gate value required by deterministic security handoff evals",
    )
    security_post_review_handoff.add_argument(
        "--expected-finding-id",
        action="append",
        default=[],
        help="Finding ID or short finding ID expected in the generated handoff",
    )
    security_post_review_handoff.add_argument(
        "--expected-target-branch",
        default="master",
        help="Target branch expected in the generated handoff",
    )
    security_post_review_handoff.add_argument(
        "--expected-target-head",
        default="e24fac5ee0d1d2fe843bb617da7700a681bbd99b",
        help="Target HEAD expected in the generated handoff",
    )
    security_post_review_handoff.add_argument(
        "--expected-untracked-entry",
        action="append",
        default=[],
        help="Pre-existing untracked target entry expected in the generated handoff",
    )
    security_post_review_handoff.add_argument(
        "--expected-changed-file",
        action="append",
        default=[],
        help="Phase 18S.13 changed file expected in the generated handoff",
    )
    security_post_review_handoff.add_argument(
        "--expected-validation-term",
        action="append",
        default=[],
        help="Phase 18S.13 validation term expected in the generated handoff",
    )
    security_post_review_handoff.set_defaults(
        func=cmd_generate_security_post_remediation_review_handoff
    )

    decision_request = subparsers.add_parser(
        "decision-request", help="Show a pending or recorded operator decision"
    )
    decision_request.add_argument("--id", required=True, help="Work Order ID")
    decision_request.set_defaults(func=cmd_decision_request)

    request_decision = subparsers.add_parser(
        "request-decision", help="Create a file-backed operator decision request"
    )
    request_decision.add_argument("--id", required=True, help="Work Order ID")
    request_decision.add_argument("--phase-type", required=True, help="Decision phase type")
    request_decision.add_argument("--question", required=True, help="Question for the operator")
    request_decision.add_argument(
        "--recommended", required=True, help="Recommended decision from the phase taxonomy"
    )
    request_decision.set_defaults(func=cmd_request_decision)

    decide = subparsers.add_parser("decide", help="Record a file-backed operator decision")
    decide.add_argument("--id", required=True, help="Work Order ID")
    decide.add_argument("--decision", required=True, help="Selected operator decision")
    decide.add_argument("--reason", required=True, help="Operator decision reason")
    decide.add_argument("--decided-by", required=True, help="Decision actor, usually operator")
    decide.set_defaults(func=cmd_decide)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
