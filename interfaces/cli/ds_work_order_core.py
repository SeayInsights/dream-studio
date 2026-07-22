"""File-backed Work Order CLI — core lifecycle commands.

Split from interfaces/cli/ds_work_order.py (WO-GF-CLI-split). Owns the
non-security-handoff commands (create/validate/status/render/record-result/
report/regenerate-handoff/decision-request/request-decision/decide) and the
safe-output-path helpers shared with ds_work_order_security.py
(``_assert_safe_handoff_output``).

Commands in this file read/write only Work Order files. They do not inspect
target repos, open the native runtime DB, or emit runtime events.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.work_orders import (
    WorkOrderError,
    create_decision_request,
    decision_status,
    default_storage_root,
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
