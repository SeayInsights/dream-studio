#!/usr/bin/env python3
"""File-backed Work Order CLI for Phase 16B.

Commands in this file read/write only Work Order files. They do not inspect
target repos, open the native runtime DB, or emit runtime events.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.work_orders import (  # noqa: E402
    SUPPORTED_RENDER_TARGETS,
    WorkOrderError,
    build_security_post_remediation_review_handoff_prompt,
    build_security_remediation_mutation_handoff_prompt,
    build_security_review_remediation_handoff_prompt,
    create_decision_request,
    default_storage_root,
    decision_status,
    evaluate_security_post_remediation_review_handoff_prompt,
    evaluate_security_remediation_mutation_handoff_prompt,
    evaluate_security_review_next_handoff_prompt,
    generate_report,
    load_work_order,
    load_work_order_file,
    record_operator_decision,
    record_result,
    regenerate_handoff_prompt,
    render_work_order,
    save_work_order,
    status_summary,
    validate_work_order,
)


def _storage_root(args: argparse.Namespace) -> Path | None:
    return Path(args.storage_root) if getattr(args, "storage_root", None) else None


def _print_validation_errors(result) -> None:
    for issue in result.issues:
        print(f"{issue.field}: {issue.message}", file=sys.stderr)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_handoff_output_roots(args: argparse.Namespace) -> tuple[Path, Path]:
    storage_root = _storage_root(args) or default_storage_root()
    resolved_storage = storage_root.expanduser().resolve()
    return resolved_storage, (resolved_storage.parent / "audit").resolve()


def _assert_safe_handoff_output(path: Path, args: argparse.Namespace) -> Path:
    resolved = path.expanduser().resolve()
    allowed_roots = _safe_handoff_output_roots(args)
    if not any(_is_relative_to(resolved, root) for root in allowed_roots):
        roots = ", ".join(str(root) for root in allowed_roots)
        raise WorkOrderError(
            f"regenerated handoff output must be under Work Order storage or audit paths: {roots}"
        )
    return resolved


def cmd_create(args: argparse.Namespace) -> int:
    try:
        work_order = load_work_order_file(args.from_file)
        result = validate_work_order(
            work_order,
            allow_missing_target=args.allow_missing_target,
        )
        if not result.ok:
            _print_validation_errors(result)
            return 2
        path = save_work_order(result.work_order, storage_root=_storage_root(args))
    except WorkOrderError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"created: {result.work_order['work_order_id']}")
    print(f"work_order_path: {path}")
    print(f"storage_root: {path.parent.parent}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        work_order, path = load_work_order(args.id, storage_root=_storage_root(args))
    except WorkOrderError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    result = validate_work_order(work_order)
    if not result.ok:
        _print_validation_errors(result)
        return 2

    print(f"valid: {result.work_order['work_order_id']}")
    print(f"work_order_path: {path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    try:
        summary = status_summary(args.id, storage_root=_storage_root(args))
    except WorkOrderError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    for key in (
        "work_order_id",
        "status",
        "approval_mode",
        "risk_level",
        "target_path",
        "storage_root",
        "next_required_action",
    ):
        print(f"{key}: {summary.get(key)}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    try:
        result = render_work_order(
            args.id,
            target=args.target,
            storage_root=_storage_root(args),
        )
    except WorkOrderError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"rendered: {result['work_order_id']}")
    print(f"target: {result['target']}")
    print(f"packet_path: {result['packet_path']}")
    for eval_path in result["eval_paths"]:
        print(f"eval_path: {eval_path}")
    return 0


def cmd_record_result(args: argparse.Namespace) -> int:
    try:
        result = record_result(
            args.id,
            source_path=args.from_file,
            storage_root=_storage_root(args),
        )
    except WorkOrderError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"result_recorded: {result['work_order_id']}")
    print(f"result_path: {result['result_path']}")
    print(f"metadata_path: {result['metadata_path']}")
    for eval_path in result["eval_paths"]:
        print(f"eval_path: {eval_path}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    try:
        result = generate_report(args.id, storage_root=_storage_root(args))
    except WorkOrderError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"report: {result['work_order_id']}")
    print(f"report_path: {result['report_path']}")
    print(f"result_present: {str(result['result_present']).lower()}")
    for eval_path in result["eval_paths"]:
        print(f"eval_path: {eval_path}")
    return 0


def cmd_regenerate_handoff(args: argparse.Namespace) -> int:
    try:
        source_path = Path(args.from_file)
        output_path = _assert_safe_handoff_output(Path(args.to_file), args)
        prompt_text = source_path.read_text(encoding="utf-8")
        regenerated = regenerate_handoff_prompt(prompt_text)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = output_path.parent / f".{output_path.name}.tmp"
        tmp_path.write_text(regenerated, encoding="utf-8")
        tmp_path.replace(output_path)
    except (OSError, ValueError, WorkOrderError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"handoff_regenerated: {output_path}")
    print(f"source_path: {source_path}")
    print("target_repo_mutation: no")
    return 0


def _load_yaml_mapping(path: Path) -> dict:
    import yaml

    if not path.is_file():
        raise WorkOrderError(f"required artifact not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise WorkOrderError(f"artifact must be a mapping: {path}")
    return data


def _load_yaml_dir(path: Path) -> list[dict]:
    if not path.is_dir():
        raise WorkOrderError(f"required artifact directory not found: {path}")
    records = [_load_yaml_mapping(item) for item in sorted(path.glob("*.yaml"))]
    if not records:
        raise WorkOrderError(f"no YAML artifacts found in: {path}")
    return records


def cmd_generate_security_next_handoff(args: argparse.Namespace) -> int:
    try:
        source_report_path = Path(args.source_report)
        if not source_report_path.is_file():
            raise WorkOrderError(f"source report not found: {source_report_path}")
        output_path = _assert_safe_handoff_output(Path(args.to_file), args)
        security_report_path = Path(args.security_report)
        release_gate_path = Path(args.release_gate)
        findings_dir = Path(args.findings_dir)
        evidence_dir = Path(args.evidence_dir)
        dashboard_projection_path = Path(args.dashboard_projection)
        prompt_text = build_security_review_remediation_handoff_prompt(
            source_report_text=source_report_path.read_text(encoding="utf-8"),
            source_report_path=source_report_path,
            security_report=_load_yaml_mapping(security_report_path),
            security_report_path=security_report_path,
            release_gate=_load_yaml_mapping(release_gate_path),
            release_gate_path=release_gate_path,
            finding_records=_load_yaml_dir(findings_dir),
            findings_dir=findings_dir,
            evidence_records=_load_yaml_dir(evidence_dir),
            evidence_dir=evidence_dir,
            dashboard_projection_path=dashboard_projection_path,
            output_report_path=args.output_report_path,
            dream_studio_repo_path=args.dream_studio_repo_path,
            baseline_dream_studio=args.baseline_dream_studio,
        )
        evals = evaluate_security_review_next_handoff_prompt(
            prompt_text,
            expected_release_gate=args.expected_release_gate,
            expected_finding_ids=args.expected_finding_id,
            expected_target_branch=args.expected_target_branch,
            expected_target_head=args.expected_target_head,
            expected_untracked_entries=args.expected_untracked_entry,
        )
        failing = {key: value for key, value in evals.items() if value.get("pass_fail") != "pass"}
        if failing:
            failed = ", ".join(sorted(failing))
            raise WorkOrderError(f"generated security handoff failed evals: {failed}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = output_path.parent / f".{output_path.name}.tmp"
        tmp_path.write_text(prompt_text, encoding="utf-8")
        tmp_path.replace(output_path)
    except (OSError, WorkOrderError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"security_handoff_generated: {output_path}")
    print("security_handoff_evals: pass")
    print("target_repo_mutation: no")
    return 0


def cmd_generate_security_mutation_handoff(args: argparse.Namespace) -> int:
    try:
        planning_report_path = Path(args.planning_report)
        if not planning_report_path.is_file():
            raise WorkOrderError(f"planning report not found: {planning_report_path}")
        output_path = _assert_safe_handoff_output(Path(args.to_file), args)
        security_report_path = Path(args.security_report)
        release_gate_path = Path(args.release_gate)
        findings_dir = Path(args.findings_dir)
        evidence_dir = Path(args.evidence_dir)
        prompt_text = build_security_remediation_mutation_handoff_prompt(
            planning_report_text=planning_report_path.read_text(encoding="utf-8"),
            planning_report_path=planning_report_path,
            security_report=_load_yaml_mapping(security_report_path),
            security_report_path=security_report_path,
            release_gate=_load_yaml_mapping(release_gate_path),
            release_gate_path=release_gate_path,
            finding_records=_load_yaml_dir(findings_dir),
            findings_dir=findings_dir,
            evidence_records=_load_yaml_dir(evidence_dir),
            evidence_dir=evidence_dir,
            output_report_path=args.output_report_path,
            dream_studio_repo_path=args.dream_studio_repo_path,
            baseline_dream_studio=args.baseline_dream_studio,
            included_finding_ids=args.included_finding_id,
        )
        evals = evaluate_security_remediation_mutation_handoff_prompt(
            prompt_text,
            expected_release_gate=args.expected_release_gate,
            expected_finding_ids=args.expected_finding_id,
            expected_target_branch=args.expected_target_branch,
            expected_target_head=args.expected_target_head,
            expected_untracked_entries=args.expected_untracked_entry,
        )
        failing = {key: value for key, value in evals.items() if value.get("pass_fail") != "pass"}
        if failing:
            failed = ", ".join(sorted(failing))
            raise WorkOrderError(f"generated security mutation handoff failed evals: {failed}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = output_path.parent / f".{output_path.name}.tmp"
        tmp_path.write_text(prompt_text, encoding="utf-8")
        tmp_path.replace(output_path)
    except (OSError, WorkOrderError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"security_mutation_handoff_generated: {output_path}")
    print("security_mutation_handoff_evals: pass")
    print("target_repo_mutation: no")
    return 0


def cmd_generate_security_post_remediation_review_handoff(args: argparse.Namespace) -> int:
    try:
        mutation_report_path = Path(args.mutation_report)
        if not mutation_report_path.is_file():
            raise WorkOrderError(f"mutation report not found: {mutation_report_path}")
        output_path = _assert_safe_handoff_output(Path(args.to_file), args)
        mutation_evidence_path = Path(args.mutation_evidence)
        paused_work_path = Path(args.paused_work)
        security_report_path = Path(args.security_report)
        release_gate_path = Path(args.release_gate)
        findings_dir = Path(args.findings_dir)
        mutation_evidence = _load_yaml_mapping(mutation_evidence_path)
        prompt_text = build_security_post_remediation_review_handoff_prompt(
            mutation_report_text=mutation_report_path.read_text(encoding="utf-8"),
            mutation_report_path=mutation_report_path,
            mutation_evidence=mutation_evidence,
            mutation_evidence_path=mutation_evidence_path,
            paused_work_path=paused_work_path,
            security_report=_load_yaml_mapping(security_report_path),
            security_report_path=security_report_path,
            release_gate=_load_yaml_mapping(release_gate_path),
            release_gate_path=release_gate_path,
            finding_records=_load_yaml_dir(findings_dir),
            findings_dir=findings_dir,
            output_report_path=args.output_report_path,
            dream_studio_repo_path=args.dream_studio_repo_path,
            baseline_dream_studio=args.baseline_dream_studio,
        )
        evals = evaluate_security_post_remediation_review_handoff_prompt(
            prompt_text,
            expected_release_gate=args.expected_release_gate,
            expected_finding_ids=args.expected_finding_id,
            expected_target_branch=args.expected_target_branch,
            expected_target_head=args.expected_target_head,
            expected_untracked_entries=args.expected_untracked_entry,
            expected_changed_files=args.expected_changed_file,
            expected_validation_terms=args.expected_validation_term,
        )
        failing = {key: value for key, value in evals.items() if value.get("pass_fail") != "pass"}
        if failing:
            failed = ", ".join(sorted(failing))
            raise WorkOrderError(
                f"generated security post-remediation handoff failed evals: {failed}"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = output_path.parent / f".{output_path.name}.tmp"
        tmp_path.write_text(prompt_text, encoding="utf-8")
        tmp_path.replace(output_path)
    except (OSError, WorkOrderError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"security_post_remediation_handoff_generated: {output_path}")
    print("security_post_remediation_handoff_evals: pass")
    print("target_repo_mutation: no")
    return 0


def cmd_decision_request(args: argparse.Namespace) -> int:
    try:
        status = decision_status(args.id, storage_root=_storage_root(args))
    except WorkOrderError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    request = status.get("decision_request")
    decision = status.get("operator_decision")
    print(f"work_order_id: {status.get('work_order_id')}")
    print(f"decision_status: {status.get('status')}")
    print(f"decision_request_path: {status.get('decision_request_path')}")
    print(f"operator_decision_path: {status.get('operator_decision_path')}")
    if request:
        print(f"phase_type: {request.get('phase_type')}")
        print(f"recommended_decision: {request.get('recommended_decision')}")
        print("allowed_decisions:")
        for allowed in request.get("allowed_decisions", []):
            print(f"- {allowed}")
    if decision:
        print(f"decision: {decision.get('decision')}")
        print(f"decided_by: {decision.get('decided_by')}")
    return 0


def cmd_request_decision(args: argparse.Namespace) -> int:
    try:
        request = create_decision_request(
            args.id,
            phase_type=args.phase_type,
            question=args.question,
            recommended_decision=args.recommended,
            storage_root=_storage_root(args),
        )
    except WorkOrderError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    status = decision_status(args.id, storage_root=_storage_root(args))
    print(f"decision_request_created: {request['work_order_id']}")
    print(f"decision_request_path: {status['decision_request_path']}")
    print(f"phase_type: {request['phase_type']}")
    print(f"recommended_decision: {request['recommended_decision']}")
    print("allowed_decisions:")
    for allowed in request["allowed_decisions"]:
        print(f"- {allowed}")
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    try:
        decision = record_operator_decision(
            args.id,
            decision=args.decision,
            reason=args.reason,
            decided_by=args.decided_by,
            storage_root=_storage_root(args),
        )
    except WorkOrderError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    status = decision_status(args.id, storage_root=_storage_root(args))
    print(f"operator_decision_recorded: {decision['work_order_id']}")
    print(f"operator_decision_path: {status['operator_decision_path']}")
    print(f"decision: {decision['decision']}")
    print(f"approved_next_handoff_type: {decision['approved_next_handoff_type']}")
    return 0


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


if __name__ == "__main__":
    sys.exit(main())
