"""File-backed Work Order CLI — security Handoff Packet generation commands.

Split from interfaces/cli/ds_work_order.py (WO-GF-CLI-split). Owns the three
generate-security-*-handoff commands and the YAML artifact loaders they share.
Reuses ``_assert_safe_handoff_output`` from ds_work_order_core.py (defined
there since the non-security `regenerate-handoff` command needs it too).

Commands in this file read/write only Work Order files. They do not inspect
target repos, open the native runtime DB, or emit runtime events.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.work_orders import (
    WorkOrderError,
    build_security_post_remediation_review_handoff_prompt,
    build_security_remediation_mutation_handoff_prompt,
    build_security_review_remediation_handoff_prompt,
    evaluate_security_post_remediation_review_handoff_prompt,
    evaluate_security_remediation_mutation_handoff_prompt,
    evaluate_security_review_next_handoff_prompt,
)
from interfaces.cli.ds_work_order_core import _assert_safe_handoff_output


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
